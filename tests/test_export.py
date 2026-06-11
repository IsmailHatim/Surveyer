from __future__ import annotations

import polars as pl
from openpyxl import load_workbook

from surveyer.export import (
    _to_frame,
    export_bibtex,
    export_csv,
    export_results,
    export_xlsx,
)
from surveyer.models import Ledger, Record, SourceCount


def test_export_creates_sheets(tmp_path):
    kept = [Record(title="Kept paper", doi="10.1/a", sources=["dblp"], llm_score=0.8)]
    excluded = [Record(title="Dropped paper", sources=["openalex"])]
    ledger = Ledger(identified=[SourceCount(source="dblp", count=1)], included=1)
    out = tmp_path / "survey.xlsx"
    export_xlsx(kept, excluded, ledger, out)

    wb = load_workbook(out)
    assert set(wb.sheetnames) == {"papers", "excluded", "summary"}
    assert wb["papers"]["A1"].value == "title"
    assert wb["papers"]["A2"].value == "Kept paper"
    assert wb["excluded"]["A1"].value == "title"
    assert wb["summary"]["A1"].value == "stage"
    assert wb["summary"]["B1"].value == "count"


def test_export_xlsx_pins_row_heights(tmp_path):
    # Multiline bibtex cells must not autofit rows to a full BibTeX entry
    kept = [
        Record(title="P", bibtex="@article{k,\n  title = {T}\n}", bibtex_source="dblp")
    ]
    out = tmp_path / "survey.xlsx"
    export_xlsx(kept, [], Ledger(), out)

    row = load_workbook(out)["papers"].row_dimensions[2]
    assert row.customHeight, "bibtex row height not pinned; rows will auto-expand"


def test_export_handles_empty_inputs(tmp_path):
    from surveyer.models import Ledger

    out = tmp_path / "empty.xlsx"
    export_xlsx([], [], Ledger(), out)
    wb = load_workbook(out)
    assert set(wb.sheetnames) == {"papers", "excluded", "summary"}
    assert wb["papers"]["A1"].value == "title"


def test_export_csv_writes_three_files(tmp_path):
    kept = [Record(title="Kept paper", doi="10.1/a", sources=["dblp"], llm_score=0.8)]
    excluded = [Record(title="Dropped paper", sources=["openalex"])]
    ledger = Ledger(identified=[SourceCount(source="dblp", count=1)], included=1)

    export_csv(kept, excluded, ledger, tmp_path)

    papers = pl.read_csv(tmp_path / "papers.csv")
    excluded_df = pl.read_csv(tmp_path / "excluded.csv")
    summary = pl.read_csv(tmp_path / "summary.csv")
    assert papers["title"].to_list() == ["Kept paper"]
    assert papers["llm_score"].to_list() == [0.8]
    assert excluded_df["title"].to_list() == ["Dropped paper"]
    assert summary.columns == ["stage", "count"]


def test_export_csv_handles_empty_inputs(tmp_path):
    export_csv([], [], Ledger(), tmp_path)

    papers = pl.read_csv(tmp_path / "papers.csv")
    assert papers.columns[0] == "title"
    assert papers.height == 0


def test_export_results_dispatches_xlsx(tmp_path):
    kept = [Record(title="Kept paper", sources=["dblp"], llm_score=0.8)]
    export_results(kept, [], Ledger(included=1), tmp_path, fmt="xlsx")

    assert (tmp_path / "survey.xlsx").exists()
    wb = load_workbook(tmp_path / "survey.xlsx")
    assert set(wb.sheetnames) == {"papers", "excluded", "summary"}


def test_export_results_dispatches_csv(tmp_path):
    kept = [Record(title="Kept paper", sources=["dblp"], llm_score=0.8)]
    export_results(kept, [], Ledger(included=1), tmp_path, fmt="csv")

    assert not (tmp_path / "survey.xlsx").exists()
    assert {p.name for p in tmp_path.glob("*.csv")} == {
        "papers.csv",
        "excluded.csv",
        "summary.csv",
    }


def test_export_results_rejects_unknown_format(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="Unknown export format"):
        export_results([], [], Ledger(), tmp_path, fmt="json")


def test_to_frame_includes_bibtex_columns():
    df = _to_frame([Record(title="P", bibtex="@misc{p}", bibtex_source="local")])
    assert "bibtex" in df.columns
    assert "bibtex_source" in df.columns
    assert df["bibtex"][0] == "@misc{p}"
    assert df["bibtex_source"][0] == "local"


def test_export_includes_exclusion_reason_column(tmp_path):
    excluded = [Record(title="Dropped paper", exclusion_reason="no graph")]
    out = tmp_path / "survey.xlsx"
    export_xlsx([], excluded, Ledger(), out)

    ws = load_workbook(out)["excluded"]
    header = [c.value for c in ws[1]]
    assert "exclusion_reason" in header
    col = header.index("exclusion_reason") + 1
    assert ws.cell(row=2, column=col).value == "no graph"


def test_export_bibtex_writes_references_file(tmp_path):
    kept = [
        Record(title="A", bibtex="@article{a, title={A}}"),
        Record(title="B", bibtex="@misc{b, title={B}}"),
    ]
    export_bibtex(kept, tmp_path)
    text = (tmp_path / "references.bib").read_text()
    assert "@article{a, title={A}}" in text
    assert "@misc{b, title={B}}" in text


def test_export_results_csv_writes_references_and_columns(tmp_path):
    kept = [Record(title="A", bibtex="@misc{a}", bibtex_source="local")]
    export_results(kept, [], Ledger(), tmp_path, fmt="csv")
    assert (tmp_path / "references.bib").exists()
    papers = (tmp_path / "papers.csv").read_text()
    assert "bibtex" in papers
    assert "@misc{a}" in papers
