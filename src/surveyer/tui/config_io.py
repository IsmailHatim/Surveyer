"""Tomlkit helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import msgspec
import tomlkit
from tomlkit import TOMLDocument

from surveyer.config import (
    VALID_SOURCES,
    LLMConfig,
    ProjectConfig,
    SearchConfig,
    load_config,
)

#: Sources shown as checkboxes in the dashboard.
TOGGLEABLE_SOURCES = ("dblp", "openalex", "semantic_scholar", "google_scholar")

assert set(TOGGLEABLE_SOURCES) <= VALID_SOURCES, (
    "TOGGLEABLE_SOURCES contains unknown sources; update VALID_SOURCES in config.py"
)

# Sentinel instances used to derive canonical defaults
_PROJECT_DEFAULTS = ProjectConfig(name="")
_SEARCH_DEFAULTS = SearchConfig(sources=[], queries=[])
_LLM_DEFAULTS = LLMConfig()


class FormValues(msgspec.Struct, kw_only=True):
    """The daily knobs the dashboard form owns."""

    name: str = ""
    output_dir: str = msgspec.field(default=_PROJECT_DEFAULTS.output_dir)
    sources: list[str] = []
    year_min: int | None = None
    year_max: int | None = None
    max_results_per_query: int = msgspec.field(
        default=_SEARCH_DEFAULTS.max_results_per_query
    )
    exclude: list[str] = []
    llm_enabled: bool = msgspec.field(default=_LLM_DEFAULTS.enabled)
    llm_provider: str = msgspec.field(default=_LLM_DEFAULTS.provider)
    llm_model: str = msgspec.field(default=_LLM_DEFAULTS.model)
    llm_host: str = msgspec.field(default=_LLM_DEFAULTS.host)
    llm_threshold: float = msgspec.field(default=_LLM_DEFAULTS.threshold)
    extend_xlsx: str = ""


def load_document(path: str | Path) -> TOMLDocument:
    """Parse the TOML file preserving comments and formatting."""
    return tomlkit.parse(Path(path).read_text(encoding="utf-8"))


def save_document(doc: TOMLDocument, path: str | Path) -> None:
    """Write the document back to disk."""
    Path(path).write_text(tomlkit.dumps(doc), encoding="utf-8")


def _table(parent, key: str):
    """Return parent[key], creating an empty table if missing."""
    if key not in parent:
        parent[key] = tomlkit.table()
    return parent[key]


def _set(table, key: str, value) -> None:
    """Set table[key] only if the value changed (preserves formatting)."""
    if key in table and table[key] == value:
        return
    table[key] = value


def _set_or_remove(table, key: str, value) -> None:
    """Like _set, but a None value removes the key entirely."""
    if value is None:
        if key in table:
            del table[key]
        return
    _set(table, key, value)


def extract_form(doc: TOMLDocument) -> FormValues:
    """Read the form keys out of a parsed config document."""

    def _expect_table(value, section: str):
        if not hasattr(value, "get"):
            raise ValueError(
                f"Invalid config shape: [{section}] must be a table,"
                f" got {type(value).__name__!r}"
            )

    try:
        project = doc.get("project", {})
        _expect_table(project, "project")
        search = doc.get("search", {})
        _expect_table(search, "search")
        flt = doc.get("filter", {})
        _expect_table(flt, "filter")
        keyword = flt.get("keyword", {}) if flt else {}
        _expect_table(keyword, "filter.keyword")
        llm = flt.get("llm", {}) if flt else {}
        _expect_table(llm, "filter.llm")
        extend = doc.get("extend", {})
        if extend:
            _expect_table(extend, "extend")
    except (AttributeError, TypeError) as exc:
        raise ValueError(f"Invalid config shape: {exc}") from exc

    return FormValues(
        name=str(project.get("name", "")),
        output_dir=str(project.get("output_dir", _PROJECT_DEFAULTS.output_dir)),
        sources=[str(s) for s in search.get("sources", [])],
        year_min=search.get("year_min"),
        year_max=search.get("year_max"),
        max_results_per_query=int(
            search.get("max_results_per_query", _SEARCH_DEFAULTS.max_results_per_query)
        ),
        exclude=[str(t) for t in keyword.get("exclude", [])],
        llm_enabled=bool(llm.get("enabled", _LLM_DEFAULTS.enabled)),
        llm_provider=str(llm.get("provider", _LLM_DEFAULTS.provider)),
        llm_model=str(llm.get("model", _LLM_DEFAULTS.model)),
        llm_host=str(llm.get("host", _LLM_DEFAULTS.host)),
        llm_threshold=float(llm.get("threshold", _LLM_DEFAULTS.threshold)),
        extend_xlsx=str(extend.get("xlsx", "")) if extend else "",
    )


def apply_form(doc: TOMLDocument, values: FormValues) -> None:
    """Write the form keys back into the document, touching nothing else."""
    project = _table(doc, "project")
    _set(project, "name", values.name)
    _set(project, "output_dir", values.output_dir)

    search = _table(doc, "search")
    _set(search, "sources", values.sources)
    _set_or_remove(search, "year_min", values.year_min)
    _set_or_remove(search, "year_max", values.year_max)
    _set(search, "max_results_per_query", values.max_results_per_query)

    flt = _table(doc, "filter")
    keyword = _table(flt, "keyword")
    _set(keyword, "exclude", values.exclude)
    llm = _table(flt, "llm")
    _set(llm, "enabled", values.llm_enabled)
    _set(llm, "provider", values.llm_provider)
    _set(llm, "model", values.llm_model)
    if "host" in llm or values.llm_host != _LLM_DEFAULTS.host:
        _set(llm, "host", values.llm_host)
    _set(llm, "threshold", values.llm_threshold)

    if values.extend_xlsx.strip():
        extend = _table(doc, "extend")
        _set(extend, "xlsx", values.extend_xlsx.strip())
    elif "extend" in doc:
        del doc["extend"]


def validate_text(text: str) -> str | None:
    """Validate TOML text via load_config; return the error message or None."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".toml", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    try:
        load_config(tmp_path)
    except Exception as exc:  # any config problem becomes a UI message
        return str(exc)
    finally:
        tmp_path.unlink(missing_ok=True)
    return None
