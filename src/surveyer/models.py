"""Canonical data models shared across the pipeline."""

from __future__ import annotations

import msgspec


class Record(msgspec.Struct, kw_only=True):
    """One paper in the canonical schema all sources map into."""

    title: str
    doi: str | None = None
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    keywords: list[str] = []
    url: str | None = None
    n_citations: int | None = None
    sources: list[str] = []
    query_labels: list[str] = []
    llm_score: float | None = None
    llm_reason: str | None = None
    dblp_key: str | None = None
    bibtex: str | None = None
    bibtex_source: str | None = None


class SourceCount(msgspec.Struct, kw_only=True):
    """How many records a single source contributed."""

    source: str
    count: int


class Ledger(msgspec.Struct, kw_only=True):
    """Provenance counts at each pipeline stage."""

    identified: list[SourceCount] = []
    duplicates_removed: int = 0
    excluded_keyword: int = 0
    excluded_keyword_reasons: dict[str, int] = {}
    excluded_llm: int = 0
    included: int = 0
    failed_sources: list[str] = []

    def total_identified(self) -> int:
        """Records identified across all sources before deduplication."""
        return sum(sc.count for sc in self.identified)

    def after_dedup(self) -> int:
        """Records remaining after duplicates removed."""
        return self.total_identified() - self.duplicates_removed
