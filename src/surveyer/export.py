"""Export results to an Excel sheet."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import xlsxwriter

from surveyer.models import Ledger, Record

# Explicit schema so polars never infers a column type from a leading run of
# null values (e.g. records with no llm_score) and then chokes on a later float.
_SCHEMA: dict[str, pl.DataType] = {
    "title": pl.Utf8,
    "authors": pl.Utf8,
    "year": pl.Int64,
    "venue": pl.Utf8,
    "doi": pl.Utf8,
    "url": pl.Utf8,
    "abstract": pl.Utf8,
    "keywords": pl.Utf8,
    "n_citations": pl.Int64,
    "sources": pl.Utf8,
    "query_labels": pl.Utf8,
    "llm_score": pl.Float64,
    "llm_reason": pl.Utf8,
}

_COLUMNS = list(_SCHEMA)

# Bold, shaded header row applied to every sheet.
_HEADER_FORMAT = {
    "bold": True,
    "bg_color": "#D9E1F2",
    "border": 1,
    "align": "center",
    "valign": "vcenter",
}

# Fixed column widths (in pixels, as polars expects) instead of autofit, so
# every column keeps a predictable size and the sheet fits on one screen.
_COLUMN_WIDTHS = {
    "title": 290,
    "authors": 200,
    "year": 50,
    "venue": 130,
    "doi": 150,
    "url": 190,
    "abstract": 360,
    "keywords": 170,
    "n_citations": 70,
    "sources": 100,
    "query_labels": 110,
    "llm_score": 75,
    "llm_reason": 290,
}

# Yellow (low) to green (high) colour scale over the 0..1 llm_score.
_SCORE_COLOR_SCALE = {
    "llm_score": {
        "type": "2_color_scale",
        "min_type": "num",
        "min_value": 0.0,
        "min_color": "#FFEB84",
        "max_type": "num",
        "max_value": 1.0,
        "max_color": "#63BE7B",
    }
}


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
    return pl.DataFrame(rows, schema=_SCHEMA).select(_COLUMNS)


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
        _to_frame(kept).write_excel(
            workbook=wb,
            worksheet="papers",
            header_format=_HEADER_FORMAT,
            conditional_formats=_SCORE_COLOR_SCALE,
            column_widths=_COLUMN_WIDTHS,
            freeze_panes=(1, 0),
        )
        _to_frame(excluded).write_excel(
            workbook=wb,
            worksheet="excluded",
            header_format=_HEADER_FORMAT,
            conditional_formats=_SCORE_COLOR_SCALE,
            column_widths=_COLUMN_WIDTHS,
            freeze_panes=(1, 0),
        )
        _summary_frame(ledger).write_excel(
            workbook=wb,
            worksheet="summary",
            header_format=_HEADER_FORMAT,
            autofit=True,
            freeze_panes=(1, 0),
        )
    finally:
        wb.close()


def export_csv(
    kept: list[Record],
    excluded: list[Record],
    ledger: Ledger,
    out_dir: str | Path,
) -> None:
    """Write kept and excluded records and a ledger summary as CSV files.

    Unlike the .xlsx export, CSV has no concept of sheets or cell styling,
    so each sheet is written to its own file in ``out_dir``: ``papers.csv``,
    ``excluded.csv`` and ``summary.csv``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _to_frame(kept).write_csv(out_dir / "papers.csv")
    _to_frame(excluded).write_csv(out_dir / "excluded.csv")
    _summary_frame(ledger).write_csv(out_dir / "summary.csv")


def export_results(
    kept: list[Record],
    excluded: list[Record],
    ledger: Ledger,
    out_dir: str | Path,
    fmt: str = "xlsx",
) -> None:
    """Export results to ``out_dir`` in the requested format ("xlsx" or "csv")."""
    out_dir = Path(out_dir)
    if fmt == "csv":
        export_csv(kept, excluded, ledger, out_dir)
    elif fmt == "xlsx":
        export_xlsx(kept, excluded, ledger, out_dir / "survey.xlsx")
    else:
        raise ValueError(f"Unknown export format: {fmt!r}")
