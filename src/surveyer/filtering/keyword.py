"""Keyword include/exclude filtering over title, abstract and keywords."""

from __future__ import annotations

from surveyer.config import KeywordConfig
from surveyer.models import Record


def _haystack(r: Record) -> str:
    parts = [r.title or "", r.abstract or "", " ".join(r.keywords)]
    return " ".join(parts).lower()


def _matches(record: Record, cfg: KeywordConfig) -> bool:
    text = _haystack(record)
    if any(term.lower() in text for term in cfg.exclude):
        return False
    if cfg.include and not any(term.lower() in text for term in cfg.include):
        return False
    return True


def apply_keyword_filter(
    records: list[Record], cfg: KeywordConfig
) -> tuple[list[Record], int]:
    """Return (kept records, number excluded)."""
    kept = [r for r in records if _matches(r, cfg)]
    return kept, len(records) - len(kept)
