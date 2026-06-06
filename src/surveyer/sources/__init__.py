"""Source adapter registry and multi-source fetch."""

from __future__ import annotations

from pathlib import Path

import structlog

from surveyer.config import SearchConfig
from surveyer.models import Record
from surveyer.sources.agent import AgentSource
from surveyer.sources.base import HttpClient, Source
from surveyer.sources.dblp import DblpSource
from surveyer.sources.google_scholar import GoogleScholarSource
from surveyer.sources.openalex import OpenAlexSource
from surveyer.sources.semantic_scholar import SemanticScholarSource, make_headers

log = structlog.get_logger()


def build_registry(search: SearchConfig, cache_root: str | Path) -> dict[str, Source]:
    """Instantiate the adapters named in the config."""
    cache = Path(cache_root)
    registry: dict[str, Source] = {}
    for name in search.sources:
        if name == "dblp":
            registry[name] = DblpSource(
                # DBLP throttles hard and signals it inconsistently (500/429/
                # dropped connections, often with no Retry-After), so we space
                # requests out and retry patiently.
                HttpClient(cache_dir=cache / "dblp", min_interval=2.0, max_retries=6)
            )
        elif name == "openalex":
            registry[name] = OpenAlexSource(
                HttpClient(cache_dir=cache / "openalex", min_interval=0.2),
                year_min=search.year_min,
                year_max=search.year_max,
            )
        elif name == "semantic_scholar":
            registry[name] = SemanticScholarSource(
                HttpClient(
                    cache_dir=cache / "s2", min_interval=1.0, headers=make_headers()
                )
            )
        elif name == "google_scholar":
            registry[name] = GoogleScholarSource()
        elif name == "agent":
            registry[name] = AgentSource()
        else:
            log.warning("source.unknown", name=name)
    return registry


def fetch_all(
    search: SearchConfig, registry: dict[str, Source]
) -> tuple[list[Record], dict[str, int], list[str]]:
    """Run every (source, query) pair, tagging provenance.

    Returns (records, per-source counts, failed source names).
    """
    records: list[Record] = []
    counts: dict[str, int] = {}
    failed: list[str] = []
    for name, source in registry.items():
        n = 0
        had_error = False
        for query in search.queries:
            try:
                hits = source.search(
                    query.terms, max_results=search.max_results_per_query
                )
            except Exception as exc:
                log.warning(
                    "source.failed", source=name, query=query.label, error=str(exc)
                )
                had_error = True
                continue
            for r in hits:
                r.sources = [name]
                r.query_labels = [query.label]
            records.extend(hits)
            n += len(hits)
        counts[name] = n
        if had_error:
            failed.append(name)
    return records, counts, failed
