from __future__ import annotations

import random

from rapidfuzz import fuzz

from surveyer.dedup import (
    _is_weak_doi,
    _merge,
    deduplicate,
    normalize_title,
)
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


def test_dedup_threshold_controls_fuzzy_match():
    # Two near-but-not-identical titles: a strict threshold keeps them apart,
    # a looser one collapses them.
    a = Record(title="Graph neural networks for traffic", sources=["dblp"])
    b = Record(title="Graph neural networks for traffic forecasting", sources=["oa"])
    strict, removed_strict = deduplicate([a, b], title_threshold=95)
    assert len(strict) == 2 and removed_strict == 0
    a2 = Record(title="Graph neural networks for traffic", sources=["dblp"])
    b2 = Record(title="Graph neural networks for traffic forecasting", sources=["oa"])
    loose, removed_loose = deduplicate([a2, b2], title_threshold=70)
    assert len(loose) == 1 and removed_loose == 1


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


def test_dedup_merges_preprint_doi_into_publisher_doi():
    # arXiv preprint and publisher version of the same paper
    a = Record(title="SDR-GNN for incomplete learning", doi="10.48550/arXiv.2411.19822")
    b = Record(
        title="SDR-GNN for incomplete learning", doi="10.1016/j.knosys.2024.112825"
    )
    merged, removed = deduplicate([a, b])
    assert len(merged) == 1
    assert removed == 1
    assert merged[0].doi == "10.1016/j.knosys.2024.112825"


def test_dedup_merges_publisher_doi_then_preprint():
    # Same paper, publisher version first
    a = Record(
        title="GCNet: Graph Completion Network", doi="10.1109/tpami.2023.3234553"
    )
    b = Record(title="GCNet: Graph Completion Network", doi="10.48550/arxiv.2203.02177")
    merged, removed = deduplicate([a, b])
    assert len(merged) == 1
    assert removed == 1
    assert merged[0].doi == "10.1109/tpami.2023.3234553"


def test_dedup_zenodo_doi_is_weak_too():
    a = Record(title="GraphPL: Robust Imputation", doi="10.5281/zenodo.19849992")
    b = Record(title="GraphPL: Robust Imputation", doi="10.1109/icassp.2026.11465108")
    merged, removed = deduplicate([a, b])
    assert len(merged) == 1
    assert merged[0].doi == "10.1109/icassp.2026.11465108"


def test_dedup_two_publisher_dois_still_distinct():
    # Two strong (publisher) DOIs with the same title stay separate records.
    a = Record(title="GSDNet: Revisiting Incompleteness", doi="10.24963/ijcai.2024/688")
    b = Record(title="GSDNet: Revisiting Incompleteness", doi="10.24963/ijcai.2025/688")
    merged, removed = deduplicate([a, b])
    assert len(merged) == 2
    assert removed == 0


def test_dedup_backfills_missing_fields():
    a = Record(title="Paper one", doi="10.1/z", sources=["dblp"])
    b = Record(title="Paper two", doi="10.1/z", abstract="hello", sources=["openalex"])
    merged, removed = deduplicate([a, b])
    assert len(merged) == 1
    assert merged[0].abstract == "hello"


def test_dedup_backfills_authors_and_keywords():
    # The survivor has empty author/keyword lists; the duplicate has them filled.
    a = Record(title="Same paper", doi="10.1/x")
    b = Record(title="Same paper", doi="10.1/x", authors=["Jane Doe"], keywords=["gnn"])
    merged, removed = deduplicate([a, b])
    assert removed == 1
    assert merged[0].authors == ["Jane Doe"]
    assert merged[0].keywords == ["gnn"]


def test_dedup_unions_keywords():
    a = Record(title="Same paper", doi="10.1/x", keywords=["graph"])
    b = Record(title="Same paper", doi="10.1/x", keywords=["neural"])
    merged, _ = deduplicate([a, b])
    assert set(merged[0].keywords) == {"graph", "neural"}


def test_dedup_does_not_merge_empty_titles():
    # token_sort_ratio("", "") == 100, so DOI-less empty titles must not collapse.
    a = Record(title="", sources=["dblp"])
    b = Record(title="   ", sources=["openalex"])
    merged, removed = deduplicate([a, b])
    assert len(merged) == 2
    assert removed == 0


def test_dedup_backfills_dblp_key():
    # First record has the DOI but no DBLP key
    records = [
        Record(title="Same paper", doi="10.1/x"),
        Record(title="Same paper", doi="10.1/x", dblp_key="conf/abc/Foo24"),
    ]
    deduped, removed = deduplicate(records)
    assert removed == 1
    assert deduped[0].dblp_key == "conf/abc/Foo24"


# Equivalence test for the vectorized deduplicate rewrite


def _brute_dedup(records, *, title_threshold=90):
    """Pure-Python replica of the original O(n^2) algorithm (oracle)."""
    kept = []  # list[tuple[Record, str]]
    by_doi = {}
    removed = 0
    for r in records:
        doi = r.doi.lower().strip() if r.doi else None
        if doi and doi in by_doi:
            _merge(by_doi[doi], r)
            removed += 1
            continue
        norm = normalize_title(r.title)
        match = None
        if norm:
            for existing, ex_norm in kept:
                ex_doi = existing.doi.lower().strip() if existing.doi else None
                if (
                    doi
                    and ex_doi
                    and ex_doi != doi
                    and not (_is_weak_doi(doi) or _is_weak_doi(ex_doi))
                ):
                    continue
                if fuzz.token_sort_ratio(norm, ex_norm) >= title_threshold:
                    match = existing
                    break
        if match is not None:
            _merge(match, r)
            removed += 1
            if match.doi:
                by_doi[match.doi.lower().strip()] = match
            if doi:
                by_doi[doi] = match
            continue
        kept.append((r, norm))
        if doi:
            by_doi[doi] = r
    return [rec for rec, _ in kept], removed


def _random_corpus(n, seed):
    rng = random.Random(seed)
    stems = [
        "deep learning for security",
        "graph neural networks",
        "secure aggregation",
        "federated averaging methods",
        "differential privacy survey",
    ]
    recs = []
    for i in range(n):
        if recs and rng.random() < 0.3:
            t = rng.choice(stems)
            if rng.random() < 0.5:
                t = t.title() + "."
        else:
            t = rng.choice(stems) + f" variant {i}"
        if rng.random() < 0.15:
            t = ""  # exercise empty-title path
        doi = None
        roll = rng.random()
        if roll < 0.3:
            doi = f"10.1/x{i % 7}"  # collisions + conflicts
        elif roll < 0.4:
            doi = f"10.48550/arXiv.{i}"  # weak DOI
        recs.append(Record(title=t, doi=doi, sources=[f"s{i % 3}"]))
    return recs


def test_dedup_matches_brute_force_oracle():
    for seed in range(25):
        corpus = _random_corpus(40, seed)
        oracle = _brute_dedup(
            [Record(title=r.title, doi=r.doi, sources=list(r.sources)) for r in corpus],
            title_threshold=90,
        )
        actual = deduplicate(
            [Record(title=r.title, doi=r.doi, sources=list(r.sources)) for r in corpus],
            title_threshold=90,
        )
        assert [r.title for r in actual[0]] == [r.title for r in oracle[0]], seed
        assert actual[1] == oracle[1], seed
