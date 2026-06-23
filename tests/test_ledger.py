from __future__ import annotations

from surveyer.ledger import load_ledger, save_ledger
from surveyer.models import Ledger, QueryRetrieval, SnowballLedger, SourceCount


def test_ledger_save_load_roundtrip(tmp_path):
    led = Ledger(
        identified=[
            SourceCount(source="dblp", count=5),
            SourceCount(source="openalex", count=7),
        ],
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


def test_ledger_extend_fields_default_zero():
    led = Ledger()
    assert led.previously_included == 0
    assert led.already_screened == 0
    assert led.total_included() == 0


def test_ledger_total_included_sums_old_and_new():
    led = Ledger(previously_included=7, included=4)
    assert led.total_included() == 11


def test_old_ledger_json_still_loads(tmp_path):
    # A ledger written before the extend feature has no extend fields.
    p = tmp_path / "ledger.json"
    p.write_text(
        '{"identified":[{"source":"dblp","count":3}],"duplicates_removed":1,'
        '"excluded_keyword":0,"excluded_keyword_reasons":{},"excluded_llm":0,'
        '"included":2,"failed_sources":[]}'
    )
    led = load_ledger(p)
    assert led.included == 2
    assert led.previously_included == 0
    assert led.already_screened == 0


def test_ledger_roundtrips_snowball(tmp_path):
    led = Ledger(
        included=2,
        snowball=SnowballLedger(
            seeds=2,
            seeds_resolved=2,
            identified=10,
            backward=7,
            forward=3,
            duplicates_removed=1,
            excluded_keyword=2,
            excluded_keyword_reasons={"no graph": 2},
            excluded_llm=1,
            included=4,
            retrieval=[
                QueryRetrieval(
                    source="openalex",
                    query_label="snowball:backward",
                    requested=200,
                    retrieved=7,
                )
            ],
        ),
    )
    save_ledger(led, tmp_path / "l.json")
    back = load_ledger(tmp_path / "l.json")
    assert back.snowball is not None
    assert back.snowball.included == 4
    assert back.snowball.excluded_keyword_reasons == {"no graph": 2}
    assert back.snowball.retrieval[0].query_label == "snowball:backward"
