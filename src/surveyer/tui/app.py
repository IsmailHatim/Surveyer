"""Textual application entry point for the Surveyer dashboard."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from surveyer.tui.home import HomeScreen


class SurveyerApp(App):
    """Surveyer terminal dashboard."""

    TITLE = "Surveyer"
    BINDINGS = [("q", "quit", "Quit")]

    CSS = """
    #home {
        align: center middle;
        width: 1fr;
        height: 1fr;
    }
    #home-logo {
        width: auto;
        color: $accent;
        margin-bottom: 1;
    }
    #home-tagline {
        width: auto;
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }
    #home-steps {
        width: auto;
        border: round $primary;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 1 2;
    }
    #home-hint {
        width: auto;
        color: $text-muted;
        margin-top: 1;
    }
    HomeScreen {
        align: center middle;
    }

    PickerScreen {
        align: center middle;
    }
    #picker-box {
        width: 80;
        height: auto;
        border: round $primary;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 1 2;
    }
    #picker-box Label {
        color: $text-muted;
        margin-top: 1;
    }
    #config_list {
        height: auto;
        max-height: 12;
        margin-top: 1;
        background: transparent;
    }
    #path_input {
        margin-top: 1;
    }

    #left {
        width: 55%;
    }
    #form {
        width: 1fr;
        border: round $primary;
        border-title-color: $accent;
        border-title-style: bold;
        padding: 0 2 1 2;
    }
    #form Label {
        color: $text-muted;
        margin-top: 1;
    }
    #form .section-title {
        color: $accent;
        text-style: bold;
        margin-top: 1;
        border-bottom: solid $panel;
        width: 1fr;
    }
    #form .row {
        height: auto;
    }
    #form .cell {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }
    #form .cell Label {
        margin-top: 1;
    }
    #form Checkbox {
        background: transparent;
        border: none;
        padding: 0;
    }
    #llm_enabled {
        margin-top: 1;
        margin-bottom: 1;
    }
    #concepts {
        margin-top: 1;
        color: $text-muted;
        border: round $panel;
        padding: 0 1;
    }
    #concepts_editor {
        width: 1fr;
        border: round $primary;
        border-title-color: $accent;
        padding: 0 2 1 2;
    }
    #edit-concepts {
        margin-bottom: 1;
        width: 1fr;
    }
    .ce-title {
        color: $accent;
        text-style: bold;
        margin-top: 1;
        border-bottom: solid $panel;
        width: 1fr;
    }
    .ce-actions {
        height: auto;
        margin-top: 1;
    }
    .ce-actions Button {
        margin-right: 1;
    }
    .ce-hint {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
    }
    #search-rows, #filter-rows {
        height: auto;
    }
    .concept-row {
        height: auto;
        margin-top: 1;
    }
    .concept-name {
        width: 24;
        margin-right: 1;
    }
    .concept-syn {
        width: 1fr;
        margin-right: 1;
    }
    .concept-del {
        width: 5;
        min-width: 5;
    }
    #log {
        border: round $success;
        border-title-color: $success;
        border-title-style: bold;
        margin-left: 1;
        padding: 0 1;
        background: transparent;
    }
    """

    def __init__(self, config_path: Path | None = None) -> None:
        """Remember the config to open."""
        super().__init__()
        self._config_path = config_path

    def on_mount(self) -> None:
        """Open the dashboard directly with -c, otherwise show the home page."""
        self.push_screen(HomeScreen())
        if self._config_path is not None:
            from surveyer.tui.dashboard import DashboardScreen

            self.push_screen(DashboardScreen(self._config_path))


def run_tui(config: str | None = None) -> None:
    """Launch the Surveyer dashboard app."""
    SurveyerApp(Path(config) if config else None).run()
