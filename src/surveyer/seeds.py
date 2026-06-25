"""Must-cite seed injection: resolve configured ids into pinned Records."""

from __future__ import annotations

import threading
from pathlib import Path

import structlog

from surveyer.cancel import PipelineCancelled, check_cancelled
from surveyer.models import Record, SeedLedger
from surveyer.sources.base import HttpClient
from surveyer.sources.openalex import API as OPENALEX_API
from surveyer.sources.openalex import _strip_doi, parse_openalex_work
from surveyer.sources.semantic_scholar import (
    FIELDS,
    PAPER_API,
    make_headers,
    parse_s2_paper,
)

log = structlog.get_logger()


def detect_seed_id(raw: str) -> tuple[str, str | None]:
    """Return (s2_lookup_id, bare_doi_or_none) for a configured seed id."""
    s = raw.strip()
    low = s.lower()
    if low.startswith("corpusid:"):
        return f"CorpusID:{s.split(':', 1)[1]}", None
    if low.startswith("arxiv:"):
        return f"ARXIV:{s.split(':', 1)[1]}", None
    if low.startswith("doi:"):
        s = s.split(":", 1)[1]
        low = s.lower()
    if low.startswith("10.") or low.startswith("http"):
        doi = _strip_doi(s) or s
        return f"DOI:{doi}", doi
    # Bare Semantic Scholar paper id (40-char hash) or anything else: hand to S2 as-is.
    return s, None


class SeedResolver:
    """Resolve seed ids into Records: Semantic Scholar first, OpenAlex fallback."""

    def __init__(self, s2_client: HttpClient, openalex_client: HttpClient) -> None:
        """Initialise with Semantic Scholar and OpenAlex HTTP clients."""
        self.s2 = s2_client
        self.openalex = openalex_client

    def resolve(
        self, ids: list[str], *, cancel: threading.Event | None = None
    ) -> tuple[list[Record], SeedLedger]:
        """Resolve each id to a pinned Record; unresolved ids warn and continue."""
        records: list[Record] = []
        ledger = SeedLedger(imported=len(ids))
        for raw in ids:
            check_cancelled(cancel)
            lookup_id, doi = detect_seed_id(raw)
            record = self._via_s2(lookup_id)
            origin = "s2"
            if record is None and doi is not None:
                record = self._via_openalex(doi)
                origin = "openalex"
            if record is None:
                log.warning("seed.unresolved", id=raw)
                ledger.unresolved += 1
                continue
            record.sources = ["seed"]
            record.query_labels = [f"seed:{origin}"]
            record.screening_status = "include"
            records.append(record)
            ledger.resolved += 1
        log.info(
            "seed.resolved",
            imported=ledger.imported,
            resolved=ledger.resolved,
            unresolved=ledger.unresolved,
        )
        return records, ledger

    def _via_s2(self, lookup_id: str) -> Record | None:
        """Look the id up in Semantic Scholar; None on any miss/error."""
        url = f"{PAPER_API}/{lookup_id}"
        try:
            raw = self.s2.get_json(url, params={"fields": FIELDS})
        except PipelineCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - any failure means "try fallback"
            log.warning("seed.s2_failed", id=lookup_id, error=str(exc))
            return None
        if not raw.get("title"):
            return None
        return parse_s2_paper(raw)

    def _via_openalex(self, doi: str) -> Record | None:
        """Look a DOI up in OpenAlex; None on any miss/error."""
        url = f"{OPENALEX_API}/doi:{doi}"
        try:
            raw = self.openalex.get_json(url, params={})
        except PipelineCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - any failure means "unresolved"
            log.warning("seed.openalex_failed", doi=doi, error=str(exc))
            return None
        if not raw.get("title"):
            return None
        return parse_openalex_work(raw)


def build_seed_resolver(
    cache_root: str | Path, *, refresh: bool = False
) -> SeedResolver:
    """Build a SeedResolver sharing the run's s2/ and openalex/ cache dirs."""
    cache = Path(cache_root)
    s2 = HttpClient(
        cache_dir=cache / "s2",
        min_interval=1.1,
        headers=make_headers(),
        refresh=refresh,
    )
    openalex = HttpClient(
        cache_dir=cache / "openalex", min_interval=0.2, refresh=refresh
    )
    return SeedResolver(s2, openalex)
