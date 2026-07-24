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


SIGNED_POLICY = {
    "name": "smallest_positive_physical",
    "nonneg_fallback_vars": ["u", "s", "v"],
    "signed_fallback_vars": ["v", "s", "a"],
    "signed_fallback_difficulties": ["medium", "hard"],
}


def _signed_rs(policy=None):
    return make_root_select(policy or SIGNED_POLICY,
                            compile_constraints(SPECS, SYMS))


def test_signed_fallback_lone_negative_v_at_medium():
    assert _signed_rs()([sympy.Integer(-8)], v, "medium") == -8


def test_signed_fallback_rejected_at_easy():
    assert _signed_rs()([sympy.Integer(-8)], v, "easy") is None


def test_signed_fallback_never_applies_to_t():
    assert _signed_rs()([sympy.Integer(-3)], t, "medium") is None


def test_signed_fallback_positive_still_wins():
    assert _signed_rs()([sympy.Integer(-8), sympy.Integer(3)], v, "medium") == 3


def test_signed_fallback_smallest_magnitude():
    assert _signed_rs()([sympy.Integer(-8), sympy.Integer(-3)], v, "medium") == -3


def test_signed_fallback_absent_keys_keeps_old_behavior():
    assert _rs()([sympy.Integer(-8)], v, "medium") is None


def test_signed_fallback_difficulties_default_medium_hard():
    policy = {k: val for k, val in SIGNED_POLICY.items()
              if k != "signed_fallback_difficulties"}
    rs = _signed_rs(policy)
    assert rs([sympy.Integer(-8)], v, "medium") == -8
    assert rs([sympy.Integer(-8)], v, "easy") is None


def test_signed_fallback_vars_must_be_string_list():
    with pytest.raises(ValueError):
        _signed_rs({**SIGNED_POLICY, "signed_fallback_vars": "v"})


def test_signed_fallback_bad_difficulty_rejected():
    with pytest.raises(ValueError):
        _signed_rs({**SIGNED_POLICY,
                    "signed_fallback_difficulties": ["extreme"]})


def test_signed_fallback_difficulties_require_vars():
    policy = {"name": "smallest_positive_physical",
              "signed_fallback_difficulties": ["medium"]}
    with pytest.raises(ValueError):
        _signed_rs(policy)


def test_signed_fallback_unhashable_difficulty_rejected():
    with pytest.raises(ValueError):
        _signed_rs({**SIGNED_POLICY,
                    "signed_fallback_difficulties": ["medium", ["hard"]]})


def test_signed_fallback_mixed_type_vars_rejected():
    with pytest.raises(ValueError):
        _signed_rs({**SIGNED_POLICY, "signed_fallback_vars": ["v", 5]})
