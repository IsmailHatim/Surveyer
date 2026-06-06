"""Deduplication: exact DOI, then fuzzy title for records without DOI."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from surveyer.models import Record

_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase and strip punctuation and whitespace from a title."""
    t = _PUNCT.sub("", title.lower())
    return _SPACE.sub(" ", t).strip()


def _merge(into: Record, other: Record) -> None:
    into.sources = sorted(set(into.sources) | set(other.sources))
    into.query_labels = sorted(set(into.query_labels) | set(other.query_labels))
    # Backfill missing scalar fields from the duplicate.
    for field in ("doi", "abstract", "venue", "year", "url", "n_citations"):
        if getattr(into, field) is None and getattr(other, field) is not None:
            setattr(into, field, getattr(other, field))


def deduplicate(
    records: list[Record], *, title_threshold: int = 90
) -> tuple[list[Record], int]:
    """Return (deduplicated records, number removed). Provenance is merged."""
    kept: list[Record] = []
    by_doi: dict[str, Record] = {}
    removed = 0

    for r in records:
        doi = r.doi.lower().strip() if r.doi else None
        if doi and doi in by_doi:
            _merge(by_doi[doi], r)
            removed += 1
            continue

        norm = normalize_title(r.title)
        match = None
        for existing in kept:
            ex_doi = existing.doi.lower().strip() if existing.doi else None
            if doi and ex_doi and ex_doi != doi:
                continue
            if (
                fuzz.token_sort_ratio(norm, normalize_title(existing.title))
                >= title_threshold
            ):
                match = existing
                break

        if match is not None:
            _merge(match, r)
            removed += 1
            if match.doi:  # a DOI may have been backfilled during merge
                by_doi[match.doi.lower().strip()] = match
            continue

        kept.append(r)
        if doi:
            by_doi[doi] = r

    return kept, removed
