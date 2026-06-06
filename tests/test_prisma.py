from __future__ import annotations

from surveyer.models import Ledger, SourceCount
from surveyer.prisma import render_prisma


def test_render_prisma_creates_file(tmp_path):
    ledger = Ledger(
        identified=[SourceCount(source="dblp", count=120), SourceCount(source="openalex", count=80)],
        duplicates_removed=40,
        excluded_keyword=60,
        excluded_llm=30,
        included=70,
    )
    out = tmp_path / "prisma.png"
    render_prisma(ledger, out)
    assert out.exists()
    assert out.stat().st_size > 0
