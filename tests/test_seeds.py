from __future__ import annotations

import httpx
import pytest

from surveyer.seeds import SeedResolver, detect_seed_id
from surveyer.sources.base import HttpClient


@pytest.mark.parametrize(
    "raw,expected_doi",
    [
        ("10.1/abc", "10.1/abc"),
        ("https://doi.org/10.1/abc", "10.1/abc"),
        ("CorpusID:268417919", None),
        ("arXiv:2409.07825", None),
        ("DOI:10.1/abc", "10.1/abc"),
    ],
)
def test_detect_seed_id_doi(raw, expected_doi):
    _, doi = detect_seed_id(raw)
    assert doi == expected_doi


def test_detect_seed_id_lookup_prefixes():
    assert detect_seed_id("10.1/abc")[0] == "DOI:10.1/abc"
    assert detect_seed_id("CorpusID:123")[0] == "CorpusID:123"
    assert detect_seed_id("arXiv:2409.07825")[0] == "ARXIV:2409.07825"
    assert detect_seed_id("DOI:10.1/abc")[0] == "DOI:10.1/abc"


def _s2_client(tmp_path, handler):
    return HttpClient(cache_dir=tmp_path / "s2", transport=httpx.MockTransport(handler))


def _oa_client(tmp_path, handler):
    return HttpClient(cache_dir=tmp_path / "oa", transport=httpx.MockTransport(handler))


def test_resolve_seed_via_s2(tmp_path):
    def s2(request):
        assert request.url.path.endswith("/paper/CorpusID:1")
        return httpx.Response(
            200,
            json={"title": "MUSE", "externalIds": {}, "authors": [], "year": 2024},
        )

    def oa(request):  # should never be called for a CorpusID
        raise AssertionError("OpenAlex fallback should not run")

    resolver = SeedResolver(_s2_client(tmp_path, s2), _oa_client(tmp_path, oa))
    records, led = resolver.resolve(["CorpusID:1"])
    assert len(records) == 1
    assert records[0].title == "MUSE"
    assert records[0].sources == ["seed"]
    assert records[0].query_labels == ["seed:s2"]
    assert records[0].screening_status == "include"
    assert (led.imported, led.resolved, led.unresolved) == (1, 1, 0)


def test_resolve_falls_back_to_openalex_when_s2_misses(tmp_path):
    def s2(request):
        return httpx.Response(404, json={"error": "not found"})

    def oa(request):
        assert "doi:10.1/x" in str(request.url)
        return httpx.Response(
            200, json={"title": "GCNet", "doi": "10.1/x", "publication_year": 2023}
        )

    resolver = SeedResolver(_s2_client(tmp_path, s2), _oa_client(tmp_path, oa))
    records, led = resolver.resolve(["10.1/x"])
    assert len(records) == 1
    assert records[0].title == "GCNet"
    assert records[0].query_labels == ["seed:openalex"]
    assert (led.resolved, led.unresolved) == (1, 0)


def test_unresolved_seed_warns_and_continues(tmp_path):
    def s2(request):
        return httpx.Response(404, json={})

    def oa(request):
        return httpx.Response(404, json={})

    resolver = SeedResolver(_s2_client(tmp_path, s2), _oa_client(tmp_path, oa))
    # CorpusID has no OpenAlex fallback and S2 misses -> unresolved, no raise.
    records, led = resolver.resolve(["CorpusID:999"])
    assert records == []
    assert (led.imported, led.resolved, led.unresolved) == (1, 0, 1)
