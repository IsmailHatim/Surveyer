from __future__ import annotations

import pytest
import structlog

from surveyer.config import (
    LLMConfig,
    Query,
    SearchConfig,
    SurveyConfig,
    expand_concepts,
    load_config,
)

SAMPLE = """
[project]
name = "demo"
output_dir = "runs/demo"

[search]
year_min = 2015
year_max = 2026
max_results_per_query = 100
sources = ["dblp", "openalex"]

[[search.queries]]
label = "A"
terms = "adversarial attacks"

[filter.keyword]
include = ["security"]
exclude = ["survey"]

[filter.llm]
enabled = true
provider = "openai"
model = "gpt-4o-mini"
threshold = 0.6
survey_abstract = "We survey X."
"""


def test_load_config(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(SAMPLE)
    cfg = load_config(p)
    assert isinstance(cfg, SurveyConfig)
    assert cfg.project.name == "demo"
    assert cfg.search.sources == ["dblp", "openalex"]
    assert cfg.search.queries[0].label == "A"
    assert cfg.filter.keyword.include == ["security"]
    assert cfg.filter.llm.threshold == 0.6


def test_unknown_source_rejected(tmp_path):
    bad = SAMPLE.replace('["dblp", "openalex"]', '["dblp", "bogus"]')
    p = tmp_path / "survey.toml"
    p.write_text(bad)
    with pytest.raises(ValueError, match="bogus"):
        load_config(p)


def test_llm_enabled_requires_abstract(tmp_path):
    bad = SAMPLE.replace('survey_abstract = "We survey X."', 'survey_abstract = ""')
    p = tmp_path / "survey.toml"
    p.write_text(bad)
    with pytest.raises(ValueError, match="survey_abstract"):
        load_config(p)


def test_llm_host_defaults():
    cfg = LLMConfig()
    assert cfg.host == "http://localhost:11434"


def test_ollama_provider_with_host(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(
        SAMPLE.replace('provider = "openai"', 'provider = "ollama"').replace(
            'survey_abstract = "We survey X."',
            'survey_abstract = "We survey X."\nhost = "http://ollama.example:11434"',
        )
    )
    cfg = load_config(p)
    assert cfg.filter.llm.provider == "ollama"
    assert cfg.filter.llm.host == "http://ollama.example:11434"


def test_unknown_provider_rejected(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(SAMPLE.replace('provider = "openai"', 'provider = "anthropic"'))
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        load_config(p)


def test_ollama_empty_host_rejected(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(
        SAMPLE.replace('provider = "openai"', 'provider = "ollama"').replace(
            'survey_abstract = "We survey X."',
            'survey_abstract = "We survey X."\nhost = ""',
        )
    )
    with pytest.raises(ValueError, match="host"):
        load_config(p)


CONCEPTS_SAMPLE = """
[project]
name = "demo"
output_dir = "runs/demo"

[search]
sources = ["dblp"]

[[search.queries]]
label = "manual"
terms = "hand written query"

[search.concepts]
graph = ["graph machine learning", "GNN"]
missingness = ["missing", "incomplete"]
"""


def test_load_config_with_concepts(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(CONCEPTS_SAMPLE)
    cfg = load_config(p)
    assert cfg.search.concepts == {
        "graph": ["graph machine learning", "GNN"],
        "missingness": ["missing", "incomplete"],
    }


def test_load_config_without_concepts_defaults_none(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(SAMPLE)
    cfg = load_config(p)
    assert cfg.search.concepts is None


def test_concept_with_empty_synonym_list_rejected(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(
        CONCEPTS_SAMPLE.replace(
            'graph = ["graph machine learning", "GNN"]', "graph = []"
        )
    )
    with pytest.raises(ValueError, match="must have at least one synonym") as excinfo:
        load_config(p)
    assert "graph" in str(excinfo.value)


def test_concept_with_blank_synonym_rejected(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(CONCEPTS_SAMPLE.replace('"missing", "incomplete"', '"missing", "  "'))
    with pytest.raises(ValueError, match="has an empty synonym") as excinfo:
        load_config(p)
    assert "missingness" in str(excinfo.value)


FILTER_CONCEPTS_SAMPLE = """
[project]
name = "demo"
output_dir = "runs/demo"

[search]
sources = ["dblp"]

[[search.queries]]
label = "manual"
terms = "hand written query"

[filter.concepts]
graph = ["graph neural network", "GNN"]
missingness = ["missing", "incomplete"]
"""


def test_load_config_with_filter_concepts(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(FILTER_CONCEPTS_SAMPLE)
    cfg = load_config(p)
    assert cfg.filter.concepts == {
        "graph": ["graph neural network", "GNN"],
        "missingness": ["missing", "incomplete"],
    }


def test_filter_concepts_default_none(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(SAMPLE)
    cfg = load_config(p)
    assert cfg.filter.concepts is None


def test_filter_concept_empty_list_rejected(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(
        FILTER_CONCEPTS_SAMPLE.replace(
            'graph = ["graph neural network", "GNN"]', "graph = []"
        )
    )
    with pytest.raises(ValueError, match="must have at least one synonym") as excinfo:
        load_config(p)
    assert "graph" in str(excinfo.value)
    assert "filter.concepts" in str(excinfo.value)


def test_filter_concept_blank_synonym_rejected(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(
        FILTER_CONCEPTS_SAMPLE.replace('"missing", "incomplete"', '"missing", "  "')
    )
    with pytest.raises(ValueError, match="has an empty synonym") as excinfo:
        load_config(p)
    assert "missingness" in str(excinfo.value)
    assert "filter.concepts" in str(excinfo.value)


def test_warns_when_filter_concepts_and_include_both_set(tmp_path):
    src = FILTER_CONCEPTS_SAMPLE + '\n[filter.keyword]\ninclude = ["graph"]\n'
    p = tmp_path / "survey.toml"
    p.write_text(src)
    with structlog.testing.capture_logs() as logs:
        load_config(p)
    assert [e for e in logs if e["event"] == "filter.include_ignored"]


def test_no_include_ignored_warning_without_concepts(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(SAMPLE)  # has include but no filter.concepts
    with structlog.testing.capture_logs() as logs:
        load_config(p)
    assert [e for e in logs if e["event"] == "filter.include_ignored"] == []


def test_expand_concepts_none_returns_empty():
    assert expand_concepts(None) == []


def test_expand_concepts_empty_dict_returns_empty():
    assert expand_concepts({}) == []


def test_expand_concepts_single_concept_one_query_per_synonym():
    out = expand_concepts({"graph": ["a", "b", "c"]})
    assert [q.terms for q in out] == ["a", "b", "c"]
    assert [q.label for q in out] == [
        "concept_graph0",
        "concept_graph1",
        "concept_graph2",
    ]


def test_expand_concepts_product_and_ordering():
    out = expand_concepts({"graph": ["g0", "g1"], "miss": ["m0", "m1", "m2"]})
    assert [q.terms for q in out] == [
        "g0 m0",
        "g0 m1",
        "g0 m2",
        "g1 m0",
        "g1 m1",
        "g1 m2",
    ]
    assert out[4].label == "concept_graph1__miss1"


def test_expand_concepts_label_determinism():
    concepts = {"a": ["x", "y"], "b": ["p"]}
    assert [q.label for q in expand_concepts(concepts)] == [
        q.label for q in expand_concepts(concepts)
    ]


def test_expand_concepts_duplicate_synonyms_get_distinct_labels():
    out = expand_concepts({"graph": ["a", "b", "a"]})
    assert [q.terms for q in out] == ["a", "b", "a"]
    assert [q.label for q in out] == [
        "concept_graph0",
        "concept_graph1",
        "concept_graph2",
    ]


def test_resolved_queries_concatenates_explicit_and_generated():
    cfg = SearchConfig(
        sources=["dblp"],
        queries=[Query(label="manual", terms="hand written")],
        concepts={"a": ["x", "y"]},
    )
    resolved = cfg.resolved_queries()
    assert [q.terms for q in resolved] == ["hand written", "x", "y"]


def test_resolved_queries_no_concepts_returns_explicit_only():
    cfg = SearchConfig(
        sources=["dblp"],
        queries=[Query(label="manual", terms="hand written")],
    )
    assert [q.terms for q in cfg.resolved_queries()] == ["hand written"]


def test_resolved_queries_dedups_generated_against_explicit():
    cfg = SearchConfig(
        sources=["dblp"],
        queries=[Query(label="manual", terms="x")],
        concepts={"a": ["x", "y"]},
    )
    resolved = cfg.resolved_queries()
    assert [q.terms for q in resolved] == ["x", "y"]
    assert [q.label for q in resolved] == ["manual", "concept_a1"]


def test_resolved_queries_warns_above_threshold():
    big = [f"s{i}" for i in range(11)]
    cfg = SearchConfig(
        sources=["dblp"],
        queries=[],
        concepts={"a": big, "b": big},
    )
    with structlog.testing.capture_logs() as logs:
        cfg.resolved_queries()
    warnings = [e for e in logs if e["event"] == "concepts.explosion"]
    assert len(warnings) == 1
    assert warnings[0]["generated"] == 121


def test_resolved_queries_no_warning_below_threshold():
    cfg = SearchConfig(
        sources=["dblp"],
        queries=[],
        concepts={"a": ["x", "y"]},
    )
    with structlog.testing.capture_logs() as logs:
        cfg.resolved_queries()
    assert [e for e in logs if e["event"] == "concepts.explosion"] == []


def test_resolved_queries_no_warning_at_threshold():
    # Exactly 100
    ten = [f"s{i}" for i in range(10)]
    cfg = SearchConfig(
        sources=["dblp"],
        queries=[],
        concepts={"a": ten, "b": ten},
    )
    with structlog.testing.capture_logs() as logs:
        cfg.resolved_queries()
    assert [e for e in logs if e["event"] == "concepts.explosion"] == []


EXTEND_SAMPLE = """
[project]
name = "demo-v2"
output_dir = "OUT"

[search]
sources = ["dblp"]

[[search.queries]]
label = "new-angle"
terms = "fresh terms"

[extend]
xlsx = "BASELINE"
"""


def _write_extend_config(tmp_path):
    baseline = tmp_path / "v1.xlsx"
    baseline.touch()
    p = tmp_path / "survey.toml"
    src = EXTEND_SAMPLE.replace("OUT", str(tmp_path / "out")).replace(
        "BASELINE", str(baseline)
    )
    p.write_text(src)
    return p, baseline


def test_extend_config_parsed(tmp_path):
    p, baseline = _write_extend_config(tmp_path)
    cfg = load_config(p)
    assert cfg.extend is not None
    assert cfg.extend.xlsx == str(baseline)


def test_extend_defaults_none(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(SAMPLE)
    assert load_config(p).extend is None


def test_extend_missing_baseline_rejected(tmp_path):
    p, baseline = _write_extend_config(tmp_path)
    baseline.unlink()
    with pytest.raises(ValueError, match="extend.xlsx not found"):
        load_config(p)


def test_extend_rejects_csv_format(tmp_path):
    p, _ = _write_extend_config(tmp_path)
    src = p.read_text().replace(
        'name = "demo-v2"', 'name = "demo-v2"\nexport_format = "csv"'
    )
    p.write_text(src)
    with pytest.raises(ValueError, match="export_format"):
        load_config(p)


def test_extend_rejects_overwriting_baseline(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    baseline = out / "survey.xlsx"
    baseline.touch()
    p = tmp_path / "survey.toml"
    p.write_text(
        EXTEND_SAMPLE.replace("OUT", str(out)).replace("BASELINE", str(baseline))
    )
    with pytest.raises(ValueError, match="output_dir"):
        load_config(p)
