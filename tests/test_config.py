from __future__ import annotations

import pytest
import structlog

from surveyer.config import (
    FilterConfig,
    KeywordConfig,
    LLMConfig,
    ProjectConfig,
    Query,
    SearchConfig,
    SurveyConfig,
    disable_filters,
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


def test_year_min_after_year_max_rejected(tmp_path):
    bad = SAMPLE.replace("year_max = 2026", "year_max = 2010")
    p = tmp_path / "survey.toml"
    p.write_text(bad)
    with pytest.raises(ValueError, match="year_min"):
        load_config(p)


@pytest.mark.parametrize("bad", [0, -5])
def test_non_positive_max_results_rejected(tmp_path, bad):
    cfg = SAMPLE.replace(
        "max_results_per_query = 100", f"max_results_per_query = {bad}"
    )
    p = tmp_path / "survey.toml"
    p.write_text(cfg)
    with pytest.raises(ValueError, match="max_results_per_query"):
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


def test_dedup_threshold_defaults():
    cfg = SurveyConfig(
        project=ProjectConfig(name="demo"),
        search=SearchConfig(sources=["dblp"], queries=[Query(label="A", terms="x")]),
    )
    assert cfg.dedup.title_threshold == 90


def test_dedup_threshold_loaded(tmp_path):
    p = tmp_path / "survey.toml"
    p.write_text(SAMPLE + "\n[dedup]\ntitle_threshold = 85\n")
    cfg = load_config(p)
    assert cfg.dedup.title_threshold == 85


@pytest.mark.parametrize("bad", [-1, 101, 200])
def test_dedup_threshold_out_of_range_rejected(tmp_path, bad):
    p = tmp_path / "survey.toml"
    p.write_text(SAMPLE + f"\n[dedup]\ntitle_threshold = {bad}\n")
    with pytest.raises(ValueError, match="title_threshold"):
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


def test_expand_concepts_quotes_multi_word_synonyms():
    out = expand_concepts({"graph": ["graph neural network", "gnn"]})
    assert [q.terms for q in out] == ['"graph neural network"', "gnn"]


def test_expand_concepts_quotes_phrases_in_cross_product():
    out = expand_concepts({"a": ["graph neural network"], "b": ["link prediction"]})
    assert [q.terms for q in out] == ['"graph neural network" "link prediction"']


def test_expand_concepts_does_not_double_wrap_quoted_synonym():
    out = expand_concepts({"graph": ['"already quoted"']})
    assert [q.terms for q in out] == ['"already quoted"']


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


def test_disable_filters_clears_all_screening():
    cfg = SurveyConfig(
        project=ProjectConfig(name="demo"),
        search=SearchConfig(sources=["dblp"], queries=[Query(label="A", terms="x")]),
        filter=FilterConfig(
            concepts={"method": ["gnn"]},
            keyword=KeywordConfig(include=["a"], exclude=["b"]),
            llm=LLMConfig(enabled=True, survey_abstract="abstract"),
        ),
    )
    disable_filters(cfg)
    assert cfg.filter.concepts is None
    assert cfg.filter.keyword.include == []
    assert cfg.filter.keyword.exclude == []
    assert cfg.filter.llm.enabled is False


def test_snowball_config_defaults_absent(tmp_path):
    from surveyer.config import load_config

    p = tmp_path / "s.toml"
    p.write_text(
        '[project]\nname = "t"\n[search]\nsources = ["openalex"]\nqueries = []\n'
    )
    cfg = load_config(p)
    assert cfg.snowball is None


def test_snowball_config_parsed(tmp_path):
    from surveyer.config import load_config

    p = tmp_path / "s.toml"
    p.write_text(
        '[project]\nname = "t"\n'
        '[search]\nsources = ["openalex"]\nqueries = []\n'
        '[snowball]\nenabled = true\ndirection = "backward"\n'
        "max_results_per_seed = 25\n"
    )
    cfg = load_config(p)
    assert cfg.snowball is not None
    assert cfg.snowball.enabled is True
    assert cfg.snowball.direction == "backward"
    assert cfg.snowball.max_results_per_seed == 25


def test_snowball_rejects_bad_direction(tmp_path):
    import pytest

    from surveyer.config import load_config

    p = tmp_path / "s.toml"
    p.write_text(
        '[project]\nname = "t"\n'
        '[search]\nsources = ["openalex"]\nqueries = []\n'
        '[snowball]\nenabled = true\ndirection = "sideways"\n'
    )
    with pytest.raises(ValueError, match="snowball.direction"):
        load_config(p)


def test_snowball_rejects_nonpositive_cap(tmp_path):
    import pytest

    from surveyer.config import load_config

    p = tmp_path / "s.toml"
    p.write_text(
        '[project]\nname = "t"\n'
        '[search]\nsources = ["openalex"]\nqueries = []\n'
        "[snowball]\nenabled = true\nmax_results_per_seed = 0\n"
    )
    with pytest.raises(ValueError, match="max_results_per_seed"):
        load_config(p)


# --- Task 2: concept_mode, review_margin, validation ---


def _write(tmp_path, body: str):
    p = tmp_path / "c.toml"
    p.write_text(
        '[project]\nname = "t"\n[search]\nsources = ["openalex"]\n'
        'queries = [{label="a", terms="x"}]\n' + body
    )
    return p


def test_resolve_required_concepts():
    from surveyer.config import resolve_required_concepts

    assert resolve_required_concepts("any", 3) == 1
    assert resolve_required_concepts("all", 3) == 3
    assert resolve_required_concepts("min:2", 3) == 2


def test_concept_mode_default_is_any(tmp_path):
    from surveyer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.filter.concept_mode == "any"


def test_bad_concept_mode_rejected(tmp_path):
    from surveyer.config import load_config

    with pytest.raises(ValueError, match="concept_mode"):
        load_config(_write(tmp_path, '[filter]\nconcept_mode = "some"\n'))


def test_min_n_out_of_range_rejected(tmp_path):
    from surveyer.config import load_config

    body = '[filter]\nconcept_mode = "min:4"\n[filter.concepts]\na = ["x"]\nb = ["y"]\n'
    with pytest.raises(ValueError, match="concept_mode"):
        load_config(_write(tmp_path, body))


def test_min_zero_rejected_without_concepts(tmp_path):
    from surveyer.config import load_config

    with pytest.raises(ValueError, match="concept_mode"):
        load_config(_write(tmp_path, '[filter]\nconcept_mode = "min:0"\n'))


def test_threshold_range_validated(tmp_path):
    from surveyer.config import load_config

    body = '[filter.llm]\nenabled = true\nsurvey_abstract = "s"\nthreshold = 1.5\n'
    with pytest.raises(ValueError, match="threshold"):
        load_config(_write(tmp_path, body))


def test_review_margin_range_validated(tmp_path):
    from surveyer.config import load_config

    body = "[filter.llm]\nreview_margin = 2.0\n"
    with pytest.raises(ValueError, match="review_margin"):
        load_config(_write(tmp_path, body))


# --- Task 1: keyword_gate field + validation ---


def test_keyword_gate_defaults_to_soft(tmp_path):
    from surveyer.config import load_config

    cfg = load_config(_write(tmp_path, ""))
    assert cfg.filter.keyword_gate == "soft"


def test_keyword_gate_rejects_unknown(tmp_path):
    from surveyer.config import load_config

    with pytest.raises(ValueError, match="keyword_gate"):
        load_config(_write(tmp_path, '[filter]\nkeyword_gate = "bogus"\n'))


# --- Task 1: SeedConfig block + validation ---


def test_seed_block_parsed(tmp_path):
    from surveyer.config import load_config

    cfg_path = tmp_path / "s.toml"
    cfg_path.write_text(
        """
[project]
name = "t"
[search]
sources = ["openalex"]
queries = [{label = "A", terms = "x"}]
[seed]
ids = ["10.1/a", "CorpusID:123", "arXiv:2409.07825"]
"""
    )
    cfg = load_config(cfg_path)
    assert cfg.seed is not None
    assert cfg.seed.ids == ["10.1/a", "CorpusID:123", "arXiv:2409.07825"]


def test_seed_block_absent_is_none(tmp_path):
    from surveyer.config import load_config

    cfg_path = tmp_path / "s.toml"
    cfg_path.write_text(
        """
[project]
name = "t"
[search]
sources = ["openalex"]
queries = [{label = "A", terms = "x"}]
"""
    )
    assert load_config(cfg_path).seed is None


def test_seed_blank_id_rejected(tmp_path):
    import pytest

    from surveyer.config import load_config

    cfg_path = tmp_path / "s.toml"
    cfg_path.write_text(
        """
[project]
name = "t"
[search]
sources = ["openalex"]
queries = [{label = "A", terms = "x"}]
[seed]
ids = ["10.1/a", "   "]
"""
    )
    with pytest.raises(ValueError, match="seed.ids"):
        load_config(cfg_path)
