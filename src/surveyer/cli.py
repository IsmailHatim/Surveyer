"""Command-line interface for Surveyer.

Every survey is driven by a TOML config for reproducibility.
"""

from __future__ import annotations

from pathlib import Path

import typer

from surveyer.config import disable_filters, load_config
from surveyer.pipeline import run_pipeline

app = typer.Typer(add_completion=False, help="Reproducible survey literature search.")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    config: str | None = typer.Option(
        None, "--config", "-c", help="Open this survey.toml in the dashboard."
    ),
) -> None:
    """Launch the interactive dashboard when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        import surveyer.tui as tui
    except ImportError:
        typer.echo(
            "The dashboard needs the 'tui' extra: uv sync --extra tui "
            "(or: pip install 'surveyer[tui]')"
        )
        typer.echo(ctx.get_help())
        raise typer.Exit(0) from None
    tui.run_tui(config)


@app.command()
def run(
    config: str = typer.Option(..., "--config", "-c", help="Path to survey.toml"),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Bypass the HTTP cache and refetch from sources and BibTeX "
        "(does not re-run LLM scoring).",
    ),
) -> None:
    """Run the full pipeline: fetch -> deduplication -> filter -> export -> prisma."""
    cfg = load_config(config)
    result = run_pipeline(cfg, refresh=refresh)
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
def fetch(
    config: str = typer.Option(..., "--config", "-c"),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Bypass the HTTP cache and refetch from sources.",
    ),
) -> None:
    """Fetch, deduplication and export the raw record set."""
    cfg = load_config(config)
    disable_filters(cfg)
    result = run_pipeline(cfg, resolve_bibtex=False, refresh=refresh)
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


@app.command()
def extend(
    config: str = typer.Option(..., "--config", "-c", help="Path to survey.toml"),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Bypass the HTTP cache and refetch from sources and BibTeX "
        "(does not re-run LLM scoring).",
    ),
) -> None:
    """Extend a screened survey: new queries on top of a screened xlsx."""
    cfg = load_config(config)
    if cfg.extend is None:
        typer.echo(
            "Error: config has no [extend] section. "
            'Add [extend]\\nxlsx = "runs/v1/survey.xlsx" to extend a run.',
            err=True,
        )
        raise typer.Exit(1)
    result = run_pipeline(cfg, refresh=refresh)
    led = result.ledger
    typer.echo(
        f"Done. Carried over {led.previously_included} screened papers, "
        f"skipped {led.already_screened} already screened, "
        f"newly included {led.included} "
        f"(total {led.total_included()}). "
        f"Outputs in {cfg.project.output_dir}/"
    )
    if led.failed_sources:
        typer.echo(
            "Warning: these sources errored on one or more queries: "
            f"{', '.join(led.failed_sources)}",
            err=True,
        )


@app.command()
def snowball(
    config: str = typer.Option(..., "--config", "-c", help="Path to survey.toml"),
    papers: str = typer.Option(
        ..., "--papers", "-p", help="Screened survey.xlsx to snowball from."
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Bypass the HTTP cache and refetch from OpenAlex."
    ),
) -> None:
    """Chase references and citations of a screened workbook's included papers."""
    from surveyer.snowball import run_snowball

    cfg = load_config(config)
    if cfg.snowball is None or not cfg.snowball.enabled:
        typer.echo(
            "Error: config has no enabled [snowball] section. "
            "Add [snowball]\nenabled = true to chase citations.",
            err=True,
        )
        raise typer.Exit(1)
    result = run_snowball(cfg, papers, refresh=refresh)
    snow = result.ledger.snowball
    typer.echo(
        f"Done. Seeded from {result.ledger.previously_included} papers, "
        f"identified {snow.identified} via citation searching, "
        f"newly included {snow.included} "
        f"(total {result.ledger.total_included()}). "
        f"Outputs in {cfg.project.output_dir}/"
    )


if __name__ == "__main__":
    app()
