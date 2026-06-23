"""Backend-agnostic description of a PRISMA flow chart."""

from __future__ import annotations

import msgspec

from surveyer.config import SearchConfig
from surveyer.models import Ledger

MAX_PANEL_TERMS = 6  # truncate long synonym

# Debug switch: put to True to render the "search completeness"
SHOW_COMPLETENESS_TABLE = False


class ExclusionBox(msgspec.Struct, kw_only=True):
    """A right-hand "records excluded" box attached to a process row."""

    label: str
    count: int
    breakdown: list[tuple[str, int]] = []  # (reason, count) sub-lines


class Row(msgspec.Struct, kw_only=True):
    """One process box in the vertical flow below the per-source boxes."""

    id: str
    swimlane: str
    title: str
    count: int | None = None
    exclusion: ExclusionBox | None = None
    dashed: bool = False  # optional styling


class SourceCompleteness(msgspec.Struct, kw_only=True):
    """Per-source retrieval audit row: requested/retrieved/API-total + truncation."""

    source: str
    requested: int
    retrieved: int
    api_total: int | None = None
    truncated: bool = False
    partial_total: bool = False


class PrismaModel(msgspec.Struct, kw_only=True):
    """Everything both renderers need, derived once from the ledger + search."""

    sources: list[tuple[str, int]]
    total_identified: int
    duplicates_removed: int
    after_dedup: int
    rows: list[Row]
    query_panel: str | None = None
    show_manual_screening: bool = False
    llm_model: str | None = None
    previous_included: int | None = None
    source_completeness: list[SourceCompleteness] = []
    snowball_rows: list[Row] = []


def _build_query_panel(search: SearchConfig) -> str | None:
    """Compact text for the search-query side panel, or None if empty."""
    if search.concepts:
        lines = []
        for concept, synonyms in search.concepts.items():
            shown = synonyms[:MAX_PANEL_TERMS]
            text = " OR ".join(shown)
            if len(synonyms) > MAX_PANEL_TERMS:
                text += " OR …"
            lines.append(f"{concept}: {text}")
        return "\n".join(lines)
    if search.queries:
        return "\n".join(f"{q.label}: {q.terms}" for q in search.queries)
    return None


def _build_completeness(ledger: Ledger) -> list[SourceCompleteness]:
    """Aggregate ledger.retrieval into one audit row per source (first-seen order)."""
    order: list[str] = []
    rows: dict[str, list] = {}
    for qr in ledger.retrieval:
        if qr.source not in rows:
            order.append(qr.source)
            rows[qr.source] = []
        rows[qr.source].append(qr)

    out: list[SourceCompleteness] = []
    for source in order:
        group = rows[source]
        totals = [qr.api_total for qr in group if qr.api_total is not None]
        api_total = sum(totals) if totals else None
        partial_total = bool(totals) and len(totals) < len(group)
        truncated = any(
            qr.api_total is not None and qr.retrieved < qr.api_total for qr in group
        )
        out.append(
            SourceCompleteness(
                source=source,
                requested=group[0].requested,  # per-query cap, shown as-is
                retrieved=sum(qr.retrieved for qr in group),
                api_total=api_total,
                truncated=truncated,
                partial_total=partial_total,
            )
        )
    return out


def _build_snowball_rows(snow, *, llm_model: str | None) -> list[Row]:
    """Build the citation-searching arm: identified -> dedup -> screened -> included."""
    after_dedup = snow.identified - snow.duplicates_removed
    assessed = after_dedup - snow.excluded_keyword
    keyword_breakdown = sorted(
        snow.excluded_keyword_reasons.items(), key=lambda kv: kv[1], reverse=True
    )
    rows: list[Row] = [
        Row(
            id="snow_identified",
            swimlane="identification",
            title="Records identified via citation searching",
            count=snow.identified,
        ),
        Row(
            id="snow_dedup",
            swimlane="identification",
            title="Records after duplicates removed",
            count=after_dedup,
            exclusion=ExclusionBox(
                label="Duplicates removed", count=snow.duplicates_removed
            ),
        ),
        Row(
            id="snow_screened",
            swimlane="screening",
            title="Records screened",
            count=after_dedup,
            exclusion=ExclusionBox(
                label="Excluded by keyword filter",
                count=snow.excluded_keyword,
                breakdown=keyword_breakdown,
            ),
        ),
    ]
    if llm_model is not None:
        rows.append(
            Row(
                id="snow_assessed",
                swimlane="screening",
                title=f"Records assessed by {llm_model}",
                count=assessed,
                exclusion=ExclusionBox(
                    label="Excluded by relevance score", count=snow.excluded_llm
                ),
            )
        )
    rows.append(
        Row(
            id="snow_included",
            swimlane="included",
            title="Studies included via citation searching",
            count=snow.included,
        )
    )
    return rows


def build_model(
    ledger: Ledger,
    search: SearchConfig,
    *,
    llm_model: str | None = None,
    show_manual_screening: bool = False,
) -> PrismaModel:
    """Derive a PrismaModel from a provenance ledger and the search config."""
    after_dedup = ledger.after_dedup() - ledger.already_screened
    assessed = after_dedup - ledger.excluded_keyword
    keyword_breakdown = sorted(
        ledger.excluded_keyword_reasons.items(), key=lambda kv: kv[1], reverse=True
    )

    dedup_exclusion = ExclusionBox(
        label="Duplicates removed", count=ledger.duplicates_removed
    )
    if ledger.already_screened:
        dedup_exclusion = ExclusionBox(
            label="Records removed before screening",
            count=ledger.duplicates_removed + ledger.already_screened,
            breakdown=[
                ("duplicate records", ledger.duplicates_removed),
                ("already screened in previous version", ledger.already_screened),
            ],
        )

    rows: list[Row] = [
        Row(
            id="identified",
            swimlane="identification",
            title="Records identified",
            count=ledger.total_identified(),
        ),
        Row(
            id="dedup",
            swimlane="identification",
            title="Records after duplicates removed",
            count=after_dedup,
            exclusion=dedup_exclusion,
        ),
        Row(
            id="screened",
            swimlane="screening",
            title="Records screened",
            count=after_dedup,
            exclusion=ExclusionBox(
                label="Excluded by keyword filter",
                count=ledger.excluded_keyword,
                breakdown=keyword_breakdown,
            ),
        ),
    ]
    if llm_model is not None:
        rows.append(
            Row(
                id="assessed",
                swimlane="screening",
                title=f"Records assessed by {llm_model}",
                count=assessed,
                exclusion=ExclusionBox(
                    label="Excluded by relevance score", count=ledger.excluded_llm
                ),
            )
        )
    if show_manual_screening:
        rows.append(
            Row(
                id="manual",
                swimlane="screening",
                title="Manual screening (by hand)",
                dashed=True,
            )
        )
    snowball_rows: list[Row] = []
    if ledger.snowball is not None:
        snowball_rows = _build_snowball_rows(ledger.snowball, llm_model=llm_model)

    if ledger.previously_included or ledger.snowball is not None:
        main_label = (
            "Studies included from databases"
            if ledger.snowball is not None
            else "New studies included"
        )
        rows.append(
            Row(
                id="included",
                swimlane="included",
                title=main_label,
                count=ledger.included,
            )
        )
        rows.append(
            Row(
                id="total",
                swimlane="included",
                title="Total studies included in review",
                count=ledger.total_included(),
            )
        )
    else:
        rows.append(
            Row(
                id="included",
                swimlane="included",
                title="Studies included",
                count=ledger.included,
            )
        )

    return PrismaModel(
        sources=[(sc.source, sc.count) for sc in ledger.identified],
        total_identified=ledger.total_identified(),
        duplicates_removed=ledger.duplicates_removed,
        after_dedup=after_dedup,
        rows=rows,
        query_panel=_build_query_panel(search),
        show_manual_screening=show_manual_screening,
        llm_model=llm_model,
        previous_included=ledger.previously_included or None,
        source_completeness=(
            _build_completeness(ledger) if SHOW_COMPLETENESS_TABLE else []
        ),
        snowball_rows=snowball_rows,
    )
