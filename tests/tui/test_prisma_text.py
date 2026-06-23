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
