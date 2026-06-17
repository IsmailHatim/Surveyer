"""Deduplication: exact DOI, then fuzzy title for records without DOI."""

from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from surveyer.models import Record

_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")

# DOI prefixes of preprint/deposit registrars (arXiv, Zenodo).
_WEAK_DOI_PREFIXES = ("10.48550/", "10.5281/")


def _is_weak_doi(doi: str | None) -> bool:
    """True for preprint/deposit registrar DOIs (arXiv, Zenodo)."""
    return bool(doi) and doi.lower().startswith(_WEAK_DOI_PREFIXES)


def normalize_title(title: str) -> str:
    """Lowercase and strip punctuation and whitespace from a title."""
    t = _PUNCT.sub("", title.lower())
    return _SPACE.sub(" ", t).strip()


def _merge(into: Record, other: Record) -> None:
    into.sources = sorted(set(into.sources) | set(other.sources))
    into.query_labels = sorted(set(into.query_labels) | set(other.query_labels))
    # Prefer the publisher DOI over a preprint registrar.
    if other.doi and _is_weak_doi(into.doi) and not _is_weak_doi(other.doi):
        into.doi = other.doi
    # Backfill missing scalar fields from the duplicate.
    for field in ("doi", "abstract", "venue", "year", "url", "n_citations", "dblp_key"):
        if getattr(into, field) is None and getattr(other, field) is not None:
            setattr(into, field, getattr(other, field))
    # Backfill an empty author list and union keywords across sources.
    if not into.authors and other.authors:
        into.authors = list(other.authors)
    if other.keywords:
        into.keywords = sorted(set(into.keywords) | set(other.keywords))


def deduplicate(
    records: list[Record], *, title_threshold: int = 90
) -> tuple[list[Record], int]:
    """Return (deduplicated records, number removed). Provenance is merged."""
    kept_records: list[Record] = []
    kept_norms: list[str] = []
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
        if norm and kept_norms:
            # All kept titles at or above threshold.
            cands = process.extract(
                norm,
                kept_norms,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=title_threshold,
                limit=None,
            )
            for _, _score, idx in sorted(cands, key=lambda c: c[2]):
                existing = kept_records[idx]
                ex_doi = existing.doi.lower().strip() if existing.doi else None
                if (
                    doi
                    and ex_doi
                    and ex_doi != doi
                    and not (_is_weak_doi(doi) or _is_weak_doi(ex_doi))
                ):
                    continue
                match = existing
                break

        if match is not None:
            _merge(match, r)
            removed += 1
            if match.doi:
                by_doi[match.doi.lower().strip()] = match
            if doi:
                by_doi[doi] = match
            continue

        kept_records.append(r)
        kept_norms.append(norm)
        if doi:
            by_doi[doi] = r

    return kept_records, removed
