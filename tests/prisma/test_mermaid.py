from __future__ import annotations

from surveyer.config import Query, SearchConfig
from surveyer.models import Ledger, QueryRetrieval, SourceCount
from surveyer.prisma.model import build_model
from surveyer.prisma.mermaid_render import to_mermaid


def _model(**kw):
    ledger = Ledger(
        identified=[
            SourceCount(source="dblp", count=120),
            SourceCount(source="openalex", count=80),
        ],
        duplicates_removed=40,
        excluded_keyword=60,
        excluded_llm=30,
        included=70,
    )
    search = SearchConfig(sources=["dblp"], queries=[Query(label="q1", terms="graph")])
    return build_model(ledger, search, **kw)


def test_to_mermaid_header_and_nodes():
    out = to_mermaid(_model(llm_model="gpt-4o-mini"))
    assert out.startswith("flowchart TD")
    assert "dblp" in out
    assert "Records screened" in out
    assert "n = 160" in out
    assert "Records assessed by gpt-4o-mini" in out
    assert "Studies included" in out
    assert "Excluded by keyword filter" in out


def test_to_mermaid_includes_query_panel():
    assert "Search query" in to_mermaid(_model())
    assert "q1" in to_mermaid(_model())


def test_to_mermaid_omits_llm_box():
    out = to_mermaid(_model(llm_model=None))
    assert "Records assessed by" not in out


def test_mermaid_renders_previous_version_box():
    ledger = Ledger(
        identified=[SourceCount(source="dblp", count=10)],
        duplicates_removed=2,
        already_screened=3,
        included=4,
        previously_included=5,
    )
    model = build_model(ledger, SearchConfig(sources=["dblp"], queries=[]))
    text = to_mermaid(model)
    assert "Studies included in previous version of review" in text
    assert "previous --> total" in text


def test_mermaid_no_previous_box_for_normal_runs():
    ledger = Ledger(identified=[SourceCount(source="dblp", count=10)], included=4)
    model = build_model(ledger, SearchConfig(sources=["dblp"], queries=[]))
    assert "previous" not in to_mermaid(model)


def _completeness_model():
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
    return build_model(
        led, SearchConfig(sources=["openalex"], queries=[Query(label="q1", terms="x")])
    )


def test_mermaid_includes_completeness_table(monkeypatch):
    monkeypatch.setattr("surveyer.prisma.model.SHOW_COMPLETENESS_TABLE", True)
    out = to_mermaid(_completeness_model())
    assert "completeness" in out
    assert "openalex" in out
    assert "9100" in out
    assert "⚠" in out  # truncated marker


def test_mermaid_omits_completeness_when_empty():
    m = build_model(
        Ledger(included=1),
        SearchConfig(sources=["x"], queries=[Query(label="q", terms="t")]),
    )
    assert "completeness" not in to_mermaid(m)
