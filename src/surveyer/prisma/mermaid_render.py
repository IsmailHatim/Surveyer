"""Render a PrismaModel as Mermaid flowchart text."""

from __future__ import annotations

from surveyer.prisma.model import PrismaModel


def _text(title: str, count: int | None) -> str:
    """Node label with an optional count on a second line."""
    if count is None:
        return title
    return f"{title}<br/>n = {count}"


def to_mermaid(model: PrismaModel) -> str:
    """Return a Mermaid flowchart TD block describing the PRISMA flow."""
    lines = ["flowchart TD"]

    src_ids: list[str] = []
    for i, (name, count) in enumerate(model.sources):
        sid = f"src{i}"
        src_ids.append(sid)
        lines.append(f'    {sid}["{name}<br/>n = {count}"]')

    first = model.rows[0].id
    for sid in src_ids:
        lines.append(f"    {sid} --> {first}")

    prev: str | None = None
    for row in model.rows:
        lines.append(f'    {row.id}["{_text(row.title, row.count)}"]')
        if row.exclusion is not None:
            eid = f"{row.id}_excl"
            excl = _text(row.exclusion.label, row.exclusion.count)
            for reason, n in row.exclusion.breakdown:
                excl += f"<br/>{reason}: {n}"
            lines.append(f'    {eid}["{excl}"]')
            lines.append(f"    {row.id} --> {eid}")
        if prev is not None:
            lines.append(f"    {prev} --> {row.id}")
        prev = row.id

    snow_prev: str | None = None
    for row in model.snowball_rows:
        lines.append(f'    {row.id}["{_text(row.title, row.count)}"]')
        if row.exclusion is not None:
            eid = f"{row.id}_excl"
            excl = _text(row.exclusion.label, row.exclusion.count)
            for reason, n in row.exclusion.breakdown:
                excl += f"<br/>{reason}: {n}"
            lines.append(f'    {eid}["{excl}"]')
            lines.append(f"    {row.id} --> {eid}")
        if snow_prev is not None:
            lines.append(f"    {snow_prev} --> {row.id}")
        snow_prev = row.id
    if model.snowball_rows:
        # Converge the citation-searching arm on the shared total box.
        lines.append(f"    {model.snowball_rows[-1].id} --> total")

    if model.previous_included is not None:
        lines.append(
            '    previous["Studies included in previous version of review'
            f'<br/>n = {model.previous_included}"]'
        )
        lines.append("    previous --> total")

    if model.query_panel:
        panel = model.query_panel.replace("\n", "<br/>")
        lines.append(f'    query["Search query<br/>{panel}"]')
        lines.append(f"    query -.-> {first}")

    lines += _completeness_lines(model)

    return "\n".join(lines) + "\n"


def _completeness_lines(model: PrismaModel) -> list[str]:
    """A single node summarising per-source retrieved / API-total + truncation."""
    if not model.source_completeness:
        return []
    parts = ["Search completeness", "source · req/query · retrieved · API total"]
    truncated = False
    for c in model.source_completeness:
        total = "n/a" if c.api_total is None else str(c.api_total)
        if c.partial_total:
            total += "*"
        flag = " ⚠️" if c.truncated else ""
        truncated = truncated or c.truncated
        parts.append(f"{c.source} · {c.requested} · {c.retrieved} · {total}{flag}")
    if truncated:
        parts.append("⚠️ retrieved fewer than the database reports — search capped")
    body = "<br/>".join(parts)
    return [f'    completeness["{body}"]', f"    {model.rows[-1].id} -.-> completeness"]
