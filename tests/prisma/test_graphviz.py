from __future__ import annotations

from surveyer.config import Query, SearchConfig
from surveyer.models import Ledger, QueryRetrieval, SourceCount
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


def test_graphviz_includes_completeness_table(monkeypatch):
    monkeypatch.setattr("surveyer.prisma.model.SHOW_COMPLETENESS_TABLE", True)
    led = Ledger(
        identified=[SourceCount(source="openalex", count=280)],
        retrieval=[
            QueryRetrieval(
                source="openalex",
                query_label="q1",
                requested=100,
                retrieved=280,
                api_total=9100,
            ),
        ],
        included=1,
    )
    m = build_model(
        led,
        SearchConfig(sources=["openalex"], queries=[Query(label="q1", terms="x")]),
    )
    src = to_graphviz(m).source
    assert "completeness" in src
    assert "openalex" in src
    assert "9100" in src


def test_graphviz_omits_completeness_when_empty():
    ledger = Ledger(identified=[SourceCount(source="dblp", count=10)], included=4)
    model = build_model(ledger, SearchConfig(sources=["dblp"], queries=[]))
    assert "completeness" not in to_graphviz(model).source


def _snowball_model():
    from surveyer.models import SnowballLedger

    led = Ledger(
        identified=[SourceCount(source="openalex", count=10)],
        duplicates_removed=2,
        excluded_keyword=1,
        excluded_llm=1,
        included=3,
        snowball=SnowballLedger(
            identified=8,
            backward=6,
            forward=2,
            duplicates_removed=2,
            excluded_keyword=1,
            excluded_llm=1,
            included=2,
        ),
    )
    return build_model(led, SearchConfig(sources=["openalex"], queries=[]),
                       llm_model="gpt-4o-mini")


def test_graphviz_builds_snowball_arm():
    src = to_graphviz(_snowball_model()).source
    assert "snow_identified" in src
    assert "Records identified via citation searching" in src
    assert "snowspine" in src
