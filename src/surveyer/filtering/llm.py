"""LLM relevance scoring against the survey's abstract."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Protocol

import structlog

from surveyer.cancel import check_cancelled
from surveyer.config import LLMConfig
from surveyer.models import Record

log = structlog.get_logger()

_PROMPT = (
    "You score how relevant a candidate paper is to a survey.\n"
    "Survey abstract:\n{survey}\n\n"
    "Candidate paper:\nTitle: {title}\nAbstract: {abstract}\n\n"
    'Return JSON: {{"score": <float 0..1>, "reason": <short string>}}.'
)


class Scorer(Protocol):
    """Protocol for LLM relevance scorers."""

    def score(self, survey_abstract: str, record: Record) -> tuple[float, str]:
        """Return (score 0..1, reason) for a candidate record against the survey."""
        ...


class OpenAIScorer:
    """OpenAI-backed scorer. Reads OPENAI_API_KEY from env."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        """Initialise the scorer with the given OpenAI model name."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set; the OpenAI scorer cannot run. "
                "Set it in the environment (or via `uv run --env-file .env ...`)."
            )

        from openai import OpenAI

        self.model = model
        self.client = OpenAI(api_key=api_key)

    def score(self, survey_abstract: str, record: Record) -> tuple[float, str]:
        """Score a record against the survey abstract via the OpenAI chat API."""
        prompt = _PROMPT.format(
            survey=survey_abstract,
            title=record.title,
            abstract=record.abstract or "(no abstract)",
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = resp.choices[0].message.content
        if content is None:
            raise ValueError("LLM response had no content")
        data = json.loads(content)
        score = data.get("score")
        if not isinstance(score, (int, float)):
            raise ValueError(f"LLM response missing numeric score: {data!r}")
        return float(score), str(data.get("reason", ""))


class OllamaScorer:
    """Ollama scorer talking to a local or networked Ollama server."""

    def __init__(
        self, model: str = "llama3.1", host: str = "http://localhost:11434"
    ) -> None:
        """Initialise the scorer with an Ollama model name and server host."""
        try:
            from ollama import Client
        except ImportError as exc:
            raise RuntimeError(
                "Ollama needs the optional extra: pip install surveyer[ollama]"
            ) from exc

        self.model = model
        self.client = Client(host=host)

    def score(self, survey_abstract: str, record: Record) -> tuple[float, str]:
        """Score a record against the survey abstract via the Ollama chat API."""
        prompt = _PROMPT.format(
            survey=survey_abstract,
            title=record.title,
            abstract=record.abstract or "(no abstract)",
        )
        resp = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={"temperature": 0},
        )
        content = resp["message"]["content"]
        if not content:
            raise ValueError("LLM response had no content")
        data = json.loads(content)
        score = data.get("score")
        if not isinstance(score, (int, float)):
            raise ValueError(f"LLM response missing numeric score: {data!r}")
        return float(score), str(data.get("reason", ""))


def build_scorer(cfg: LLMConfig) -> Scorer:
    """Build a Scorer for the configured provider."""
    if cfg.provider == "openai":
        return OpenAIScorer(model=cfg.model)
    if cfg.provider == "ollama":
        return OllamaScorer(model=cfg.model, host=cfg.host)
    raise ValueError(f"Unknown LLM provider: {cfg.provider!r}")


class CachingScorer:
    """Wrap a Scorer, caching results on disk to avoid rescoring."""

    def __init__(
        self, inner: Scorer, cache_dir: str | Path, *, namespace: str = ""
    ) -> None:
        """Initialise the caching scorer with an inner scorer and cache directory."""
        self.inner = inner
        self.namespace = namespace
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, survey_abstract: str, record: Record) -> Path:
        ident = record.doi or f"{record.title}|{record.abstract or ''}"
        key = json.dumps(
            {"ns": self.namespace, "survey": survey_abstract, "ident": ident},
            sort_keys=True,
        )
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.cache_dir / f"{digest}.json"

    def score(self, survey_abstract: str, record: Record) -> tuple[float, str]:
        """Return cached (score, reason) or delegate to inner scorer and cache."""
        cache = self._cache_path(survey_abstract, record)
        if cache.exists():
            data = json.loads(cache.read_text())
            return data["score"], data["reason"]
        value, reason = self.inner.score(survey_abstract, record)
        cache.write_text(json.dumps({"score": value, "reason": reason}))
        return value, reason


def apply_llm_filter(
    records: list[Record],
    cfg: LLMConfig,
    scorer: Scorer,
    *,
    cancel: threading.Event | None = None,
) -> tuple[list[Record], int]:
    """Score each record; keep those above threshold. Returns (kept, excluded)."""
    if not cfg.enabled:
        return records, 0

    total = len(records)
    kept: list[Record] = []
    for i, r in enumerate(records, start=1):
        check_cancelled(cancel)
        log.info("llm.scoring", done=i, total=total, title=r.title)
        try:
            value, reason = scorer.score(cfg.survey_abstract, r)
        except Exception as exc:
            log.warning("llm.score_failed", title=r.title, error=str(exc))
            r.llm_score = None
            r.llm_reason = "scoring failed - review manually"
            kept.append(r)  # not scored records are kept for manual review
            continue
        r.llm_score = value
        r.llm_reason = reason
        if value >= cfg.threshold:
            kept.append(r)
        else:
            r.exclusion_reason = f"llm score {value:.2f} < threshold {cfg.threshold}"
    log.info("llm.scoring_done", total=total, kept=len(kept))
    return kept, len(records) - len(kept)
