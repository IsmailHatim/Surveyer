from __future__ import annotations

from surveyer.config import LLMConfig
from surveyer.filtering.llm import apply_llm_filter
from surveyer.models import Record


class FakeScorer:
    """Scores by length of abstract; deterministic, no network."""

    def __init__(self):
        self.calls = 0

    def score(self, survey_abstract: str, record: Record) -> tuple[float, str]:
        self.calls += 1
        val = 0.9 if record.abstract and "relevant" in record.abstract else 0.1
        return val, "reason"


def test_apply_llm_filter_threshold():
    cfg = LLMConfig(enabled=True, threshold=0.5, survey_abstract="my survey")
    recs = [
        Record(title="Good", abstract="this is relevant work"),
        Record(title="Bad", abstract="off topic"),
    ]
    scorer = FakeScorer()
    kept, excluded = apply_llm_filter(recs, cfg, scorer)
    assert [r.title for r in kept] == ["Good"]
    assert excluded == 1
    assert kept[0].llm_score == 0.9
    assert kept[0].llm_reason == "reason"


def test_disabled_is_passthrough():
    cfg = LLMConfig(enabled=False)
    recs = [Record(title="x")]
    scorer = FakeScorer()
    kept, excluded = apply_llm_filter(recs, cfg, scorer)
    assert len(kept) == 1
    assert excluded == 0
    assert scorer.calls == 0


def test_unscored_records_kept_on_scorer_error():
    class BoomScorer:
        def score(self, survey_abstract, record):
            raise RuntimeError("api down")

    cfg = LLMConfig(enabled=True, threshold=0.5, survey_abstract="s")
    recs = [Record(title="x", abstract="y")]
    kept, excluded = apply_llm_filter(recs, cfg, BoomScorer())
    assert len(kept) == 1
    assert excluded == 0
    assert kept[0].llm_score is None


def test_caching_scorer_avoids_recompute(tmp_path):
    from surveyer.filtering.llm import CachingScorer

    class CountingScorer:
        def __init__(self):
            self.calls = 0

        def score(self, survey_abstract, record):
            self.calls += 1
            return 0.7, "r"

    inner = CountingScorer()
    cached = CachingScorer(inner, tmp_path / "llm", namespace="gpt-x")
    r = Record(title="T", doi="10.1/a", abstract="x")
    assert cached.score("survey", r) == (0.7, "r")
    assert cached.score("survey", r) == (0.7, "r")
    assert inner.calls == 1
