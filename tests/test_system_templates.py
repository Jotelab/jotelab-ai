"""System templates (spec 2026-07-27): branch derivation, parsing, loop, contract."""

import pytest
import sympy

from engine.errors import TemplateValidationError
from templates.base import Template, VarSpec
from templates.declarative import parse_template
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


def _toy_doc(**overrides):
    doc = {
        "topic": "toy-meet",
        "variables": {
            "d": {"unit": "m",   "ranges": {"easy": [2, 20, False], "medium": [2, 40, False], "hard": [2, 60, False]}},
            "w": {"unit": "m/s", "ranges": {"easy": [1, 10, False], "medium": [1, 15, False], "hard": [1, 20, False]}},
            "t": {"unit": "s",   "ranges": {"easy": [1, 10, False], "medium": [1, 20, False], "hard": [1, 30, False]}},
        },
        "auxiliary": {"p": {"unit": "m"}},
        "equations": ["Eq(p, w*t)", "Eq(p, d)"],
        "root_policy": {"name": "smallest_positive_physical"},
        "constraints": [{"var": "t", "op": ">", "value": 0},
                        {"var": "p", "op": ">", "value": 0}],
        "default_split": {"given": ["d", "w"], "find": "t"},
        "golden_cases": [{"given": {"d": 12, "w": 3}, "find": "t",
                          "difficulty": "easy", "expected": "4"}],
        "trust_state": "unverified",
    }
    doc.update(overrides)
    return doc


def test_parse_toy_system_doc():
    tpl = parse_template(_toy_doc())
    assert set(s.name for s in tpl.auxiliaries) == {"p"}
    aux_p = next(iter(tpl.auxiliaries))
    assert tpl.unit_for(aux_p) == "m"
    ok, info = tpl.solvability(tpl.default_split[0], tpl.default_split[1])
    assert ok is True and len(info.branches) == 1


def test_parse_without_auxiliary_unchanged():
    doc = _toy_doc()
    del doc["auxiliary"]
    doc["equations"] = ["Eq(d, w*t)"]
    doc["constraints"] = [{"var": "t", "op": ">", "value": 0}]
    tpl = parse_template(doc)
    assert tpl.auxiliaries is None


def test_parse_valid_splits_derived_for_system():
    tpl = parse_template(_toy_doc())
    finds = {f.name for _, f in tpl.valid_splits()}
    assert finds == {"d", "w", "t"}


def test_parse_rejects_aux_overlapping_variable():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(auxiliary={"t": {"unit": "s"}}))


def test_parse_rejects_aux_without_unit():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(auxiliary={"p": {}}))


def test_parse_rejects_aux_with_ranges():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(
            auxiliary={"p": {"unit": "m", "ranges": {"easy": [1, 5, False]}}}))


def test_parse_rejects_empty_aux_block():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(auxiliary={}))


def test_parse_rejects_aux_in_default_split():
    with pytest.raises(TemplateValidationError, match="auxiliary"):
        parse_template(_toy_doc(
            default_split={"given": ["d", "p"], "find": "t"}))


def test_parse_rejects_aux_in_golden_given():
    with pytest.raises(TemplateValidationError, match="auxiliary"):
        parse_template(_toy_doc(
            golden_cases=[{"given": {"d": 12, "p": 12}, "find": "t",
                           "difficulty": "easy", "expected": "4"}]))


def test_parse_equations_may_reference_aux():
    # covered by test_parse_toy_system_doc; here: undeclared names still rejected
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(equations=["Eq(q, w*t)", "Eq(q, d)"]))
