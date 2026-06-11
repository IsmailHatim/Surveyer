"""Home screen: logo, pipeline overview, and entry into the config picker."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static

from surveyer.tui.logo import LOGO

_TAGLINE = "reproducible literature search for academic surveys"

_STEPS = """\
[b $accent]1[/]  [b]Fetch   [/]query DBLP, OpenAlex, Semantic Scholar, Google Scholar
[b $accent]2[/]  [b]Dedup   [/]merge duplicates by DOI and title match
[b $accent]3[/]  [b]Filter  [/]keyword concepts and optional LLM relevance scoring
[b $accent]4[/]  [b]BibTeX  [/]resolve citations: DBLP key, then DOI, then local
[b $accent]5[/]  [b]Export  [/]survey.xlsx and .csv plus references.bib
[b $accent]6[/]  [b]PRISMA  [/]render the flow diagram from the ledger\
"""

_HINT = "[b]enter [/]choose a survey config    [b]q [/]quit"


class HomeScreen(Screen):
    """Landing page shown when Surveyer starts without a config."""

    BINDINGS = [
        ("enter", "start", "Choose config"),
        ("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Build the centered logo, tagline, steps panel and key hints."""
        with Vertical(id="home"):
            yield Static(LOGO, id="home-logo", markup=False)
            yield Static(_TAGLINE, id="home-tagline")
            yield Static(_STEPS, id="home-steps")
            yield Static(_HINT, id="home-hint")
        yield Footer()

    def on_mount(self) -> None:
        """Title the steps panel."""
        self.query_one("#home-steps").border_title = "the pipeline"

    def action_start(self) -> None:
        """Open the config picker."""
        from surveyer.tui.picker import PickerScreen

        self.app.push_screen(PickerScreen())
