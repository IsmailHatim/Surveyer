from __future__ import annotations

import json

from surveyer.sources.dblp import parse_dblp


def test_parse_dblp(fixtures_dir):
    raw = json.loads((fixtures_dir / "dblp_sample.json").read_text())
    records = parse_dblp(raw)
    assert len(records) == 1
    r = records[0]
    assert r.title == "Attention Is All You Need"  # trailing period stripped
    assert r.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert r.year == 2017
    assert r.doi == "10.5555/3295222.3295349"
    assert r.venue == "NeurIPS"
    assert r.url == "https://arxiv.org/abs/1706.03762"
