from __future__ import annotations

import httpx

from surveyer.sources.base import HttpClient


def test_http_client_caches(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = HttpClient(cache_dir=tmp_path, transport=transport)

    a = client.get_json("https://example.test/x", params={"q": "1"})
    b = client.get_json("https://example.test/x", params={"q": "1"})

    assert a == b == {"ok": True}
    assert calls["n"] == 1  # second call served from cache


def test_http_client_retries_on_500(tmp_path):
    seq = [500, 500, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        code = seq.pop(0)
        return httpx.Response(code, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = HttpClient(cache_dir=tmp_path, transport=transport, max_retries=3, backoff=0.0)

    out = client.get_json("https://example.test/y", params={})
    assert out == {"ok": True}
    assert seq == []  # all three attempts consumed
