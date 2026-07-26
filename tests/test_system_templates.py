"""System templates (spec 2026-07-27): branch derivation, parsing, loop, contract."""

import pytest
import sympy

from templates.base import Template, VarSpec
from templates.declarative.system import (Branch, SystemSolution,
                                          derive_branches,
                                          make_system_solvability)

gap, a, v, t, x = sympy.symbols("gap a v t x", real=True)
PURSUIT_EQS = [sympy.Eq(x, v * t), sympy.Eq(x, gap + a * t**2 / 2)]


def test_derive_branches_pursuit_two_branches():
    branches = derive_branches(PURSUIT_EQS, {gap, a, v}, t, {x})
    assert len(branches) == 2
    for b in branches:
        assert isinstance(b, Branch)
        assert b.find_expr.free_symbols <= {gap, a, v}
        assert set(b.aux_exprs) == {x}
        assert b.aux_exprs[x].free_symbols <= {gap, a, v}


def test_derive_branches_linear_single_branch():
    d, w, tt, p = sympy.symbols("d w tt p", real=True)
    eqs = [sympy.Eq(p, w * tt), sympy.Eq(p, d)]
    branches = derive_branches(eqs, {d, w}, tt, {p})
    assert len(branches) == 1
    assert sympy.simplify(branches[0].find_expr - d / w) == 0
    assert sympy.simplify(branches[0].aux_exprs[p] - d) == 0


def test_system_solvability_valid_split():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    ok, info = solv((gap, a, v), t)
    assert ok is True
    assert isinstance(info, SystemSolution)
    assert len(info.branches) == 2


def test_system_solvability_rejects_unused_variable():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    ok, reason = solv((gap, a), t)  # v unused
    assert ok is False
    assert "no unused variables" in reason


def test_system_solvability_rejects_find_in_given():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    ok, reason = solv((gap, a, v, t), t)
    assert ok is False


def test_system_solvability_rejects_unknown_symbol():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    z = sympy.Symbol("z", real=True)
    ok, reason = solv((gap, a, z), t)
    assert ok is False


def test_system_solvability_caches_derivation():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    _, info1 = solv((gap, a, v), t)
    _, info2 = solv((v, a, gap), t)  # same set, different order
    assert info1 is info2


def test_template_unit_for_resolves_auxiliaries():
    tpl = Template(
        topic="toy", symbols={"t": t}, variables={t: VarSpec("s", {})},
        equations=[], solvability=lambda g, f: (False, "n/a"),
        constraints=[], root_select=lambda vals, f, d: None,
        default_split=((), t), auxiliaries={x: "m"},
    )
    assert tpl.unit_for(t) == "s"
    assert tpl.unit_for(x) == "m"
