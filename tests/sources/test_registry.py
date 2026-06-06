from __future__ import annotations

from surveyer.config import SearchConfig, Query
from surveyer.models import Record
from surveyer.sources import fetch_all


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
