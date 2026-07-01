"""Safe declarative parser -> Template + stage-1 sandbox rejection (ADR-007)."""

import json
import pytest
from engine.errors import TemplateValidationError
from templates.declarative import parse_template
from templates.declarative.parse import trust_state_of

MINIMAL = {
    "topic": "mini",
    "variables": {
        "u": {"unit": "m/s", "ranges": {"easy": [0, 20, False]}},
        "a": {"unit": "m/s^2", "ranges": {"easy": [1, 10, False]}},
        "t": {"unit": "s", "ranges": {"easy": [1, 10, False]}},
        "v": {"unit": "m/s", "ranges": {"easy": [0, 30, False]}},
    },
    "equations": ["Eq(v, u + a*t)"],
    "root_policy": {"name": "smallest_positive_physical", "nonneg_fallback_vars": ["u", "v"]},
    "constraints": [{"var": "t", "op": ">", "value": 0}],
    "default_split": {"given": ["u", "a", "t"], "find": "v"},
    "golden_cases": [{"given": {"u": 0, "a": 2, "t": 5}, "find": "v", "difficulty": "easy", "expected": "10"}],
    "trust_state": "unverified",
}


def test_parse_builds_template():
    tpl = parse_template(MINIMAL)
    assert tpl.topic == "mini"
    assert len(tpl.equations) == 1
    assert set(s.name for s in tpl.symbols.values()) == {"u", "a", "t", "v"}
    assert tpl.default_split[1].name == "v"
    ok, eq = tpl.solvability([tpl.symbols[n] for n in ("u", "a", "t")], tpl.symbols["v"])
    assert ok


def test_parse_rejects_unknown_symbol():
    bad = json.loads(json.dumps(MINIMAL))
    bad["equations"] = ["Eq(v, u + a*t + w)"]
    with pytest.raises(TemplateValidationError) as ei:
        parse_template(bad)
    assert ei.value.stage == 1


def test_parse_rejects_hostile_callable():
    bad = json.loads(json.dumps(MINIMAL))
    bad["equations"] = ["Eq(v, __import__('os').system('echo hi'))"]
    with pytest.raises(TemplateValidationError) as ei:
        parse_template(bad)
    assert ei.value.stage == 1


def test_parse_rejects_attribute_access():
    bad = json.loads(json.dumps(MINIMAL))
    bad["equations"] = ["Eq(v, u.foo)"]
    with pytest.raises(TemplateValidationError) as ei:
        parse_template(bad)
    assert ei.value.stage == 1


def test_parse_trust_state_carried():
    assert trust_state_of(MINIMAL) == "unverified"
    assert trust_state_of({}) == "unverified"
