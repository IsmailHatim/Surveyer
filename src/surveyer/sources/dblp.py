"""DBLP source adapter. API: https://dblp.org/search/publ/api."""

from __future__ import annotations

import httpx
import structlog

from surveyer.models import Record, SearchResult
from surveyer.sources.base import HttpClient, coerce_int, dequote_terms

log = structlog.get_logger()

API = "https://dblp.org/search/publ/api"
# Official DBLP mirror with identical content.
MIRROR_API = "https://dblp.uni-trier.de/search/publ/api"


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_dblp(raw: dict) -> list[Record]:
    """Parse a DBLP API response into a list of Records."""
    hits = _as_list(raw.get("result", {}).get("hits", {}).get("hit"))
    out: list[Record] = []
    for hit in hits:
        info = hit.get("info", {})
        authors_field = info.get("authors", {}).get("author")
        authors = [a["text"] for a in _as_list(authors_field)]
        year = info.get("year")
        out.append(
            Record(
                title=info.get("title", "").rstrip(". "),
                doi=info.get("doi"),
                authors=authors,
                year=int(year) if year else None,
                venue=info.get("venue"),
                url=_as_list(ee)[0] if (ee := info.get("ee")) else None,
                dblp_key=info.get("key"),
            )
        )
    return out


class DblpSource:
    """DBLP bibliographic source adapter."""

    name = "dblp"

    def __init__(self, client: HttpClient) -> None:
        """Initialise the DBLP source with the given HTTP client."""
        self.client = client
        self.api = API

    def search(self, terms: str, *, max_results: int) -> SearchResult:
        """Search DBLP and return records + API total, falling back to the mirror."""
        # DBLP has no phrase operator; drop phrase quotes to prefix-AND matching.
        params = {"q": dequote_terms(terms), "format": "json", "h": max_results}
        try:
            raw = self.client.get_json(self.api, params=params)
        except (httpx.HTTPError, RuntimeError):
            if self.api == MIRROR_API:
                raise  # the mirror failed too
            log.warning("dblp.primary_failed", fallback=MIRROR_API)
            # Sticky: dblp.org is rate-limiting us
            self.api = MIRROR_API
            raw = self.client.get_json(self.api, params=params)
        api_total = coerce_int(
            ((raw.get("result") or {}).get("hits") or {}).get("@total")
        )
        return SearchResult(records=parse_dblp(raw), api_total=api_total)
