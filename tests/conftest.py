"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Directory holding saved sample API responses."""
    FIXTURES.mkdir(exist_ok=True)
    return FIXTURES
