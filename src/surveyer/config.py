"""Survey configuration, loaded from a TOML file."""

from __future__ import annotations

import tomllib
from pathlib import Path

import msgspec

VALID_SOURCES = {
    "dblp",
    "openalex",
    "semantic_scholar",
    "google_scholar",
    "agent",
}

VALID_LLM_PROVIDERS = {"openai", "ollama"}

VALID_EXPORT_FORMATS = {"xlsx", "csv"}


class ProjectConfig(msgspec.Struct, kw_only=True):
    """Project configuration."""

    name: str
    output_dir: str = "runs/default"
    export_format: str = "xlsx"


class Query(msgspec.Struct, kw_only=True):
    """Search query."""

    label: str
    terms: str


class SearchConfig(msgspec.Struct, kw_only=True):
    """Search configuration."""

    sources: list[str]
    queries: list[Query]
    year_min: int | None = None
    year_max: int | None = None
    max_results_per_query: int = 200


class KeywordConfig(msgspec.Struct, kw_only=True):
    """Keyword configuration."""

    include: list[str] = []
    exclude: list[str] = []


class LLMConfig(msgspec.Struct, kw_only=True):
    """LLM configuration."""

    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    host: str = "http://localhost:11434"
    threshold: float = 0.5
    survey_abstract: str = ""


class FilterConfig(msgspec.Struct, kw_only=True):
    """Filtering configuration."""

    keyword: KeywordConfig = msgspec.field(default_factory=KeywordConfig)
    llm: LLMConfig = msgspec.field(default_factory=LLMConfig)


class SurveyConfig(msgspec.Struct, kw_only=True):
    """Top level Survey configuration."""

    project: ProjectConfig
    search: SearchConfig
    filter: FilterConfig = msgspec.field(default_factory=FilterConfig)


def load_config(path: str | Path) -> SurveyConfig:
    """Load and validate a survey TOML config."""
    raw = tomllib.loads(Path(path).read_text())
    try:
        cfg = msgspec.convert(raw, SurveyConfig)
    except msgspec.ValidationError as exc:
        raise ValueError(f"Invalid config: {exc}") from exc

    unknown = set(cfg.search.sources) - VALID_SOURCES
    if unknown:
        raise ValueError(f"Unknown source(s): {', '.join(sorted(unknown))}")
    if cfg.project.export_format not in VALID_EXPORT_FORMATS:
        raise ValueError(
            f"Unknown export format: {cfg.project.export_format!r}. "
            f"Valid formats: {', '.join(sorted(VALID_EXPORT_FORMATS))}"
        )
    if cfg.filter.llm.provider not in VALID_LLM_PROVIDERS:
        raise ValueError(
            f"Unknown LLM provider: {cfg.filter.llm.provider!r}. "
            f"Valid providers: {', '.join(sorted(VALID_LLM_PROVIDERS))}"
        )
    if cfg.filter.llm.provider == "ollama" and not cfg.filter.llm.host.strip():
        raise ValueError('filter.llm.host must be set when provider = "ollama"')
    if cfg.filter.llm.enabled and not cfg.filter.llm.survey_abstract.strip():
        raise ValueError(
            "filter.llm.survey_abstract must be set when filter.llm.enabled = true"
        )
    return cfg
