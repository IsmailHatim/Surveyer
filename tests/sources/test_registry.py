from __future__ import annotations

import threading
import time

import pytest
import structlog

from surveyer.cancel import PipelineCancelled
from surveyer.config import Query, SearchConfig
from surveyer.models import Record, SearchResult
from surveyer.sources import build_registry, fetch_all


def test_build_registry_propagates_refresh(tmp_path):
    search = SearchConfig(
        sources=["dblp", "openalex", "semantic_scholar"],
        queries=[Query(label="A", terms="x")],
        max_results_per_query=10,
    )
    registry = build_registry(search, tmp_path, refresh=True)
    assert all(src.client.refresh for src in registry.values())


def test_build_registry_defaults_refresh_off(tmp_path):
    search = SearchConfig(
        sources=["dblp"],
        queries=[Query(label="A", terms="x")],
        max_results_per_query=10,
    )
    registry = build_registry(search, tmp_path)
    assert registry["dblp"].client.refresh is False


class FakeSource:
    name = "fake"

    def __init__(self, titles):
        self.titles = titles

    def search(self, terms, *, max_results):
        return SearchResult(records=[Record(title=t) for t in self.titles])


def test_fetch_all_isolates_source_failures():
    class BoomSource:
        name = "boom"

        def search(self, terms, *, max_results) -> SearchResult:
            raise RuntimeError("api down")

    search = SearchConfig(
        sources=["boom", "fake"],
        queries=[Query(label="A", terms="x")],
        max_results_per_query=10,
    )
    registry = {"boom": BoomSource(), "fake": FakeSource(["P1"])}
    result = fetch_all(search, registry)
    assert [r.title for r in result.records] == ["P1"]
    assert result.counts["boom"] == 0
    assert result.counts["fake"] == 1
    assert result.failed == ["boom"]
    # A failed query produces no retrieval row.
    assert [qr.source for qr in result.retrieval] == ["fake"]
    assert result.retrieval[0].retrieved == 1
    assert result.retrieval[0].requested == 10


def test_fetch_all_tags_provenance():
    search = SearchConfig(
        sources=["fake"],
        queries=[Query(label="A", terms="x"), Query(label="B", terms="y")],
        max_results_per_query=10,
    )
    registry = {"fake": FakeSource(["P1"])}
    result = fetch_all(search, registry)
    # one source x two queries x one title = 2 records
    assert len(result.records) == 2
    assert all(r.sources == ["fake"] for r in result.records)
    assert {lbl for r in result.records for lbl in r.query_labels} == {"A", "B"}
    assert result.counts["fake"] == 2
    assert result.failed == []
    assert [qr.query_label for qr in result.retrieval] == ["A", "B"]


def test_fetch_all_uses_resolved_queries():
    seen: list[str] = []

    class RecordingSource:
        name = "rec"

        def search(self, terms, *, max_results):
            seen.append(terms)
            return SearchResult(records=[])

    search = SearchConfig(
        sources=["rec"],
        queries=[Query(label="manual", terms="hand written")],
        concepts={"a": ["x", "y"]},
        max_results_per_query=10,
    )
    fetch_all(search, {"rec": RecordingSource()})
    assert seen == ["hand written", "x", "y"]


def test_fetch_all_warns_once_across_sources():
    big = [f"s{i}" for i in range(11)]  # > 100

    class EmptySource:
        def search(self, terms, *, max_results):
            return SearchResult(records=[])

    search = SearchConfig(
        sources=["a", "b"],
        queries=[],
        concepts={"a": big, "b": big},
        max_results_per_query=10,
    )
    registry = {"a": EmptySource(), "b": EmptySource()}
    with structlog.testing.capture_logs() as logs:
        fetch_all(search, registry)
    warnings = [e for e in logs if e["event"] == "concepts.explosion"]
    assert len(warnings) == 1


def test_fetch_all_cancel_before_search():
    class BoomSource:
        name = "boom"

        def search(self, terms, *, max_results) -> SearchResult:
            raise AssertionError("search must not run when already cancelled")

    search = SearchConfig(sources=["boom"], queries=[Query(label="A", terms="x")])
    event = threading.Event()
    event.set()
    with pytest.raises(PipelineCancelled):
        fetch_all(search, {"boom": BoomSource()}, cancel=event)


def test_fetch_all_cancel_mid_loop():
    event = threading.Event()

    class CancelAfterFirst:
        name = "src"

        def __init__(self):
            self.calls = 0

        def search(self, terms, *, max_results):
            self.calls += 1
            event.set()  # trip cancel after the first query returns
            return SearchResult(records=[Record(title="hit")])

    search = SearchConfig(
        sources=["src"],
        queries=[Query(label="A", terms="x"), Query(label="B", terms="y")],
    )
    source = CancelAfterFirst()
    with pytest.raises(PipelineCancelled):
        fetch_all(search, {"src": source}, cancel=event)
    # First query ran; the check at the top of the 2nd iteration raised.
    assert source.calls == 1


def test_build_registry_includes_pubmed(tmp_path):
    from surveyer.sources.pubmed import PubMedSource

    search = SearchConfig(
        sources=["pubmed"],
        queries=[Query(label="A", terms="x")],
        year_min=2010,
        year_max=2020,
        max_results_per_query=10,
    )
    registry = build_registry(search, tmp_path)
    assert isinstance(registry["pubmed"], PubMedSource)
    assert registry["pubmed"].year_min == 2010
    assert registry["pubmed"].year_max == 2020


def test_fetch_all_preserves_registry_order_under_concurrency():
    class SlowSource:
        def __init__(self, delay, title):
            self.delay = delay
            self.title = title

        def search(self, terms, *, max_results):
            time.sleep(self.delay)
            return SearchResult(records=[Record(title=self.title)])

    search = SearchConfig(
        sources=["slow", "fast"],
        queries=[Query(label="A", terms="x")],
        max_results_per_query=10,
    )
    # "slow" finishes last but must still appear first (registry order).
    registry = {
        "slow": SlowSource(0.05, "SLOW"),
        "fast": SlowSource(0.0, "FAST"),
    }
    result = fetch_all(search, registry)
    assert [r.title for r in result.records] == ["SLOW", "FAST"]
    assert result.counts == {"slow": 1, "fast": 1}
    assert result.failed == []
    assert [qr.source for qr in result.retrieval] == ["slow", "fast"]


def test_fetch_all_records_api_total_per_query():
    class TotalSource:
        name = "t"

        def search(self, terms, *, max_results):
            return SearchResult(records=[Record(title="P")], api_total=999)

    search = SearchConfig(
        sources=["t"],
        queries=[Query(label="A", terms="x")],
        max_results_per_query=25,
    )
    result = fetch_all(search, {"t": TotalSource()})
    [qr] = result.retrieval
    assert (qr.requested, qr.retrieved, qr.api_total) == (25, 1, 999)
