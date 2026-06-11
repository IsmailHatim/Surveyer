from __future__ import annotations

from surveyer.config import Query, SearchConfig
from surveyer.models import Ledger, SourceCount
from surveyer.prisma.graphviz_render import to_graphviz
from surveyer.prisma.model import build_model


def _model(**kw):
    ledger = Ledger(
        identified=[SourceCount(source="dblp", count=120)],
        duplicates_removed=40,
        excluded_keyword=60,
        excluded_llm=30,
        included=70,
    )
    search = SearchConfig(sources=["dblp"], queries=[Query(label="q1", terms="graph")])
    return build_model(ledger, search, **kw)


def test_to_graphviz_source_contains_labels():
    src = to_graphviz(_model(llm_model="gpt-4o-mini")).source
    assert "Records screened" in src
    assert "Studies included" in src
    assert "Excluded by keyword filter" in src


def test_to_graphviz_has_swimlane_labels():
    src = to_graphviz(_model()).source
    assert "Identification" in src
    assert "Screening" in src
    assert "Included" in src


def test_to_graphviz_query_panel_present():
    assert "Search query" in to_graphviz(_model()).source


def test_graphviz_renders_previous_version_box():
    ledger = Ledger(
        identified=[SourceCount(source="dblp", count=10)],
        duplicates_removed=2,
        already_screened=3,
        included=4,
        previously_included=5,
    )
    model = build_model(ledger, SearchConfig(sources=["dblp"], queries=[]))
    src = to_graphviz(model).source
    assert "previous" in src
    assert "previous -> total" in src


def test_graphviz_no_previous_box_for_normal_runs():
    ledger = Ledger(identified=[SourceCount(source="dblp", count=10)], included=4)
    model = build_model(ledger, SearchConfig(sources=["dblp"], queries=[]))
    assert "previous ->" not in to_graphviz(model).source
