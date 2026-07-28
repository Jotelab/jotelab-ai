"""Five-stage template validation gate (ADR-007 sub-decision c)."""

import json
from pathlib import Path
import pytest
from engine.errors import TemplateValidationError
from engine import registry
from templates.declarative.gate import validate_template, register_declarative

SUVAT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "suvat.json"


def _doc():
    return json.loads(SUVAT_JSON.read_text())


def test_suvat_json_passes_all_five_stages():
    report = validate_template(_doc(), n_smoke=4)
    assert report.passed, [(s.number, s.reason) for s in report.stages if not s.passed]
    assert [s.number for s in report.stages] == [1, 2, 3, 4, 5]
    assert all(s.passed for s in report.stages)


def test_stage2_rejects_inhomogeneous():
    bad = _doc()
    bad["equations"][0] = "Eq(v, u + a*t**2)"
    report = validate_template(bad, n_smoke=4)
    assert not report.passed
    failing = [s for s in report.stages if not s.passed]
    assert failing and failing[0].number == 2


def test_stage4_rejects_wrong_golden_case():
    bad = _doc()
    bad["golden_cases"] = [{"given": {"u": 0, "a": 2, "t": 5}, "find": "v",
                            "difficulty": "easy", "expected": "999"}]
    report = validate_template(bad, n_smoke=4)
    assert not report.passed
    assert any((not s.passed) and s.number == 4 for s in report.stages)


def test_dropped_half_passes_dimensions_but_caught_by_golden_replay():
    """ADR-007(d) thesis case: a self-consistent wrong equation slips past the
    dimensional gate and is caught only by golden-case replay.

    Dropping the 1/2 from ``s = u*t + a*t**2/2`` leaves it dimensionally valid
    (both terms are a length), so stage 2 passes; but with a *correct* golden case
    for ``s`` the engine now produces the wrong value, so stage 4 fails. This is
    exactly the residue ADR-007 names: dimensional analysis is necessary, not
    sufficient, and the golden case is the backstop.
    """
    bad = _doc()
    bad["equations"][1] = "Eq(s, u*t + a*t**2)"  # E2 with the 1/2 dropped
    # correct answer for {u:0, a:2, t:5}, find s, is u*t + a*t**2/2 = 25
    bad["golden_cases"] = [{"given": {"u": 0, "a": 2, "t": 5}, "find": "s",
                            "difficulty": "easy", "expected": "25"}]
    report = validate_template(bad, n_smoke=4)
    assert not report.passed
    by_num = {s.number: s for s in report.stages}
    assert by_num[2].passed, "dimensional analysis must NOT catch a dropped 1/2"
    failing = [s for s in report.stages if not s.passed]
    assert failing and failing[0].number == 4, "golden replay must catch it"


def test_stage1_rejects_unknown_symbol():
    bad = _doc()
    bad["equations"][0] = "Eq(v, u + a*t + w)"
    report = validate_template(bad, n_smoke=4)
    assert not report.passed
    assert report.stages[0].number == 1 and not report.stages[0].passed


def test_stage3_rejects_undecidable_default_split():
    bad = _doc()
    bad["default_split"] = {"given": ["u", "a"], "find": "v"}  # only 2 givens
    report = validate_template(bad, n_smoke=4)
    assert not report.passed
    assert any((not s.passed) and s.number == 3 for s in report.stages)


def test_register_declarative_registers_on_pass_and_raises_on_fail():
    doc = _doc()
    doc["topic"] = "suvat_probe"
    try:
        tpl = register_declarative(doc)
        assert tpl.topic == "suvat_probe"
        assert "suvat_probe" in registry.topics()
    finally:
        registry._REGISTRY.pop("suvat_probe", None)

    bad = _doc()
    bad["topic"] = "suvat_bad"
    bad["equations"][0] = "Eq(v, u + a*t**2)"
    with pytest.raises(TemplateValidationError) as ei:
        register_declarative(bad)
    assert ei.value.stage == 2
    assert "suvat_bad" not in registry.topics()


def test_gate_rejects_a_diagram_naming_an_undeclared_variable():
    """A typo in a declarative diagram must fail the gate, not ship silently."""
    from templates.declarative.parse import parse_template

    free_fall_json = Path(__file__).resolve().parents[1] / "templates" / "data" / "free_fall.json"
    doc = json.loads(free_fall_json.read_text())
    doc["diagram"]["segments"][0]["velocity_in"] = "nope"
    with pytest.raises(TemplateValidationError, match="undeclared variable"):
        parse_template(doc)
