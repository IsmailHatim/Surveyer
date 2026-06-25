from __future__ import annotations

from surveyer.config import Query, SearchConfig
from surveyer.models import Ledger, QueryRetrieval, SourceCount
from surveyer.prisma.model import _build_completeness, build_model


def _ledger() -> Ledger:
    return Ledger(
        identified=[
            SourceCount(source="dblp", count=120),
            SourceCount(source="openalex", count=80),
        ],
        duplicates_removed=40,
        excluded_keyword=60,
        excluded_llm=30,
        included=70,
    )


def _search() -> SearchConfig:
    return SearchConfig(
        sources=["dblp"],
        queries=[Query(label="q1", terms="graph neural network")],
    )


def test_build_model_counts():
    m = build_model(_ledger(), _search(), llm_model="gpt-4o-mini")
    assert m.total_identified == 200
    assert m.after_dedup == 160
    assert m.sources == [("dblp", 120), ("openalex", 80)]
    rows = {r.id: r for r in m.rows}
    assert rows["identified"].count == 200  # total across sources, before dedup
    assert rows["dedup"].count == 160
    assert rows["dedup"].exclusion.count == 40
    assert rows["screened"].count == 160
    assert rows["screened"].exclusion.count == 60
    assert rows["assessed"].count == 100  # 160 - 60 keyword-excluded
    assert rows["assessed"].exclusion.count == 30
    assert rows["included"].count == 70


def test_build_model_identified_is_first_row():
    m = build_model(_ledger(), _search())
    assert m.rows[0].id == "identified"
    assert m.rows[0].count == m.total_identified


def test_build_model_keyword_breakdown():
    ledger = _ledger()
    ledger.excluded_keyword_reasons = {"no graph": 40, "no missingness": 20}
    m = build_model(ledger, _search())
    screened = next(r for r in m.rows if r.id == "screened")
    assert screened.exclusion.breakdown == [("no graph", 40), ("no missingness", 20)]


def test_build_model_omits_llm_when_no_model():
    m = build_model(_ledger(), _search(), llm_model=None)
    assert all(r.id != "assessed" for r in m.rows)
    ids = [r.id for r in m.rows]
    assert ids.index("screened") == ids.index("included") - 1


def test_build_model_manual_box_optional():
    with_manual = build_model(_ledger(), _search(), show_manual_screening=True)
    without = build_model(_ledger(), _search())
    assert any(r.id == "manual" and r.dashed for r in with_manual.rows)
    assert all(r.id != "manual" for r in without.rows)


def test_build_model_query_panel_from_concepts():
    s = SearchConfig(
        sources=["dblp"],
        queries=[],
        concepts={"method": ["gnn", "graph neural network"]},
    )
    m = build_model(_ledger(), s)
    assert m.query_panel is not None
    assert "method" in m.query_panel
    assert "gnn" in m.query_panel


def test_build_model_query_panel_from_queries():
    m = build_model(_ledger(), _search())
    assert "q1" in m.query_panel
    assert "graph neural network" in m.query_panel


def _extend_ledger():
    return Ledger(
        identified=[SourceCount(source="dblp", count=10)],
        duplicates_removed=2,
        already_screened=3,
        excluded_keyword=1,
        included=4,
        previously_included=5,
    )


def test_build_model_extend_adjusts_counts():
    model = build_model(_extend_ledger(), SearchConfig(sources=["dblp"], queries=[]))
    rows = {r.id: r for r in model.rows}
    # 10 identified - 2 duplicates - 3 already screened = 5 enter screening
    assert rows["dedup"].count == 5
    assert rows["screened"].count == 5
    assert model.after_dedup == 5
    excl = rows["dedup"].exclusion
    assert excl.count == 5  # 2 + 3
    assert ("already screened in previous version", 3) in excl.breakdown


def test_build_model_extend_adds_total_box():
    model = build_model(_extend_ledger(), SearchConfig(sources=["dblp"], queries=[]))
    rows = {r.id: r for r in model.rows}
    assert rows["included"].title == "New studies included"
    assert rows["included"].count == 4
    assert rows["total"].count == 9
    assert model.previous_included == 5


def test_build_model_without_extend_is_unchanged():
    ledger = Ledger(
        identified=[SourceCount(source="dblp", count=10)],
        duplicates_removed=2,
        included=4,
    )
    model = build_model(ledger, SearchConfig(sources=["dblp"], queries=[]))
    rows = {r.id: r for r in model.rows}
    assert "total" not in rows
    assert rows["included"].title == "Studies included"
    assert rows["dedup"].exclusion.label == "Duplicates removed"
    assert model.previous_included is None


def _completeness_ledger() -> Ledger:
    return Ledger(
        identified=[
            SourceCount(source="openalex", count=280),
            SourceCount(source="dblp", count=5),
        ],
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
                retrieved=180,
                api_total=4100,
            ),  # truncated
            QueryRetrieval(
                source="dblp", query_label="q1", requested=100, retrieved=5, api_total=5
            ),  # complete
        ],
        included=1,
    )


def test_build_completeness_aggregation():
    by_src = {c.source: c for c in _build_completeness(_completeness_ledger())}
    oa = by_src["openalex"]
    assert oa.requested == 100  # per-query cap, shown as-is
    assert oa.retrieved == 280  # summed across queries
    assert oa.api_total == 9100  # summed
    assert oa.truncated is True
    assert oa.partial_total is False
    db = by_src["dblp"]
    assert db.retrieved == 5
    assert db.api_total == 5
    assert db.truncated is False


def test_build_completeness_partial_total():
    led = Ledger(
        retrieval=[
            QueryRetrieval(
                source="s2", query_label="q1", requested=50, retrieved=50, api_total=900
            ),
            QueryRetrieval(
                source="s2",
                query_label="q2",
                requested=50,
                retrieved=10,
                api_total=None,
            ),  # unknown
        ]
    )
    [c] = _build_completeness(led)
    assert c.api_total == 900
    assert c.partial_total is True
    assert c.truncated is True


def test_build_completeness_all_unknown_total():
    led = Ledger(
        retrieval=[
            QueryRetrieval(
                source="gscholar",
                query_label="q1",
                requested=20,
                retrieved=20,
                api_total=None,
            ),
        ]
    )
    [c] = _build_completeness(led)
    assert c.api_total is None
    assert c.partial_total is False
    assert c.truncated is False


def test_build_completeness_empty_when_no_retrieval():
    assert _build_completeness(_ledger()) == []  # _ledger() has no retrieval rows


def test_build_model_completeness_off_by_default():
    # Hardcoded off: build_model omits the table even with retrieval present.
    m = build_model(_completeness_ledger(), _search())
    assert m.source_completeness == []


def test_build_model_completeness_on_when_toggled(monkeypatch):
    monkeypatch.setattr("surveyer.prisma.model.SHOW_COMPLETENESS_TABLE", True)
    m = build_model(_completeness_ledger(), _search())
    assert [c.source for c in m.source_completeness] == ["openalex", "dblp"]
