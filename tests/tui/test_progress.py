"""Tests for structlog -> UI forwarding."""

import structlog

from surveyer.tui.progress import forward_logs


def test_forward_captures_events_as_lines():
    lines: list[str] = []
    with forward_logs(lines.append):
        structlog.get_logger().info("llm.scoring", done=3, total=10)
    assert lines == ["llm.scoring done=3 total=10"]


def test_config_restored_after_context():
    before = structlog.get_config()["processors"]
    with forward_logs(lambda _line: None):
        pass
    assert structlog.get_config()["processors"] == before


def test_fetch_all_emits_source_done_event():
    from surveyer.config import Query, SearchConfig
    from surveyer.models import Record, SearchResult
    from surveyer.sources import fetch_all

    class FakeSource:
        def search(self, terms, max_results):
            return SearchResult(records=[Record(title="t", year=2020)])

    search = SearchConfig(sources=["dblp"], queries=[Query(label="q", terms="x")])
    lines: list[str] = []
    with forward_logs(lines.append):
        fetch_all(search, {"dblp": FakeSource()})
    assert "fetch.source_done source=dblp count=1" in lines
