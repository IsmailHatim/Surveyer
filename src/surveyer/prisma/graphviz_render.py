"""Render a PrismaModel as a Graphviz Digraph."""

from __future__ import annotations

import json
from itertools import groupby

import graphviz

from surveyer.prisma.model import ExclusionBox, PrismaModel

_FILL_GREEN = "#cfe2cf"  # identification / included
_FILL_BLUE = "#dbe9f6"  # screening process boxes
_FILL_RED = "#f6dada"  # exclusion boxes
_FILL_TEAL = "#3a9188"  # swimlane labels
_FILL_NOTE = "#fff7d6"  # query panel
_EDGE = "#2b5d8b"

_BAND_WIDTH = "1.25"
_BAND_HEIGHT = "0.9"

_STAGE_LABEL = {
    "identification": "Identification",
    "screening": "Screening",
    "included": "Included",
}


def _text(title: str, count: int | None) -> str:
    if count is None:
        return title
    return f"{title}\nn = {count}"


def _exclusion_text(excl: ExclusionBox) -> str:
    """Exclusion-box label: title, count, then one line per breakdown reason."""
    text = _text(excl.label, excl.count)
    for reason, n in excl.breakdown:
        text += f"\n{reason}: {n}"
    return text


def to_graphviz(model: PrismaModel) -> graphviz.Digraph:
    """Build a Graphviz Digraph for the PRISMA flow (no binary needed to build)."""
    dot = _build(model, _estimate_rail_width(model))
    span = _measure_source_span(dot, len(model.sources))
    if span is not None:
        dot = _build(model, span)
    return dot


def _estimate_rail_width(model: PrismaModel) -> float:
    """Fallback rail width (inches) when the layout can't be measured."""
    return max(1.0, len(model.sources) * 1.4)


def _measure_source_span(dot: graphviz.Digraph, n_sources: int) -> float | None:
    """Width in inches between the outermost source-box centres, via -Tjson."""
    if n_sources == 0:
        return None
    try:
        raw = dot.pipe(format="json")
    except (graphviz.ExecutableNotFound, graphviz.CalledProcessError):
        return None
    try:
        data = json.loads(raw.decode())
    except (ValueError, UnicodeDecodeError):
        return None
    centres = [
        float(obj["pos"].split(",")[0])
        for obj in data.get("objects", [])
        if obj.get("name", "").startswith("src")
        and obj.get("name") != "src_bus"
        and "pos" in obj
    ]
    if len(centres) < 2:
        return None
    return (max(centres) - min(centres)) / 72.0  # points to inches


def _build(model: PrismaModel, rail_width: float) -> graphviz.Digraph:
    """Assemble the Digraph with the bus rail at the given width (inches)."""
    dot = graphviz.Digraph("prisma")
    dot.attr(rankdir="TB", nodesep="0.35", ranksep="0.4", splines="ortho")
    dot.attr(
        "node",
        shape="box",
        style="rounded,filled",
        fontname="Helvetica",
        fontsize="10",
        color=_EDGE,
    )
    dot.attr("edge", color=_EDGE, arrowsize="0.8")

    with dot.subgraph() as s:
        s.attr(rank="same")
        for i, (name, count) in enumerate(model.sources):
            s.node(f"src{i}", f"{name}\nn = {count}", fillcolor=_FILL_GREEN)
        for i in range(len(model.sources) - 1):
            s.edge(f"src{i}", f"src{i + 1}", style="invis")

    first = model.rows[0].id
    if model.sources:
        dot.node(
            "src_bus",
            "",
            shape="box",
            width=f"{rail_width:.2f}",
            height="0.01",
            fixedsize="true",
            style="filled",
            fillcolor=_EDGE,
            color=_EDGE,
            group="spine",
        )
        for i in range(len(model.sources)):
            dot.edge(f"src{i}", "src_bus", arrowhead="none", tailport="s", headport="n")
        dot.edge("src_bus", first, tailport="s", headport="n")

    prev: str | None = None
    for row in model.rows:
        fill = _FILL_BLUE if row.swimlane == "screening" else _FILL_GREEN
        style = "rounded,filled,dashed" if row.dashed else "rounded,filled"
        dot.node(
            row.id,
            _text(row.title, row.count),
            fillcolor=fill,
            style=style,
            group="spine",
        )
        if row.exclusion is not None:
            eid = f"{row.id}_excl"
            dot.node(eid, _exclusion_text(row.exclusion), fillcolor=_FILL_RED)
            with dot.subgraph() as s:
                s.attr(rank="same")
                s.node(row.id)
                s.node(eid)
            dot.edge(row.id, eid)
        if prev is not None:
            dot.edge(prev, row.id)
        prev = row.id

    _add_swimlane_bands(dot, model)

    # Search-query panel: to the right
    if model.query_panel:
        dot.node(
            "query",
            f"Search query\n{model.query_panel}",
            shape="note",
            fillcolor=_FILL_NOTE,
            fontsize="9",
        )
        excl_anchor = next(
            (f"{r.id}_excl" for r in model.rows if r.exclusion is not None), first
        )
        with dot.subgraph() as s:
            s.attr(rank="same")
            s.node(excl_anchor)
            s.node("query")
            s.edge(excl_anchor, "query", style="invis")

    return dot


def _add_swimlane_bands(dot: graphviz.Digraph, model: PrismaModel) -> None:
    """One teal label block per stage, left-aligned in a single column."""
    # Anchor node id for every rank
    rank_anchors: list[tuple[str, str]] = []
    if model.sources:
        rank_anchors.append(("identification", "src0"))
    for row in model.rows:
        rank_anchors.append((row.swimlane, row.id))

    stages = [
        (key, [anchor for _, anchor in grp])
        for key, grp in groupby(rank_anchors, key=lambda x: x[0])
    ]

    prev_band: str | None = None
    for key, anchors in stages:
        anchor = anchors[len(anchors) // 2]  # middle rank
        band = f"stage_{key}"
        dot.node(
            band,
            _STAGE_LABEL[key],
            shape="box",
            style="filled",
            fillcolor=_FILL_TEAL,
            fontcolor="white",
            fontname="Helvetica-Bold",
            fontsize="11",
            fixedsize="true",
            width=_BAND_WIDTH,
            height=_BAND_HEIGHT,
            group="bands",
        )
        with dot.subgraph() as s:
            s.attr(rank="same")
            s.node(band)
            s.node(anchor)
            if prev_band is None:
                s.edge(band, anchor, style="invis")
        if prev_band is not None:
            dot.edge(prev_band, band, style="invis")
        prev_band = band
