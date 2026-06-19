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
| `c` | edit search/filter concept blocks in-app |
| `E` | open the TOML in `$EDITOR` |
| `R` / `F` | run the full pipeline or fetch-only, with live logs and a PRISMA summary |
| `Esc` | back, or cancel a running pipeline |
| `O` | open the output folder (xlsx, references.bib, PRISMA figure) |
| `Q` | quit |

Check the **Refresh** checkbox before running to bypass the HTTP cache and refetch
sources and BibTeX.

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

# Bypass the HTTP cache and refetch (works on run, fetch and extend)
uv run surveyer run --config examples/survey.toml --refresh
```

## Configure

Copy `examples/survey.toml` and edit it for your survey (sources, query groups,
year range, keyword include/exclude, and your survey abstract for LLM scoring).

Set credentials in your environment:

```bash
export OPENAI_API_KEY=sk-...
export SEMANTIC_SCHOLAR_API_KEY=...   # strongly recommended
export NCBI_API_KEY=...               # strongly recommended for PubMed's papers
```

Or keep them in the `.env` file and load it automatically:

```bash
uv run --env-file .env surveyer run --config examples/survey.toml
```

### Concept groups

Rather than handwriting every keyword combination, you can declare concept blocks of
synonyms. Synonyms within a concept are OR statements; concepts combine with
AND. `[search.concepts]` expands the cross-product into queries, while `[filter.concepts]`
keeps a record only if it matches one synonym from **every** concept and contains
no `exclude` term. The two are independent, so you can do a vast search but keep
only records that cover all concepts.

```toml
[search.concepts]   # [filter.concepts] works the same way
federated = ["federated learning", "federated averaging"]
security  = ["secure aggregation", "model poisoning", "byzantine robust"]
privacy   = ["differential privacy", "privacy preserving"]
```

Generated queries are added to any explicit `[[search.queries]]`. 
In the dashboard, edit both blocks in-app with `c`: no
manual TOML required. See `examples/survey.toml` for a complete example.

### LLM scoring provider

LLM relevance scoring runs through `filter.llm`. Two providers are supported:

- `openai` (default) - set `OPENAI_API_KEY`.
- `ollama` - runs a local or networked [Ollama](https://ollama.com) model, no
  API key needed. Install the extra (`uv sync --extra ollama`), then set
  `provider = "ollama"`, the `model` name, and `host` (default
  `http://localhost:11434`).

## Extend a screened survey

After a run, you can check `survey.xlsx` by hand: move rows between the
`papers` and `excluded` sheets, add papers you found on your own, color cells or
leave comments. Then, to search for *additional* studies later (new queries or
keywords) without redoing that work, point a new config at the screened
workbook:

```toml
[extend]
xlsx = "runs/v1/survey.xlsx"   # the manually screened workbook

[project]
output_dir = "runs/v2"         # must differ from the v1
```

Your manual decisions are final: `papers` rows are  kept) and `excluded` rows 
stay excluded, and re-found records are dropped as `already_screened`. 
Filters apply only to newly discovered papers.

The output `survey.xlsx` is a **copy** of your screened file with new rows appended, missing 
BibTeX is backfilled, and the PRISMA diagram switches to the 2020 review-update layout
(previous-version box and cumulative total). Requires `export_format = "xlsx"` (updates can be iterated)

## Sources

| Source            | API key | Notes                                   |
|-------------------|---------|-----------------------------------------|
| DBLP              | no      | CS bibliography                         |
| OpenAlex          | no      | broad coverage, abstracts               |
| Semantic Scholar  | recommended | abstracts, citations                |
| PubMed            | recommended | biomedical and MEDLINE; abstracts + MeSH keywords |
| Google Scholar    | no      | optional extra; fragile, off by default |
| Agent web search  | -       | TODO                                    |

## Outputs

- `survey.xlsx` - `papers`, `excluded`, and `summary` sheets.
- `references.bib` - one BibTeX entry per included paper.
- `ledger.json` - per-stage counts (the input to PRISMA).

### BibTeX citations

`surveyer run` resolves a BibTeX entry for every included paper and writes them
to `references.bib`. Each citation also appears in a `bibtex` column of the
`papers` sheet (and `papers.csv`), so you can copy a single citation directly
from the sheet.

Entries are fetched from authoritative sources rather than synthesized, in
this priority order:

| `bibtex_source` | Where it comes from |
|-----------------|---------------------|
| `dblp` | DBLP's curated entry (`dblp.org/rec/<key>.bib`) preferred |
| `doi` | CrossRef/DataCite via DOI content negotiation |
| `local` | Minimal `@misc` built from the record's own metadata |

`local` entries are a last resort for papers with neither a DBLP key nor a DOI.
They are highlighted red in the `.xlsx` so you can spot and hand-fix lower-quality citations. 
Fetched entries are cached under the `cache/` directory, so you can re run without extra requests.

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

Without the binary the run still writes `prisma.mmd` and `prisma.dot` (the raw
diagram source) and logs a warning.

## License

Released under the [MIT License](LICENSE) © 2026 Ismail Hatim.
