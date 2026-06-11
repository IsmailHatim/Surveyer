"""Tests for the bare-invocation TUI entry point."""

from typer.testing import CliRunner

from surveyer.cli import app

runner = CliRunner()


def test_bare_invocation_launches_tui(monkeypatch):
    calls: list[str | None] = []
    monkeypatch.setattr("surveyer.tui.run_tui", calls.append)
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert calls == [None]


def test_bare_invocation_passes_config(monkeypatch):
    calls: list[str | None] = []
    monkeypatch.setattr("surveyer.tui.run_tui", calls.append)
    result = runner.invoke(app, ["-c", "examples/survey.toml"])
    assert result.exit_code == 0
    assert calls == ["examples/survey.toml"]


def test_subcommands_still_work():
    for cmd in ("run", "fetch", "extend", "prisma"):
        result = runner.invoke(app, [cmd, "--help"])
        assert result.exit_code == 0, cmd
