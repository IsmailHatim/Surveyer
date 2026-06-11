"""Pilot tests for the dashboard form."""

from pathlib import Path

import pytest

pytest.importorskip("textual")

from surveyer.tui.app import SurveyerApp  # noqa: E402
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
