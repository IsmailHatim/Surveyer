"""Source adapter registry and multi-source fetch."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import msgspec
import structlog

from surveyer.cancel import check_cancelled
from surveyer.config import Query, SearchConfig
from surveyer.models import QueryRetrieval, Record, SearchResult
from surveyer.sources.agent import AgentSource
from surveyer.sources.base import HttpClient, Source
from surveyer.sources.dblp import DblpSource
from surveyer.sources.google_scholar import GoogleScholarSource
from surveyer.sources.openalex import OpenAlexSource
from surveyer.sources.pubmed import PubMedSource
from surveyer.sources.semantic_scholar import SemanticScholarSource, make_headers

log = structlog.get_logger()


class FetchResult(msgspec.Struct):
    """Aggregated output of a multi-source fetch."""

    records: list[Record]
    counts: dict[str, int]
    retrieval: list[QueryRetrieval]
    failed: list[str]


def build_registry(
    search: SearchConfig, cache_root: str | Path, *, refresh: bool = False
) -> dict[str, Source]:
    """Instantiate the adapters named in the config."""
    cache = Path(cache_root)
    registry: dict[str, Source] = {}
    for name in search.sources:
        if name == "dblp":
            registry[name] = DblpSource(
                # DBLP throttles hard and signals it inconsistently (500/429/
                # dropped connections, often with no Retry-After), so we space
                # requests out and retry patiently.
                HttpClient(
                    cache_dir=cache / "dblp",
                    min_interval=2.0,
                    max_retries=6,
                    refresh=refresh,
                )
            )
        elif name == "openalex":
            registry[name] = OpenAlexSource(
                HttpClient(
                    cache_dir=cache / "openalex", min_interval=0.2, refresh=refresh
                ),
                year_min=search.year_min,
                year_max=search.year_max,
            )
        elif name == "semantic_scholar":
            headers = make_headers()
            log.info(
                "semantic_scholar.auth",
                api_key="present" if headers else "absent (expect 429s)",
            )
            registry[name] = SemanticScholarSource(
                HttpClient(
                    cache_dir=cache / "s2",
                    min_interval=1.1,
                    headers=headers,
                    refresh=refresh,
                )
            )
        elif name == "google_scholar":
            registry[name] = GoogleScholarSource()
        elif name == "pubmed":
            # NCBI: 3 req/s without a key and 10 with NCBI_API_KEY
            has_key = bool(os.environ.get("NCBI_API_KEY"))
            log.info("pubmed.auth", api_key="present" if has_key else "absent")
            registry[name] = PubMedSource(
                HttpClient(
                    cache_dir=cache / "pubmed",
                    min_interval=0.11 if has_key else 0.4,
                    refresh=refresh,
                ),
                year_min=search.year_min,
                year_max=search.year_max,
            )
        elif name == "agent":
            registry[name] = AgentSource()
        else:
            log.warning("source.unknown", name=name)
    return registry


def _fetch_one_source(
    name: str,
    source: Source,
    queries: list[Query],
    max_results: int,
    cancel: threading.Event | None,
) -> tuple[list[Record], list[QueryRetrieval], bool]:
    """Run all queries for a single source. Returns (records, retrieval, had_error)."""
    out: list[Record] = []
    retrieval: list[QueryRetrieval] = []
    had_error = False
    for query in queries:
        check_cancelled(cancel)
        try:
            result: SearchResult = source.search(query.terms, max_results=max_results)
        except Exception as exc:
            log.warning("source.failed", source=name, query=query.label, error=str(exc))
            had_error = True
            continue
        hits = result.records
        for r in hits:
            r.sources = [name]
            r.query_labels = [query.label]
        out.extend(hits)
        retrieval.append(
            QueryRetrieval(
                source=name,
                query_label=query.label,
                requested=max_results,
                retrieved=len(hits),
                api_total=result.api_total,
            )
        )
        log.info(
            "fetch.query_done",
            source=name,
            query=query.label,
            hits=len(hits),
            api_total=result.api_total,
        )
    log.info("fetch.source_done", source=name, count=len(out))
    return out, retrieval, had_error


def fetch_all(
    search: SearchConfig,
    registry: dict[str, Source],
    *,
    cancel: threading.Event | None = None,
) -> FetchResult:
    """Run every (source, query) pair concurrently across sources."""
    records: list[Record] = []
    counts: dict[str, int] = {}
    retrieval: list[QueryRetrieval] = []
    failed: list[str] = []
    if not registry:
        return FetchResult(records, counts, retrieval, failed)
    queries = search.resolved_queries()

    with ThreadPoolExecutor(max_workers=len(registry)) as pool:
        futures = {
            name: pool.submit(
                _fetch_one_source,
                name,
                source,
                queries,
                search.max_results_per_query,
                cancel,
            )
            for name, source in registry.items()
        }
        # Resolve in registry order so records, counts and retrieval are deterministic.
        for name in registry:
            recs, rows, had_error = futures[name].result()
            records.extend(recs)
            counts[name] = len(recs)
            retrieval.extend(rows)
            if had_error:
                failed.append(name)
    return FetchResult(records, counts, retrieval, failed)
