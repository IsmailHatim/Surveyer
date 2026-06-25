"""Unit tests for DashboardScreen._prisma_text truncation warning."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from surveyer.models import Ledger, QueryRetrieval  # noqa: E402
from surveyer.tui.dashboard import DashboardScreen  # noqa: E402


def test_prisma_text_flags_truncation():
    """A truncated source appends a capped-below-API-total warning line."""
    led = Ledger(
        included=1,
        retrieval=[
            QueryRetrieval(
                source="openalex",
                query_label="q1",
                requested=100,
                retrieved=100,
                api_total=5000,
            ),
        ],
    )
    text = DashboardScreen._prisma_text(led, fetch_only=False, output_dir="out")
    assert "capped below API total" in text
    assert "openalex" in text


def test_prisma_text_no_flag_when_complete():
    """No warning when every source retrieved all available results."""
    led = Ledger(
        included=1,
        retrieval=[
            QueryRetrieval(
                source="dblp",
                query_label="q1",
                requested=100,
                retrieved=7,
                api_total=7,
            ),
        ],
    )
    text = DashboardScreen._prisma_text(led, fetch_only=False, output_dir="out")
    assert "capped below API total" not in text


def test_prisma_text_includes_seed_rows():
    """When seed ledger is present, a 'seeds pinned' row is included."""
    from surveyer.models import SeedLedger

    led = Ledger(included=3, seed=SeedLedger(imported=2, resolved=2, pinned=2))
    text = DashboardScreen._prisma_text(led, fetch_only=False, output_dir="runs/x")
    assert "seeds pinned" in text
    assert "2" in text
