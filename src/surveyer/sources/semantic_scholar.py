"""Semantic Scholar adapter. API: https://api.semanticscholar.org/graph/v1."""

from __future__ import annotations

import os

from surveyer.models import Record, SearchResult
from surveyer.sources.base import HttpClient, coerce_int

API = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,abstract,year,citationCount,externalIds,venue,url,authors"

# The search endpoint caps `limit` at 100 records per request.
PAGE_SIZE = 100


def parse_s2(raw: dict) -> list[Record]:
    """Parse a Semantic Scholar API response into a list of Records."""
    out: list[Record] = []
    for p in raw.get("data", []):
        ext = p.get("externalIds") or {}
        authors = [a.get("name") for a in p.get("authors", []) if a.get("name")]
        out.append(
            Record(
                title=p.get("title") or "",
                doi=ext.get("DOI"),
                authors=authors,
                year=p.get("year"),
                venue=p.get("venue"),
                abstract=p.get("abstract"),
                n_citations=p.get("citationCount"),
                url=p.get("url"),
            )
        )
    return out


class SemanticScholarSource:
    """Semantic Scholar bibliographic source adapter."""

    name = "semantic_scholar"

    def __init__(self, client: HttpClient) -> None:
        """Initialise the Semantic Scholar source with the given HTTP client."""
        self.client = client

    def search(self, terms: str, *, max_results: int) -> SearchResult:
        """Search Semantic Scholar, paginating until max_results, with API total."""
        out: list[Record] = []
        api_total: int | None = None
        offset = 0
        while len(out) < max_results:
            limit = min(max_results - len(out), PAGE_SIZE)
            params = {
                # Quotes are intentionally preserved for s2
                "query": terms,
                "offset": offset,
                "limit": limit,
                "fields": FIELDS,
            }
            raw = self.client.get_json(API, params=params)
            if api_total is None:
                api_total = coerce_int(raw.get("total"))
            batch = parse_s2(raw)
            out.extend(batch)
            nxt = raw.get("next")
            if not batch or nxt is None:
                break
            offset = nxt
        return SearchResult(records=out[:max_results], api_total=api_total)


def make_headers() -> dict[str, str]:
    """API key for higher rate limits."""
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    return {"x-api-key": key} if key else {}
