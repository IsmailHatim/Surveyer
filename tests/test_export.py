from __future__ import annotations

from openpyxl import load_workbook

from surveyer.export import export_xlsx
from surveyer.models import Ledger, Record, SourceCount


def test_export_creates_sheets(tmp_path):
    kept = [Record(title="Kept paper", doi="10.1/a", sources=["dblp"], llm_score=0.8)]
    excluded = [Record(title="Dropped paper", sources=["openalex"])]
    ledger = Ledger(
        identified=[SourceCount(source="dblp", count=1)], included=1
    )
    out = tmp_path / "survey.xlsx"
    export_xlsx(kept, excluded, ledger, out)

    wb = load_workbook(out)
    assert set(wb.sheetnames) == {"papers", "excluded", "summary"}
    assert wb["papers"]["A1"].value == "title"
    assert wb["papers"]["A2"].value == "Kept paper"
    assert wb["excluded"]["A1"].value == "title"
    assert wb["summary"]["A1"].value == "stage"
    assert wb["summary"]["B1"].value == "count"


def test_export_handles_empty_inputs(tmp_path):
    from surveyer.models import Ledger

    out = tmp_path / "empty.xlsx"
    export_xlsx([], [], Ledger(), out)
    wb = load_workbook(out)
    assert set(wb.sheetnames) == {"papers", "excluded", "summary"}
    assert wb["papers"]["A1"].value == "title"
