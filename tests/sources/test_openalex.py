from __future__ import annotations

import json

import httpx

from surveyer.sources.base import HttpClient
from surveyer.sources.openalex import (
    OpenAlexSource,
    parse_openalex,
    parse_openalex_work,
    reconstruct_abstract,
)


def test_reconstruct_abstract():
    idx = {"Deep": [0], "secure": [1], "models": [2]}
    assert reconstruct_abstract(idx) == "Deep secure models"


def test_parse_openalex_work_single():
    w = {
        "title": "Graph Completion Network",
        "doi": "https://doi.org/10.1109/TPAMI.2023.1",
        "publication_year": 2023,
        "cited_by_count": 42,
        "authorships": [{"author": {"display_name": "Z. Lian"}}],
        "primary_location": {"source": {"display_name": "TPAMI"}},
        "abstract_inverted_index": {"Missing": [0], "modality": [1]},
    }
    r = parse_openalex_work(w)
    assert r.title == "Graph Completion Network"
    assert r.doi == "10.1109/TPAMI.2023.1"
    assert r.year == 2023
    assert r.n_citations == 42
    assert r.authors == ["Z. Lian"]
    assert r.venue == "TPAMI"
    assert r.abstract == "Missing modality"


def test_parse_openalex(fixtures_dir):
    raw = json.loads((fixtures_dir / "openalex_sample.json").read_text())
    records = parse_openalex(raw)
    assert len(records) == 1
    r = records[0]
    assert r.title == "Deep Learning for Security"
    assert r.doi == "10.1145/3292500"  # https://doi.org/ prefix stripped
    assert r.year == 2019
    assert r.n_citations == 42
    assert r.venue == "ACM Computing Surveys"
    assert r.authors == ["Jane Roe", "John Doe"]
    assert r.abstract == "Deep secure models"


def test_openalex_search_paginates_past_one_page(tmp_path):
    # per-page caps at 200; asking for 250 must fetch a second page.
    total = 250

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        per = int(request.url.params["per-page"])
        start = (page - 1) * per
        ids = list(range(total))[start : start + per]
        results = [{"title": f"W{i}"} for i in ids]
        return httpx.Response(200, json={"meta": {"count": total}, "results": results})

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = OpenAlexSource(client).search("x", max_results=250)
    assert len(result.records) == 250


def test_openalex_search_preserves_quoted_phrases(tmp_path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["search"])
        return httpx.Response(200, json={"meta": {"count": 0}, "results": []})

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    OpenAlexSource(client).search('"graph neural network" survey', max_results=10)
    assert seen == ['"graph neural network" survey']


def test_openalex_search_stops_when_results_exhausted(tmp_path):
    # Only 30 results exist even though 200 were requested.
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        results = [{"title": f"W{i}"} for i in range(30)] if page == 1 else []
        return httpx.Response(200, json={"meta": {"count": 30}, "results": results})

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = OpenAlexSource(client).search("x", max_results=200)
    assert len(result.records) == 30


def test_openalex_search_returns_api_total(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"meta": {"count": 5231}, "results": [{"title": "W"}]}
        )

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = OpenAlexSource(client).search("x", max_results=10)
    assert result.api_total == 5231
    assert [r.title for r in result.records] == ["W"]
