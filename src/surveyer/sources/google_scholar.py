"""Google Scholar adapter (requires the scholar optional extra)."""

from __future__ import annotations

import itertools
from typing import Any

from surveyer.models import Record, SearchResult

_scholarly_lib: Any = None
try:  # pragma: no cover - optional dep
    from scholarly import scholarly as _scholarly_lib
except ImportError:  # pragma: no cover - optional dep
    pass

# Module-level alias so tests can monkeypatch ``gs.scholarly``.
scholarly: Any = _scholarly_lib


def parse_scholar_entry(entry: dict) -> Record:
    """Parse a single scholarly entry dict into a Record."""
    bib = entry.get("bib", {})
    author = bib.get("author")
    authors = author if isinstance(author, list) else ([author] if author else [])
    year = bib.get("pub_year")
    return Record(
        title=bib.get("title", ""),
        authors=authors,
        year=int(year) if year and str(year).isdigit() else None,
        venue=bib.get("venue"),
        abstract=bib.get("abstract"),
        url=entry.get("pub_url"),
        n_citations=entry.get("num_citations"),
    )


def _get_scholarly() -> Any:
    """Return the scholarly singleton, raising if the optional dep is missing."""
    import surveyer.sources.google_scholar as _mod

    if _mod.scholarly is None:  # pragma: no cover - import guard
        raise RuntimeError(
            "Google Scholar needs the optional extra: pip install surveyer[scholar]"
        )
    return _mod.scholarly


class GoogleScholarSource:
    """Google Scholar bibliographic source adapter."""

    name = "google_scholar"

    def search(self, terms: str, *, max_results: int) -> SearchResult:
        """Search Google Scholar; api_total is None (scraper exposes no total)."""
        _scholarly = _get_scholarly()
        results = _scholarly.search_pubs(terms)
        records = [
            parse_scholar_entry(e) for e in itertools.islice(results, max_results)
        ]
        return SearchResult(records=records, api_total=None)
