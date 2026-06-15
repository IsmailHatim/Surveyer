"""Orchestrate fetch -> dedup -> filter -> export -> prisma."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING

import msgspec
import structlog

from surveyer.cancel import check_cancelled
from surveyer.config import SurveyConfig
from surveyer.dedup import deduplicate
from surveyer.export import export_extended, export_results
from surveyer.extend import Baseline, load_baseline, split_already_screened
from surveyer.filtering.keyword import apply_keyword_filter
from surveyer.filtering.llm import Scorer, apply_llm_filter, build_scorer
from surveyer.ledger import save_ledger
from surveyer.models import Ledger, Record, SourceCount
from surveyer.prisma import render_prisma
from surveyer.sources import build_registry, fetch_all

if TYPE_CHECKING:
    from surveyer.bibtex import BibtexResolver

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
    resolver: BibtexResolver | None = None,
    resolve_bibtex: bool = True,
    refresh: bool = False,
    cancel: threading.Event | None = None,
) -> PipelineResult:
    """Run the full pipeline: fetch -> dedup -> filter -> bibtex -> export -> prisma."""
    out_dir = Path(cfg.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_root = out_dir / "cache"

    baseline: Baseline | None = None
    if cfg.extend is not None:
        baseline = load_baseline(cfg.extend.xlsx)
        log.info(
            "extend.baseline_loaded",
            xlsx=cfg.extend.xlsx,
            included=len(baseline.included),
            excluded=len(baseline.excluded),
        )

    if cfg.filter.llm.enabled and scorer is None:
        from surveyer.filtering.llm import CachingScorer

        scorer = CachingScorer(
            build_scorer(cfg.filter.llm),
            cache_root / "llm",
            namespace=f"{cfg.filter.llm.provider}:{cfg.filter.llm.model}",
        )

    if registry is None:
        registry = build_registry(cfg.search, cache_root, refresh=refresh)

    # 1. Fetch
    records, counts, failed = fetch_all(cfg.search, registry, cancel=cancel)
    ledger = Ledger(
        identified=[SourceCount(source=s, count=n) for s, n in counts.items()]
    )
    ledger.failed_sources = failed

    # 2. Deduplicate
    deduped, removed = deduplicate(records, title_threshold=cfg.dedup.title_threshold)
    ledger.duplicates_removed = removed
    log.info("dedup.done", removed=removed, remaining=len(deduped))
    check_cancelled(cancel)

    # 2bis. Drop records already screened in the baseline workbook.
    if baseline is not None:
        deduped, n_screened = split_already_screened(deduped, baseline)
        ledger.already_screened = n_screened
        ledger.previously_included = len(baseline.included)

    # 3. Keyword filter
    after_kw, excluded_kw, kw_reasons = apply_keyword_filter(
        deduped, cfg.filter.keyword, concepts=cfg.filter.concepts
    )
    ledger.excluded_keyword = excluded_kw
    ledger.excluded_keyword_reasons = kw_reasons
    log.info("filter.keyword_done", excluded=excluded_kw, remaining=len(after_kw))
    kept_kw_ids = {id(r) for r in after_kw}
    dropped: list[Record] = [r for r in deduped if id(r) not in kept_kw_ids]

    # 4. LLM filter (scorer was built up front, before fetching)
    if cfg.filter.llm.enabled and scorer is not None:
        after_llm, excluded_llm = apply_llm_filter(
            after_kw, cfg.filter.llm, scorer, cancel=cancel
        )
    else:
        after_llm, excluded_llm = after_kw, 0
    ledger.excluded_llm = excluded_llm
    kept_llm_ids = {id(r) for r in after_llm}
    dropped.extend(r for r in after_kw if id(r) not in kept_llm_ids)

    ledger.included = len(after_llm)

    check_cancelled(cancel)

    # 4bis Resolve BibTeX for kept records (DBLP key -> DOI -> local fallback).
    if resolve_bibtex:
        if resolver is None:
            from surveyer.bibtex import build_resolver

            resolver = build_resolver(cache_root, refresh=refresh)
        if baseline is None:
            resolver.resolve_all(after_llm)
        else:
            # Baseline rows keep their bibtex.
            resolver.resolve_all(
                after_llm + [r for r in baseline.included if not r.bibtex]
            )

    if baseline is not None:
        kept_all = baseline.included + after_llm
        excluded_all = baseline.excluded + dropped
    else:
        kept_all, excluded_all = after_llm, dropped

    # 5. Persist outputs
    save_ledger(ledger, out_dir / "ledger.json")
    if baseline is not None and cfg.extend is not None:
        export_extended(cfg.extend.xlsx, kept_all, after_llm, dropped, ledger, out_dir)
    else:
        export_results(
            after_llm, dropped, ledger, out_dir, fmt=cfg.project.export_format
        )
    log.info("export.done", out_dir=str(out_dir), fmt=cfg.project.export_format)
    render_prisma(
        ledger,
        cfg.search,
        out_dir,
        llm_model=cfg.filter.llm.model if cfg.filter.llm.enabled else None,
    )
    log.info("prisma.done", out=str(out_dir / "prisma"))

    return PipelineResult(ledger=ledger, kept=kept_all, excluded=excluded_all)
