from __future__ import annotations

from surveyer.ledger import load_ledger, save_ledger
from surveyer.models import Ledger, SourceCount


def test_ledger_save_load_roundtrip(tmp_path):
    led = Ledger(
        identified=[SourceCount(source="dblp", count=5), SourceCount(source="openalex", count=7)],
        duplicates_removed=2,
        excluded_keyword=1,
        excluded_llm=3,
        included=6,
    )
    path = tmp_path / "ledger.json"
    save_ledger(led, path)
    loaded = load_ledger(path)
    assert loaded.total_identified() == 12
    assert loaded.after_dedup() == 10
    assert loaded.included == 6
    assert loaded.identified[0].source == "dblp"
