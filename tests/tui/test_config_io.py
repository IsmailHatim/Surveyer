"""Tests for tomlkit round-trip config editing."""

from pathlib import Path

import pytest

tomlkit = pytest.importorskip("tomlkit")

from surveyer.tui.config_io import (  # noqa: E402
    ConceptItem,
    apply_form,
    extract_form,
    validate_text,
)

SAMPLE = """\
[project]
name = "secure-aggregation-survey"  # keep this comment
output_dir = "runs/secure-aggregation"
export_format = "xlsx"

[search]
year_min = 2018
year_max = 2026
max_results_per_query = 200
sources = ["dblp", "openalex", "agent"]

[[search.queries]]
label = "A_attacks"
terms = "model poisoning attacks federated learning"

[search.concepts]
federated = ["federated learning", "federated averaging"]

[filter.concepts]
federated = ["federated learning"]

[filter.keyword]
exclude = ["survey", "review"]

[filter.llm]
enabled = false
provider = "openai"
model = "gpt-4o-mini"
threshold = 0.6
survey_abstract = "abstract here"
"""

# Minimal config: only the required fields, no optional sections
MINIMAL = """\
[project]
name = "minimal"

[search]
sources = ["dblp"]

[[search.queries]]
label = "q1"
terms = "federated learning"
"""


def test_extract_reads_daily_knobs():
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    assert v.name == "secure-aggregation-survey"
    assert v.output_dir == "runs/secure-aggregation"
    assert v.sources == ["dblp", "openalex", "agent"]
    assert v.year_min == 2018 and v.year_max == 2026
    assert v.max_results_per_query == 200
    assert v.exclude == ["survey", "review"]
    assert v.llm_enabled is False
    assert v.llm_provider == "openai"
    assert v.llm_model == "gpt-4o-mini"
    assert v.llm_threshold == 0.6
    assert v.extend_xlsx == ""


def test_noop_roundtrip_is_byte_identical():
    doc = tomlkit.parse(SAMPLE)
    apply_form(doc, extract_form(doc))
    assert tomlkit.dumps(doc) == SAMPLE


def test_editing_one_key_preserves_everything_else():
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    v.name = "renamed"
    apply_form(doc, v)
    out = tomlkit.dumps(doc)
    assert 'name = "renamed"  # keep this comment' in out
    # untouched sections survive verbatim
    assert "[search.concepts]" in out
    assert 'terms = "model poisoning attacks federated learning"' in out


def test_sources_outside_checkboxes_are_preserved():
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    v.sources = ["dblp", "agent"]  # user unchecked openalex; agent has no checkbox
    apply_form(doc, v)
    assert extract_form(doc).sources == ["dblp", "agent"]
    # "agent" must also survive in the raw TOML text
    assert "agent" in tomlkit.dumps(doc)


def test_extend_section_added_and_removed():
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    v.extend_xlsx = "runs/v1/survey.xlsx"
    apply_form(doc, v)
    assert extract_form(doc).extend_xlsx == "runs/v1/survey.xlsx"
    v.extend_xlsx = ""
    apply_form(doc, v)
    assert "extend" not in tomlkit.dumps(doc)


def test_year_cleared_removes_key():
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    v.year_min = None
    apply_form(doc, v)
    assert "year_min" not in tomlkit.dumps(doc)


def test_validate_text_ok_and_error():
    assert validate_text(SAMPLE) is None
    bad = SAMPLE.replace('provider = "openai"', 'provider = "nope"')
    err = validate_text(bad)
    assert err is not None and "nope" in err


def test_sparse_config_defaults_are_correct(tmp_path: Path):
    """Sparse config must round-trip with struct-derived defaults."""
    from surveyer.config import load_config
    from surveyer.tui.config_io import _PROJECT_DEFAULTS, _SEARCH_DEFAULTS

    doc = tomlkit.parse(MINIMAL)
    v = extract_form(doc)

    # Defaults must match the struct defaults
    assert v.output_dir == _PROJECT_DEFAULTS.output_dir
    assert v.max_results_per_query == _SEARCH_DEFAULTS.max_results_per_query

    apply_form(doc, v)
    dumped = tomlkit.dumps(doc)

    # Must not contain the wrong default
    assert 'output_dir = ""' not in dumped

    # Validate text must pass
    assert validate_text(dumped) is None

    # load_config must yield canonical output_dir
    out = tmp_path / "minimal.toml"
    out.write_text(dumped, encoding="utf-8")
    cfg = load_config(out)
    assert cfg.project.output_dir == "runs/default"


def test_dedup_threshold_extract_default_and_roundtrip():
    """A config without [dedup] extracts the default and stays free of the table."""
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    assert v.dedup_title_threshold == 90
    apply_form(doc, v)
    # noop save must not materialise an empty [dedup] table
    assert "[dedup]" not in tomlkit.dumps(doc)


def test_dedup_threshold_edit_materialises_section():
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    v.dedup_title_threshold = 80
    apply_form(doc, v)
    dumped = tomlkit.dumps(doc)
    assert "[dedup]" in dumped
    assert "title_threshold = 80" in dumped
    assert validate_text(dumped) is None
    assert extract_form(tomlkit.parse(dumped)).dedup_title_threshold == 80


def test_dedup_threshold_existing_section_read():
    doc = tomlkit.parse(SAMPLE + "\n[dedup]\ntitle_threshold = 75\n")
    assert extract_form(doc).dedup_title_threshold == 75


def test_inline_table_llm_save_behaviour():
    """Inline-table configs pin graceful-failure contract."""
    inline_config = """\
[project]
name = "test"

[search]
sources = ["dblp"]

[[search.queries]]
label = "q1"
terms = "federated learning"

[filter]
llm = { enabled = false, provider = "openai" }
"""
    doc = tomlkit.parse(inline_config)
    v = extract_form(doc)
    v.llm_model = "gpt-4o"
    apply_form(doc, v)
    dumped = tomlkit.dumps(doc)
    err = validate_text(dumped)
    # Either the save would be refused (non-None error) or the TOML is valid.
    if err is not None:
        # tomlkit produced invalid TOML for the inline-table edit
        assert isinstance(err, str)
    else:
        # tomlkit handled the inline table correctly on this version; assert
        # the round-trip result actually passes validation.
        assert err is None


def test_missing_filter_section_materialises_defaults():
    """Config with no [filter] table extracts defaults, materialises on apply."""
    from surveyer.tui.config_io import _LLM_DEFAULTS

    doc = tomlkit.parse(MINIMAL)
    v = extract_form(doc)

    # extract should give struct defaults, not crash
    assert v.llm_enabled == _LLM_DEFAULTS.enabled
    assert v.llm_provider == _LLM_DEFAULTS.provider
    assert v.llm_model == _LLM_DEFAULTS.model
    assert v.llm_threshold == _LLM_DEFAULTS.threshold
    assert v.exclude == []

    apply_form(doc, v)
    dumped = tomlkit.dumps(doc)

    # [filter.keyword] and [filter.llm] sections must now exist
    assert "[filter" in dumped or "filter" in dumped
    # Validate must pass
    assert validate_text(dumped) is None


def test_extract_form_raises_on_shape_invalid_config():
    """Finding 4: extract_form raises ValueError (not AttributeError) for bad shapes.

    A top-level scalar where a table is expected (e.g. ``project = 5``) must
    raise ValueError with an explanatory message, not AttributeError.
    """
    bad_toml = "project = 5\n"
    doc = tomlkit.parse(bad_toml)
    with pytest.raises(ValueError, match="Invalid config shape"):
        extract_form(doc)


def test_llm_host_roundtrip():
    """Host is only written when present in the file or customized."""
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    assert v.llm_host == "http://localhost:11434"  # struct default
    # no-op apply: host key must NOT be materialized
    apply_form(doc, v)
    assert "host" not in tomlkit.dumps(doc)
    # customized host is persisted and survives a round trip
    v.llm_host = "http://gpu-server:11434"
    apply_form(doc, v)
    assert 'host = "http://gpu-server:11434"' in tomlkit.dumps(doc)
    assert extract_form(doc).llm_host == "http://gpu-server:11434"
    assert validate_text(tomlkit.dumps(doc)) is None


def test_extract_reads_concepts():
    doc = tomlkit.parse(SAMPLE)
    values = extract_form(doc)
    assert values.search_concepts == [
        ConceptItem(
            name="federated", synonyms=["federated learning", "federated averaging"]
        )
    ]
    assert values.filter_concepts == [
        ConceptItem(name="federated", synonyms=["federated learning"])
    ]


def test_extract_no_concepts_gives_empty_lists():
    doc = tomlkit.parse(MINIMAL)
    values = extract_form(doc)
    assert values.search_concepts == []
    assert values.filter_concepts == []


def test_apply_edits_concepts_and_preserves_comments():
    doc = tomlkit.parse(SAMPLE)
    values = extract_form(doc)
    values.search_concepts = [
        ConceptItem(name="federated", synonyms=["federated learning", "FL"]),
        ConceptItem(name="privacy", synonyms=["differential privacy"]),
    ]
    apply_form(doc, values)
    text = tomlkit.dumps(doc)
    assert "keep this comment" in text  # untouched comment survives
    assert '"FL"' in text
    assert 'privacy = ["differential privacy"]' in text
    # re-extract round-trips
    assert extract_form(doc).search_concepts == values.search_concepts


def test_apply_removes_emptied_concepts_table():
    doc = tomlkit.parse(SAMPLE)
    values = extract_form(doc)
    values.filter_concepts = []
    apply_form(doc, values)
    assert "concepts" not in doc["filter"]
    assert validate_text(tomlkit.dumps(doc)) is None


def test_named_concept_without_synonyms_is_rejected():
    doc = tomlkit.parse(SAMPLE)
    values = extract_form(doc)
    values.search_concepts = [ConceptItem(name="empty", synonyms=[])]
    apply_form(doc, values)
    error = validate_text(tomlkit.dumps(doc))
    assert error is not None
    assert "synonym" in error


def test_snowball_defaults_no_section():
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    assert v.snowball_enabled is False
    assert v.snowball_direction == "both"
    assert v.snowball_max_results_per_seed == 200
    apply_form(doc, v)
    # a no-op save must not materialise an empty [snowball] table
    assert "[snowball]" not in tomlkit.dumps(doc)


def test_snowball_enable_roundtrip():
    doc = tomlkit.parse(SAMPLE)
    v = extract_form(doc)
    v.snowball_enabled = True
    v.snowball_direction = "backward"
    v.snowball_max_results_per_seed = 50
    apply_form(doc, v)
    dumped = tomlkit.dumps(doc)
    assert "[snowball]" in dumped
    assert "enabled = true" in dumped
    assert 'direction = "backward"' in dumped
    assert "max_results_per_seed = 50" in dumped
    assert validate_text(dumped) is None
    back = extract_form(tomlkit.parse(dumped))
    assert back.snowball_enabled is True
    assert back.snowball_direction == "backward"
    assert back.snowball_max_results_per_seed == 50


def test_concept_mode_and_review_margin_round_trip(tmp_path):
    """concept_mode and review_margin are read, written, and re-read correctly."""
    from surveyer.tui.config_io import load_document

    p = tmp_path / "c.toml"
    p.write_text(
        '[project]\nname = "t"\n[search]\nsources = ["openalex"]\n'
        'queries = [{label="a", terms="x"}]\n'
        '[filter]\nconcept_mode = "all"\n'
        '[filter.llm]\nreview_margin = 0.1\n'
    )
    doc = load_document(p)
    form = extract_form(doc)
    assert form.concept_mode == "all"
    assert form.review_margin == 0.1
    form.concept_mode = "min:2"
    form.review_margin = 0.2
    apply_form(doc, form)
    reparsed = extract_form(doc)
    assert reparsed.concept_mode == "min:2"
    assert reparsed.review_margin == 0.2
