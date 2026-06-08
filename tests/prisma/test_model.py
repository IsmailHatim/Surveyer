from __future__ import annotations

from surveyer.config import Query, SearchConfig
from surveyer.models import Ledger, SourceCount
from surveyer.prisma.model import build_model


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
