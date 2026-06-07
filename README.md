<div align="center">
  <img src="figures/surveyer_logo.png" alt="Surveyer logo" width="300"/>
</div>

<br>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/Python-3.11+-informational?logo=python&logoColor=white"></a>
  <a href="https://docs.astral.sh/uv/"><img alt="managed with uv" src="https://img.shields.io/badge/uv-managed-blueviolet?logo=uv&logoColor=white"></a>
  <a href="https://github.com/astral-sh/ruff"><img alt="Ruff" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json"></a>
  <img alt="Version" src="https://img.shields.io/badge/version-0.1.0-success">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-lightgrey">
  <a href="https://github.com/IsmailHatim/Surveyer/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/IsmailHatim/Surveyer?logo=github&color=yellow"></a>
  <a href="https://github.com/IsmailHatim/Surveyer/issues"><img alt="Issues" src="https://img.shields.io/github/issues/IsmailHatim/Surveyer?color=orange"></a>
  <a href="https://github.com/IsmailHatim/Surveyer/commits"><img alt="Last commit" src="https://img.shields.io/github/last-commit/IsmailHatim/Surveyer?color=teal"></a>
</p>

Surveyer is an open source Literature search tool for academic surveys: fetch from
multiple sources, deduplicate, filter (keyword and LLM relevance), export to Excel,
and generate a PRISMA flow diagram.
It's reproducible and based on configuration files, so you can easily update your 
survey as new papers come out or share it with collaborators.

## Install

```bash
uv sync
# optional Google Scholar support:
uv sync --extra scholar
# optional local LLM scoring via Ollama:
uv sync --extra ollama
```

## Configure

Copy `examples/survey.toml` and edit it for your survey (sources, query groups,
year range, keyword include/exclude, and your survey abstract for LLM scoring).

Set credentials in your environment:

```bash
export OPENAI_API_KEY=sk-...
export SEMANTIC_SCHOLAR_API_KEY=...   # strongly recommended
```

Or keep them in the `.env` file and load it automatically:

```bash
uv run --env-file .env surveyer run --config examples/survey.toml
```

### Concept-group expansion

Rather than hand-writing every keyword combination as a separate
`[[search.queries]]`, you can declare concept blocks of synonyms. Synonyms
within a concept are OR alternatives; the concepts are combined with AND. The
tool expands the cross-product into queries automatically:

```toml
[search.concepts]
federated = ["federated learning", "federated averaging"]
security  = ["secure aggregation", "model poisoning", "byzantine robust"]
privacy   = ["differential privacy", "privacy preserving"]
```

The block above generates 2 × 3 × 2 = 12 queries. Generated queries are added to
any explicit `[[search.queries]]` (a generated query whose terms exactly match an
explicit one is dropped). Each gets a traceable label such as
`concept_federated0__security0__privacy0`. Above 100 generated queries the tool
logs a warning, since every query hits every source. See `examples/survey.toml`
for a complete example.

### LLM scoring provider

LLM relevance scoring runs through `filter.llm`. Two providers are supported:

- `openai` (default) — set `OPENAI_API_KEY`.
- `ollama` — runs a local or networked [Ollama](https://ollama.com) model, no
  API key needed. Install the extra (`uv sync --extra ollama`), then set
  `provider = "ollama"`, the `model` name, and `host` (default
  `http://localhost:11434`; point it at any Ollama server on your network).

## Run

```bash
# Full run will create : runs/<name>/survey.xlsx, ledger.json, prisma.png
uv run surveyer run --config examples/survey.toml

# Fetch and deduplicate only
uv run surveyer fetch --config examples/survey.toml

# Render PRISMA from a saved ledger
uv run surveyer prisma --config examples/survey.toml
```

## Sources

| Source            | API key | Notes                                   |
|-------------------|---------|-----------------------------------------|
| DBLP              | no      | CS bibliography                         |
| OpenAlex          | no      | broad coverage, abstracts               |
| Semantic Scholar  | recommended | abstracts, citations                |
| Google Scholar    | no      | optional extra; fragile, off by default |
| Agent web search  | -       | TODO                                    |

## Outputs

- `survey.xlsx` - `papers`, `excluded`, and `summary` sheets.
- `ledger.json` - per-stage counts (the input to PRISMA).
- `prisma.png` - PRISMA flow diagram.

## License

Released under the [MIT License](LICENSE) © 2026 Ismail Hatim.
