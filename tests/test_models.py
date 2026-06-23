from __future__ import annotations

from surveyer.models import Ledger, QueryRetrieval, Record, SearchResult, SourceCount


def test_search_result_defaults():
    sr = SearchResult(records=[Record(title="A")])
    assert sr.api_total is None
    assert [r.title for r in sr.records] == ["A"]


def test_query_retrieval_fields():
    qr = QueryRetrieval(
        source="openalex", query_label="q1", requested=100, retrieved=80, api_total=5000
    )
    assert (qr.source, qr.requested, qr.retrieved, qr.api_total) == (
        "openalex",
        100,
        80,
        5000,
    )


def test_ledger_truncated_sources():
    led = Ledger(
        retrieval=[
            QueryRetrieval(source="openalex", query_label="q1", requested=100,
                           retrieved=100, api_total=5000),   # truncated
            QueryRetrieval(source="openalex", query_label="q2", requested=100,
                           retrieved=12, api_total=12),       # not truncated
            QueryRetrieval(source="dblp", query_label="q1", requested=100,
                           retrieved=5, api_total=5),         # not truncated
            QueryRetrieval(source="gscholar", query_label="q1", requested=100,
                           retrieved=10, api_total=None),     # unknown total
        ]
    )
    assert led.truncated_sources() == ["openalex"]


def test_ledger_truncated_sources_empty_by_default():
    assert Ledger().truncated_sources() == []


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
