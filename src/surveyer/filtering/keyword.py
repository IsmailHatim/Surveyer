"""Keyword include/exclude filtering over title, abstract and keywords."""

from __future__ import annotations

import re
from functools import lru_cache

from surveyer.config import KeywordConfig, resolve_required_concepts
from surveyer.models import Record


@lru_cache(maxsize=4096)
def _term_pattern(term: str) -> re.Pattern[str]:
    """Compile a cached whole-word, case-insensitive matcher for term."""
    return re.compile(rf"\b{re.escape(term.lower())}\b")


def _contains(term: str, text: str) -> bool:
    """Whole-word match of term within already-lowercased text."""
    return _term_pattern(term).search(text) is not None


def _haystack(r: Record) -> str:
    parts = [r.title or "", r.abstract or "", " ".join(r.keywords)]
    return " ".join(parts).lower()


def _exclude_hit(text: str, cfg: KeywordConfig) -> str | None:
    """Return the first exclude term contained in text, or None."""
    for term in cfg.exclude:
        if _contains(term, text):
            return f"contains '{term}'"
    return None


def _classify(
    record: Record,
    cfg: KeywordConfig,
    concepts: dict[str, list[str]] | None,
    concept_mode: str,
    gate: str,
) -> tuple[str | None, str | None]:
    """Return (drop_reason, keyword_note) for a record."""
    text = _haystack(record)
    hit = _exclude_hit(text, cfg)
    if hit is not None:
        return hit, None
    if concepts:
        total = len(concepts)
        required = resolve_required_concepts(concept_mode, total)
        matched = sum(
            1
            for synonyms in concepts.values()
            if any(_contains(syn, text) for syn in synonyms)
        )
        if matched < required:
            if gate == "soft":
                return None, f"matched {matched}/{total} concepts lexically"
            return f"matched {matched}/{total} concepts (need ≥{required})", None
        return None, None
    if cfg.include and not any(_contains(term, text) for term in cfg.include):
        if gate == "soft":
            return None, "no included keyword (advisory)"
        return "no included keyword", None
    return None, None


def apply_keyword_filter(
    records: list[Record],
    cfg: KeywordConfig,
    concepts: dict[str, list[str]] | None = None,
    concept_mode: str = "any",
    gate: str = "hard",
) -> tuple[list[Record], int, dict[str, int]]:
    """Return (kept records, number excluded, per-reason exclusion counts)."""
    kept: list[Record] = []
    reasons: dict[str, int] = {}
    for record in records:
        reason, note = _classify(record, cfg, concepts, concept_mode, gate)
        if note is not None:
            record.keyword_note = note
        if reason is None:
            kept.append(record)
        else:
            record.exclusion_reason = reason
            reasons[reason] = reasons.get(reason, 0) + 1
    return kept, len(records) - len(kept), reasons
