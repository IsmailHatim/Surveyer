from __future__ import annotations

import httpx

from surveyer.sources.base import HttpClient
from surveyer.sources.pubmed import (
    PubMedSource,
    make_pubmed_params,
    parse_pubmed,
)


def test_parse_pubmed_full_record(fixtures_dir):
    records = parse_pubmed((fixtures_dir / "pubmed_sample.xml").read_text())
    assert len(records) == 2
    r = records[0]
    assert r.title == "Graph neural networks for protein folding"
    assert r.doi == "10.1000/jgm.2021.001"
    assert r.year == 2021
    assert r.venue == "Journal of Graph Methods"
    assert r.authors == ["Alice Smith", "Bob Jones"]
    assert r.abstract == "BACKGROUND: We study folding.\nRESULTS: It works well."
    assert r.keywords == ["Algorithms", "Neural Networks, Computer"]
    assert r.url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert r.n_citations is None


def test_parse_pubmed_sparse_record(fixtures_dir):
    r = parse_pubmed((fixtures_dir / "pubmed_sample.xml").read_text())[1]
    assert r.title == "A sparse record"
    assert r.doi is None
    assert r.abstract is None
    assert r.keywords == []
    assert r.authors == []
    assert r.year == 2008  # parsed from MedlineDate "2008 Spring"


def test_make_pubmed_params_without_key(monkeypatch):
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    assert make_pubmed_params() == {"tool": "surveyer"}


def test_make_pubmed_params_with_key(monkeypatch):
    monkeypatch.setenv("NCBI_API_KEY", "secret")
    assert make_pubmed_params() == {"tool": "surveyer", "api_key": "secret"}


_MINIMAL_ARTICLE = (
    "<PubmedArticle><MedlineCitation><PMID>1</PMID>"
    "<Article><ArticleTitle>T</ArticleTitle></Article>"
    "</MedlineCitation></PubmedArticle>"
)


def _is_esearch(request: httpx.Request) -> bool:
    return "esearch" in request.url.path


def test_pubmed_search_two_step_flow(tmp_path, fixtures_dir):
    xml_text = (fixtures_dir / "pubmed_sample.xml").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_esearch(request):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["1", "2"]}})
        return httpx.Response(200, text=xml_text)

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = PubMedSource(client).search("graph", max_results=10)
    assert [r.title for r in result.records] == [
        "Graph neural networks for protein folding",
        "A sparse record",
    ]


def test_pubmed_search_empty_skips_efetch(tmp_path):
    efetch_calls: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_esearch(request):
            return httpx.Response(200, json={"esearchresult": {"idlist": []}})
        efetch_calls.append(True)
        return httpx.Response(200, text="<PubmedArticleSet/>")

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = PubMedSource(client).search("graph", max_results=10)
    assert result.records == []
    assert efetch_calls == []


def test_pubmed_search_preserves_quoted_phrases(tmp_path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_esearch(request):
            seen.append(request.url.params["term"])
            return httpx.Response(200, json={"esearchresult": {"idlist": []}})
        return httpx.Response(200, text="<PubmedArticleSet/>")

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    PubMedSource(client).search('"graph neural network" survey', max_results=10)
    assert seen == ['"graph neural network" survey']


def test_pubmed_search_applies_year_filter(tmp_path):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_esearch(request):
            seen.update(dict(request.url.params))
            return httpx.Response(200, json={"esearchresult": {"idlist": []}})
        return httpx.Response(200, text="<PubmedArticleSet/>")

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    PubMedSource(client, year_min=2015, year_max=2020).search("x", max_results=10)
    assert seen["datetype"] == "pdat"
    assert seen["mindate"] == "2015"
    assert seen["maxdate"] == "2020"


def test_pubmed_search_paginates_and_batches(tmp_path):
    total = 250

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_esearch(request):
            retstart = int(request.url.params.get("retstart", "0"))
            retmax = int(request.url.params["retmax"])
            ids = [str(i) for i in range(total)][retstart : retstart + retmax]
            return httpx.Response(200, json={"esearchresult": {"idlist": ids}})
        count = len(request.url.params["id"].split(","))
        body = "".join(_MINIMAL_ARTICLE for _ in range(count))
        return httpx.Response(200, text=f"<PubmedArticleSet>{body}</PubmedArticleSet>")

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = PubMedSource(client).search("x", max_results=250)
    assert len(result.records) == 250


def test_parse_pubmed_title_preserves_inline_markup():
    xml = (
        "<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>5</PMID>"
        "<Article><ArticleTitle>Effects of <i>E. coli</i> on growth.</ArticleTitle>"
        "</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"
    )
    r = parse_pubmed(xml)[0]
    assert r.title == "Effects of E. coli on growth"


def test_pubmed_search_returns_api_total(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_esearch(request):
            return httpx.Response(
                200, json={"esearchresult": {"count": "874", "idlist": ["1"]}}
            )
        return httpx.Response(
            200, text=f"<PubmedArticleSet>{_MINIMAL_ARTICLE}</PubmedArticleSet>"
        )

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    result = PubMedSource(client).search("x", max_results=10)
    assert result.api_total == 874
    assert len(result.records) == 1
