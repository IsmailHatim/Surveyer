"""Pilot tests for the dashboard form."""

from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.widgets import Button, ContentSwitcher, Input  # noqa: E402

from surveyer.tui.app import SurveyerApp  # noqa: E402
from surveyer.tui.concepts import ConceptRow, ConceptsEditor  # noqa: E402
from surveyer.tui.picker import TEMPLATE  # noqa: E402


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "survey.toml"
    p.write_text(TEMPLATE)
    return p


async def test_form_renders_config_values(config_file):
    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        assert app.screen.query_one("#name").value == "my-survey"
        assert app.screen.query_one("#src_dblp").value is True
        assert app.screen.query_one("#src_google_scholar").value is False
        assert app.screen.query_one("#llm_model").value == "gpt-4o-mini"
        # ollama host is editable, defaulting to the struct default
        assert app.screen.query_one("#llm_host").value == "http://localhost:11434"


async def test_save_writes_changed_value(config_file):
    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        name = app.screen.query_one("#name")
        name.value = "renamed-survey"
        app.screen.action_save()
        await pilot.pause()
    text = config_file.read_text()
    assert 'name = "renamed-survey"' in text
    # untouched parts survive verbatim
    assert 'terms = "your search terms here"' in text


async def test_save_rejects_invalid_config(config_file):
    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        # enabling LLM with an empty survey_abstract is invalid
        app.screen.query_one("#llm_enabled").value = True
        app.screen.action_save()
        await pilot.pause()
    assert "enabled = false" in config_file.read_text()  # file NOT rewritten


async def test_dashboard_with_missing_config_does_not_crash(tmp_path):
    app = SurveyerApp(tmp_path / "missing.toml")
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        # app must still be alive, with the load error surfaced
        assert app.screen is not None
        assert app.screen.load_error is not None


async def test_unknown_llm_provider_does_not_crash_mount(tmp_path):
    """An unknown provider in the TOML must not raise InvalidSelectValueError on mount."""
    # Build a config that is otherwise valid but has an unknown LLM provider.
    bad_text = TEMPLATE.replace('provider = "openai"', 'provider = "nope"')
    config_file = tmp_path / "survey.toml"
    config_file.write_text(bad_text)
    original_bytes = config_file.read_bytes()

    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        # The app must survive mounting (no InvalidSelectValueError).
        assert app.screen is not None

        # Trigger save
        app.screen.action_save()
        await pilot.pause()

    # File must be byte-for-byte unchanged: save was correctly refused.
    assert config_file.read_bytes() == original_bytes, (
        "action_save() must not overwrite the file when the provider is unknown"
    )


async def test_run_streams_logs_and_summary(config_file, monkeypatch):
    """Pipeline log events and the summary line appear in the log pane."""
    import structlog

    from surveyer.models import Ledger
    from surveyer.pipeline import PipelineResult

    def fake_run_pipeline(cfg, **kwargs):
        structlog.get_logger().info("fetch.source_done", source="dblp", count=2)
        return PipelineResult(ledger=Ledger(included=2), kept=[], excluded=[])

    monkeypatch.setattr("surveyer.pipeline.run_pipeline", fake_run_pipeline)

    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.action_run()
        await app.workers.wait_for_complete()
        await pilot.pause()
        richlog = app.screen.query_one("#log")
        log_lines = "\n".join(
            "".join(seg.text for seg in line) for line in richlog.lines
        )
    assert "fetch.source_done" in log_lines
    assert "included 2" in log_lines
    # the PRISMA text summary is printed at the end of the run
    assert "PRISMA flow" in log_lines
    assert "prisma.svg" in log_lines


async def test_refresh_checkbox_forwarded_to_pipeline(config_file, monkeypatch):
    """Ticking the run refresh checkbox passes refresh=True to run_pipeline."""
    from textual.widgets import Checkbox

    from surveyer.models import Ledger
    from surveyer.pipeline import PipelineResult

    seen: dict[str, object] = {}

    def fake_run_pipeline(cfg, **kwargs):
        seen.update(kwargs)
        return PipelineResult(ledger=Ledger(included=0), kept=[], excluded=[])

    monkeypatch.setattr("surveyer.pipeline.run_pipeline", fake_run_pipeline)

    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.query_one("#refresh", Checkbox).value = True
        app.screen.action_run()
        await app.workers.wait_for_complete()
        await pilot.pause()
    assert seen.get("refresh") is True


async def test_refresh_checkbox_defaults_off(config_file, monkeypatch):
    """Without ticking refresh, run_pipeline receives refresh=False."""
    from surveyer.models import Ledger
    from surveyer.pipeline import PipelineResult

    seen: dict[str, object] = {}

    def fake_run_pipeline(cfg, **kwargs):
        seen.update(kwargs)
        return PipelineResult(ledger=Ledger(included=0), kept=[], excluded=[])

    monkeypatch.setattr("surveyer.pipeline.run_pipeline", fake_run_pipeline)

    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.action_run()
        await app.workers.wait_for_complete()
        await pilot.pause()
    assert seen.get("refresh") is False


async def test_run_reports_pipeline_error(config_file, monkeypatch):
    """When the pipeline raises, the error message appears in the log pane."""

    def boom(cfg, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("surveyer.pipeline.run_pipeline", boom)

    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.action_run()
        await app.workers.wait_for_complete()
        await pilot.pause()
        richlog = app.screen.query_one("#log")
        log_lines = "\n".join(
            "".join(seg.text for seg in line) for line in richlog.lines
        )
    assert "network down" in log_lines


async def test_escape_cancels_running_run(config_file):
    """Pressing Esc during a run sets the cancel event without leaving the screen."""
    import threading

    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        # Simulate an in-flight run: pretend the worker is running with a cancel event.
        screen._pipeline_running = True
        screen._cancel = threading.Event()
        await pilot.press("escape")
        await pilot.pause()
        assert screen._cancel is not None
        assert screen._cancel.is_set()
        # The run must still be marked running and the screen must not have popped.
        assert screen._pipeline_running is True
        assert app.screen is screen


SEED_CONFIG = """\
[project]
name = "seed-survey"

[search]
sources = ["dblp"]

[[search.queries]]
label = "q1"
terms = "federated learning"

[search.concepts]
federated = ["federated learning", "federated averaging"]
"""


@pytest.fixture()
def seed_config_file(tmp_path: Path) -> Path:
    """Write a config with [search.concepts] but no [filter.concepts]."""
    p = tmp_path / "seed.toml"
    p.write_text(SEED_CONFIG)
    return p


async def test_button_switches_to_concepts_editor(config_file):
    """Editing concepts swaps the left panel; back returns to the form."""
    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        switcher = app.screen.query_one("#left", ContentSwitcher)
        assert switcher.current == "form"
        app.screen.action_edit_concepts()
        await pilot.pause()
        assert switcher.current == "concepts_editor"
        # Escape returns to the form
        app.screen.action_back()
        await pilot.pause()
        assert switcher.current == "form"


async def test_filter_seeded_from_search_when_absent(seed_config_file):
    """When [filter.concepts] is absent, the editor seeds it from search."""
    app = SurveyerApp(seed_config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        editor = app.screen.query_one(ConceptsEditor)
        filter_items = editor.read("filter")
        assert [c.name for c in filter_items] == ["federated"]
        assert filter_items[0].synonyms == ["federated learning", "federated averaging"]


async def test_add_concept_and_save_writes_toml(config_file):
    """Adding a search concept and saving writes it to the TOML on disk."""
    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.action_edit_concepts()
        await pilot.pause()
        editor = app.screen.query_one(ConceptsEditor)
        editor.query_one("#add-search", Button).press()
        await pilot.pause()
        rows = list(editor.query_one("#search-rows").query(ConceptRow))
        rows[-1].query_one(".concept-name", Input).value = "graph"
        rows[-1].query_one(".concept-syn", Input).value = "graph neural network, GNN"
        app.screen.action_save()
        await pilot.pause()
    text = config_file.read_text()
    assert "[search.concepts]" in text
    assert "graph neural network" in text


async def test_blind_save_does_not_materialize_filter_concepts(seed_config_file):
    """Saving without opening the editor must not write a seeded [filter.concepts]."""
    app = SurveyerApp(seed_config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.action_save()
        await pilot.pause()
    text = seed_config_file.read_text()
    assert "[filter.concepts]" not in text
    # the search concepts the user did have are still present/untouched
    assert "[search.concepts]" in text


async def test_save_after_opening_editor_writes_seeded_filter(seed_config_file):
    """Opening the editor then saving persists the filter seeded from search."""
    app = SurveyerApp(seed_config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.action_edit_concepts()
        await pilot.pause()
        app.screen.action_save()
        await pilot.pause()
    text = seed_config_file.read_text()
    assert "[filter.concepts]" in text
    assert "federated" in text


async def test_added_concept_rows_stack_without_overlap(config_file):
    """Added rows render at distinct, non-zero heights (row container is auto-height)."""
    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.action_edit_concepts()
        await pilot.pause()
        editor = app.screen.query_one(ConceptsEditor)
        for _ in range(2):
            editor.query_one("#add-search", Button).press()
            await pilot.pause()
        rows = list(editor.query_one("#search-rows").query(ConceptRow))
        assert len(rows) >= 2
        # every row is visible (non-zero height) and at a distinct vertical offset:
        # a 1fr/overflow-hidden container would clip later rows to height 0 / same y.
        assert all(r.region.height > 0 for r in rows)
        assert len({r.region.y for r in rows}) == len(rows)


async def test_reset_concepts_discards_unsaved_edits(seed_config_file):
    """Reset rebuilds the editor from the saved config, dropping unsaved edits."""
    app = SurveyerApp(seed_config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.action_edit_concepts()
        await pilot.pause()
        editor = app.screen.query_one(ConceptsEditor)
        # mutate an existing row and add a brand-new one
        srows = list(editor.query_one("#search-rows").query(ConceptRow))
        srows[0].query_one(".concept-name", Input).value = "garbage"
        editor.query_one("#add-search", Button).press()
        await pilot.pause()
        assert len(list(editor.query_one("#search-rows").query(ConceptRow))) == 2
        # reset -> back to exactly the saved config's single 'federated' concept
        editor.query_one("#reset-concepts", Button).press()
        await pilot.pause()
        search = editor.read("search")
        assert [c.name for c in search] == ["federated"]
        assert search[0].synonyms == ["federated learning", "federated averaging"]
        # filter is re-seeded from search (saved config had no [filter.concepts])
        assert [c.name for c in editor.read("filter")] == ["federated"]


async def test_reset_concepts_is_noop_on_form(config_file):
    """Reset only acts while the editor is open; on the form it does nothing."""
    app = SurveyerApp(config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        # never opened the editor: action_reset_concepts must be a quiet no-op
        app.screen.action_reset_concepts()
        await pilot.pause()
        assert app.screen.query_one("#left", ContentSwitcher).current == "form"


async def test_copy_from_search_mirrors_into_filter(seed_config_file):
    """'Copy from search' replaces the filter rows with the search rows."""
    app = SurveyerApp(seed_config_file)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.screen.action_edit_concepts()
        await pilot.pause()
        editor = app.screen.query_one(ConceptsEditor)
        # add a fresh search concept, then copy everything to filter
        editor.query_one("#add-search", Button).press()
        await pilot.pause()
        srows = list(editor.query_one("#search-rows").query(ConceptRow))
        srows[-1].query_one(".concept-name", Input).value = "privacy"
        srows[-1].query_one(".concept-syn", Input).value = "differential privacy"
        editor.query_one("#copy-search", Button).press()
        await pilot.pause()
        # pre-seeded federated row is replaced (not duplicated); synonyms copy too
        filter_items = editor.read("filter")
        assert [c.name for c in filter_items] == ["federated", "privacy"]
        assert filter_items[0].synonyms == ["federated learning", "federated averaging"]
        assert filter_items[1].synonyms == ["differential privacy"]
