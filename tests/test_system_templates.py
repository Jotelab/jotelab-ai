"""System templates (spec 2026-07-27): branch derivation, parsing, loop, contract."""

import copy
import pytest
import sympy

from engine.errors import TemplateValidationError
from harness.verify import FidelityError
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


from engine import contract as contract_mod


def test_contract_emits_sorted_auxiliary_array():
    tpl = parse_template(_toy_doc())
    d_sym, w_sym, t_sym = (tpl.symbol(n) for n in ("d", "w", "t"))
    p_sym = next(iter(tpl.auxiliaries))
    ok, info = tpl.solvability((d_sym, w_sym), t_sym)
    branch = info.branches[0]
    inputs = {d_sym: sympy.Integer(12), w_sym: sympy.Integer(3)}
    data = contract_mod.build_sympy_data(
        tpl, (d_sym, w_sym), t_sym, inputs, sympy.Integer(4),
        branch.find_expr, seed=0,
        policy=type("P", (), {"label": "easy"})(), plausible=True,
        aux_values={p_sym: sympy.Integer(12)},
    )
    assert data["auxiliary"] == [
        {"symbol": "p", "value": 12, "exact": "12", "unit": "m"}
    ]


def test_contract_without_aux_values_has_no_key():
    tpl = parse_template(_toy_doc())
    d_sym, w_sym, t_sym = (tpl.symbol(n) for n in ("d", "w", "t"))
    ok, info = tpl.solvability((d_sym, w_sym), t_sym)
    data = contract_mod.build_sympy_data(
        tpl, (d_sym, w_sym), t_sym,
        {d_sym: sympy.Integer(12), w_sym: sympy.Integer(3)},
        sympy.Integer(4), info.branches[0].find_expr, seed=0,
        policy=type("P", (), {"label": "easy"})(), plausible=True,
    )
    assert "auxiliary" not in data


from engine import registry
from engine.errors import NoCleanInstanceError
from engine.loop import generate


def test_generate_system_template_end_to_end():
    tpl = parse_template(_toy_doc())
    with registry.temporary(tpl):
        data = generate("toy-meet", given=["d", "w"], find="t",
                        conditions={"d": 12, "w": 3}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "4"
    assert data["auxiliary"] == [
        {"symbol": "p", "value": 12, "exact": "12", "unit": "m"}
    ]


def test_generate_system_respects_aux_constraint():
    # p > 0 is declared; pin d < 0 so p = d violates it -> no clean instance.
    tpl = parse_template(_toy_doc())
    with registry.temporary(tpl):
        with pytest.raises(NoCleanInstanceError):
            generate("toy-meet", given=["d", "w"], find="t",
                     conditions={"d": -12, "w": 3}, difficulty="medium",
                     seed=1, max_attempts=10)


IRR_DOC = {
    "topic": "toy-irr",
    "variables": {
        "c": {"unit": "1", "ranges": {"easy": [2, 2, False], "medium": [2, 2, False], "hard": [2, 2, False]}},
        "t": {"unit": "1", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]}},
    },
    "auxiliary": {"q": {"unit": "1"}},
    "equations": ["Eq(q**2, c)", "Eq(t, c)"],
    "root_policy": {"name": "smallest_positive_physical"},
    "constraints": [],
    "default_split": {"given": ["c"], "find": "t"},
    "golden_cases": [{"given": {"c": 4}, "find": "t", "difficulty": "easy",
                      "expected": "4"}],
    "trust_state": "unverified",
}


def test_irrational_auxiliary_is_a_failed_roll():
    # c = 2 -> q = ±sqrt(2): find t=2 is clean but q is irrational -> re-roll
    # forever -> NoCleanInstanceError (spec: auxiliaries must be Rational).
    tpl = parse_template(IRR_DOC)
    with registry.temporary(tpl):
        with pytest.raises(NoCleanInstanceError):
            generate("toy-irr", given=["c"], find="t", conditions={"c": 2},
                     difficulty="easy", seed=1, max_attempts=10)


def test_rational_auxiliary_generates():
    tpl = parse_template(IRR_DOC)
    with registry.temporary(tpl):
        data = generate("toy-irr", given=["c"], find="t", conditions={"c": 4},
                        difficulty="easy", seed=1)
    assert data["find"]["exact"] == "4"
    assert data["auxiliary"][0]["exact"] in ("2", "-2")


from harness.verify import verify_generic


def _toy_instance():
    tpl = parse_template(_toy_doc())
    with registry.temporary(tpl):
        data = generate("toy-meet", given=["d", "w"], find="t",
                        conditions={"d": 12, "w": 3}, difficulty="easy", seed=1)
    return tpl, data


def test_verify_system_instance_passes():
    tpl, data = _toy_instance()
    assert verify_generic(data, tpl, difficulty="easy") is True


def test_verify_catches_corrupted_auxiliary():
    tpl, data = _toy_instance()
    bad = copy.deepcopy(data)
    bad["auxiliary"][0]["exact"] = "99"
    bad["auxiliary"][0]["value"] = 99
    with pytest.raises(FidelityError, match=r"\(a\)"):
        verify_generic(bad, tpl, difficulty="easy")


def test_verify_catches_missing_auxiliary():
    tpl, data = _toy_instance()
    bad = copy.deepcopy(data)
    del bad["auxiliary"]
    with pytest.raises(FidelityError, match=r"\(a\)"):
        verify_generic(bad, tpl, difficulty="easy")


def test_verify_catches_aux_display_drift():
    tpl, data = _toy_instance()
    bad = copy.deepcopy(data)
    bad["auxiliary"][0]["value"] = 13  # exact stays "12"
    with pytest.raises(FidelityError, match=r"\(e\)"):
        verify_generic(bad, tpl, difficulty="easy")


def test_verify_catches_aux_unit_mismatch():
    tpl, data = _toy_instance()
    bad = copy.deepcopy(data)
    bad["auxiliary"][0]["unit"] = "s"
    with pytest.raises(FidelityError, match=r"\(c\)"):
        verify_generic(bad, tpl, difficulty="easy")


from engine.errors import TemplateValidationError as TVE
from templates.declarative.gate import validate_template
from templates.declarative.units import check_homogeneous


def test_gate_accepts_fractional_golden_given():
    doc = _toy_doc(golden_cases=[
        {"given": {"d": 12, "w": 3}, "find": "t", "difficulty": "easy",
         "expected": "4"},
        {"given": {"d": "7/2", "w": 1}, "find": "t", "difficulty": "easy",
         "expected": "7/2"},
    ])
    report = validate_template(doc, n_smoke=2)
    assert report.passed, [(s.number, s.reason) for s in report.stages]


def test_dimensional_stage_covers_auxiliary_units():
    doc = _toy_doc(auxiliary={"p": {"unit": "s"}})  # wrong: p should be m
    tpl = parse_template(doc)
    with pytest.raises(TVE):
        check_homogeneous(tpl)


# -- F1: tied find roots exhaust every matching branch (final review) ---------

TIED_DOC = {
    "topic": "toy-tied",
    "variables": {
        "c": {"unit": "1", "ranges": {"easy": [4, 4, False], "medium": [4, 4, False], "hard": [4, 4, False]}},
        "t": {"unit": "1", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]}},
    },
    "auxiliary": {"q": {"unit": "1"}},
    "equations": ["Eq(q**2, c)", "Eq(t, c)"],
    "root_policy": {"name": "smallest_positive_physical"},
    "constraints": [],
    "default_split": {"given": ["c"], "find": "t"},
    "golden_cases": [{"given": {"c": 4}, "find": "t", "difficulty": "easy",
                      "expected": "4"}],
    "trust_state": "unverified",
}


def test_tied_branches_rational_aux_generates():
    # c = 4 -> t = 4 with q = ±2, both rational; previously succeeded via the
    # first matching branch, still must succeed after the exhaustion fix.
    tpl = parse_template(TIED_DOC)
    with registry.temporary(tpl):
        data = generate("toy-tied", given=["c"], find="t",
                        conditions={"c": 4}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "4"


def test_tied_branches_all_irrational_exhausted():
    # c = 2 -> t = 2 with q = ±sqrt(2); both tied branches are irrational, so
    # every matching branch must be tried and exhausted before re-rolling,
    # eventually raising NoCleanInstanceError (not an early return None).
    tpl = parse_template(TIED_DOC)
    with registry.temporary(tpl):
        with pytest.raises(NoCleanInstanceError):
            generate("toy-tied", given=["c"], find="t",
                     conditions={"c": 2}, difficulty="easy", seed=1,
                     max_attempts=10)


# -- F2: harness branch selection must match emitted auxiliaries -------------

from harness.verify import _assert_system_recompute


def test_harness_recompute_rejects_branch_with_wrong_auxiliary():
    tpl = parse_template(_toy_doc())
    d_sym, w_sym, t_sym = (tpl.symbol(n) for n in ("d", "w", "t"))
    p_sym = next(iter(tpl.auxiliaries))
    given = {d_sym: sympy.Integer(12), w_sym: sympy.Integer(3)}
    with pytest.raises(FidelityError, match="matches the emitted auxiliaries"):
        _assert_system_recompute(
            tpl, given, t_sym, sympy.Integer(4),
            {p_sym: sympy.Integer(99)}, "easy",
        )
