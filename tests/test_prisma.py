from __future__ import annotations

import shutil

import pytest

from surveyer.config import Query, SearchConfig
from surveyer.models import Ledger, SourceCount
from surveyer.prisma import render_prisma


def _ledger() -> Ledger:
    return Ledger(
        identified=[SourceCount(source="dblp", count=120)],
        duplicates_removed=40,
        excluded_keyword=60,
        excluded_llm=30,
        included=70,
    )


def _search() -> SearchConfig:
    return SearchConfig(sources=["dblp"], queries=[Query(label="q1", terms="graph")])


def test_render_prisma_always_writes_mermaid(tmp_path):
    render_prisma(_ledger(), _search(), tmp_path, llm_model="gpt-4o-mini")
    mmd = tmp_path / "prisma.mmd"
    assert mmd.exists()
    assert mmd.stat().st_size > 0
    assert mmd.read_text().startswith("flowchart TD")


@pytest.mark.skipif(
    shutil.which("dot") is None, reason="graphviz dot binary not installed"
)
def test_render_prisma_writes_svg_when_dot_available(tmp_path):
    render_prisma(_ledger(), _search(), tmp_path)
    assert (tmp_path / "prisma.svg").exists()
    assert (tmp_path / "prisma.svg").stat().st_size > 0


def test_render_prisma_degrades_without_dot(tmp_path, monkeypatch):
    import graphviz

    def _raise(*args, **kwargs):
        raise graphviz.ExecutableNotFound(["dot"])

    monkeypatch.setattr(graphviz.Digraph, "render", _raise)
    render_prisma(_ledger(), _search(), tmp_path)
    assert (tmp_path / "prisma.mmd").exists()
    assert (tmp_path / "prisma.dot").exists()


def test_build_model_adds_snowball_arm():
    from surveyer.config import SearchConfig
    from surveyer.models import Ledger, SnowballLedger, SourceCount
    from surveyer.prisma.model import build_model

    led = Ledger(
        identified=[SourceCount(source="openalex", count=10)],
        duplicates_removed=2,
        excluded_keyword=1,
        excluded_llm=1,
        included=3,
        snowball=SnowballLedger(
            seeds=3,
            seeds_resolved=3,
            identified=8,
            backward=6,
            forward=2,
            duplicates_removed=2,
            excluded_keyword=1,
            excluded_keyword_reasons={"no graph": 1},
            excluded_llm=1,
            included=2,
        ),
    )
    search = SearchConfig(sources=["openalex"], queries=[])
    model = build_model(led, search, llm_model="gpt-4o-mini")

    snow_ids = [r.id for r in model.snowball_rows]
    assert snow_ids == [
        "snow_identified",
        "snow_dedup",
        "snow_screened",
        "snow_assessed",
        "snow_included",
    ]
    identified = next(r for r in model.snowball_rows if r.id == "snow_identified")
    assert identified.title == "Records identified via citation searching"
    assert identified.count == 8
    included = next(r for r in model.snowball_rows if r.id == "snow_included")
    assert included.count == 2
    # main flow converges on a shared total
    main_ids = [r.id for r in model.rows]
    assert "total" in main_ids
    total = next(r for r in model.rows if r.id == "total")
    assert total.count == 5  # 3 main + 2 snowball


def test_build_model_no_snowball_arm_when_absent():
    from surveyer.config import SearchConfig
    from surveyer.models import Ledger, SourceCount
    from surveyer.prisma.model import build_model

    led = Ledger(identified=[SourceCount(source="openalex", count=4)], included=2)
    model = build_model(led, SearchConfig(sources=["openalex"], queries=[]))
    assert model.snowball_rows == []
    assert [r.id for r in model.rows][-1] == "included"
