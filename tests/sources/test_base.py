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


def test_http_client_refresh_bypasses_cache(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"n": calls["n"]})

    transport = httpx.MockTransport(handler)
    client = HttpClient(cache_dir=tmp_path, transport=transport, refresh=True)

    a = client.get_json("https://example.test/x", params={"q": "1"})
    b = client.get_json("https://example.test/x", params={"q": "1"})

    assert calls["n"] == 2  # refresh refetches every time
    assert a == {"n": 1}
    assert b == {"n": 2}  # cache overwritten with the fresh response


def test_http_client_refresh_overwrites_then_serves_fresh(tmp_path):
    # A refresh run rewrites the cache so a later normal client is fast again.
    seq = [{"v": "stale"}, {"v": "fresh"}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=seq.pop(0))

    transport = httpx.MockTransport(handler)
    HttpClient(cache_dir=tmp_path, transport=transport).get_json(
        "https://example.test/x", params={}
    )  # seeds the cache with "stale"

    refreshed = HttpClient(
        cache_dir=tmp_path, transport=transport, refresh=True
    ).get_json("https://example.test/x", params={})
    assert refreshed == {"v": "fresh"}

    calls = {"n": 0}

    def count(request: httpx.Request) -> httpx.Response:  # should not be hit
        calls["n"] += 1
        return httpx.Response(200, json={"v": "should-not-happen"})

    served = HttpClient(
        cache_dir=tmp_path, transport=httpx.MockTransport(count)
    ).get_json("https://example.test/x", params={})
    assert served == {"v": "fresh"}  # normal client serves the overwritten cache
    assert calls["n"] == 0


def test_get_text_refresh_bypasses_cache(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text=f"@misc{{k{calls['n']}}}")

    transport = httpx.MockTransport(handler)
    client = HttpClient(cache_dir=tmp_path, transport=transport, refresh=True)

    client.get_text("https://dblp.org/rec/k.bib")
    client.get_text("https://dblp.org/rec/k.bib")
    assert calls["n"] == 2  # refresh refetches the bibtex too


def test_http_client_retries_on_500(tmp_path):
    seq = [500, 500, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        code = seq.pop(0)
        return httpx.Response(code, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = HttpClient(
        cache_dir=tmp_path, transport=transport, max_retries=3, backoff=0.0
    )

    out = client.get_json("https://example.test/y", params={})
    assert out == {"ok": True}
    assert seq == []  # all three attempts consumed


def test_http_client_backoff_is_exponential(tmp_path, monkeypatch):
    # DBLP/S2 throttle windows outlast a linear 1,2,3s backoff; waits must grow.
    seq = [500, 500, 500, 200]
    waits: list[float] = []
    monkeypatch.setattr("surveyer.sources.base.time.sleep", waits.append)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(seq.pop(0), json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = HttpClient(
        cache_dir=tmp_path, transport=transport, max_retries=4, backoff=1.0
    )

    assert client.get_json("https://example.test/b", params={}) == {"ok": True}
    assert waits == [1.0, 2.0, 4.0]


def test_http_client_honors_retry_after_over_backoff(tmp_path, monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr("surveyer.sources.base.time.sleep", waits.append)
    seq = [429, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        code = seq.pop(0)
        headers = {"Retry-After": "7"} if code == 429 else {}
        return httpx.Response(code, json={"ok": True}, headers=headers)

    transport = httpx.MockTransport(handler)
    client = HttpClient(
        cache_dir=tmp_path, transport=transport, max_retries=4, backoff=1.0
    )

    assert client.get_json("https://example.test/ra", params={}) == {"ok": True}
    assert waits == [7.0]


def test_http_client_honors_retry_after_http_date(tmp_path, monkeypatch):
    # Crossref and others send the HTTP-date form of Retry-After, not seconds.
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    waits: list[float] = []
    monkeypatch.setattr("surveyer.sources.base.time.sleep", waits.append)
    date_str = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30))
    seq = [503, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        code = seq.pop(0)
        headers = {"Retry-After": date_str} if code == 503 else {}
        return httpx.Response(code, json={"ok": True}, headers=headers)

    transport = httpx.MockTransport(handler)
    client = HttpClient(
        cache_dir=tmp_path, transport=transport, max_retries=4, backoff=1.0
    )

    assert client.get_json("https://example.test/rad", params={}) == {"ok": True}
    # ~30s out; allow a wide band for clock movement during the test.
    assert len(waits) == 1
    assert 25.0 <= waits[0] <= 31.0


def test_http_client_retry_after_garbage_falls_back_to_backoff(tmp_path, monkeypatch):
    # An unparseable Retry-After must not crash; fall through to backoff.
    waits: list[float] = []
    monkeypatch.setattr("surveyer.sources.base.time.sleep", waits.append)
    seq = [429, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        code = seq.pop(0)
        headers = {"Retry-After": "soon-ish"} if code == 429 else {}
        return httpx.Response(code, json={"ok": True}, headers=headers)

    transport = httpx.MockTransport(handler)
    client = HttpClient(
        cache_dir=tmp_path, transport=transport, max_retries=4, backoff=1.0
    )

    assert client.get_json("https://example.test/rag", params={}) == {"ok": True}
    assert waits == [1.0]  # backoff for attempt 1, not a crash


def test_http_client_retries_on_transport_error(tmp_path):
    # DBLP drops connections under load; a transient ReadTimeout/reset must retry,
    # not kill the whole query.
    seq = ["timeout", "reset", "ok"]

    def handler(request: httpx.Request) -> httpx.Response:
        kind = seq.pop(0)
        if kind == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if kind == "reset":
            raise httpx.ReadError("connection reset", request=request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = HttpClient(
        cache_dir=tmp_path, transport=transport, max_retries=3, backoff=0.0
    )

    out = client.get_json("https://example.test/z", params={})
    assert out == {"ok": True}
    assert seq == []  # both transport errors retried, then success


def test_http_client_gives_up_on_persistent_transport_error(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    transport = httpx.MockTransport(handler)
    client = HttpClient(
        cache_dir=tmp_path, transport=transport, max_retries=3, backoff=0.0
    )

    try:
        client.get_json("https://example.test/down", params={})
    except httpx.TransportError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected the transport error to propagate after retries")


def test_get_text_caches(tmp_path):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text="@article{k, title={X}}")

    transport = httpx.MockTransport(handler)
    client = HttpClient(cache_dir=tmp_path, transport=transport)

    a = client.get_text("https://dblp.org/rec/k.bib")
    b = client.get_text("https://dblp.org/rec/k.bib")
    assert a == b == "@article{k, title={X}}"
    assert calls["n"] == 1  # second call served from cache


def test_get_text_returns_none_on_404(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    client = HttpClient(cache_dir=tmp_path, transport=transport)
    assert client.get_text("https://doi.org/10.1/missing") is None


def test_get_text_sends_per_call_headers(tmp_path):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accept"] = request.headers.get("accept", "")
        return httpx.Response(200, text="@misc{k}")

    transport = httpx.MockTransport(handler)
    client = HttpClient(cache_dir=tmp_path, transport=transport)
    client.get_text(
        "https://doi.org/10.1/x", headers={"Accept": "application/x-bibtex"}
    )
    assert seen["accept"] == "application/x-bibtex"
