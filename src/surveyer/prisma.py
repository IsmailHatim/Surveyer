"""Render a PRISMA flow diagram from a ledger."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless no display
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from surveyer.models import Ledger


def _box(ax, x, y, w, h, text, *, color="#dbe9f6"):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.02",
            linewidth=1,
            edgecolor="#2b5d8b",
            facecolor=color,
        )
    )
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9, wrap=True)


def _arrow(ax, x1, y1, x2, y2):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=14, color="#2b5d8b"
        )
    )


def render_prisma(ledger: Ledger, path: str | Path) -> None:
    """Draw Identification -> Screening -> Included and save to path."""
    fig, ax = plt.subplots(figsize=(8, 10))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14)
    ax.axis("off")

    sources_txt = "\n".join(f"{sc.source}: {sc.count}" for sc in ledger.identified)
    _box(
        ax,
        1,
        12,
        8,
        1.6,
        f"Records identified (n = {ledger.total_identified()})\n{sources_txt}",
        color="#cfe2cf",
    )

    _box(
        ax,
        1,
        9.5,
        8,
        1.2,
        f"Records after duplicates removed (n = {ledger.after_dedup()})\n"
        f"Duplicates removed (n = {ledger.duplicates_removed})",
    )

    _box(
        ax,
        1,
        7,
        8,
        1.2,
        f"Records screened by keyword (n = {ledger.after_dedup()})",
    )
    _box(
        ax,
        6.2,
        5.2,
        3.5,
        1.0,
        f"Excluded by keyword\n(n = {ledger.excluded_keyword})",
        color="#f6dada",
    )

    kept_after_kw = ledger.after_dedup() - ledger.excluded_keyword
    _box(
        ax,
        1,
        3.2,
        5,
        1.2,
        f"Assessed by LLM relevance (n = {kept_after_kw})",
    )
    _box(
        ax,
        6.2,
        3.2,
        3.5,
        1.0,
        f"Excluded by LLM score\n(n = {ledger.excluded_llm})",
        color="#f6dada",
    )

    _box(
        ax, 1, 0.6, 8, 1.2, f"Studies included (n = {ledger.included})", color="#cfe2cf"
    )

    _arrow(ax, 5, 12, 5, 10.7)
    _arrow(ax, 5, 9.5, 5, 8.2)
    _arrow(ax, 5, 7, 5, 4.4)
    _arrow(ax, 5, 7, 6.2, 5.7)  # keyword exclusion branch
    _arrow(ax, 3.5, 3.2, 3.5, 1.8)
    _arrow(ax, 6, 3.7, 6.2, 3.7)  # llm exclusion branch

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
