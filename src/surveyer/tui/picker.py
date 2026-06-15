"""Config picker screen: choose an existing TOML or create one from template."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, OptionList
from textual.widgets.option_list import Option

TEMPLATE = """\
[project]
name = "my-survey"
output_dir = "runs/my-survey"
export_format = "xlsx"

[search]
year_min = 2018
year_max = 2026
max_results_per_query = 200
sources = ["dblp", "openalex"]

[[search.queries]]
label = "main"
terms = "your search terms here"

[filter.keyword]
exclude = ["survey", "review"]

[filter.llm]
enabled = false
provider = "openai"
model = "gpt-4o-mini"
threshold = 0.6
survey_abstract = ""
"""


# Known TOML files that are never survey configs.
_NOT_CONFIGS = {"pyproject.toml", "uv.lock", "ruff.toml", ".ruff.toml"}


def discover_configs() -> list[Path]:
    """List survey *.toml files in the working directory and examples/, sorted.

    Tooling files like ``pyproject.toml`` are excluded.
    """
    found = sorted(Path.cwd().glob("*.toml"))
    examples = Path.cwd() / "examples"
    if examples.is_dir():
        found += sorted(examples.glob("*.toml"))
    return [p for p in found if p.name not in _NOT_CONFIGS]


def _display_path(path: Path) -> str:
    """Render a discovered config path relative to the working directory."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


class PickerScreen(Screen):
    """Pick an existing survey TOML or type a path to create one."""

    BINDINGS = [("escape", "back", "Home")]

    def action_back(self) -> None:
        """Return to the home screen."""
        self.app.pop_screen()

    def compose(self) -> ComposeResult:
        """Build the picker layout."""
        with Vertical(id="picker-box"):
            yield Label("Select a survey config:")
            yield OptionList(
                *[Option(_display_path(p), id=str(p)) for p in discover_configs()],
                id="config_list",
            )
            yield Label("...or type a path (created from template if missing):")
            yield Input(placeholder="path/to/survey.toml", id="path_input")
        yield Footer()

    def on_mount(self) -> None:
        """Title the picker box."""
        self.query_one("#picker-box").border_title = "surveyer - choose a survey"

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Open the selected config in the dashboard."""
        self._open(Path(str(event.option.id)))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Open (or create from template, then open) the typed path."""
        text = event.value.strip()
        if not text:
            return
        path = Path(text)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(TEMPLATE)
        self._open(path)

    def _open(self, path: Path) -> None:
        from surveyer.tui.dashboard import DashboardScreen

        self.app.push_screen(DashboardScreen(path))
