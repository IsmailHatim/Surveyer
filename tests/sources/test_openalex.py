from __future__ import annotations

import json

from surveyer.sources.openalex import parse_openalex, reconstruct_abstract


def test_reconstruct_abstract():
    idx = {"Deep": [0], "secure": [1], "models": [2]}
    assert reconstruct_abstract(idx) == "Deep secure models"


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
