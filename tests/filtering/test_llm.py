from __future__ import annotations

import pytest

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


def test_apply_llm_filter_sets_exclusion_reason():
    cfg = LLMConfig(enabled=True, threshold=0.5, survey_abstract="my survey")
    good = Record(title="Good", abstract="this is relevant work")
    bad = Record(title="Bad", abstract="off topic")
    apply_llm_filter([good, bad], cfg, FakeScorer())
    assert good.exclusion_reason is None
    assert bad.exclusion_reason == "llm score 0.10 < threshold 0.5"


def test_apply_llm_filter_logs_progress():
    import structlog

    cfg = LLMConfig(enabled=True, threshold=0.5, survey_abstract="my survey")
    recs = [
        Record(title="A", abstract="relevant"),
        Record(title="B", abstract="off topic"),
        Record(title="C", abstract="relevant"),
    ]
    with structlog.testing.capture_logs() as logs:
        apply_llm_filter(recs, cfg, FakeScorer())

    progress = [e for e in logs if e["event"] == "llm.scoring"]
    assert len(progress) == 3
    assert progress[0]["done"] == 1
    assert progress[-1]["done"] == 3
    assert all(e["total"] == 3 for e in progress)


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
    assert kept[0].llm_reason == "scoring failed — review manually"


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


def test_ollama_scorer_parses_response(mocker):
    from surveyer.filtering.llm import OllamaScorer

    fake_client = mocker.Mock()
    fake_client.chat.return_value = {
        "message": {"content": '{"score": 0.8, "reason": "on topic"}'}
    }
    client_cls = mocker.patch("ollama.Client", return_value=fake_client)

    scorer = OllamaScorer(model="llama3.1", host="http://ollama.example:11434")
    score, reason = scorer.score("survey", Record(title="T", abstract="A"))

    assert score == 0.8
    assert reason == "on topic"
    client_cls.assert_called_once_with(host="http://ollama.example:11434")
    kwargs = fake_client.chat.call_args.kwargs
    assert kwargs["model"] == "llama3.1"
    assert kwargs["format"] == "json"


def test_ollama_scorer_raises_on_missing_score(mocker):
    from surveyer.filtering.llm import OllamaScorer

    fake_client = mocker.Mock()
    fake_client.chat.return_value = {"message": {"content": '{"reason": "x"}'}}
    mocker.patch("ollama.Client", return_value=fake_client)

    scorer = OllamaScorer()
    with pytest.raises(ValueError, match="score"):
        scorer.score("survey", Record(title="T", abstract="A"))


def test_build_scorer_openai(mocker):
    from surveyer.filtering.llm import OpenAIScorer, build_scorer

    mocker.patch("openai.OpenAI")
    cfg = LLMConfig(enabled=True, provider="openai", model="gpt-4o-mini")
    scorer = build_scorer(cfg)
    assert isinstance(scorer, OpenAIScorer)


def test_build_scorer_ollama(mocker):
    from surveyer.filtering.llm import OllamaScorer, build_scorer

    mocker.patch("ollama.Client")
    cfg = LLMConfig(
        enabled=True, provider="ollama", model="llama3.1", host="http://h:11434"
    )
    scorer = build_scorer(cfg)
    assert isinstance(scorer, OllamaScorer)
    assert scorer.model == "llama3.1"


def test_build_scorer_unknown_provider():
    from surveyer.filtering.llm import build_scorer

    cfg = LLMConfig(enabled=True, provider="bogus")
    with pytest.raises(ValueError, match="provider"):
        build_scorer(cfg)
