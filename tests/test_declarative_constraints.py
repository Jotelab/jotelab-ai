"""Declarative constraint DSL -> predicates + is_physical filter (ADR-007)."""

import sympy
from templates.declarative.constraints import compile_constraints

SYMS = dict(zip("uvats", sympy.symbols("u v a t s", real=True)))
u, v, a, t, s = (SYMS[n] for n in "uvats")


def _specs():
    return [
        {"var": "t", "op": ">", "value": 0},
        {"var": "u", "op": "abs<=", "value": 100},
        {"var": "v", "op": "abs<=", "value": 100},
        {"var": "a", "op": "!=", "value": 0},
        {"var": "u", "op": ">=", "value": 0, "difficulty": "easy"},
        {"var": "v", "op": ">=", "value": 0, "difficulty": "easy"},
        {"var": "s", "op": ">=", "value": 0, "difficulty": "easy"},
        {"var": "a", "op": ">=", "value": 0, "difficulty": "easy", "scope": "root"},
    ]


def test_loop_predicates_match_suvat_semantics():
    cc = compile_constraints(_specs(), SYMS)
    # time must be positive
    assert not all(p({t: sympy.Integer(-1)}, "easy") for p in cc.loop_predicates)
    assert all(p({t: sympy.Integer(3)}, "easy") for p in cc.loop_predicates)
    # speed bounded
    assert not all(p({v: sympy.Integer(200)}, "medium") for p in cc.loop_predicates)
    # accel nonzero
    assert not all(p({a: sympy.Integer(0)}, "medium") for p in cc.loop_predicates)
    # easy nonneg applies to u,v,s (NOT a — that constraint is scope=root)
    assert not all(p({s: sympy.Integer(-5)}, "easy") for p in cc.loop_predicates)
    assert all(p({a: sympy.Integer(-5)}, "easy") for p in cc.loop_predicates)
    # medium relaxes the easy nonneg
    assert all(p({s: sympy.Integer(-5)}, "medium") for p in cc.loop_predicates)


def test_is_physical_filters_per_find():
    cc = compile_constraints(_specs(), SYMS)
    # find=t must be strictly positive
    assert cc.is_physical(sympy.Integer(3), t, "easy")
    assert not cc.is_physical(sympy.Integer(-3), t, "easy")
    # find=a on easy: negative rejected (scope=root constraint), zero rejected (!=0)
    assert not cc.is_physical(sympy.Integer(-2), a, "easy")
    assert not cc.is_physical(sympy.Integer(0), a, "easy")
    # find=v: |v|<=100
    assert not cc.is_physical(sympy.Integer(250), v, "medium")
    assert cc.is_physical(sympy.Integer(30), v, "medium")
