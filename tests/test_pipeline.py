from __future__ import annotations

from surveyer.config import (
    FilterConfig,
    KeywordConfig,
    LLMConfig,
    ProjectConfig,
    Query,
    SearchConfig,
    SurveyConfig,
)
from surveyer.ledger import load_ledger
from surveyer.models import Record
from surveyer.pipeline import run_pipeline


class FakeSource:
    name = "fake"

    def search(self, terms, *, max_results):
        return [
            Record(title="Relevant security paper", abstract="relevant", doi="10.1/a"),
            Record(title="Relevant security paper", abstract="relevant", doi="10.1/a"),
            Record(title="Off topic cooking", abstract="recipes", doi="10.1/b"),
        ]


class FakeScorer:
    def score(self, survey_abstract, record):
        return (0.9, "ok") if "relevant" in (record.abstract or "") else (0.1, "no")


def _cfg(tmp_path) -> SurveyConfig:
    return SurveyConfig(
        project=ProjectConfig(name="t", output_dir=str(tmp_path)),
        search=SearchConfig(sources=["fake"], queries=[Query(label="A", terms="x")]),
        filter=FilterConfig(
            keyword=KeywordConfig(include=["security"], exclude=[]),
            llm=LLMConfig(enabled=True, threshold=0.5, survey_abstract="s"),
        ),
    )


def test_run_pipeline_end_to_end(tmp_path):
    cfg = _cfg(tmp_path)
    result = run_pipeline(
        cfg,
        registry={"fake": FakeSource()},
        scorer=FakeScorer(),
    )
    assert result.ledger.total_identified() == 3
    assert result.ledger.duplicates_removed == 1
    assert result.ledger.excluded_keyword == 1
    assert result.ledger.included == 1
    assert (tmp_path / "survey.xlsx").exists()
    assert (tmp_path / "prisma.mmd").exists()  # always written
    led = load_ledger(tmp_path / "ledger.json")
    assert led.included == 1
    assert result.ledger.excluded_llm == 0
    assert len(result.excluded) == 1
