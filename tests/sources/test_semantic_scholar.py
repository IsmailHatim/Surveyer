from __future__ import annotations

import json

from surveyer.sources.semantic_scholar import parse_s2


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
