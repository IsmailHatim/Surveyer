from __future__ import annotations

from surveyer.dedup import deduplicate, normalize_title
from surveyer.models import Record


def test_normalize_title():
    assert normalize_title("Attention Is All You Need!") == "attention is all you need"


def test_dedup_by_doi_merges_provenance():
    a = Record(title="Paper A", doi="10.1/x", sources=["dblp"], query_labels=["A"])
    b = Record(
        title="Paper A v2", doi="10.1/x", sources=["openalex"], query_labels=["B"]
    )
    merged, removed = deduplicate([a, b])
    assert len(merged) == 1
    assert removed == 1
    assert set(merged[0].sources) == {"dblp", "openalex"}
    assert set(merged[0].query_labels) == {"A", "B"}


def test_dedup_by_fuzzy_title_when_no_doi():
    a = Record(title="Deep Learning for Security", sources=["dblp"])
    b = Record(title="Deep learning for security.", sources=["openalex"])
    merged, removed = deduplicate([a, b], title_threshold=90)
    assert len(merged) == 1
    assert removed == 1


def test_dedup_keeps_distinct():
    a = Record(title="Topic A", sources=["dblp"])
    b = Record(title="Completely Different Subject", sources=["openalex"])
    merged, removed = deduplicate([a, b])
    assert len(merged) == 2
    assert removed == 0


def test_dedup_mixed_doi_and_missing_doi():
    a = Record(title="Deep Learning for Security", sources=["dblp"])
    b = Record(title="Deep learning for security.", doi="10.1/x", sources=["openalex"])
    merged, removed = deduplicate([a, b], title_threshold=90)
    assert len(merged) == 1
    assert removed == 1
    assert merged[0].doi == "10.1/x"


def test_dedup_distinct_dois_not_merged_despite_similar_title():
    a = Record(title="Deep Learning for Security", doi="10.1/x")
    b = Record(title="Deep Learning for Security", doi="10.1/y")
    merged, removed = deduplicate([a, b])
    assert len(merged) == 2
    assert removed == 0


def test_dedup_backfills_missing_fields():
    a = Record(title="Paper one", doi="10.1/z", sources=["dblp"])
    b = Record(title="Paper two", doi="10.1/z", abstract="hello", sources=["openalex"])
    merged, removed = deduplicate([a, b])
    assert len(merged) == 1
    assert merged[0].abstract == "hello"


def test_dedup_backfills_dblp_key():
    # First record has the DOI but no DBLP key
    records = [
        Record(title="Same paper", doi="10.1/x"),
        Record(title="Same paper", doi="10.1/x", dblp_key="conf/abc/Foo24"),
    ]
    deduped, removed = deduplicate(records)
    assert removed == 1
    assert deduped[0].dblp_key == "conf/abc/Foo24"
