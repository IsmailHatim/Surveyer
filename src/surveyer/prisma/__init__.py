"""Render PRISMA flow diagrams: a Graphviz figure plus a Mermaid text block."""

from __future__ import annotations

from pathlib import Path

import graphviz
import structlog

from surveyer.config import SearchConfig
from surveyer.models import Ledger
from surveyer.prisma.graphviz_render import to_graphviz
from surveyer.prisma.mermaid_render import to_mermaid
from surveyer.prisma.model import PrismaModel, build_model

log = structlog.get_logger()

__all__ = [
    "PrismaModel",
    "build_model",
    "render_prisma",
    "to_graphviz",
    "to_mermaid",
]

_RASTER_FORMATS = ("svg", "pdf", "png")


def render_prisma(
    ledger: Ledger,
    search: SearchConfig,
    out_dir: str | Path,
    *,
    llm_model: str | None = None,
    show_manual_screening: bool = False,
) -> None:
    """Write prisma.{mmd,svg,pdf,png} into out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model = build_model(
        ledger,
        search,
        llm_model=llm_model,
        show_manual_screening=show_manual_screening,
    )

    (out_dir / "prisma.mmd").write_text(to_mermaid(model))

    dot = to_graphviz(model)
    stem = out_dir / "prisma"
    try:
        for fmt in _RASTER_FORMATS:
            dot.format = fmt
            dot.render(str(stem), cleanup=True)
    except graphviz.ExecutableNotFound:
        log.warning(
            "prisma.graphviz_missing",
            hint="install the graphviz `dot` binary (e.g. `brew install graphviz`)",
        )
        stem.unlink(missing_ok=True)
        (out_dir / "prisma.dot").write_text(dot.source)
