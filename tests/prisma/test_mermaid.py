from __future__ import annotations

from surveyer.config import Query, SearchConfig
from surveyer.models import Ledger, SourceCount
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
