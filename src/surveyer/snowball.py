"""Citation chasing (snowballing) over OpenAlex: refs + citations of seed papers."""

from __future__ import annotations

import threading
from pathlib import Path

import msgspec
import structlog

from surveyer.cancel import PipelineCancelled, check_cancelled
from surveyer.config import SnowballConfig, SurveyConfig
from surveyer.dedup import deduplicate
from surveyer.export import export_extended
from surveyer.extend import Baseline, load_baseline, split_already_screened
from surveyer.filtering.keyword import apply_keyword_filter
from surveyer.filtering.llm import Scorer, apply_llm_filter
from surveyer.ledger import save_ledger
from surveyer.models import Ledger, QueryRetrieval, Record, SnowballLedger
from surveyer.prisma import render_prisma
from surveyer.sources.base import HttpClient
from surveyer.sources.openalex import API, PAGE_SIZE, _strip_doi, parse_openalex

log = structlog.get_logger()

_ID_PREFIX = "https://openalex.org/"
_BATCH = 50  # OpenAlex allows up to 50 OR values per filter


class SnowballFetch(msgspec.Struct):
    """Raw candidates fetched from the seed set, plus per-direction accounting."""

    candidates: list[Record]
    seeds_total: int
    seeds_resolved: int
    backward: int
    forward: int
    retrieval: list[QueryRetrieval]


def build_openalex_client(
    cache_root: str | Path, *, refresh: bool = False
) -> HttpClient:
    """Build an OpenAlex HTTP client sharing the run's openalex cache dir."""
    return HttpClient(
        cache_dir=Path(cache_root) / "openalex", min_interval=0.2, refresh=refresh
    )


def _bare_id(url: str | None) -> str | None:
    """Strip the OpenAlex URL prefix from a work id, leaving e.g. 'W123'."""
    if not url:
        return None
    return url.removeprefix(_ID_PREFIX)


class OpenAlexSnowball:
    """Fetch references (backward) and citations (forward) of seed papers."""

    def __init__(self, client: HttpClient) -> None:
        """Initialise with an OpenAlex HTTP client."""
        self.client = client

    def fetch(
        self,
        seeds: list[Record],
        cfg: SnowballConfig,
        *,
        cancel: threading.Event | None = None,
    ) -> SnowballFetch:
        """Resolve each seed in OpenAlex and collect its refs/citations."""
        candidates: list[Record] = []
        resolved = 0
        backward = 0
        forward = 0
        backward_total = 0  # references available across seeds (pre-cap)
        forward_total = 0  # citing works available across seeds (API meta.count)
        want_back = cfg.direction in ("backward", "both")
        want_fwd = cfg.direction in ("forward", "both")

        for seed in seeds:
            check_cancelled(cancel)
            if not seed.doi:
                continue
            work = self._resolve(seed.doi)
            if work is None:
                continue
            resolved += 1
            if want_back:
                ref_ids = [_bare_id(u) for u in work.get("referenced_works", [])]
                ref_ids = [r for r in ref_ids if r]
                backward_total += len(ref_ids)
                recs = self._works_by_ids(ref_ids[: cfg.max_results_per_seed])
                _tag(recs, "snowball:backward")
                backward += len(recs)
                candidates.extend(recs)
            if want_fwd:
                wid = _bare_id(work.get("id"))
                if wid:
                    recs, citing_total = self._citing(wid, cfg.max_results_per_seed)
                    forward_total += citing_total
                    _tag(recs, "snowball:forward")
                    forward += len(recs)
                    candidates.extend(recs)

        log.info(
            "snowball.fetched",
            seeds=len(seeds),
            resolved=resolved,
            backward=backward,
            forward=forward,
        )
        retrieval = [
            QueryRetrieval(
                source="openalex",
                query_label="snowball:backward",
                requested=cfg.max_results_per_seed,
                retrieved=backward,
                api_total=backward_total if want_back else None,
            ),
            QueryRetrieval(
                source="openalex",
                query_label="snowball:forward",
                requested=cfg.max_results_per_seed,
                retrieved=forward,
                api_total=forward_total if want_fwd else None,
            ),
        ]
        return SnowballFetch(
            candidates=candidates,
            seeds_total=len(seeds),
            seeds_resolved=resolved,
            backward=backward,
            forward=forward,
            retrieval=retrieval,
        )

    def _resolve(self, doi: str) -> dict | None:
        """Look a seed up by DOI; return the OpenAlex work or None if not found."""
        # OpenAlex wants a bare DOI; a full https://doi.org/... URL 404s.
        clean = _strip_doi(doi) or doi.strip()
        url = f"{API}/doi:{clean}"
        try:
            return self.client.get_json(url, params={"select": "id,referenced_works"})
        except PipelineCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - any failure means "skip this seed"
            log.warning("snowball.resolve_failed", doi=doi, error=str(exc))
            return None

    def _works_by_ids(self, ids: list[str]) -> list[Record]:
        """Fetch metadata for OpenAlex work ids, batched 50 at a time."""
        out: list[Record] = []
        for i in range(0, len(ids), _BATCH):
            chunk = ids[i : i + _BATCH]
            raw = self.client.get_json(
                API,
                params={"filter": f"openalex_id:{'|'.join(chunk)}", "per-page": 200},
            )
            out.extend(parse_openalex(raw))
        return out

    def _citing(self, work_id: str, cap: int) -> tuple[list[Record], int]:
        """Fetch works citing work_id (forward), paginated up to cap."""
        per_page = min(cap, PAGE_SIZE)
        out: list[Record] = []
        page = 1
        api_total = 0
        while len(out) < cap:
            raw = self.client.get_json(
                API,
                params={
                    "filter": f"cites:{work_id}",
                    "per-page": per_page,
                    "page": page,
                },
            )
            if page == 1:
                api_total = int(raw.get("meta", {}).get("count", 0) or 0)
            batch = parse_openalex(raw)
            out.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return out[:cap], api_total


def _tag(records: list[Record], label: str) -> None:
    """Stamp snowball provenance onto fetched candidates."""
    for r in records:
        r.sources = ["openalex"]
        r.query_labels = [label]


def snowball_stage(
    seeds: list[Record],
    already_seen: list[Record],
    cfg: SurveyConfig,
    scorer: Scorer | None,
    fetcher: OpenAlexSnowball,
    *,
    cancel: threading.Event | None = None,
) -> tuple[list[Record], list[Record], SnowballLedger]:
    """Fetch, dedup and screen citation-search candidates from the seed set."""
    assert cfg.snowball is not None  # caller guards on cfg.snowball.enabled
    fetch = fetcher.fetch(seeds, cfg.snowball, cancel=cancel)

    # Dedup candidates among themselves, then against everything already screened.
    deduped, internal_dupes = deduplicate(
        fetch.candidates, title_threshold=cfg.dedup.title_threshold
    )
    baseline = Baseline(included=already_seen, excluded=[])
    fresh, seen_dupes = split_already_screened(deduped, baseline)

    # Keyword filter, then LLM filter, mirroring the main pipeline.
    gate = cfg.filter.keyword_gate
    if gate == "soft" and not cfg.filter.llm.enabled:
        gate = "hard"
        log.warning(
            "filter.soft_gate_downgraded",
            reason="keyword_gate=soft has no LLM judge; using hard gate",
        )
    after_kw, excluded_kw, kw_reasons = apply_keyword_filter(
        fresh,
        cfg.filter.keyword,
        concepts=cfg.filter.concepts,
        concept_mode=cfg.filter.concept_mode,
        gate=gate,
    )
    kept_kw_ids = {id(r) for r in after_kw}
    excluded: list[Record] = [r for r in fresh if id(r) not in kept_kw_ids]

    if cfg.filter.llm.enabled and scorer is not None:
        after_llm, _, _ = apply_llm_filter(
            after_kw,
            cfg.filter.llm,
            scorer,
            concepts=cfg.filter.concepts,
            cancel=cancel,
        )
    else:
        after_llm = after_kw
    kept_llm_ids = {id(r) for r in after_llm}
    excluded.extend(r for r in after_kw if id(r) not in kept_llm_ids)

    ledger = SnowballLedger(
        seeds=fetch.seeds_total,
        seeds_resolved=fetch.seeds_resolved,
        identified=len(fetch.candidates),
        backward=fetch.backward,
        forward=fetch.forward,
        duplicates_removed=internal_dupes + seen_dupes,
        excluded_keyword=excluded_kw,
        excluded_keyword_reasons=kw_reasons,
        excluded_llm=len(after_kw) - len(after_llm),
        included=len(after_llm),
        retrieval=fetch.retrieval,
    )
    log.info(
        "snowball.screened",
        identified=ledger.identified,
        duplicates_removed=ledger.duplicates_removed,
        included=ledger.included,
    )
    return after_llm, excluded, ledger


def run_snowball(
    cfg: SurveyConfig,
    papers_xlsx: str | Path,
    *,
    scorer: Scorer | None = None,
    fetcher: OpenAlexSnowball | None = None,
    resolve_bibtex: bool = True,
    refresh: bool = False,
):
    """Snowball from a screened workbook: chase its included papers citations."""
    from surveyer.pipeline import PipelineResult  # local import avoids a cycle

    assert cfg.snowball is not None
    out_dir = Path(cfg.project.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_root = out_dir / "cache"

    baseline = load_baseline(papers_xlsx)
    log.info("snowball.baseline_loaded", included=len(baseline.included))

    if cfg.filter.llm.enabled and scorer is None:
        from surveyer.filtering.llm import CachingScorer, build_scorer

        scorer = CachingScorer(
            build_scorer(cfg.filter.llm),
            cache_root / "llm",
            namespace=f"{cfg.filter.llm.provider}:{cfg.filter.llm.model}",
        )
    if fetcher is None:
        fetcher = OpenAlexSnowball(build_openalex_client(cache_root, refresh=refresh))

    seeds = baseline.included
    already_seen = baseline.included + baseline.excluded
    kept_b, excluded_b, snow_ledger = snowball_stage(
        seeds, already_seen, cfg, scorer, fetcher
    )

    if resolve_bibtex:
        from surveyer.bibtex import build_resolver, extract_bibtex_keys

        # Reserve the baseline's existing keys so newly synthesized local keys for
        # snowball candidates don't collide with entries already in the workbook.
        seed_keys = extract_bibtex_keys(baseline.included + baseline.excluded)
        build_resolver(cache_root, refresh=refresh).resolve_all(
            kept_b, seed_keys=seed_keys
        )

    ledger = Ledger(
        included=0,
        previously_included=len(baseline.included),
        snowball=snow_ledger,
    )
    save_ledger(ledger, out_dir / "ledger.json")

    kept_all = baseline.included + kept_b
    export_extended(
        papers_xlsx,
        kept_all,
        kept_b,
        excluded_b,
        ledger,
        out_dir,
        concept_names=list(cfg.filter.concepts or {}),
    )
    render_prisma(
        ledger,
        cfg.search,
        out_dir,
        llm_model=cfg.filter.llm.model if cfg.filter.llm.enabled else None,
    )
    log.info("snowball.exported", out_dir=str(out_dir), included=snow_ledger.included)
    return PipelineResult(
        ledger=ledger, kept=kept_all, excluded=baseline.excluded + excluded_b
    )
