"""OpenAlex source adapter. API: https://api.openalex.org/works."""

from __future__ import annotations

import os
import re

from surveyer.models import Record, SearchResult
from surveyer.sources.base import HttpClient, coerce_int

API = "https://api.openalex.org/works"

# OpenAlex caps `per-page` at 200 records per request.
PAGE_SIZE = 200


def _polite_params(params: dict) -> dict:
    """Append OpenAlex polite-pool mailto from OPENALEX_MAILTO env, if set."""
    email = os.environ.get("OPENALEX_MAILTO", "").strip()
    if email:
        return {**params, "mailto": email}
    return params


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


def parse_openalex_work(w: dict) -> Record:
    """Parse a single OpenAlex work dict into a Record."""
    loc = (w.get("primary_location") or {}).get("source") or {}
    authors = [
        a.get("author", {}).get("display_name")
        for a in w.get("authorships", [])
        if a.get("author", {}).get("display_name")
    ]
    return Record(
        title=w.get("title") or "",
        doi=_strip_doi(w.get("doi")),
        authors=authors,
        year=w.get("publication_year"),
        venue=loc.get("display_name"),
        abstract=reconstruct_abstract(w.get("abstract_inverted_index")),
        n_citations=w.get("cited_by_count"),
        url=w.get("doi"),
    )


def parse_openalex(raw: dict) -> list[Record]:
    """Parse an OpenAlex API response into a list of Records."""
    return [parse_openalex_work(w) for w in raw.get("results", [])]


class OpenAlexSource:
    """OpenAlex bibliographic source adapter."""

    name = "openalex"

    def __init__(self, client: HttpClient, *, year_min=None, year_max=None) -> None:
        """Initialise the OpenAlex source with the given HTTP client and year bounds."""
        self.client = client
        self.year_min = year_min
        self.year_max = year_max

    def search(self, terms: str, *, max_results: int) -> SearchResult:
        """Search OpenAlex, paginating until max_results, with the API total."""
        per_page = min(max_results, PAGE_SIZE)
        filters = []
        if self.year_min:
            filters.append(f"from_publication_date:{self.year_min}-01-01")
        if self.year_max:
            filters.append(f"to_publication_date:{self.year_max}-12-31")

        out: list[Record] = []
        api_total: int | None = None
        page = 1
        while len(out) < max_results:
            # Quotes are intentionally preserved for OpenAlex
            params: dict = {"search": terms, "per-page": per_page, "page": page}
            if filters:
                params["filter"] = ",".join(filters)
            raw = self.client.get_json(API, params=_polite_params(params))
            if api_total is None:
                api_total = coerce_int((raw.get("meta") or {}).get("count"))
            batch = parse_openalex(raw)
            out.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return SearchResult(records=out[:max_results], api_total=api_total)
