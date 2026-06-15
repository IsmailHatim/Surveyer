"""Config dashboard: form for the daily knobs, $EDITOR fallback, run panel."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import tomlkit
import tomlkit.exceptions
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    ContentSwitcher,
    Footer,
    Input,
    Label,
    RichLog,
    Select,
    Static,
)

from surveyer.config import VALID_LLM_PROVIDERS
from surveyer.models import Ledger
from surveyer.tui.concepts import ConceptsEditor
from surveyer.tui.config_io import (
    TOGGLEABLE_SOURCES,
    FormValues,
    apply_form,
    extract_form,
    load_document,
    save_document,
    validate_text,
)


def _opt_str(value: int | None) -> str:
    """Render an optional int for an Input widget."""
    return "" if value is None else str(value)


def _opt_int(text: str) -> int | None:
    """Parse an optional int from an Input widget ('' -> None)."""
    text = text.strip()
    return int(text) if text else None


class DashboardScreen(Screen):
    """Edit one survey TOML and launch pipeline runs from it."""

    BINDINGS = [
        ("s", "save", "Save"),
        ("e", "edit", "Open in $EDITOR"),
        ("c", "edit_concepts", "Concepts"),
        ("ctrl+r", "reset_concepts", "Reset concepts"),
        ("r", "run", "Run"),
        ("f", "fetch", "Fetch only"),
        ("o", "open_output", "Open output"),
        ("escape", "back", "Back"),
        ("q", "app.quit", "Quit"),
    ]

    def __init__(self, path: Path) -> None:
        """Load the config document this dashboard edits."""
        super().__init__()
        self._path = Path(path)
        self.load_error: str | None = None
        try:
            self._doc = load_document(self._path)
            self._values = extract_form(self._doc)
        except (OSError, ValueError, tomlkit.exceptions.ParseError) as exc:
            self.load_error = str(exc)
            self._doc = tomlkit.document()
            self._values = FormValues()
        self._pipeline_running = False
        self._concepts_opened = False

    def compose(self) -> ComposeResult:
        """Build the form panel and the log pane."""
        v = self._values
        with Horizontal():
            with ContentSwitcher(initial="form", id="left"):
                with VerticalScroll(id="form"):
                    yield Button("Edit concepts ▸", id="edit-concepts")
                    yield Static("project", classes="section-title")
                    yield Label("Name")
                    yield Input(value=v.name, id="name")
                    yield Label("Output dir")
                    yield Input(value=v.output_dir, id="output_dir")

                    yield Static("search", classes="section-title")
                    yield Label("Sources")
                    for src in TOGGLEABLE_SOURCES:
                        yield Checkbox(src, value=src in v.sources, id=f"src_{src}")
                    with Horizontal(classes="row"):
                        with Vertical(classes="cell"):
                            yield Label("Year min")
                            yield Input(value=_opt_str(v.year_min), id="year_min")
                        with Vertical(classes="cell"):
                            yield Label("Year max")
                            yield Input(value=_opt_str(v.year_max), id="year_max")
                        with Vertical(classes="cell"):
                            yield Label("Max results")
                            yield Input(
                                value=str(v.max_results_per_query), id="max_results"
                            )

                    yield Static("dedup", classes="section-title")
                    yield Label("Fuzzy title threshold (0-100)")
                    yield Input(
                        value=str(v.dedup_title_threshold), id="dedup_title_threshold"
                    )

                    yield Static("filters", classes="section-title")
                    yield Label("Keyword exclude (comma-separated)")
                    yield Input(value=", ".join(v.exclude), id="exclude")
                    yield Checkbox(
                        "LLM relevance filter", value=v.llm_enabled, id="llm_enabled"
                    )
                    with Horizontal(classes="row"):
                        with Vertical(classes="cell"):
                            yield Label("Provider")
                            yield Select(
                                [(p, p) for p in sorted(VALID_LLM_PROVIDERS)],
                                value=v.llm_provider
                                if v.llm_provider in VALID_LLM_PROVIDERS
                                else Select.NULL,
                                allow_blank=True,
                                id="llm_provider",
                            )
                        with Vertical(classes="cell"):
                            yield Label("Model")
                            yield Input(value=v.llm_model, id="llm_model")
                        with Vertical(classes="cell"):
                            yield Label("Threshold")
                            yield Input(value=str(v.llm_threshold), id="llm_threshold")
                    yield Label("Ollama host (used when provider = ollama)")
                    yield Input(value=v.llm_host, id="llm_host")

                    yield Static("extend", classes="section-title")
                    yield Label("Screened xlsx (blank = off; needs xlsx export)")
                    yield Input(value=v.extend_xlsx, id="extend_xlsx")
                    yield Static(
                        self._concepts_summary_text(
                            v.search_concepts, v.filter_concepts
                        ),
                        id="concepts",
                    )

                    yield Static("run", classes="section-title")
                    yield Checkbox(
                        "Refresh — bypass HTTP cache, refetch from sources",
                        value=False,
                        id="refresh",
                    )
                yield ConceptsEditor(
                    v.search_concepts, v.filter_concepts, id="concepts_editor"
                )
            yield RichLog(id="log", wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        """Title the panels and surface a load error, if any."""
        self.query_one("#form").border_title = f"config - {self._path.name}"
        self.query_one("#log").border_title = "run log"
        if self.load_error is not None:
            self._write_log(
                f"Could not load {self._path}: {self.load_error}\n"
                "The form shows defaults; saving is disabled. "
                "Press E to edit the file directly, or Q to quit."
            )

    @staticmethod
    def _concepts_summary_text(search: list, filter_: list) -> str:
        """Read-only one-line-per-section summary of the current concept blocks."""
        lines = ["Concepts (press 'c' or the button to edit):"]
        for label, items in (("search", search), ("filter", filter_)):
            if items:
                blocks = ", ".join(
                    f"{i.name} ({len(i.synonyms)} synonyms)" for i in items
                )
                lines.append(f"  [{label}.concepts] {blocks}")
        if len(lines) == 1:
            lines.append("  (none)")
        return "\n".join(lines)

    def _refresh_concepts_summary(self) -> None:
        """Update the read-only summary from the editor's live rows."""
        editor = self.query_one(ConceptsEditor)
        self.query_one("#concepts", Static).update(
            self._concepts_summary_text(editor.read("search"), editor.read("filter"))
        )

    def _collect(self) -> FormValues | None:
        """Read the widgets back into FormValues; log and return None on bad input."""
        try:
            sources = [
                s for s in self._values.sources if s not in TOGGLEABLE_SOURCES
            ] + [
                s
                for s in TOGGLEABLE_SOURCES
                if self.query_one(f"#src_{s}", Checkbox).value
            ]
            if self._concepts_opened:
                editor = self.query_one(ConceptsEditor)
                search_concepts = editor.read("search")
                filter_concepts = editor.read("filter")
            else:
                search_concepts = self._values.search_concepts
                filter_concepts = self._values.filter_concepts
            return FormValues(
                name=self.query_one("#name", Input).value,
                output_dir=self.query_one("#output_dir", Input).value,
                sources=sources,
                year_min=_opt_int(self.query_one("#year_min", Input).value),
                year_max=_opt_int(self.query_one("#year_max", Input).value),
                max_results_per_query=int(self.query_one("#max_results", Input).value),
                dedup_title_threshold=int(
                    self.query_one("#dedup_title_threshold", Input).value
                ),
                exclude=[
                    t.strip()
                    for t in self.query_one("#exclude", Input).value.split(",")
                    if t.strip()
                ],
                llm_enabled=self.query_one("#llm_enabled", Checkbox).value,
                llm_provider=(
                    self._values.llm_provider
                    if (raw_prov := self.query_one("#llm_provider", Select).value)
                    is Select.NULL
                    else str(raw_prov)
                ),
                llm_model=self.query_one("#llm_model", Input).value,
                llm_host=self.query_one("#llm_host", Input).value,
                llm_threshold=float(self.query_one("#llm_threshold", Input).value),
                extend_xlsx=self.query_one("#extend_xlsx", Input).value,
                search_concepts=search_concepts,
                filter_concepts=filter_concepts,
            )
        except ValueError as exc:
            self._write_log(f"Invalid form value: {exc}")
            return None

    def _write_log(self, line: str) -> None:
        """Append a line to the log pane."""
        self.query_one("#log", RichLog).write(line)

    def action_save(self) -> None:
        """Validate the edited config and write it back if valid."""
        if self._pipeline_running:
            self._write_log("A run is in progress - wait for it to finish.")
            return
        if self.load_error is not None:
            self._write_log(
                "Saving is disabled because the file failed to load. "
                "Press E to fix it in $EDITOR."
            )
            return
        values = self._collect()
        if values is None:
            return
        try:
            doc = load_document(self._path)
        except (OSError, ValueError, tomlkit.exceptions.ParseError) as exc:
            self._write_log(f"Could not reload config for saving: {exc}")
            return
        apply_form(doc, values)
        error = validate_text(tomlkit.dumps(doc))
        if error is not None:
            self._write_log(f"Not saved - invalid config: {error}")
            return
        save_document(doc, self._path)
        self._doc, self._values = doc, values
        self._write_log(f"Saved {self._path}")

    def action_edit(self) -> None:
        """Suspend the app and open the TOML in $EDITOR, then reload."""
        if self._pipeline_running:
            self._write_log("A run is in progress - wait for it to finish.")
            return
        editor = os.environ.get("EDITOR", "vi")
        cmd = shlex.split(editor) + [str(self._path)]
        try:
            with self.app.suspend():
                subprocess.call(cmd)
        except (FileNotFoundError, OSError) as exc:
            self._write_log(f"$EDITOR not found: {exc}")
            return
        if self._path.is_file():
            error = validate_text(self._path.read_text(encoding="utf-8"))
            if error is not None:
                self.app.notify(f"Config is now invalid: {error}", severity="warning")
        self.app.switch_screen(DashboardScreen(self._path))

    def action_edit_concepts(self) -> None:
        """Swap the left panel to the concepts editor."""
        if self._pipeline_running:
            self._write_log("A run is in progress - wait for it to finish.")
            return
        self._concepts_opened = True
        self.query_one("#left", ContentSwitcher).current = "concepts_editor"

    def action_reset_concepts(self) -> None:
        """Reload concept blocks from the saved config, discarding unsaved edits."""
        if self._pipeline_running:
            self._write_log("A run is in progress - wait for it to finish.")
            return
        if self.query_one("#left", ContentSwitcher).current != "concepts_editor":
            return
        try:
            values = extract_form(load_document(self._path))
        except (OSError, ValueError, tomlkit.exceptions.ParseError) as exc:
            self._write_log(f"Could not reload concepts: {exc}")
            return
        self.query_one(ConceptsEditor).reset(
            values.search_concepts, values.filter_concepts
        )
        self.app.notify("Concepts reset to saved config.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the form's 'Edit concepts' button and the editor's nav buttons."""
        if event.button.id == "edit-concepts":
            self.action_edit_concepts()
            event.stop()
        elif event.button.id == "concepts-back":
            self.query_one("#left", ContentSwitcher).current = "form"
            self._refresh_concepts_summary()
            event.stop()
        elif event.button.id == "reset-concepts":
            self.action_reset_concepts()
            event.stop()

    def action_back(self) -> None:
        """From the editor, return to the form; from the form, leave the dashboard."""
        if self._pipeline_running:
            self._write_log("A run is in progress - wait for it to finish.")
            return
        switcher = self.query_one("#left", ContentSwitcher)
        if switcher.current == "concepts_editor":
            switcher.current = "form"
            self._refresh_concepts_summary()
            return
        self.app.pop_screen()

    def action_open_output(self) -> None:
        """Open the run's output directory in the system file manager."""
        out = Path(self.query_one("#output_dir", Input).value.strip() or ".")
        if not out.is_dir():
            self._write_log(f"Output dir does not exist yet: {out}")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(out)])
            elif sys.platform.startswith("win"):
                os.startfile(out)  # type: ignore[attr-defined]  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(out)])
        except OSError as exc:
            self._write_log(f"Could not open {out}: {exc}")

    def action_run(self) -> None:
        """Run the full pipeline in a worker thread."""
        self._start_run(fetch_only=False)

    def action_fetch(self) -> None:
        """Run fetch + dedup only (no filters, no bibtex) in a worker thread."""
        self._start_run(fetch_only=True)

    def _start_run(self, *, fetch_only: bool) -> None:
        """Launch the pipeline worker unless one is already running."""
        if self._pipeline_running:
            self._write_log("A run is already in progress.")
            return
        self._pipeline_running = True
        refresh = self.query_one("#refresh", Checkbox).value
        mode = "fetch-only" if fetch_only else "full pipeline"
        if refresh:
            mode += " (refresh)"
        self.query_one("#log", RichLog).border_title = f"run log - {mode} running…"
        self._write_log(f"Starting {mode} run...")
        self.run_worker(
            lambda: self._pipeline_worker(fetch_only=fetch_only, refresh=refresh),
            thread=True,
            exclusive=True,
        )

    def _pipeline_worker(self, *, fetch_only: bool, refresh: bool = False) -> None:
        """Worker body: run the pipeline, streaming structlog events to the pane."""
        import surveyer.pipeline as pipeline
        from surveyer.config import disable_filters, load_config
        from surveyer.tui.progress import forward_logs

        def write(line: str) -> None:
            self.app.call_from_thread(self._write_log, line)

        try:
            cfg = load_config(self._path)
            if fetch_only:
                disable_filters(cfg)
            with forward_logs(write):
                result = pipeline.run_pipeline(
                    cfg, resolve_bibtex=not fetch_only, refresh=refresh
                )
            led = result.ledger
            if fetch_only:
                write(
                    f"Done. Fetched and deduplicated {led.after_dedup()} "
                    f"records in {cfg.project.output_dir}/"
                )
            elif cfg.extend is not None:
                write(
                    f"Done. Carried over {led.previously_included}, skipped "
                    f"{led.already_screened} already screened, newly "
                    f"included {led.included} (total {led.total_included()}). "
                    f"Outputs in {cfg.project.output_dir}/"
                )
            else:
                write(
                    f"Done. Identified {led.total_identified()}, "
                    f"included {led.included}. "
                    f"Outputs in {cfg.project.output_dir}/"
                )
            write(
                self._prisma_text(
                    led, fetch_only=fetch_only, output_dir=cfg.project.output_dir
                )
            )
            if led.failed_sources:
                write("Warning: sources errored: " + ", ".join(led.failed_sources))
        except Exception as exc:
            write(f"ERROR: {exc}")
        finally:
            self.app.call_from_thread(self._finish_run)

    @staticmethod
    def _prisma_text(led: Ledger, *, fetch_only: bool, output_dir: str) -> str:
        """Plain-text PRISMA flow summary written to the log pane after a run."""
        rows: list[tuple[str, int]] = [
            ("identified", led.total_identified()),
            ("duplicates removed", led.duplicates_removed),
        ]
        if led.already_screened:
            rows.append(("already screened", led.already_screened))
        rows.append(("screened", led.after_dedup() - led.already_screened))
        if not fetch_only:
            rows.append(("excluded by keyword", led.excluded_keyword))
            rows.append(("excluded by LLM", led.excluded_llm))
            if led.previously_included:
                rows.append(("carried over", led.previously_included))
                rows.append(("included (new)", led.included))
                rows.append(("included (total)", led.total_included()))
            else:
                rows.append(("included", led.included))
        lines = ["", "========== PRISMA flow =========="]
        lines += [f" {label:<20}{value:>7}" for label, value in rows]
        lines.append(f" diagram  {output_dir}/prisma.svg (.pdf/.png/.mmd)")
        lines.append(" press 'o' to open output directory.")
        return "\n".join(lines)

    def _finish_run(self) -> None:
        """Mark the run as finished (re-enables run/save/edit)."""
        self._pipeline_running = False
        self.query_one("#log", RichLog).border_title = "run log"
