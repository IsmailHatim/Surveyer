from __future__ import annotations

import threading

import pytest
import structlog

from surveyer.cancel import PipelineCancelled
from surveyer.config import Query, SearchConfig
from surveyer.models import Record
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
        return [Record(title=t) for t in self.titles]


def test_fetch_all_isolates_source_failures():
    class BoomSource:
        name = "boom"

        def search(self, terms, *, max_results):
            raise RuntimeError("api down")

    search = SearchConfig(
        sources=["boom", "fake"],
        queries=[Query(label="A", terms="x")],
        max_results_per_query=10,
    )
    registry = {"boom": BoomSource(), "fake": FakeSource(["P1"])}
    records, counts, failed = fetch_all(search, registry)
    assert [r.title for r in records] == ["P1"]
    assert counts["boom"] == 0
    assert counts["fake"] == 1
    assert failed == ["boom"]


def test_fetch_all_tags_provenance():
    search = SearchConfig(
        sources=["fake"],
        queries=[Query(label="A", terms="x"), Query(label="B", terms="y")],
        max_results_per_query=10,
    )
    registry = {"fake": FakeSource(["P1"])}
    records, counts, failed = fetch_all(search, registry)
    # one source x two queries x one title = 2 records
    assert len(records) == 2
    assert all(r.sources == ["fake"] for r in records)
    assert {lbl for r in records for lbl in r.query_labels} == {"A", "B"}
    assert counts["fake"] == 2
    assert failed == []


def test_fetch_all_uses_resolved_queries():
    seen: list[str] = []

    class RecordingSource:
        name = "rec"

        def search(self, terms, *, max_results):
            seen.append(terms)
            return []

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
            return []

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

        def search(self, terms, *, max_results):
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
            return [Record(title="hit")]

    search = SearchConfig(
        sources=["src"],
        queries=[Query(label="A", terms="x"), Query(label="B", terms="y")],
    )
    source = CancelAfterFirst()
    with pytest.raises(PipelineCancelled):
        fetch_all(search, {"src": source}, cancel=event)
    # First query ran; the check at the top of the 2nd iteration raised.
    assert source.calls == 1
