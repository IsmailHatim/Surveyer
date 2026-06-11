"""Pilot smoke tests for the Textual app."""

from pathlib import Path

import pytest

pytest.importorskip("textual")

from surveyer.tui.app import SurveyerApp  # noqa: E402
from surveyer.tui.home import HomeScreen  # noqa: E402
from surveyer.tui.logo import LOGO  # noqa: E402
from surveyer.tui.picker import TEMPLATE, PickerScreen, discover_configs  # noqa: E402

VALID_TOML = TEMPLATE


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "survey.toml"
    p.write_text(VALID_TOML)
    return p


def test_discover_configs_lists_cwd_and_examples(tmp_path, monkeypatch):
    (tmp_path / "a.toml").write_text("x = 1")
    (tmp_path / "pyproject.toml").write_text("x = 1")  # tooling file: excluded
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "b.toml").write_text("x = 1")
    monkeypatch.chdir(tmp_path)
    found = [p.name for p in discover_configs()]
    assert found == ["a.toml", "b.toml"]


async def test_app_without_config_shows_home():
    app = SurveyerApp()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)
        # the logo and the pipeline steps are on the page
        assert str(app.screen.query_one("#home-logo").render()) == LOGO
        steps = str(app.screen.query_one("#home-steps").render())
        for word in ("Fetch", "Dedup", "Filter", "BibTeX", "Export", "PRISMA"):
            assert word in steps


async def test_home_enter_opens_picker():
    app = SurveyerApp()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, PickerScreen)


async def test_picker_input_creates_from_template(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = SurveyerApp()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        await pilot.press("enter")  # leave the home screen
        await pilot.pause()
        path_input = app.screen.query_one("#path_input")
        path_input.focus()
        await pilot.pause()
        path_input.value = "new_survey.toml"
        await pilot.press("enter")
        await pilot.pause()
    assert (tmp_path / "new_survey.toml").read_text() == TEMPLATE


async def test_escape_navigates_back_to_home(config_file):
    """Esc pops from the dashboard back to home, even when launched with -c."""
    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        assert not isinstance(app.screen, HomeScreen)  # dashboard on top
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)


async def test_escape_from_picker_returns_home():
    app = SurveyerApp()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, PickerScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, HomeScreen)
