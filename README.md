# Surveyer
<div align="center">
  <img src="figures/surveyer_logo.png" alt="Surveyer logo" width="400"/>
</div>


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
```

## Configure

Copy `examples/survey.toml` and edit it for your survey (sources, query groups,
year range, keyword include/exclude, and your survey abstract for LLM scoring).

Set credentials in your environment:

```bash
export OPENAI_API_KEY=sk-...
export SEMANTIC_SCHOLAR_API_KEY=...   # optional, raises rate limits
```

Or keep them in the `.env` file and load it automatically:

```bash
uv run --env-file .env surveyer run --config examples/survey.toml
```

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
| Semantic Scholar  | optional| abstracts, citations                    |
| Google Scholar    | no      | optional extra; fragile, off by default |
| Agent web search  | -       | TODO            |

## Outputs

- `survey.xlsx` - `papers`, `excluded`, and `summary` sheets.
- `ledger.json` - per-stage counts (the input to PRISMA).
- `prisma.png` - PRISMA flow diagram.
