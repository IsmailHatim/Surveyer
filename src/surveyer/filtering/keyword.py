"""Keyword include/exclude filtering over title, abstract and keywords."""

from __future__ import annotations

from surveyer.config import KeywordConfig
from surveyer.models import Record


def _haystack(r: Record) -> str:
    parts = [r.title or "", r.abstract or "", " ".join(r.keywords)]
    return " ".join(parts).lower()


def _matches(
    record: Record, cfg: KeywordConfig, concepts: dict[str, list[str]] | None
) -> bool:
    text = _haystack(record)
    if any(term.lower() in text for term in cfg.exclude):
        return False
    if concepts:
        return all(
            any(syn.lower() in text for syn in synonyms)
            for synonyms in concepts.values()
        )
    if cfg.include and not any(term.lower() in text for term in cfg.include):
        return False
    return True


def apply_keyword_filter(
    records: list[Record],
    cfg: KeywordConfig,
    concepts: dict[str, list[str]] | None = None,
) -> tuple[list[Record], int]:
    """Return (kept records, number excluded)."""
    kept = [r for r in records if _matches(r, cfg, concepts)]
    return kept, len(records) - len(kept)
