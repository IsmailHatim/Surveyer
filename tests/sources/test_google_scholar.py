from __future__ import annotations

from surveyer.sources.google_scholar import parse_scholar_entry


def test_parse_scholar_entry():
    entry = {
        "bib": {
            "title": "Adversarial Examples",
            "author": ["I Goodfellow", "J Shlens"],
            "pub_year": "2015",
            "venue": "ICLR",
            "abstract": "We craft adversarial examples.",
        },
        "pub_url": "https://example.org/paper",
        "num_citations": 9000,
    }
    r = parse_scholar_entry(entry)
    assert r.title == "Adversarial Examples"
    assert r.authors == ["I Goodfellow", "J Shlens"]
    assert r.year == 2015
    assert r.venue == "ICLR"
    assert r.url == "https://example.org/paper"
    assert r.n_citations == 9000


def test_google_scholar_search_api_total_is_none(monkeypatch):
    import surveyer.sources.google_scholar as gs

    class FakeScholarly:
        def search_pubs(self, terms):
            return iter([{"bib": {"title": "P"}}])

    monkeypatch.setattr(gs, "scholarly", FakeScholarly(), raising=False)
    result = gs.GoogleScholarSource().search("x", max_results=5)
    assert result.api_total is None
    assert [r.title for r in result.records] == ["P"]
