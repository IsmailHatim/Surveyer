"""Survey configuration, loaded from a TOML file."""

from __future__ import annotations

import itertools
import tomllib
from pathlib import Path

import msgspec
import structlog

log = structlog.get_logger()

CONCEPT_QUERY_WARN_THRESHOLD = 100

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


def _quote_phrase(synonym: str) -> str:
    """Wrap a multi-word synonym in double quotes for phrase matching."""
    s = synonym.strip()
    return f'"{s}"' if (" " in s and not s.startswith('"')) else s


def expand_concepts(concepts: dict[str, list[str]] | None) -> list[Query]:
    """Expand concept OR into the AND cross-product of queries."""
    if not concepts:
        return []
    keys = list(concepts.keys())
    value_lists = [concepts[k] for k in keys]
    queries: list[Query] = []
    for combo in itertools.product(*(enumerate(v) for v in value_lists)):
        terms = " ".join(_quote_phrase(syn) for _, syn in combo)
        label = "concept_" + "__".join(
            f"{key}{idx}" for key, (idx, _) in zip(keys, combo)
        )
        queries.append(Query(label=label, terms=terms))
    return queries


class SearchConfig(msgspec.Struct, kw_only=True):
    """Search configuration."""

    sources: list[str]
    queries: list[Query]
    concepts: dict[str, list[str]] | None = None
    year_min: int | None = None
    year_max: int | None = None
    max_results_per_query: int = 200

    def resolved_queries(self) -> list[Query]:
        """Explicit queries plus the concept cross-product."""
        generated = expand_concepts(self.concepts)
        if len(generated) > CONCEPT_QUERY_WARN_THRESHOLD:
            log.warning(
                "concepts.explosion",
                generated=len(generated),
                threshold=CONCEPT_QUERY_WARN_THRESHOLD,
            )
        explicit_terms = {q.terms for q in self.queries}
        deduped = [q for q in generated if q.terms not in explicit_terms]
        return list(self.queries) + deduped


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

    concepts: dict[str, list[str]] | None = None
    keyword: KeywordConfig = msgspec.field(default_factory=KeywordConfig)
    llm: LLMConfig = msgspec.field(default_factory=LLMConfig)


class DedupConfig(msgspec.Struct, kw_only=True):
    """Deduplication configuration."""

    title_threshold: int = 90


class ExtendConfig(msgspec.Struct, kw_only=True):
    """Extend-mode configuration: build on a manually screened workbook."""

    xlsx: str


class SurveyConfig(msgspec.Struct, kw_only=True):
    """Top level Survey configuration."""

    project: ProjectConfig
    search: SearchConfig
    dedup: DedupConfig = msgspec.field(default_factory=DedupConfig)
    filter: FilterConfig = msgspec.field(default_factory=FilterConfig)
    extend: ExtendConfig | None = None


def disable_filters(cfg: SurveyConfig) -> None:
    """Strip every screening filter for fetch-only mode."""
    cfg.filter.concepts = None
    cfg.filter.keyword.include = []
    cfg.filter.keyword.exclude = []
    cfg.filter.llm.enabled = False


def _validate_concepts(concepts: dict[str, list[str]] | None, where: str) -> None:
    """Reject empty synonym lists or blank synonyms, naming the location."""
    if concepts is None:
        return
    for key, synonyms in concepts.items():
        if not synonyms:
            raise ValueError(
                f"Concept {key!r} in {where} must have at least one synonym."
            )
        for syn in synonyms:
            if not syn.strip():
                raise ValueError(f"Concept {key!r} in {where} has an empty synonym.")


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
    if not 0 <= cfg.dedup.title_threshold <= 100:
        raise ValueError(
            f"dedup.title_threshold must be between 0 and 100, "
            f"got {cfg.dedup.title_threshold}"
        )
    _validate_concepts(cfg.search.concepts, "search.concepts")
    _validate_concepts(cfg.filter.concepts, "filter.concepts")
    if cfg.filter.concepts and cfg.filter.keyword.include:
        log.warning(
            "filter.include_ignored",
            reason="filter.concepts is active; filter.keyword.include is ignored",
        )
    if cfg.project.export_format not in VALID_EXPORT_FORMATS:
        raise ValueError(
            f"Unknown export format: {cfg.project.export_format!r}. "
            f"Valid formats: {', '.join(sorted(VALID_EXPORT_FORMATS))}"
        )
    if cfg.extend is not None:
        baseline = Path(cfg.extend.xlsx)
        if not baseline.is_file():
            raise ValueError(f"extend.xlsx not found: {baseline}")
        if cfg.project.export_format != "xlsx":
            raise ValueError('[extend] requires project.export_format = "xlsx"')
        out_xlsx = Path(cfg.project.output_dir) / "survey.xlsx"
        if baseline.resolve() == out_xlsx.resolve():
            raise ValueError(
                "extend.xlsx is the file this run would write; "
                "use a different project.output_dir"
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
