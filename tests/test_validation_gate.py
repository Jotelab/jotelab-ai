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
