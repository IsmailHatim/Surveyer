"""TODO(ismailhatim): Agent web search adapter."""

from __future__ import annotations

from surveyer.models import SearchResult


class AgentSource:
    """Agent source adapter."""

    name = "agent"

    def search(self, terms: str, *, max_results: int) -> SearchResult:
        """Raise NotImplementedError - agent search is not yet implemented."""
        raise NotImplementedError(
            "Agent-based search is alpha and not implemented in v1. "
            "Planned: leads-only proposals verified against a trusted index."
        )
