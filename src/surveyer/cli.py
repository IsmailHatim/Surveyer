"""Command-line interface for Surveyer.

Every survey is driven by a TOML config for reproducibility.
"""

from __future__ import annotations

from pathlib import Path

import typer

from surveyer.config import load_config
from surveyer.pipeline import run_pipeline

app = typer.Typer(add_completion=False, help="Reproducible survey literature search.")


@app.command()
def run(
    config: str = typer.Option(..., "--config", "-c", help="Path to survey.toml"),
) -> None:
    """Run the full pipeline: fetch -> deduplication -> filter -> export -> prisma."""
    cfg = load_config(config)
    result = run_pipeline(cfg)
    typer.echo(
        f"Done. Identified {result.ledger.total_identified()}, "
        f"included {result.ledger.included}. "
        f"Outputs in {cfg.project.output_dir}/"
    )
    n_local = sum(1 for r in result.kept if r.bibtex_source == "local")
    typer.echo(
        f"references.bib written ({len(result.kept)} entries,"
        f" {n_local} local fallbacks)."
    )
    if result.ledger.failed_sources:
        typer.echo(
            "Warning: these sources errored on one or more queries: "
            f"{', '.join(result.ledger.failed_sources)}",
            err=True,
        )


@app.command()
def fetch(config: str = typer.Option(..., "--config", "-c")) -> None:
    """Fetch, deduplication and export the raw record set."""
    cfg = load_config(config)
    # No Filtering
    cfg.filter.keyword.include = []
    cfg.filter.keyword.exclude = []
    cfg.filter.llm.enabled = False
    result = run_pipeline(cfg, resolve_bibtex=False)
    typer.echo(
        f"Fetched and deduplicated: {result.ledger.after_dedup()} records "
        f"in {cfg.project.output_dir}/"
    )


@app.command()
def prisma(config: str = typer.Option(..., "--config", "-c")) -> None:
    """Recreates the PRISMA diagram from the existing ledger."""
    from surveyer.ledger import load_ledger
    from surveyer.prisma import render_prisma

    cfg = load_config(config)
    out = Path(cfg.project.output_dir)
    try:
        ledger = load_ledger(out / "ledger.json")
    except FileNotFoundError:
        typer.echo(
            f"Error: no ledger.json found in {out}. Run surveyer run first.",
            err=True,
        )
        raise typer.Exit(1) from None
    render_prisma(
        ledger,
        cfg.search,
        out,
        llm_model=cfg.filter.llm.model if cfg.filter.llm.enabled else None,
    )
    typer.echo(f"PRISMA written to {out}/prisma.{{svg,pdf,png,mmd}}")


if __name__ == "__main__":
    app()
