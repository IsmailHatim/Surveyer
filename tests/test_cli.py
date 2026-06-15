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


CONCEPT_SAMPLE = """
[project]
name = "demo"
output_dir = "OUT"

[search]
sources = ["dblp"]
[[search.queries]]
label = "A"
terms = "x"

[filter.concepts]
method = ["graph neural network"]
"""


def test_fetch_disables_concept_filter(tmp_path, monkeypatch):
    cfg_path = tmp_path / "survey.toml"
    cfg_path.write_text(CONCEPT_SAMPLE.replace("OUT", str(tmp_path / "out")))

    seen = {}

    def fake_run(cfg, **kwargs):
        seen["concepts"] = cfg.filter.concepts
        from surveyer.models import Ledger
        from surveyer.pipeline import PipelineResult

        return PipelineResult(ledger=Ledger(), kept=[], excluded=[])

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    result = runner.invoke(cli.app, ["fetch", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert seen["concepts"] is None


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


def test_fetch_skips_bibtex(tmp_path, monkeypatch):
    cfg_path = tmp_path / "survey.toml"
    cfg_path.write_text(SAMPLE.replace("OUT", str(tmp_path / "out")))

    captured = {}

    def fake_run(cfg, **kwargs):
        captured.update(kwargs)
        from surveyer.models import Ledger
        from surveyer.pipeline import PipelineResult

        return PipelineResult(ledger=Ledger(), kept=[], excluded=[])

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    result = runner.invoke(cli.app, ["fetch", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert captured.get("resolve_bibtex") is False


def test_run_reports_bibtex(tmp_path, monkeypatch):
    cfg_path = tmp_path / "survey.toml"
    cfg_path.write_text(SAMPLE.replace("OUT", str(tmp_path / "out")))

    def fake_run(cfg, **kwargs):
        from surveyer.models import Ledger, Record
        from surveyer.pipeline import PipelineResult

        kept = [
            Record(title="A", bibtex_source="dblp"),
            Record(title="B", bibtex_source="local"),
        ]
        return PipelineResult(ledger=Ledger(included=2), kept=kept, excluded=[])

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    result = runner.invoke(cli.app, ["run", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "references.bib written (2 entries, 1 local fallbacks)" in result.output


EXTEND_SAMPLE = """
[project]
name = "demo-v2"
output_dir = "OUT"

[search]
sources = ["dblp"]
[[search.queries]]
label = "B"
terms = "y"

[extend]
xlsx = "BASELINE"
"""


def test_extend_command_requires_section(tmp_path):
    cfg_path = tmp_path / "survey.toml"
    cfg_path.write_text(SAMPLE.replace("OUT", str(tmp_path / "out")))
    result = runner.invoke(cli.app, ["extend", "--config", str(cfg_path)])
    assert result.exit_code == 1
    assert "[extend]" in result.output


def test_extend_command_reports_counts(tmp_path, monkeypatch):
    baseline = tmp_path / "v1.xlsx"
    baseline.touch()
    cfg_path = tmp_path / "survey.toml"
    cfg_path.write_text(
        EXTEND_SAMPLE.replace("OUT", str(tmp_path / "out")).replace(
            "BASELINE", str(baseline)
        )
    )

    def fake_run(cfg, **kwargs):
        from surveyer.models import Ledger
        from surveyer.pipeline import PipelineResult

        ledger = Ledger(included=4, previously_included=5, already_screened=3)
        return PipelineResult(ledger=ledger, kept=[], excluded=[])

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    result = runner.invoke(cli.app, ["extend", "--config", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert "5" in result.output  # carried over
    assert "3" in result.output  # already screened
    assert "9" in result.output  # total included
