"""Orchestrate fetch -> dedup -> filter -> export -> prisma."""

from __future__ import annotations

from pathlib import Path

import msgspec
import structlog

from surveyer.config import SurveyConfig
from surveyer.dedup import deduplicate
from surveyer.export import export_xlsx
from surveyer.filtering.keyword import apply_keyword_filter
from surveyer.filtering.llm import Scorer, apply_llm_filter
from surveyer.ledger import save_ledger
from surveyer.models import Ledger, Record, SourceCount
from surveyer.prisma import render_prisma
from surveyer.sources import build_registry, fetch_all

log = structlog.get_logger()


class PipelineResult(msgspec.Struct):
    """Result returned by run_pipeline containing ledger and record lists."""

    ledger: Ledger
    kept: list[Record]
    excluded: list[Record]


def run_pipeline(
    cfg: SurveyConfig,
    *,
    registry: dict | None = None,
    scorer: Scorer | None = None,
) -> PipelineResult:
    """Run the full pipeline: fetch -> dedup -> filter -> export -> prisma."""
    out_dir = Path(cfg.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_root = out_dir / "cache"

    if registry is None:
        registry = build_registry(cfg.search, cache_root)

    # 1. Fetch
    records, counts, failed = fetch_all(cfg.search, registry)
    ledger = Ledger(
        identified=[SourceCount(source=s, count=n) for s, n in counts.items()]
    )
    ledger.failed_sources = failed

    # 2. Deduplicate
    deduped, removed = deduplicate(records)
    ledger.duplicates_removed = removed

    # 3. Keyword filter
    after_kw, excluded_kw = apply_keyword_filter(deduped, cfg.filter.keyword)
    ledger.excluded_keyword = excluded_kw
    kept_kw_ids = {id(r) for r in after_kw}
    dropped: list[Record] = [r for r in deduped if id(r) not in kept_kw_ids]

    # 4. LLM filter
    if cfg.filter.llm.enabled:
        if scorer is None:
            from surveyer.filtering.llm import CachingScorer, OpenAIScorer

            scorer = CachingScorer(
                OpenAIScorer(model=cfg.filter.llm.model),
                cache_root / "llm",
                namespace=cfg.filter.llm.model,
            )
        after_llm, excluded_llm = apply_llm_filter(after_kw, cfg.filter.llm, scorer)
    else:
        after_llm, excluded_llm = after_kw, 0
    ledger.excluded_llm = excluded_llm
    kept_llm_ids = {id(r) for r in after_llm}
    dropped.extend(r for r in after_kw if id(r) not in kept_llm_ids)

    ledger.included = len(after_llm)

    # 5. Persist outputs
    save_ledger(ledger, out_dir / "ledger.json")
    export_xlsx(after_llm, dropped, ledger, out_dir / "survey.xlsx")
    render_prisma(ledger, out_dir / "prisma.png")

    return PipelineResult(ledger=ledger, kept=after_llm, excluded=dropped)
