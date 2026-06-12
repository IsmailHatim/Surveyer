<div align="center">
  <img src="figures/surveyer_logo.png" alt="Surveyer logo" width="300"/>
</div>

<br>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python" src="https://img.shields.io/badge/Python-3.11+-informational?logo=python&logoColor=white"></a>
  <a href="https://docs.astral.sh/uv/"><img alt="managed with uv" src="https://img.shields.io/badge/uv-managed-blueviolet?logo=uv&logoColor=white"></a>
  <img alt="Version" src="https://img.shields.io/badge/version-0.2.1-success">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-lightgrey">
  <a href="https://github.com/IsmailHatim/Surveyer/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/IsmailHatim/Surveyer?logo=github&color=yellow"></a>
  <a href="https://github.com/IsmailHatim/Surveyer/commits"><img alt="Last commit" src="https://img.shields.io/github/last-commit/IsmailHatim/Surveyer?color=teal"></a>
  <a href="https://github.com/IsmailHatim/Surveyer/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/IsmailHatim/Surveyer/ci.yml?branch=main&logo=githubactions&logoColor=white&label=CI"></a>
</p>

<div align="center">
  <img src="figures/demo.gif" alt="Surveyer terminal dashboard demo" width="850"/>
  <p><em>The built-in terminal dashboard: pick a config, tweak it, run the pipeline live.</em></p>
</div>

Surveyer is an open source Literature search tool for academic surveys: fetch from
multiple sources, deduplicate, filter (keyword and LLM relevance), export to Excel
with ready-to-use BibTeX citations, and generate a PRISMA flow diagram.
It's reproducible and based on configuration files, so you can easily update your 
survey as new papers come out or share it with collaborators.

## Install

```bash
uv sync
# optional Google Scholar support:
uv sync --extra scholar
# optional local LLM scoring via Ollama:
uv sync --extra ollama
# optional TUI dashboard (textual + tomlkit):
uv sync --extra tui
```

## Run

### Terminal dashboard (easiest)

```bash
uv run surveyer                              # home screen → pick a config → edit → run
uv run surveyer -c examples/survey.toml      # open a config directly
# with credentials from .env:
uv run --env-file .env surveyer
```

Everything is driven by a few keys:

| Key | Action |
|-----|--------|
| `Enter` | choose a survey config |
| `S` | save the config (validated first, comments preserved) |
| `E` | open the TOML in `$EDITOR` (for concept blocks) |
| `R` / `F` | run the full pipeline / fetch-only, with live logs and a PRISMA summary |
| `O` | open the output folder (xlsx, references.bib, PRISMA figure) |
| `Esc` / `Q` | back / quit |

### Command line

```bash
# Full run will create : runs/<name>/survey.xlsx, references.bib, ledger.json, prisma.{svg,pdf,png,mmd}
uv run surveyer run --config examples/survey.toml

# Fetch and deduplicate only (skips BibTeX resolution)
uv run surveyer fetch --config examples/survey.toml

# Render PRISMA from a saved ledger
uv run surveyer prisma --config examples/survey.toml

# Search new queries on top of a manually screened survey.xlsx
uv run surveyer extend --config examples/survey_v2.toml
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

### Concept filtering

Mirror the search concepts on the filtering side with `[filter.concepts]`. When
present, a record is kept only if it matches at least one synonym from **every**
concept block (AND across concepts, OR within) and contains no `exclude` term —
the flat `filter.keyword.include` list is ignored while concepts are active.

```toml
[filter.concepts]
federated = ["federated learning", "federated averaging"]
security  = ["secure aggregation", "model poisoning", "byzantine"]
privacy   = ["differential privacy", "privacy preserving"]
```

This is independent from `[search.concepts]`, so you can search broadly but keep
only records that genuinely cover all concepts.

### LLM scoring provider

LLM relevance scoring runs through `filter.llm`. Two providers are supported:

- `openai` (default) — set `OPENAI_API_KEY`.
- `ollama` — runs a local or networked [Ollama](https://ollama.com) model, no
  API key needed. Install the extra (`uv sync --extra ollama`), then set
  `provider = "ollama"`, the `model` name, and `host` (default
  `http://localhost:11434`; point it at any Ollama server on your network).

## Extend a screened survey

After a run, you typically screen `survey.xlsx` by hand: move rows between the
`papers` and `excluded` sheets, add papers you found yourself, color cells or
leave comments. To search for *additional* studies later (new queries or
keywords) without redoing that work, point a new config at the screened
workbook:

```toml
[extend]
xlsx = "runs/v1/survey.xlsx"   # the manually screened workbook

[project]
output_dir = "runs/v2"         # must differ from the v1 run
```

Your manual decisions are final: papers in the `papers` sheet are always kept
and never refiltered or rescored, papers in `excluded` stay excluded, and
records the new search re-finds are dropped and counted as `already_screened`.
The keyword and LLM filters apply only to newly discovered papers.

The output `survey.xlsx` is a **copy** of your screened file with the new rows
appended at the bottom of each sheet, manual colors and comments are
preserved, and the original file is never modified. Hand added papers missing
a BibTeX entry get one resolved and backfilled, `references.bib` covers old
and new papers, and the PRISMA diagram switches to the PRISMA 2020 review
update layout (previous-version box and cumulative total). Extending requires
`export_format = "xlsx"`, and you can chain updates.

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
- `references.bib` - one BibTeX entry per included paper.
- `ledger.json` - per-stage counts (the input to PRISMA).

### BibTeX citations

`surveyer run` resolves a BibTeX entry for every included paper and writes them
to `references.bib`. Each entry also appears in a `bibtex` column of the
`papers` sheet (and `papers.csv`), so you can copy a single citation straight
from the spreadsheet.

Entries are fetched from authoritative sources rather than synthesized, in
priority order:

| `bibtex_source` | Where it comes from |
|-----------------|---------------------|
| `dblp` | DBLP's curated entry (`dblp.org/rec/<key>.bib`) preferred |
| `doi` | CrossRef/DataCite via DOI content negotiation |
| `local` | Minimal `@misc` built from the record's own metadata |

`local` entries are a last resort for papers with neither a DBLP key nor a DOI;
they are highlighted in red in the `.xlsx` so you can spot (and hand-fix) the
lower-quality citations at a glance. In CSV, filter on the `bibtex_source`
column instead. Fetched entries are cached under the run's `cache/` directory,
so re-runs cost no extra network requests.

### PRISMA flow diagram

The pipeline writes a PRISMA flow diagram to the run's output directory:

| File | Description |
|------|-------------|
| `prisma.svg` / `prisma.pdf` / `prisma.png` | Publication figure (requires Graphviz) |
| `prisma.mmd` | Mermaid source rendered natively by GitHub and most IDEs |

The image outputs require the Graphviz binary:

```bash
# macOS
brew install graphviz
# Debian/Ubuntu
apt-get install graphviz
```

If the binray is not installed the run still creates: `prisma.mmd` and `prisma.dot`
(the raw diagram source) are written and a warning is logged.

## License

Released under the [MIT License](LICENSE) © 2026 Ismail Hatim.
