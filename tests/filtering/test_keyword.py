from __future__ import annotations

from surveyer.config import KeywordConfig
from surveyer.filtering.keyword import apply_keyword_filter
from surveyer.models import Record


def test_include_required():
    cfg = KeywordConfig(include=["security"], exclude=[])
    recs = [
        Record(title="A security study", abstract="about defenses"),
        Record(title="Unrelated topic", abstract="cooking recipes"),
    ]
    kept, excluded, reasons = apply_keyword_filter(recs, cfg)
    assert [r.title for r in kept] == ["A security study"]
    assert excluded == 1
    assert reasons == {"no included keyword": 1}


def test_exclude_wins():
    cfg = KeywordConfig(include=["security"], exclude=["survey"])
    recs = [Record(title="A security survey", abstract="")]
    kept, excluded, reasons = apply_keyword_filter(recs, cfg)
    assert kept == []
    assert excluded == 1
    assert reasons == {"contains 'survey'": 1}


def test_no_filters_keeps_all():
    cfg = KeywordConfig(include=[], exclude=[])
    recs = [Record(title="anything")]
    kept, excluded, reasons = apply_keyword_filter(recs, cfg)
    assert len(kept) == 1
    assert excluded == 0
    assert reasons == {}


def test_concepts_require_all_blocks():
    concepts = {
        "graph": ["graph neural network", "gnn"],
        "missingness": ["missing", "incomplete"],
    }
    cfg = KeywordConfig(include=[], exclude=[])
    recs = [
        Record(title="A GNN for missing data", abstract=""),  # both blocks
        Record(title="A graph neural network survey", abstract=""),  # only graph
        Record(title="Handling missing values", abstract=""),  # only missingness
    ]
    kept, excluded, reasons = apply_keyword_filter(recs, cfg, concepts=concepts)
    assert [r.title for r in kept] == ["A GNN for missing data"]
    assert excluded == 2
    assert reasons == {"no missingness": 1, "no graph": 1}


def test_concepts_exclude_still_wins():
    concepts = {"graph": ["gnn"], "missingness": ["missing"]}
    cfg = KeywordConfig(include=[], exclude=["survey"])
    recs = [Record(title="A GNN survey on missing data", abstract="")]
    kept, excluded, reasons = apply_keyword_filter(recs, cfg, concepts=concepts)
    assert kept == []
    assert excluded == 1
    assert reasons == {"contains 'survey'": 1}


def test_concepts_ignore_include_list():
    concepts = {"graph": ["gnn"], "missingness": ["missing"]}
    cfg = KeywordConfig(include=["nonexistent-term"], exclude=[])
    recs = [Record(title="GNN with missing modalities", abstract="")]
    kept, excluded, reasons = apply_keyword_filter(recs, cfg, concepts=concepts)
    assert [r.title for r in kept] == ["GNN with missing modalities"]
    assert excluded == 0
    assert reasons == {}


def test_no_concepts_uses_include_path():
    cfg = KeywordConfig(include=["security"], exclude=[])
    recs = [
        Record(title="A security study", abstract=""),
        Record(title="Unrelated", abstract=""),
    ]
    kept, excluded, reasons = apply_keyword_filter(recs, cfg, concepts=None)
    assert [r.title for r in kept] == ["A security study"]
    assert excluded == 1
    assert reasons == {"no included keyword": 1}
