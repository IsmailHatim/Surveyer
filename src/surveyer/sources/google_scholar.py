"""Google Scholar adapter (requires the scholar optional extra)."""

from __future__ import annotations

import itertools

from surveyer.models import Record


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


class GoogleScholarSource:
    """Google Scholar bibliographic source adapter."""

    name = "google_scholar"

    def search(self, terms: str, *, max_results: int) -> list[Record]:
        """Search Google Scholar and return records."""
        try:
            from scholarly import scholarly
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "Google Scholar needs the optional extra: pip install surveyer[scholar]"
            ) from exc
        results = scholarly.search_pubs(terms)
        return [parse_scholar_entry(e) for e in itertools.islice(results, max_results)]
