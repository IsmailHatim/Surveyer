from __future__ import annotations

import httpx

from surveyer.bibtex import BibtexResolver, build_local_entry
from surveyer.models import Record
from surveyer.sources.base import HttpClient


def _resolver(tmp_path) -> BibtexResolver:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "dblp.org":
            return httpx.Response(200, text="@article{DBLP:k, title={From DBLP}}")
        if host == "doi.org":
            return httpx.Response(200, text="@article{crossref, title={From DOI}}")
        return httpx.Response(404)

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    return BibtexResolver(client)


def test_resolve_prefers_dblp(tmp_path):
    r = Record(title="X", dblp_key="journals/k", doi="10.1/x")
    text, source = _resolver(tmp_path).resolve(r)
    assert source == "dblp"
    assert "From DBLP" in text


def test_resolve_falls_back_to_doi(tmp_path):
    r = Record(title="X", doi="10.1/x")
    text, source = _resolver(tmp_path).resolve(r)
    assert source == "doi"
    assert "From DOI" in text


def test_resolve_falls_back_to_local_when_no_ids(tmp_path):
    r = Record(title="Great Survey", authors=["Jane Doe"], year=2024)
    text, source = _resolver(tmp_path).resolve(r)
    assert source == "local"
    assert text.startswith("@misc{doe2024great,")
    assert "title = {Great Survey}" in text
    assert "author = {Jane Doe}" in text


def test_resolve_all_sets_fields_and_unique_keys(tmp_path):
    recs = [
        Record(title="Survey", authors=["Jane Doe"], year=2024),
        Record(title="Survey", authors=["Jane Doe"], year=2024),
    ]
    resolver = _resolver(tmp_path)
    resolver.resolve_all(recs)
    assert recs[0].bibtex_source == "local"
    assert recs[0].bibtex.startswith("@misc{doe2024survey,")
    assert recs[1].bibtex.startswith("@misc{doe2024surveya,")  # de-duplicated key


def test_resolve_chains_through_failures(tmp_path):
    # DBLP 404s and DOI errors -> fall all the way through to local.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dblp.org":
            return httpx.Response(404)
        return httpx.Response(403)

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    r = Record(
        title="Survey",
        authors=["Jane Doe"],
        year=2024,
        dblp_key="journals/k",
        doi="10.1/x",
    )
    text, source = BibtexResolver(client).resolve(r)
    assert source == "local"
    assert text.startswith("@misc{doe2024survey,")


def test_resolve_follows_doi_redirect(tmp_path):
    # doi.org answers content negotiation with a 302 to api.crossref.org;
    # the resolver's client must follow it instead of treating it as an error.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "doi.org":
            return httpx.Response(
                302, headers={"Location": "https://api.crossref.org/v1/works/x"}
            )
        return httpx.Response(200, text="@article{crossref, title={Followed}}")

    client = HttpClient(
        cache_dir=tmp_path,
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    text, source = BibtexResolver(client).resolve(Record(title="X", doi="10.1/x"))
    assert source == "doi"
    assert "Followed" in text


def test_build_resolver_follows_redirects(tmp_path):
    from surveyer.bibtex import build_resolver

    resolver = build_resolver(tmp_path)
    assert resolver.client._client.follow_redirects is True


def test_resolve_percent_encodes_doi(tmp_path):
    # A '#' in a DOI must reach the server encoded, not be parsed as a fragment.
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.raw_path.decode()
        return httpx.Response(200, text="@article{k, title={X}}")

    client = HttpClient(cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    r = Record(title="X", doi="10.1000/abc#frag")
    _, source = BibtexResolver(client).resolve(r)
    assert source == "doi"
    assert seen["path"] == "/10.1000/abc%23frag"


def test_build_local_entry_with_minimal_fields():
    # No author/year/title -> stable fallback key, no crash.
    entry = build_local_entry(Record(title=""), seen=set())
    assert entry.startswith("@misc{ref,")
