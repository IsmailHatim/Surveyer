"""OpenAlex source adapter. API: https://api.openalex.org/works."""

from __future__ import annotations

import re

from surveyer.models import Record
from surveyer.sources.base import HttpClient

API = "https://api.openalex.org/works"


def reconstruct_abstract(inverted: dict | None) -> str | None:
    """Rebuild plain text from OpenAlex's abstract_inverted_index."""
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(word for _, word in positions)


def _strip_doi(doi: str | None) -> str | None:
    """Strip the https://doi.org/ prefix from a DOI string."""
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)


def parse_openalex(raw: dict) -> list[Record]:
    """Parse an OpenAlex API response into a list of Records."""
    out: list[Record] = []
    for w in raw.get("results", []):
        loc = (w.get("primary_location") or {}).get("source") or {}
        authors = [
            a.get("author", {}).get("display_name")
            for a in w.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        out.append(
            Record(
                title=w.get("title") or "",
                doi=_strip_doi(w.get("doi")),
                authors=authors,
                year=w.get("publication_year"),
                venue=loc.get("display_name"),
                abstract=reconstruct_abstract(w.get("abstract_inverted_index")),
                n_citations=w.get("cited_by_count"),
                url=w.get("doi"),
            )
        )
    return out


class OpenAlexSource:
    """OpenAlex bibliographic source adapter."""

    name = "openalex"

    def __init__(self, client: HttpClient, *, year_min=None, year_max=None) -> None:
        """Initialise the OpenAlex source with the given HTTP client and year bounds."""
        self.client = client
        self.year_min = year_min
        self.year_max = year_max

    def search(self, terms: str, *, max_results: int) -> list[Record]:
        """Search OpenAlex and return records."""
        params: dict = {"search": terms, "per-page": min(max_results, 200)}
        filters = []
        if self.year_min:
            filters.append(f"from_publication_date:{self.year_min}-01-01")
        if self.year_max:
            filters.append(f"to_publication_date:{self.year_max}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        raw = self.client.get_json(API, params=params)
        return parse_openalex(raw)
