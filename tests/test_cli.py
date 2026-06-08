from __future__ import annotations

from typer.testing import CliRunner

from surveyer import cli

runner = CliRunner()

SAMPLE = """
[project]
name = "demo"
output_dir = "OUT"

[search]
sources = ["dblp"]
[[search.queries]]
label = "A"
terms = "x"
"""


def test_fetch_disables_filtering(tmp_path, monkeypatch):
    cfg_path = tmp_path / "survey.toml"
    cfg_path.write_text(SAMPLE.replace("OUT", str(tmp_path / "out")))

    seen = {}

    def fake_run(cfg, **kwargs):
        seen["llm_enabled"] = cfg.filter.llm.enabled
        seen["include"] = cfg.filter.keyword.include
        from surveyer.models import Ledger
        from surveyer.pipeline import PipelineResult

        return PipelineResult(ledger=Ledger(), kept=[], excluded=[])

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    result = runner.invoke(cli.app, ["fetch", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert seen["llm_enabled"] is False
    assert seen["include"] == []


def test_prisma_missing_ledger_errors(tmp_path):
    cfg_path = tmp_path / "survey.toml"
    cfg_path.write_text(SAMPLE.replace("OUT", str(tmp_path / "out")))
    result = runner.invoke(cli.app, ["prisma", "--config", str(cfg_path)])
    assert result.exit_code == 1
    assert "ledger.json" in result.output


def test_prisma_renders_from_existing_ledger(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    cfg_path = tmp_path / "survey.toml"
    cfg_path.write_text(SAMPLE.replace("OUT", str(out)))

    from surveyer.ledger import save_ledger
    from surveyer.models import Ledger, SourceCount

    save_ledger(
        Ledger(
            identified=[SourceCount(source="dblp", count=10)],
            duplicates_removed=2,
            excluded_keyword=3,
            included=5,
        ),
        out / "ledger.json",
    )

    result = runner.invoke(cli.app, ["prisma", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert (out / "prisma.mmd").exists()


def test_run_command_invokes_pipeline(tmp_path, monkeypatch):
    cfg_path = tmp_path / "survey.toml"
    cfg_path.write_text(SAMPLE.replace("OUT", str(tmp_path / "out")))

    called = {}

    def fake_run(cfg, **kwargs):
        called["name"] = cfg.project.name
        from surveyer.models import Ledger
        from surveyer.pipeline import PipelineResult

        return PipelineResult(ledger=Ledger(included=5), kept=[], excluded=[])

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    result = runner.invoke(cli.app, ["run", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert called["name"] == "demo"
    assert "5" in result.output
