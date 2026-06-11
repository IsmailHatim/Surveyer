"""Backend-agnostic description of a PRISMA flow chart."""

from __future__ import annotations

import msgspec

from surveyer.config import SearchConfig
from surveyer.models import Ledger

MAX_PANEL_TERMS = 6  # truncate long synonym


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
    if ledger.previously_included:
        rows.append(
            Row(
                id="included",
                swimlane="included",
                title="New studies included",
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
    )
