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

    return "\n".join(lines) + "\n"
