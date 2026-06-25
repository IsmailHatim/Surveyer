from __future__ import annotations

import threading

import pytest

from surveyer.cancel import PipelineCancelled
from surveyer.config import LLMConfig
from surveyer.filtering.llm import apply_llm_filter
from surveyer.models import Record


class FakeScorer:
    """Scores by length of abstract; deterministic, no network."""

    def __init__(self):
        self.calls = 0

    def score(
        self, survey_abstract: str, record: Record, *, concepts=None
    ) -> tuple[float, str, dict[str, str]]:
        self.calls += 1
        val = 0.9 if record.abstract and "relevant" in record.abstract else 0.1
        return val, "reason", {}


def test_apply_llm_filter_threshold():
    cfg = LLMConfig(enabled=True, threshold=0.5, survey_abstract="my survey")
    recs = [
        Record(title="Good", abstract="this is relevant work"),
        Record(title="Bad", abstract="off topic"),
    ]
    scorer = FakeScorer()
    kept, excluded, borderline = apply_llm_filter(recs, cfg, scorer)
    assert [r.title for r in kept] == ["Good"]
    assert excluded == 1
    assert borderline == 0
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
    kept, excluded, borderline = apply_llm_filter(recs, cfg, scorer)
    assert len(kept) == 1
    assert excluded == 0
    assert borderline == 0
    assert scorer.calls == 0


def test_unscored_records_kept_on_scorer_error():
    class BoomScorer:
        def score(self, survey_abstract, record, *, concepts=None):
            raise RuntimeError("api down")

    cfg = LLMConfig(enabled=True, threshold=0.5, survey_abstract="s")
    recs = [Record(title="x", abstract="y")]
    kept, excluded, borderline = apply_llm_filter(recs, cfg, BoomScorer())
    assert len(kept) == 1
    assert excluded == 0
    assert borderline == 0
    assert kept[0].llm_score is None
    assert kept[0].llm_reason == "scoring failed - review manually"
    assert kept[0].screening_status == "borderline"


def test_caching_scorer_avoids_recompute(tmp_path):
    from surveyer.filtering.llm import CachingScorer

    class CountingScorer:
        def __init__(self):
            self.calls = 0

        def score(self, survey_abstract, record, *, concepts=None):
            self.calls += 1
            return 0.7, "r", {}

    inner = CountingScorer()
    cached = CachingScorer(inner, tmp_path / "llm", namespace="gpt-x")
    r = Record(title="T", doi="10.1/a", abstract="x")
    assert cached.score("survey", r) == (0.7, "r", {})
    assert cached.score("survey", r) == (0.7, "r", {})
    assert inner.calls == 1


def test_ollama_scorer_parses_response(mocker):
    from surveyer.filtering.llm import OllamaScorer

    fake_client = mocker.Mock()
    fake_client.chat.return_value = {
        "message": {"content": '{"score": 0.8, "reason": "on topic"}'}
    }
    client_cls = mocker.patch("ollama.Client", return_value=fake_client)

    scorer = OllamaScorer(model="llama3.1", host="http://ollama.example:11434")
    score, reason, verdicts = scorer.score("survey", Record(title="T", abstract="A"))

    assert score == 0.8
    assert reason == "on topic"
    assert verdicts == {}
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


def test_build_scorer_openai(mocker, monkeypatch):
    from surveyer.filtering.llm import OpenAIScorer, build_scorer

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mocker.patch("openai.OpenAI")
    cfg = LLMConfig(enabled=True, provider="openai", model="gpt-4o-mini")
    scorer = build_scorer(cfg)
    assert isinstance(scorer, OpenAIScorer)


def test_openai_scorer_fails_fast_without_api_key(mocker, monkeypatch):
    from surveyer.filtering.llm import OpenAIScorer

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    open_ai = mocker.patch("openai.OpenAI")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIScorer()
    open_ai.assert_not_called()


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


def test_apply_llm_filter_cancel_before_any_record():
    cfg = LLMConfig(enabled=True, threshold=0.5, survey_abstract="s")
    scorer = FakeScorer()
    event = threading.Event()
    event.set()
    with pytest.raises(PipelineCancelled):
        apply_llm_filter(
            [Record(title="x", abstract="relevant")], cfg, scorer, cancel=event
        )
    assert scorer.calls == 0


def test_apply_llm_filter_cancel_after_n_records():
    event = threading.Event()

    class CancelOnNth:
        """Scores normally but trips the event once N records are scored."""

        def __init__(self, n):
            self.calls = 0
            self.n = n

        def score(self, survey_abstract, record, *, concepts=None):
            self.calls += 1
            if self.calls >= self.n:
                event.set()
            return 0.9, "ok", {}

    cfg = LLMConfig(enabled=True, threshold=0.5, survey_abstract="s")
    recs = [Record(title=f"r{i}", abstract="relevant") for i in range(5)]
    scorer = CancelOnNth(2)
    with pytest.raises(PipelineCancelled):
        apply_llm_filter(recs, cfg, scorer, cancel=event)
    assert scorer.calls == 2


def test_apply_llm_filter_passes_concepts_to_scorer():
    class RecordingScorer:
        def __init__(self):
            self.seen_concepts = "unset"

        def score(self, survey_abstract, record, *, concepts=None):
            self.seen_concepts = concepts
            return 0.9, "ok", {}

    cfg = LLMConfig(enabled=True, threshold=0.5, survey_abstract="s")
    scorer = RecordingScorer()
    apply_llm_filter(
        [Record(title="x", abstract="y")],
        cfg,
        scorer,
        concepts={"graphs": ["graph"]},
    )
    assert scorer.seen_concepts == {"graphs": ["graph"]}


def test_render_user_prompt_includes_concepts():
    from surveyer.filtering.llm import _render_user_prompt

    rec = Record(title="GNN survey", abstract="about graphs")
    prompt = _render_user_prompt(
        "my survey abstract",
        rec,
        {"graphs": ["graph", "network"], "survey-method": ["survey", "review"]},
    )
    assert "my survey abstract" in prompt
    assert "graphs: graph, network" in prompt
    assert "survey-method: survey, review" in prompt
    assert "GNN survey" in prompt
    assert "about graphs" in prompt


def test_render_user_prompt_without_concepts_has_no_concept_block():
    from surveyer.filtering.llm import _render_user_prompt

    rec = Record(title="T", abstract=None)
    prompt = _render_user_prompt("survey", rec, None)
    assert "Concept criteria" not in prompt
    assert "(no abstract)" in prompt


def test_system_prompt_defines_anchored_scale():
    from surveyer.filtering.llm import _SYSTEM

    for anchor in ("1.0", "0.85", "0.7", "0.6", "0.5", "0.25", "0.0"):
        assert anchor in _SYSTEM


def test_parse_response_folds_concept_verdicts_into_reason():
    from surveyer.filtering.llm import _parse_response

    score, reason, verdicts = _parse_response(
        {
            "concepts": {"graphs": "yes", "survey-method": "no"},
            "score": 0.4,
            "reason": "primary study, not a survey",
        }
    )
    assert score == 0.4
    assert reason == "graphs:yes, survey-method:no — primary study, not a survey"
    assert verdicts == {"graphs": "yes", "survey-method": "no"}


def test_parse_response_without_concepts_keeps_plain_reason():
    from surveyer.filtering.llm import _parse_response

    score, reason, verdicts = _parse_response(
        {"concepts": {}, "score": 0.9, "reason": "on topic"}
    )
    assert score == 0.9
    assert reason == "on topic"
    assert verdicts == {}


def test_parse_response_raises_on_missing_score():
    from surveyer.filtering.llm import _parse_response

    with pytest.raises(ValueError, match="score"):
        _parse_response({"reason": "x"})


def test_ollama_scorer_sends_system_message_and_concepts(mocker):
    from surveyer.filtering.llm import OllamaScorer

    fake_client = mocker.Mock()
    fake_client.chat.return_value = {
        "message": {
            "content": '{"concepts": {"graphs": "yes"}, "score": 0.8, "reason": "ok"}'
        }
    }
    mocker.patch("ollama.Client", return_value=fake_client)

    scorer = OllamaScorer()
    score, reason, verdicts = scorer.score(
        "survey", Record(title="T", abstract="A"), concepts={"graphs": ["graph"]}
    )

    assert score == 0.8
    assert reason == "graphs:yes — ok"
    assert verdicts == {"graphs": "yes"}
    messages = fake_client.chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert (
        "anchored scale" in messages[0]["content"].lower()
        or "1.0" in messages[0]["content"]
    )
    assert "graphs: graph" in messages[1]["content"]


from surveyer.filtering.llm import _parse_response  # noqa: E402


def test_parse_response_clamps_and_returns_verdicts():
    """Score above 1.0 is clamped to 1.0 and verdicts are returned."""
    score, reason, verdicts = _parse_response(
        {"score": 5, "reason": "r", "concepts": {"graph": "yes"}}
    )
    assert score == 1.0
    assert verdicts == {"graph": "yes"}


def test_parse_response_rejects_bool():
    """Boolean scores must be rejected (bools are subclass of int in Python)."""
    import pytest

    with pytest.raises(ValueError):
        _parse_response({"score": True})


def test_parse_response_clamps_negative():
    """Negative scores are clamped to 0.0."""
    score, _, _ = _parse_response({"score": -0.3})
    assert score == 0.0


def test_cache_key_busts_on_concept_change(tmp_path):
    """Changing concepts produces a different cache key (cache miss)."""
    from surveyer.filtering.llm import CachingScorer
    from surveyer.models import Record

    class Counting:
        def __init__(self):
            self.calls = 0

        def score(self, survey_abstract, record, *, concepts=None):
            self.calls += 1
            return 0.7, "r", {}

    inner = Counting()
    cs = CachingScorer(inner, tmp_path, namespace="ollama:m")
    rec = Record(title="t", abstract="a")
    cs.score("survey", rec, concepts={"x": ["x"]})
    cs.score("survey", rec, concepts={"x": ["x"]})  # cache hit
    assert inner.calls == 1
    cs.score("survey", rec, concepts={"x": ["x"], "y": ["y"]})  # edited -> miss
    assert inner.calls == 2


class TieredScorer:
    """Returns the score embedded in the abstract, e.g. abstract='0.45'."""

    def score(self, survey_abstract, record, *, concepts=None):
        """Return (score, reason, verdicts) with score parsed from abstract."""
        return float(record.abstract), "r", {"c": "partial"}


def test_borderline_band_routing():
    """Records in [threshold - margin, threshold) land in kept but counted borderline."""
    cfg = LLMConfig(enabled=True, threshold=0.5, review_margin=0.1, survey_abstract="s")
    recs = [
        Record(title="hi", abstract="0.8"),  # include
        Record(title="mid", abstract="0.45"),  # borderline [0.4, 0.5)
        Record(title="lo", abstract="0.2"),  # exclude
    ]
    kept, excluded, borderline = apply_llm_filter(
        recs, cfg, TieredScorer(), concepts={"c": ["c"]}
    )
    assert [r.title for r in kept] == ["hi", "mid"]
    assert excluded == 1
    assert borderline == 1
    assert recs[0].screening_status == "include"
    assert recs[1].screening_status == "borderline"
    assert recs[2].screening_status == "exclude"
    assert recs[0].concept_verdicts == {"c": "partial"}


def test_margin_zero_is_legacy_behavior():
    """With review_margin=0 there is no borderline band; score < threshold → exclude."""
    cfg = LLMConfig(enabled=True, threshold=0.5, review_margin=0.0, survey_abstract="s")
    recs = [Record(title="x", abstract="0.49")]
    kept, excluded, borderline = apply_llm_filter(recs, cfg, TieredScorer())
    assert kept == []
    assert excluded == 1
    assert borderline == 0


def test_score_exactly_at_threshold_is_include():
    """Score exactly at threshold is included, borderline count is 0."""
    cfg = LLMConfig(enabled=True, threshold=0.5, review_margin=0.1, survey_abstract="s")
    recs = [Record(title="edge", abstract="0.5")]
    kept, excluded, borderline = apply_llm_filter(recs, cfg, TieredScorer())
    assert recs[0].screening_status == "include"
    assert excluded == 0 and borderline == 0


def test_score_exactly_at_lo_is_borderline():
    """Score exactly at lo (threshold - review_margin) is borderline."""
    cfg = LLMConfig(enabled=True, threshold=0.5, review_margin=0.1, survey_abstract="s")
    recs = [Record(title="edge", abstract="0.4")]  # lo = 0.5 - 0.1 = 0.4
    kept, excluded, borderline = apply_llm_filter(recs, cfg, TieredScorer())
    assert recs[0].screening_status == "borderline"
    assert borderline == 1 and excluded == 0
