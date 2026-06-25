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
    kept, excluded, reasons = apply_keyword_filter(
        recs, cfg, concepts=concepts, concept_mode="all"
    )
    assert [r.title for r in kept] == ["A GNN for missing data"]
    assert excluded == 2
    assert reasons == {"matched 1/2 concepts (need ≥2)": 2}


def test_concepts_exclude_still_wins():
    concepts = {"graph": ["gnn"], "missingness": ["missing"]}
    cfg = KeywordConfig(include=[], exclude=["survey"])
    recs = [Record(title="A GNN survey on missing data", abstract="")]
    kept, excluded, reasons = apply_keyword_filter(
        recs, cfg, concepts=concepts, concept_mode="all"
    )
    assert kept == []
    assert excluded == 1
    assert reasons == {"contains 'survey'": 1}


def test_concepts_ignore_include_list():
    concepts = {"graph": ["gnn"], "missingness": ["missing"]}
    cfg = KeywordConfig(include=["nonexistent-term"], exclude=[])
    recs = [Record(title="GNN with missing modalities", abstract="")]
    kept, excluded, reasons = apply_keyword_filter(
        recs, cfg, concepts=concepts, concept_mode="all"
    )
    assert [r.title for r in kept] == ["GNN with missing modalities"]
    assert excluded == 0
    assert reasons == {}


def test_excluded_records_carry_exclusion_reason():
    concepts = {
        "graph": ["graph", "gnn"],
        "missingness": ["missing", "incomplete"],
    }
    cfg = KeywordConfig(include=[], exclude=["survey"])
    kept_rec = Record(title="A GNN for missing data", abstract="")
    no_graph = Record(
        title="Multimodal Patient Representation Learning with Missing Modalities",
        abstract=None,
    )
    has_excluded_term = Record(title="A GNN survey on missing data", abstract="")
    recs = [kept_rec, no_graph, has_excluded_term]
    kept, excluded, reasons = apply_keyword_filter(
        recs, cfg, concepts=concepts, concept_mode="all"
    )
    assert kept == [kept_rec]
    assert kept_rec.exclusion_reason is None
    assert no_graph.exclusion_reason == "matched 1/2 concepts (need ≥2)"
    assert has_excluded_term.exclusion_reason == "contains 'survey'"


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


def test_any_mode_keeps_single_concept_match():
    concepts = {"graph": ["graph"], "multimodal": ["multimodal"], "missing": ["missing"]}
    recs = [Record(title="a graph paper"), Record(title="unrelated work")]
    kept, excluded, reasons = apply_keyword_filter(
        recs, KeywordConfig(), concepts=concepts, concept_mode="any"
    )
    assert [r.title for r in kept] == ["a graph paper"]
    assert excluded == 1


def test_all_mode_matches_legacy_and_gate():
    concepts = {"graph": ["graph"], "multimodal": ["multimodal"]}
    recs = [Record(title="graph multimodal study"), Record(title="graph only")]
    kept, excluded, _ = apply_keyword_filter(
        recs, KeywordConfig(), concepts=concepts, concept_mode="all"
    )
    assert [r.title for r in kept] == ["graph multimodal study"]
    assert recs[1].exclusion_reason == "matched 1/2 concepts (need ≥2)"


def test_min_n_mode():
    concepts = {"a": ["a"], "b": ["b"], "c": ["c"]}
    recs = [Record(title="a b text"), Record(title="a text")]
    kept, _, _ = apply_keyword_filter(
        recs, KeywordConfig(), concepts=concepts, concept_mode="min:2"
    )
    assert [r.title for r in kept] == ["a b text"]


def test_exclude_still_wins_over_concept_match():
    concepts = {"graph": ["graph"]}
    recs = [Record(title="graph survey")]
    kept, excluded, _ = apply_keyword_filter(
        recs, KeywordConfig(exclude=["survey"]), concepts=concepts, concept_mode="any"
    )
    assert excluded == 1
    assert recs[0].exclusion_reason == "contains 'survey'"


def test_soft_gate_keeps_concept_near_miss():
    concepts = {
        "graph": ["graph neural network", "gnn"],
        "multimodal": ["multimodal", "multi-modal"],
        "missing": ["missing", "incomplete", "imputation"],
    }
    cfg = KeywordConfig(include=[], exclude=[])
    rec = Record(title="A multimodal graph neural network study", abstract="")
    kept, excluded, reasons = apply_keyword_filter(
        [rec], cfg, concepts=concepts, concept_mode="all", gate="soft"
    )
    assert [r.title for r in kept] == [rec.title]
    assert excluded == 0
    assert reasons == {}
    assert kept[0].keyword_note == "matched 2/3 concepts lexically"


def test_soft_gate_keeps_zero_concept_record():
    concepts = {"graph": ["gnn"], "multimodal": ["multimodal"]}
    cfg = KeywordConfig(include=[], exclude=[])
    rec = Record(title="Unrelated cooking recipes", abstract="")
    kept, excluded, reasons = apply_keyword_filter(
        [rec], cfg, concepts=concepts, concept_mode="all", gate="soft"
    )
    assert len(kept) == 1
    assert excluded == 0
    assert kept[0].keyword_note == "matched 0/2 concepts lexically"


def test_soft_gate_exclude_still_drops():
    concepts = {"graph": ["gnn"]}
    cfg = KeywordConfig(include=[], exclude=["survey"])
    rec = Record(title="A gnn survey", abstract="")
    kept, excluded, reasons = apply_keyword_filter(
        [rec], cfg, concepts=concepts, concept_mode="all", gate="soft"
    )
    assert kept == []
    assert excluded == 1
    assert reasons == {"contains 'survey'": 1}


def test_soft_gate_full_match_no_note():
    concepts = {"graph": ["gnn"], "multimodal": ["multimodal"]}
    cfg = KeywordConfig(include=[], exclude=[])
    rec = Record(title="multimodal gnn", abstract="")
    kept, _, _ = apply_keyword_filter(
        [rec], cfg, concepts=concepts, concept_mode="all", gate="soft"
    )
    assert kept[0].keyword_note is None


def test_soft_gate_include_advisory():
    cfg = KeywordConfig(include=["security"], exclude=[])
    rec = Record(title="Unrelated topic", abstract="cooking")
    kept, excluded, reasons = apply_keyword_filter([rec], cfg, gate="soft")
    assert len(kept) == 1
    assert excluded == 0
    assert kept[0].keyword_note == "no included keyword (advisory)"


def test_hard_gate_unchanged_default():
    # Default gate is hard: existing drop behavior preserved.
    concepts = {"graph": ["gnn"], "multimodal": ["multimodal"]}
    cfg = KeywordConfig(include=[], exclude=[])
    rec = Record(title="only gnn here", abstract="")
    kept, excluded, reasons = apply_keyword_filter(
        [rec], cfg, concepts=concepts, concept_mode="all"
    )
    assert kept == []
    assert excluded == 1
    assert reasons == {"matched 1/2 concepts (need ≥2)": 1}
