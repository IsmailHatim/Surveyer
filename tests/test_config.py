from __future__ import annotations

import pytest

from surveyer.config import LLMConfig, SurveyConfig, load_config

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
            "survey_abstract = \"We survey X.\"",
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
            "survey_abstract = \"We survey X.\"",
            'survey_abstract = "We survey X."\nhost = ""',
        )
    )
    with pytest.raises(ValueError, match="host"):
        load_config(p)
