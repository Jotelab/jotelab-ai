"""SUVAT-as-data loads, parses, and generates the worked example (ADR-007)."""

import json
from pathlib import Path
from templates.declarative import parse_template
from engine import registry
from engine.loop import generate

SUVAT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "suvat.json"


def test_suvat_json_parses_and_generates():
    doc = json.loads(SUVAT_JSON.read_text())
    tpl = parse_template(doc)
    assert tpl.topic == "suvat"
    assert len(tpl.equations) == 5
    with registry.temporary(tpl):
        data = generate("suvat", given=("u", "a", "t"), find="v",
                        conditions={"u": 0, "a": 2, "t": 5}, difficulty="easy", seed=80421)
    assert data["find"]["exact"] == "10"
    assert data["find"]["unit"] == "m/s"


def test_suvat_json_valid_splits_match_code_suvat():
    doc = json.loads(SUVAT_JSON.read_text())
    tpl = parse_template(doc)
    code = registry.load_template("suvat")

    def splits_as_names(t):
        return sorted(
            (tuple(sorted(s.name for s in given)), find.name)
            for given, find in t.valid_splits()
        )

    assert splits_as_names(tpl) == splits_as_names(code)
