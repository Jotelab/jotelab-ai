"""Dimensional-homogeneity checker, gate stage 2 (ADR-007)."""

import json
import pytest
from sympy.physics.units.systems.si import dimsys_SI
from engine.errors import TemplateValidationError
from templates.declarative import parse_template
from templates.declarative.units import dimension_of, check_homogeneous

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
    "golden_cases": [],
    "trust_state": "unverified",
}


def test_dimension_of_parses_compound_units():
    d_v = dimension_of("m/s")
    d_a = dimension_of("m/s^2")
    assert dimsys_SI.equivalent_dims(d_v, dimension_of("m") / dimension_of("s"))
    assert dimsys_SI.equivalent_dims(d_a, dimension_of("m") / dimension_of("s") / dimension_of("s"))


def test_homogeneous_equation_passes():
    check_homogeneous(parse_template(MINIMAL))  # v = u + a t is homogeneous


def test_inhomogeneous_equation_fails_stage_2():
    bad = json.loads(json.dumps(MINIMAL))
    bad["equations"] = ["Eq(v, u + a*t**2)"]
    tpl = parse_template(bad)
    with pytest.raises(TemplateValidationError) as ei:
        check_homogeneous(tpl)
    assert ei.value.stage == 2


def test_unknown_unit_token_fails_stage_2():
    bad = json.loads(json.dumps(MINIMAL))
    bad["variables"]["u"]["unit"] = "furlong/s"
    tpl = parse_template(bad)
    with pytest.raises(TemplateValidationError) as ei:
        check_homogeneous(tpl)
    assert ei.value.stage == 2
