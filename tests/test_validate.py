"""Automated validation-gate tests (ADR-007 §c/§d).

The gate admits a user-authored declarative template only if it passes, in order:
parse/sandbox → dimensional homogeneity → solvability derivation → golden-case
replay. The two "thesis" tests below pin exactly what automation can and cannot
catch (ADR-007 §d): dimensional analysis rejects a units-wrong equation, but a
dimensionally-valid-yet-wrong equation (a dropped ½) is caught *only* by the
golden case — and only because the author's expected answer is right.
"""

import copy

import pytest

from engine.validate import validate_template
from templates.declarative import SUVAT_SPEC


def test_valid_suvat_spec_passes_every_stage():
    report = validate_template(SUVAT_SPEC)
    assert report.ok
    assert [stage.name for stage in report.stages] == [
        "parse", "dimensional", "solvability", "golden",
    ]
    assert all(stage.passed for stage in report.stages)


def test_undeclared_symbol_fails_at_parse_stage():
    bad = copy.deepcopy(SUVAT_SPEC)
    bad["equations"][0] = "v = u + g*t"  # g is not a declared variable
    report = validate_template(bad)
    assert not report.ok
    assert report.failed_stage().name == "parse"


def test_dimensionally_wrong_equation_fails_at_dimensional_stage():
    """Thesis 1: units reject `v = u + a*t^2` automatically.

    [m/s] = [m/s] + [m/s^2][s^2]=[m] is not homogeneous, so the gate rejects it with
    no human and no golden case — the strongest automatic physics filter.
    """
    bad = copy.deepcopy(SUVAT_SPEC)
    bad["equations"][0] = "v = u + a*t**2"
    report = validate_template(bad)
    assert not report.ok
    assert report.failed_stage().name == "dimensional"


def test_dropped_half_passes_dimensions_but_fails_golden_replay():
    """Thesis 2 (the irreducible residue): a dropped ½ is dimensionally valid.

    `s = u*t + a*t^2` is homogeneous ([m] throughout), so it sails through the
    dimensional stage. It is caught only because the author supplied a *correct*
    golden answer (s = ½·2·5² = 25) that the wrong equation cannot reproduce
    (it yields 50). This is exactly the boundary ADR-007 §d names.
    """
    bad = copy.deepcopy(SUVAT_SPEC)
    bad["equations"][1] = "s = u*t + a*t**2"  # dropped the /2
    bad["golden_cases"] = [
        {"given": {"u": 0, "a": 2, "t": 5}, "find": "s", "difficulty": "easy",
         "expected": "25"},
    ]
    report = validate_template(bad)
    assert not report.ok
    dimensional = next(s for s in report.stages if s.name == "dimensional")
    assert dimensional.passed  # units did NOT catch it
    assert report.failed_stage().name == "golden"  # the golden case did
