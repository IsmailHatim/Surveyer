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
            QueryRetrieval(
                source="openalex",
                query_label="q1",
                requested=100,
                retrieved=100,
                api_total=5000,
            ),  # truncated
            QueryRetrieval(
                source="openalex",
                query_label="q2",
                requested=100,
                retrieved=12,
                api_total=12,
            ),  # not truncated
            QueryRetrieval(
                source="dblp", query_label="q1", requested=100, retrieved=5, api_total=5
            ),  # not truncated
            QueryRetrieval(
                source="gscholar",
                query_label="q1",
                requested=100,
                retrieved=10,
                api_total=None,
            ),  # unknown total
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


def test_snowball_ledger_defaults():
    from surveyer.models import SnowballLedger

    sl = SnowballLedger()
    assert sl.seeds == 0
    assert sl.included == 0
    assert sl.excluded_keyword_reasons == {}
    assert sl.retrieval == []


def test_total_included_adds_snowball():
    from surveyer.models import Ledger, SnowballLedger

    led = Ledger(included=3, previously_included=2)
    assert led.total_included() == 5
    led.snowball = SnowballLedger(included=4)
    assert led.total_included() == 9


def test_record_has_screening_fields():
    r = Record(title="x")
    assert r.screening_status is None
    assert r.concept_verdicts == {}
    r.screening_status = "borderline"
    r.concept_verdicts = {"graph": "yes"}
    assert r.concept_verdicts["graph"] == "yes"


def test_ledger_has_borderline_count():
    assert Ledger().borderline == 0


def test_record_keyword_note_defaults_none():
    assert Record(title="x").keyword_note is None


def test_seed_ledger_defaults_and_attaches():
    from surveyer.models import Ledger, SeedLedger

    sl = SeedLedger(imported=7, resolved=5, unresolved=2, pinned=5, collapsed_fetched=1)
    assert (sl.imported, sl.resolved, sl.unresolved, sl.pinned, sl.collapsed_fetched) == (
        7,
        5,
        2,
        5,
        1,
    )
    assert SeedLedger().imported == 0
    led = Ledger(seed=sl)
    assert led.seed is sl
    assert Ledger().seed is None
