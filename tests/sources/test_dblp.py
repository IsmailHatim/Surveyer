from __future__ import annotations

import json

import httpx

from surveyer.sources.base import HttpClient
from surveyer.sources.dblp import DblpSource, parse_dblp

_HIT = {
    "result": {"hits": {"hit": [{"info": {"title": "Mirror paper", "year": "2024"}}]}}
}


def test_dblp_search_falls_back_to_mirror_and_sticks(tmp_path):
    # dblp.org rate-limits by IP and starts dropping connections
    calls = {"primary": 0, "mirror": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dblp.org":
            calls["primary"] += 1
            raise httpx.ConnectError("reset", request=request)
        calls["mirror"] += 1
        return httpx.Response(200, json=_HIT)

    client = HttpClient(
        cache_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        max_retries=2,
        backoff=0.0,
    )
    source = DblpSource(client)

    first = source.search("q1", max_results=10)
    assert [r.title for r in first.records] == ["Mirror paper"]
    assert calls["primary"] == 2  # retries exhausted once, then switched

    source.search("q2", max_results=10)
    assert calls["primary"] == 2  # sticky: second query goes straight to mirror
    assert calls["mirror"] == 2


def test_dblp_search_uses_primary_when_healthy(tmp_path):
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200, json=_HIT)

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    DblpSource(client).search("q", max_results=10)
    assert hosts == ["dblp.org"]


def test_dblp_search_dequotes_phrase_terms(tmp_path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["q"])
        return httpx.Response(200, json=_HIT)

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    DblpSource(client).search('"graph neural network" survey', max_results=10)
    assert seen == ["graph neural network survey"]


def test_parse_dblp_captures_key():
    raw = {
        "result": {
            "hits": {
                "hit": [
                    {
                        "info": {
                            "title": "Incomplete graph learning: A comprehensive survey.",
                            "year": "2025",
                            "key": "journals/nn/XiaLLLZZY25",
                            "authors": {"author": [{"text": "Riting Xia"}]},
                        }
                    }
                ]
            }
        }
    }
    [rec] = parse_dblp(raw)
    assert rec.dblp_key == "journals/nn/XiaLLLZZY25"


def test_parse_dblp(fixtures_dir):
    raw = json.loads((fixtures_dir / "dblp_sample.json").read_text())
    records = parse_dblp(raw)
    assert len(records) == 1
    r = records[0]
    assert r.title == "Attention Is All You Need"  # trailing period stripped
    assert r.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert r.year == 2017
    assert r.doi == "10.5555/3295222.3295349"
    assert r.venue == "NeurIPS"
    assert r.url == "https://arxiv.org/abs/1706.03762"


def test_dblp_search_returns_api_total(tmp_path):
    raw = {"result": {"hits": {"@total": "47", "hit": [{"info": {"title": "P"}}]}}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=raw)

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = DblpSource(client).search("x", max_results=10)
    assert result.api_total == 47
    assert [r.title for r in result.records] == ["P"]


def test_parse_dblp_tolerates_malformed_authors():
    raw = {
        "result": {
            "hits": {
                "hit": [
                    {
                        "info": {
                            "title": "A paper",
                            "authors": {
                                "author": [{"text": "Ada"}, {"@pid": "x"}, "Bob"]
                            },
                        }
                    }
                ]
            }
        }
    }
    records = parse_dblp(raw)
    assert records[0].authors == ["Ada", "Bob"]


def _make_raw(venue):
    """Return a minimal DBLP API response dict with the given venue value."""
    return {
        "result": {
            "hits": {
                "hit": [
                    {
                        "info": {
                            "title": "A chapter",
                            "year": "2023",
                            "venue": venue,
                        }
                    }
                ]
            }
        }
    }


def test_parse_dblp_venue_list_is_joined():
    """When DBLP returns venue as a list, parse_dblp must coerce it to a joined str."""
    raw = _make_raw(["Federated Learning", "Lecture Notes in Computer Science"])
    [rec] = parse_dblp(raw)
    assert rec.venue == "Federated Learning, Lecture Notes in Computer Science"


def test_parse_dblp_venue_scalar_unchanged():
    """A normal scalar venue string must pass through unchanged."""
    raw = _make_raw("NeurIPS")
    [rec] = parse_dblp(raw)
    assert rec.venue == "NeurIPS"


def test_parse_dblp_venue_none():
    """A missing venue must yield None."""
    raw = _make_raw(None)
    [rec] = parse_dblp(raw)
    assert rec.venue is None
