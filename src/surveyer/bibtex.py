"""Resolve a BibTeX entry for each record: DBLP key -> DOI -> local @misc."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

import httpx
import structlog

from surveyer.models import Record
from surveyer.sources.base import HttpClient

log = structlog.get_logger()

DBLP_REC = "https://dblp.org/rec/{key}.bib"
# Official mirror with identical content, used when dblp.org rate-limits us.
DBLP_REC_MIRROR = "https://dblp.uni-trier.de/rec/{key}.bib"
DOI_BASE = "https://doi.org/{doi}"
_BIBTEX_ACCEPT = {"Accept": "application/x-bibtex"}
# DBLP rate limits
_MIN_INTERVAL = 1.5


def _citation_key(record: Record, seen: set[str]) -> str:
    """A unique-within-run key like ``doe2024great``."""
    surname = record.authors[0].split()[-1] if record.authors else ""
    first_word = record.title.split()[0] if record.title else ""
    base = f"{surname}{record.year or ''}{first_word}"
    base = re.sub(r"[^A-Za-z0-9]", "", base).lower() or "ref"
    key = base
    n = 0
    while key in seen:
        # Base26 letter suffix
        n += 1
        suffix, m = "", n
        while m:
            m, r = divmod(m - 1, 26)
            suffix = chr(ord("a") + r) + suffix
        key = f"{base}{suffix}"
    seen.add(key)
    return key


def build_local_entry(record: Record, *, seen: set[str]) -> str:
    """Construct a minimal @misc entry from whatever fields are present."""
    key = _citation_key(record, seen)
    fields: list[tuple[str, str]] = []
    if record.title:
        fields.append(("title", record.title))
    if record.authors:
        fields.append(("author", " and ".join(record.authors)))
    if record.year:
        fields.append(("year", str(record.year)))
    howpublished = record.venue or record.url
    if howpublished:
        fields.append(("howpublished", howpublished))
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
    if body:
        return f"@misc{{{key},\n{body}\n}}"
    return f"@misc{{{key},\n}}"


class BibtexResolver:
    """Resolve BibTeX for records via DBLP, then DOI, then a local fallback."""

    def __init__(self, client: HttpClient) -> None:
        """Initialise with an HTTP client used for both DBLP and DOI fetches."""
        self.client = client
        self._seen: set[str] = set()
        self._dblp_rec = DBLP_REC

    def _fetch(self, url: str, headers: dict | None = None) -> str | None:
        try:
            text = self.client.get_text(url, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("bibtex.fetch_failed", url=url, error=str(exc))
            return None
        return text.strip() if text else None

    def _fetch_dblp(self, key: str) -> str | None:
        """Fetch a DBLP .bib entry, falling back to the Trier mirror."""
        try:
            text = self.client.get_text(self._dblp_rec.format(key=key))
        except httpx.HTTPError as exc:
            if self._dblp_rec == DBLP_REC_MIRROR:
                log.warning("bibtex.dblp_mirror_failed", key=key, error=str(exc))
                return None
            log.warning("bibtex.dblp_primary_failed", fallback=DBLP_REC_MIRROR)
            self._dblp_rec = DBLP_REC_MIRROR  # sticky
            return self._fetch_dblp(key)
        return text.strip() if text else None

    def resolve(self, record: Record) -> tuple[str, str]:
        """Return ``(bibtex_text, source)`` where source is dblp/doi/local."""
        if record.dblp_key:
            text = self._fetch_dblp(record.dblp_key)
            if text:
                return text, "dblp"
        if record.doi:
            # Percent encode so DOI containing # or ? aren't truncated
            doi = quote(record.doi, safe="/")
            text = self._fetch(DOI_BASE.format(doi=doi), headers=_BIBTEX_ACCEPT)
            if text:
                return text, "doi"
        return build_local_entry(record, seen=self._seen), "local"

    def resolve_all(self, records: list[Record]) -> None:
        """Resolve and set bibtex/bibtex_source on each record."""
        self._seen = set()
        n_local = 0
        for r in records:
            text, source = self.resolve(r)
            r.bibtex = text
            r.bibtex_source = source
            if source == "local":
                n_local += 1
        log.info("bibtex.resolved", total=len(records), local_fallbacks=n_local)


def build_resolver(cache_root: str | Path) -> BibtexResolver:
    """Build a resolver with a throttled, caching HTTP client."""
    client = HttpClient(
        cache_dir=Path(cache_root) / "bibtex",
        min_interval=_MIN_INTERVAL,
        headers={"User-Agent": "Surveyer (https://github.com/IsmailHatim/Surveyer)"},
        follow_redirects=True,
    )
    return BibtexResolver(client)
