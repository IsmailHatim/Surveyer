"""Keyword include/exclude filtering over title, abstract and keywords."""

from __future__ import annotations

from surveyer.config import KeywordConfig, resolve_required_concepts
from surveyer.models import Record


def _haystack(r: Record) -> str:
    parts = [r.title or "", r.abstract or "", " ".join(r.keywords)]
    return " ".join(parts).lower()


def _exclusion_reason(
    record: Record,
    cfg: KeywordConfig,
    concepts: dict[str, list[str]] | None,
    concept_mode: str,
) -> str | None:
    """Return the primary reason a record is excluded, or None if it is kept."""
    text = _haystack(record)
    for term in cfg.exclude:
        if term.lower() in text:
            return f"contains '{term}'"
    if concepts:
        total = len(concepts)
        required = resolve_required_concepts(concept_mode, total)
        matched = sum(
            1
            for synonyms in concepts.values()
            if any(syn.lower() in text for syn in synonyms)
        )
        if matched < required:
            return f"matched {matched}/{total} concepts (need ≥{required})"
        return None
    if cfg.include and not any(term.lower() in text for term in cfg.include):
        return "no included keyword"
    return None


def apply_keyword_filter(
    records: list[Record],
    cfg: KeywordConfig,
    concepts: dict[str, list[str]] | None = None,
    concept_mode: str = "any",
) -> tuple[list[Record], int, dict[str, int]]:
    """Return (kept records, number excluded, per-reason exclusion counts)."""
    kept: list[Record] = []
    reasons: dict[str, int] = {}
    for record in records:
        reason = _exclusion_reason(record, cfg, concepts, concept_mode)
        if reason is None:
            kept.append(record)
        else:
            record.exclusion_reason = reason
            reasons[reason] = reasons.get(reason, 0) + 1
    return kept, len(records) - len(kept), reasons
