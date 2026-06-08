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
