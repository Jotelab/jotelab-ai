"""Named root policy: smallest_positive_physical (ADR-007)."""

import pytest
import sympy
from templates.declarative.constraints import compile_constraints
from templates.declarative.roots import make_root_select

SYMS = dict(zip("uvats", sympy.symbols("u v a t s", real=True)))
u, v, a, t, s = (SYMS[n] for n in "uvats")
SPECS = [
    {"var": "t", "op": ">", "value": 0},
    {"var": "u", "op": "abs<=", "value": 100},
    {"var": "v", "op": "abs<=", "value": 100},
    {"var": "a", "op": "!=", "value": 0},
    {"var": "u", "op": ">=", "value": 0, "difficulty": "easy"},
    {"var": "v", "op": ">=", "value": 0, "difficulty": "easy"},
    {"var": "s", "op": ">=", "value": 0, "difficulty": "easy"},
    {"var": "a", "op": ">=", "value": 0, "difficulty": "easy", "scope": "root"},
]
POLICY = {"name": "smallest_positive_physical", "nonneg_fallback_vars": ["u", "s", "v"]}


def _rs():
    return make_root_select(POLICY, compile_constraints(SPECS, SYMS))


def test_smallest_positive_root_chosen():
    rs = _rs()
    assert rs([sympy.Integer(-3), sympy.Integer(3)], t, "easy") == 3


def test_nonneg_fallback_for_u_when_no_positive():
    rs = _rs()
    assert rs([sympy.Integer(0)], u, "easy") == 0


def test_no_physical_root_returns_none():
    rs = _rs()
    assert rs([sympy.Integer(-3)], t, "easy") is None


def test_unknown_policy_name_raises():
    with pytest.raises(ValueError):
        make_root_select({"name": "nope"}, compile_constraints(SPECS, SYMS))
