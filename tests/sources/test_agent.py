from __future__ import annotations

import pytest

from surveyer.sources.agent import AgentSource


def test_agent_not_implemented():
    src = AgentSource()
    with pytest.raises(NotImplementedError, match="alpha"):
        src.search("anything", max_results=10)
