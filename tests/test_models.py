from __future__ import annotations

from surveyer.models import Ledger, Record, SourceCount


def test_record_defaults():
    r = Record(title="Attention Is All You Need")
    assert r.title == "Attention Is All You Need"
    assert r.authors == []
    assert r.sources == []
    assert r.doi is None
    assert r.llm_score is None


def test_record_carries_provenance():
    r = Record(title="X", sources=["dblp"], query_labels=["A_attacks"])
    assert r.sources == ["dblp"]
    assert r.query_labels == ["A_attacks"]


def test_record_bibtex_fields_default_none():
    r = Record(title="A paper")
    assert r.dblp_key is None
    assert r.bibtex is None
    assert r.bibtex_source is None


def test_ledger_roundtrip_fields():
    led = Ledger(
        identified=[SourceCount(source="dblp", count=10)],
        duplicates_removed=3,
        excluded_keyword=2,
        excluded_llm=1,
        included=4,
    )
    assert led.total_identified() == 10
    assert led.included == 4
