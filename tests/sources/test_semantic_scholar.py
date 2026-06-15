from __future__ import annotations

import json

import httpx

from surveyer.sources.base import HttpClient
from surveyer.sources.semantic_scholar import SemanticScholarSource, parse_s2


def test_parse_s2(fixtures_dir):
    raw = json.loads((fixtures_dir / "s2_sample.json").read_text())
    records = parse_s2(raw)
    assert len(records) == 1
    r = records[0]
    assert r.title == "Federated Learning Privacy"
    assert r.doi == "10.1109/TIFS.2021.123456"
    assert r.year == 2021
    assert r.n_citations == 17
    assert r.venue == "IEEE TIFS"
    assert r.authors == ["Alice Smith", "Bob Jones"]
    assert r.abstract.startswith("We study privacy")


def test_s2_search_paginates_past_the_100_cap(tmp_path):
    # The API caps `limit` at 100/page; asking for 150 must fetch a second page.
    total = 150

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        limit = int(request.url.params["limit"])
        ids = list(range(total))[offset : offset + limit]
        data = [{"title": f"P{i}", "externalIds": {}, "authors": []} for i in ids]
        body: dict = {"total": total, "offset": offset, "data": data}
        if offset + limit < total:
            body["next"] = offset + limit
        return httpx.Response(200, json=body)

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    records = SemanticScholarSource(client).search("x", max_results=150)
    assert len(records) == 150


def test_s2_search_stops_at_max_results(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        limit = int(request.url.params["limit"])
        data = [
            {"title": f"P{i}", "externalIds": {}, "authors": []} for i in range(limit)
        ]
        return httpx.Response(
            200,
            json={
                "total": 9999,
                "offset": offset,
                "next": offset + limit,
                "data": data,
            },
        )

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    records = SemanticScholarSource(client).search("x", max_results=120)
    assert len(records) == 120
