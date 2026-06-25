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
    exclusion_reason: str | None = None
    keyword_note: str | None = None  # advisory lexical match note (soft gate)
    screening_status: str | None = None  # "include" | "borderline" | "exclude"
    concept_verdicts: dict[str, str] = {}
    dblp_key: str | None = None
    bibtex: str | None = None
    bibtex_source: str | None = None


class SearchResult(msgspec.Struct, kw_only=True):
    """Records returned by one source query, plus the API's reported match total."""

    records: list[Record]
    api_total: int | None = None


class QueryRetrieval(msgspec.Struct, kw_only=True):
    """Retrieval accounting for one (source, query): requested/retrieved/API-total."""

    source: str
    query_label: str
    requested: int
    retrieved: int
    api_total: int | None = None


class SourceCount(msgspec.Struct, kw_only=True):
    """How many records a single source contributed."""

    source: str
    count: int


class SnowballLedger(msgspec.Struct, kw_only=True):
    """Per-stage counts for the citation-searching (snowball) arm."""

    seeds: int = 0  # included papers we tried to chase
    seeds_resolved: int = 0  # seeds found in OpenAlex (had a usable DOI)
    identified: int = 0  # raw candidates fetched (backward + forward)
    backward: int = 0  # references found
    forward: int = 0  # citing works found
    duplicates_removed: int = 0  # internal dupes + dupes vs the main arm
    excluded_keyword: int = 0
    excluded_keyword_reasons: dict[str, int] = {}
    excluded_llm: int = 0
    included: int = 0
    retrieval: list[QueryRetrieval] = []


class Ledger(msgspec.Struct, kw_only=True):
    """Provenance counts at each pipeline stage."""

    identified: list[SourceCount] = []
    duplicates_removed: int = 0
    excluded_keyword: int = 0
    excluded_keyword_reasons: dict[str, int] = {}
    excluded_llm: int = 0
    borderline: int = 0
    included: int = 0
    failed_sources: list[str] = []
    previously_included: int = 0
    already_screened: int = 0
    retrieval: list[QueryRetrieval] = []
    snowball: SnowballLedger | None = None

    def total_identified(self) -> int:
        """Records identified across all sources before deduplication."""
        return sum(sc.count for sc in self.identified)

    def after_dedup(self) -> int:
        """Records remaining after duplicates removed."""
        return self.total_identified() - self.duplicates_removed

    def total_included(self) -> int:
        """Studies in the final review: carried over + main arm + snowball section."""
        snow = self.snowball.included if self.snowball is not None else 0
        return self.previously_included + self.included + snow

    def truncated_sources(self) -> list[str]:
        """Sources with any query capped below the API's reported total."""
        out: list[str] = []
        for qr in self.retrieval:
            if (
                qr.api_total is not None
                and qr.retrieved < qr.api_total
                and qr.source not in out
            ):
                out.append(qr.source)
        return out
