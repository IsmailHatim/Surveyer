"""DBLP source adapter. API: https://dblp.org/search/publ/api."""

from __future__ import annotations

from surveyer.models import Record
from surveyer.sources.base import HttpClient

API = "https://dblp.org/search/publ/api"


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

    def search(self, terms: str, *, max_results: int) -> list[Record]:
        """Search DBLP and return records."""
        raw = self.client.get_json(
            API, params={"q": terms, "format": "json", "h": max_results}
        )
        return parse_dblp(raw)
