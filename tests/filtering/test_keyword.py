from __future__ import annotations

from surveyer.config import KeywordConfig
from surveyer.filtering.keyword import apply_keyword_filter
from surveyer.models import Record


def test_include_required():
    cfg = KeywordConfig(include=["security"], exclude=[])
    recs = [
        Record(title="A security study", abstract="about defenses"),
        Record(title="Unrelated topic", abstract="cooking recipes"),
    ]
    kept, excluded = apply_keyword_filter(recs, cfg)
    assert [r.title for r in kept] == ["A security study"]
    assert excluded == 1


def test_exclude_wins():
    cfg = KeywordConfig(include=["security"], exclude=["survey"])
    recs = [Record(title="A security survey", abstract="")]
    kept, excluded = apply_keyword_filter(recs, cfg)
    assert kept == []
    assert excluded == 1


def test_no_filters_keeps_all():
    cfg = KeywordConfig(include=[], exclude=[])
    recs = [Record(title="anything")]
    kept, excluded = apply_keyword_filter(recs, cfg)
    assert len(kept) == 1
    assert excluded == 0
