"""Export results to an Excel sheet."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import xlsxwriter

from surveyer.models import Ledger, Record

_COLUMNS = [
    "title",
    "authors",
    "year",
    "venue",
    "doi",
    "url",
    "abstract",
    "keywords",
    "n_citations",
    "sources",
    "query_labels",
    "llm_score",
    "llm_reason",
]


def _to_frame(records: list[Record]) -> pl.DataFrame:
    rows = []
    for r in records:
        rows.append(
            {
                "title": r.title,
                "authors": "; ".join(r.authors),
                "year": r.year,
                "venue": r.venue,
                "doi": r.doi,
                "url": r.url,
                "abstract": r.abstract,
                "keywords": "; ".join(r.keywords),
                "n_citations": r.n_citations,
                "sources": "; ".join(r.sources),
                "query_labels": "; ".join(r.query_labels),
                "llm_score": r.llm_score,
                "llm_reason": r.llm_reason,
            }
        )
    if not rows:
        return pl.DataFrame({c: [] for c in _COLUMNS})
    return pl.DataFrame(rows).select(_COLUMNS)


def _summary_frame(ledger: Ledger) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "stage": [
                "total_identified",
                "duplicates_removed",
                "after_dedup",
                "excluded_keyword",
                "excluded_llm",
                "included",
            ],
            "count": [
                ledger.total_identified(),
                ledger.duplicates_removed,
                ledger.after_dedup(),
                ledger.excluded_keyword,
                ledger.excluded_llm,
                ledger.included,
            ],
        }
    )


def export_xlsx(
    kept: list[Record],
    excluded: list[Record],
    ledger: Ledger,
    path: str | Path,
) -> None:
    """Write kept and excluded records and a ledger summary to a .xlsx."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(path))
    try:
        _to_frame(kept).write_excel(workbook=wb, worksheet="papers")
        _to_frame(excluded).write_excel(workbook=wb, worksheet="excluded")
        _summary_frame(ledger).write_excel(workbook=wb, worksheet="summary")
    finally:
        wb.close()
