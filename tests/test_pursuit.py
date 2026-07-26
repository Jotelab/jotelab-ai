"""Pursuit — the system-template proof case (spec 2026-07-27, exam problem #15)."""

import json
from pathlib import Path

import sympy

from engine.loop import generate
from engine.registry import load_template, topics
from harness.verify import verify_generic
from templates.declarative.gate import validate_template

PURSUIT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "pursuit.json"


def test_pursuit_is_registered():
    assert "pursuit" in topics()
    tpl = load_template("pursuit")
    assert {s.name for s in tpl.auxiliaries} == {"x"}


def test_bus_problem_exact_numbers():
    # PDF #15: bus leaves with a = 1.0 m/s^2, man 6.0 m behind runs at 3.5 m/s.
    data = generate("pursuit", given=["gap", "a", "v"], find="t",
                    conditions={"gap": 6, "a": 1, "v": sympy.Rational(7, 2)},
                    difficulty="easy", seed=1)
    assert data["find"]["exact"] == "3"
    assert data["final_answer"]["unit"] == "s"
    assert data["auxiliary"] == [
        {"symbol": "x", "value": 10.5, "exact": "21/2", "unit": "m"}
    ]
    assert verify_generic(data, load_template("pursuit"),
                          difficulty="easy") is True


def test_second_root_derived_and_rejected():
    tpl = load_template("pursuit")
    g = tuple(tpl.symbol(n) for n in ("gap", "a", "v"))
    ok, sol = tpl.solvability(g, tpl.symbol("t"))
    assert ok and len(sol.branches) == 2
    vals = {tpl.symbol("gap"): sympy.Integer(6), tpl.symbol("a"): sympy.Integer(1),
            tpl.symbol("v"): sympy.Rational(7, 2)}
    roots = sorted(sympy.nsimplify(b.find_expr.subs(vals)) for b in sol.branches)
    assert roots == [3, 4]  # catches at 3 s; the re-pass at 4 s is rejected


def test_pursuit_derives_four_splits():
    tpl = load_template("pursuit")
    finds = {f.name for _, f in tpl.valid_splits()}
    assert finds == {"t", "v", "gap", "a"}


def test_pursuit_passes_the_gate():
    doc = json.loads(PURSUIT_JSON.read_text())
    report = validate_template(doc, n_smoke=3)
    assert report.passed, [(s.number, s.passed, s.reason) for s in report.stages]


def test_two_car_fixture_passes_gate_but_is_not_registered():
    fixture = Path(__file__).resolve().parent / "fixtures" / "two_car_meet.json"
    doc = json.loads(fixture.read_text())
    report = validate_template(doc, n_smoke=2)
    assert report.passed, [(s.number, s.passed, s.reason) for s in report.stages]
    assert "two-car-meet" not in topics()
