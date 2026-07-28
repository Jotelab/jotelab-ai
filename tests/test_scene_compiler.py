"""Scene compiler ontology (spec 2026-07-29, Task 1): names, units, rendering.

Also covers Task 2 (principle KB, per-phase equation emission), Task 3 (the
compiler: scene -> system-template doc), Task 4 (pursuit re-derived from a
scene), and Task 5 (two-phase-ascent registered as a live engine topic)."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import sympy

from engine.loop import generate
from engine.registry import load_template, temporary, topics
from harness.verify import verify_generic
from templates.declarative.gate import validate_template
from templates.declarative.parse import parse_template
from templates.scenes.compile import compile_scene
from templates.scenes.kb import phase_equations
from templates.scenes.ontology import (
    MEET_NAME,
    UNITS,
    SceneError,
    displacement_name,
    duration_name,
    render,
    vend_name,
)


def test_duration_name():
    assert duration_name(1) == "t_1"
    assert duration_name(2) == "t_2"


def test_displacement_name():
    assert displacement_name("car", 1) == "s_car_1"
    assert displacement_name("bus", 2) == "s_bus_2"


def test_vend_name():
    assert vend_name("car", 1) == "vend_car_1"
    assert vend_name("bus", 2) == "vend_bus_2"


def test_meet_name():
    assert MEET_NAME == "x_meet"


def test_units_table():
    assert UNITS == {"duration": "s", "displacement": "m", "velocity": "m/s"}


def test_render_int_value():
    assert render(5, set()) == "5"


def test_render_given_name():
    assert render("a", {"a"}) == "a"


def test_render_neg_prefixed_name():
    assert render("neg:g", {"g"}) == "(-g)"


def test_render_unknown_name_raises():
    with pytest.raises(SceneError):
        render("b", {"a"})


def test_render_auto_raises():
    with pytest.raises(SceneError):
        render("auto", {"a"})


def test_render_exact_float_value():
    # 2.5 is exactly representable -> "5/2" via sympy.nsimplify
    assert render(2.5, set()) == "5/2"


def test_render_inexact_float_raises():
    # classic float artifact: 0.1 + 0.2 != 0.3 in binary64
    with pytest.raises(SceneError):
        render(0.1 + 0.2, set())


def test_render_neg_prefixed_not_validated_against_given_names():
    # neg:NAME is rendered structurally regardless of given_names membership;
    # validation of NAME itself is the compiler's job, not render's.
    assert render("neg:whatever", set()) == "(-whatever)"


# --- Task 2: phase_equations ---------------------------------------------


def test_phase_equations_constant_acceleration_with_vend():
    phase = {"kind": "constant-acceleration", "a": "a", "duration": "t1"}
    equations, aux = phase_equations(
        "rocket", 1, phase, "0", True, {"a", "t1"}
    )
    assert equations == [
        "Eq(s_rocket_1, 0*t1 + a*t1**2/2)",
        "Eq(vend_rocket_1, 0 + a*t1)",
    ]
    assert aux == {"s_rocket_1": "m", "vend_rocket_1": "m/s"}


def test_phase_equations_constant_velocity_no_vend():
    phase = {"kind": "constant-velocity", "v": "v", "duration": "t_1"}
    equations, aux = phase_equations(
        "runner", 1, phase, None, False, {"v"}
    )
    assert equations == ["Eq(s_runner_1, v*t_1)"]
    assert aux == {"s_runner_1": "m"}


def test_phase_equations_constant_velocity_with_vend():
    phase = {"kind": "constant-velocity", "v": "v", "duration": "t_2"}
    equations, aux = phase_equations(
        "runner", 2, phase, None, True, {"v"}
    )
    assert equations == [
        "Eq(s_runner_2, v*t_2)",
        "Eq(vend_runner_2, v)",
    ]
    assert aux == {"s_runner_2": "m", "vend_runner_2": "m/s"}


def test_phase_equations_constant_acceleration_no_vend():
    phase = {"kind": "constant-acceleration", "a": "a", "duration": "t1"}
    equations, aux = phase_equations(
        "rocket", 1, phase, "0", False, {"a", "t1"}
    )
    assert equations == ["Eq(s_rocket_1, 0*t1 + a*t1**2/2)"]
    assert aux == {"s_rocket_1": "m"}


def test_phase_equations_neg_prefixed_acceleration():
    # "neg:g" renders as "(-g)" in the equation string (render is Task 1's
    # job; phase_equations calls it on the phase's own a/v field).
    phase = {"kind": "constant-acceleration", "a": "neg:g", "duration": "t_2"}
    equations, aux = phase_equations(
        "rocket", 2, phase, "vend_rocket_1", True, {"g"}
    )
    assert equations == [
        "Eq(s_rocket_2, vend_rocket_1*t_2 + (-g)*t_2**2/2)",
        "Eq(vend_rocket_2, vend_rocket_1 + (-g)*t_2)",
    ]
    assert aux == {"s_rocket_2": "m", "vend_rocket_2": "m/s"}


def test_phase_equations_unknown_kind_raises():
    phase = {"kind": "constant-jerk", "duration": "t_1"}
    with pytest.raises(SceneError):
        phase_equations("body", 1, phase, None, False, set())


# --- Task 3: compile_scene -------------------------------------------------


def _two_phase_ascent_scene():
    """The plan's own worked example (two-phase-ascent), as a fresh dict."""
    return {
        "topic": "two-phase-ascent",
        "bodies": [
            {
                "name": "rocket",
                "phases": [
                    {"kind": "constant-acceleration", "u": 0, "a": "a", "duration": "t1"},
                    {"kind": "constant-acceleration", "u": "auto", "a": "neg:g",
                     "duration": "auto", "end_condition": {"v": 0}},
                ],
            }
        ],
        "given": {
            "a": {"unit": "m/s^2", "ranges": {"easy": [2, 10, False], "medium": [2, 15, False], "hard": [2, 20, False]}},
            "t1": {"unit": "s", "ranges": {"easy": [2, 10, False], "medium": [2, 15, False], "hard": [2, 20, False]}},
            "g": {"unit": "m/s^2", "ranges": {"easy": [10, 10, False], "medium": [10, 10, False], "hard": [10, 10, False]}},
        },
        "sought": {"quantity": "total_displacement", "body": "rocket", "name": "H",
                   "unit": "m", "ranges": {"easy": [1, 2000, False], "medium": [1, 4000, False], "hard": [1, 8000, False]}},
        "events": [],
        "constraints": [],
        "golden_cases": [
            {"given": {"a": 8, "t1": 10, "g": 10}, "difficulty": "easy", "expected": "720"},
        ],
        "trust_state": "unverified",
    }


# (a) the two-phase-ascent scene compiles with the exact aux keys, equation
# count, and default_split from the plan's worked example.
def test_compile_two_phase_ascent():
    doc = compile_scene(_two_phase_ascent_scene())
    assert set(doc["auxiliary"]) == {
        "s_rocket_1", "vend_rocket_1", "s_rocket_2", "vend_rocket_2", "t_2",
    }
    assert len(doc["equations"]) == 6
    assert doc["default_split"] == {"given": ["a", "g", "t1"], "find": "H"}


def test_compile_emits_variables_in_a_deterministic_order():
    """Givens are emitted name-sorted, so the doc is identical run to run.

    The key order becomes the Template's symbol order, which drives
    valid_splits() and therefore which split a bare CLI run picks. Building it
    from a set made that order vary per process (string hash randomization),
    which flaked the random-topic CLI test whenever the roll landed on a split
    this v1 scene cannot solve inside the re-roll budget.
    """
    doc = compile_scene(_two_phase_ascent_scene())
    given_names = [n for n in doc["variables"] if n != "H"]
    assert given_names == sorted(given_names) == ["a", "g", "t1"]
    assert list(doc["variables"])[-1] == "H"  # the find is appended last


# (b) the compiled doc parses and passes the full existing gate.
def test_compile_two_phase_ascent_passes_the_gate():
    doc = compile_scene(_two_phase_ascent_scene())
    parse_template(doc)  # must not raise
    report = validate_template(doc, n_smoke=2)
    assert report.passed, [(s.number, s.passed, s.reason) for s in report.stages]


# (c) removing the end_condition makes the scene underdetermined.
def test_compile_missing_end_condition_is_underdetermined():
    scene = _two_phase_ascent_scene()
    del scene["bodies"][0]["phases"][1]["end_condition"]
    with pytest.raises(SceneError, match="underdetermined/overdetermined"):
        compile_scene(scene)


# (d) unknown phase kind / undeclared given name / colliding sought name.
def test_compile_unknown_phase_kind_raises():
    scene = _two_phase_ascent_scene()
    scene["bodies"][0]["phases"][0]["kind"] = "constant-jerk"
    with pytest.raises(SceneError):
        compile_scene(scene)


def test_compile_undeclared_given_name_raises():
    scene = _two_phase_ascent_scene()
    scene["bodies"][0]["phases"][0]["a"] = "b"  # "b" is not a declared given
    with pytest.raises(SceneError):
        compile_scene(scene)


def test_compile_colliding_sought_name_raises():
    scene = _two_phase_ascent_scene()
    scene["sought"]["name"] = "a"  # collides with the given "a"
    with pytest.raises(SceneError):
        compile_scene(scene)


# (e) generate + verify_generic on the parsed template reproduce the plan's
# worked numbers exactly, including the auxiliary t_2.
def test_compile_two_phase_ascent_generate_exact():
    doc = compile_scene(_two_phase_ascent_scene())
    tpl = parse_template(doc)
    with temporary(tpl):
        data = generate(
            "two-phase-ascent", given=["a", "g", "t1"], find="H",
            conditions={"a": 8, "t1": 10, "g": 10}, difficulty="easy", seed=1,
        )
    assert data["find"]["exact"] == "720"
    aux_by_symbol = {a["symbol"]: a for a in data["auxiliary"]}
    assert aux_by_symbol["t_2"]["exact"] == "8"
    assert verify_generic(data, tpl, difficulty="easy") is True


# --- extra coverage for the v1 rejections (self-review checklist) ----------


def test_compile_unknown_top_level_key_raises():
    scene = _two_phase_ascent_scene()
    scene["unexpected"] = True
    with pytest.raises(SceneError):
        compile_scene(scene)


def test_compile_duplicate_body_name_raises():
    scene = _two_phase_ascent_scene()
    scene["bodies"].append(copy.deepcopy(scene["bodies"][0]))
    with pytest.raises(SceneError):
        compile_scene(scene)


def test_compile_non_identifier_body_name_raises():
    scene = _two_phase_ascent_scene()
    scene["bodies"][0]["name"] = "not-an-identifier"
    with pytest.raises(SceneError):
        compile_scene(scene)


def test_compile_multi_phase_multi_body_rejected_as_v2():
    scene = _two_phase_ascent_scene()
    second = copy.deepcopy(scene["bodies"][0])
    second["name"] = "rocket2"
    scene["bodies"].append(second)
    with pytest.raises(SceneError, match="v2"):
        compile_scene(scene)


def test_compile_meet_deeper_than_phase_1_rejected_as_v2():
    scene = {
        "topic": "two-car-meet",
        "bodies": [
            {"name": "carA", "phases": [{"kind": "constant-velocity", "v": "va", "duration": "auto"}]},
            {"name": "carB", "phases": [{"kind": "constant-velocity", "v": "vb", "duration": "auto"}]},
        ],
        "given": {
            "va": {"unit": "m/s", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]}},
            "vb": {"unit": "m/s", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]}},
            "t": {"unit": "s", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]}},
            "gap": {"unit": "m", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]}},
        },
        "sought": {"quantity": "duration_of_phase", "body": "carA", "phase": 1, "name": "t",
                   "unit": "s", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]}},
        "events": [{"kind": "meet", "bodies": ["carA", "carB"],
                    "head_start": {"body": "carB", "given": "gap"}, "at_end_of_phase": 2}],
        "constraints": [],
        "golden_cases": [],
        "trust_state": "unverified",
    }
    with pytest.raises(SceneError, match="v2"):
        compile_scene(scene)


def test_compile_unknown_sought_kind_raises():
    scene = _two_phase_ascent_scene()
    scene["sought"]["quantity"] = "average_speed"
    with pytest.raises(SceneError):
        compile_scene(scene)


def test_compile_unknown_event_kind_raises():
    scene = _two_phase_ascent_scene()
    scene["events"] = [{"kind": "collision", "bodies": ["rocket"]}]
    with pytest.raises(SceneError):
        compile_scene(scene)


# --- fix-report regression tests (task review findings) --------------------


def test_compile_nonzero_end_condition_raises():
    # Critical 1: a nonzero end_condition.v leaves a bare residual literal that
    # would fail the frozen dimensional-homogeneity gate several stages later,
    # naming an equation the scene author never wrote. The compiler must reject
    # this itself, loudly, at compile time.
    scene = _two_phase_ascent_scene()
    scene["bodies"][0]["phases"][1]["end_condition"] = {"v": 5}
    with pytest.raises(SceneError, match="unsupported in v1"):
        compile_scene(scene)


def test_compile_undeclared_sought_body_raises_scene_error_total_displacement():
    # Important 2: a typo'd sought.body must raise SceneError, not KeyError.
    scene = _two_phase_ascent_scene()
    scene["sought"]["body"] = "not-a-body"
    with pytest.raises(SceneError, match="not a declared body"):
        compile_scene(scene)


def test_compile_undeclared_sought_body_raises_scene_error_phase_field():
    scene = _two_phase_ascent_scene()
    scene["sought"] = {
        "quantity": "phase_field", "body": "not-a-body", "phase": 1, "field": "a",
        "name": "a", "unit": "m/s^2",
        "ranges": {"easy": [2, 10, False], "medium": [2, 15, False], "hard": [2, 20, False]},
    }
    with pytest.raises(SceneError, match="not a declared body"):
        compile_scene(scene)


def test_compile_end_condition_neg_prefixed_undeclared_name_raises():
    # Minor 3: end_condition.v should go through the same neg:-target declared-name
    # check as every other phase field, not silently reach render()/downstream.
    scene = _two_phase_ascent_scene()
    scene["bodies"][0]["phases"][1]["end_condition"] = {"v": "neg:zzz"}
    with pytest.raises(SceneError, match="not a declared given"):
        compile_scene(scene)


def test_compile_end_condition_non_numeric_raises():
    scene = _two_phase_ascent_scene()
    scene["bodies"][0]["phases"][1]["end_condition"] = {"v": "banana"}
    with pytest.raises(SceneError, match="must be a number"):
        compile_scene(scene)


def test_compile_meet_event_two_car_style():
    # Two bodies, one phase each (v1's allowed shape), sought = duration_of_phase
    # via the shared t_1 auxiliary the meet event's equations pin down.
    scene = {
        "topic": "two-car-meet-scene",
        "bodies": [
            {"name": "carA", "phases": [
                {"kind": "constant-velocity", "v": "va", "duration": "auto"},
            ]},
            {"name": "carB", "phases": [
                {"kind": "constant-acceleration", "u": "vb", "a": "ab", "duration": "auto"},
            ]},
        ],
        "given": {
            "va": {"unit": "m/s", "ranges": {"easy": [6, 20, False], "medium": [6, 30, False], "hard": [6, 40, False]}},
            "vb": {"unit": "m/s", "ranges": {"easy": [1, 5, False], "medium": [1, 10, False], "hard": [1, 15, False]}},
            "ab": {"unit": "m/s^2", "ranges": {"easy": [1, 4, False], "medium": [1, 6, False], "hard": [1, 8, False]}},
            "gap": {"unit": "m", "ranges": {"easy": [0, 10, False], "medium": [0, 30, False], "hard": [0, 60, False]}},
        },
        "sought": {"quantity": "duration_of_phase", "body": "carA", "phase": 1, "name": "t",
                   "unit": "s", "ranges": {"easy": [1, 10, False], "medium": [1, 20, False], "hard": [1, 30, False]}},
        "events": [{"kind": "meet", "bodies": ["carA", "carB"],
                    "head_start": {"body": "carB", "given": "gap"}, "at_end_of_phase": 1}],
        "constraints": [],
        "golden_cases": [
            {"given": {"gap": 0, "va": 20, "vb": 10, "ab": 4}, "difficulty": "easy", "expected": "5"},
        ],
        "trust_state": "unverified",
    }
    doc = compile_scene(scene)
    assert set(doc["auxiliary"]) == {"s_carA_1", "s_carB_1", MEET_NAME}
    assert doc["default_split"] == {"given": ["ab", "gap", "va", "vb"], "find": "t"}
    report = validate_template(doc, n_smoke=2)
    assert report.passed, [(s.number, s.passed, s.reason) for s in report.stages]
    tpl = parse_template(doc)
    with temporary(tpl):
        data = generate(
            "two-car-meet-scene", given=["ab", "gap", "va", "vb"], find="t",
            conditions={"gap": 0, "va": 20, "vb": 10, "ab": 4}, difficulty="easy", seed=1,
        )
    assert data["find"]["exact"] == "5"


# --- Task 4: pursuit re-derived from a scene, behavioral parity ------------

PURSUIT_SCENE_JSON = (
    Path(__file__).resolve().parents[1] / "templates" / "scenes" / "data" / "pursuit_scene.json"
)


def test_pursuit_scene_behaviorally_identical_to_hand_written_pursuit():
    scene = json.loads(PURSUIT_SCENE_JSON.read_text())
    doc = compile_scene(scene)
    assert set(doc["auxiliary"]) == {"s_runner_1", "s_bus_1", MEET_NAME}

    report = validate_template(doc, n_smoke=2)
    assert report.passed, [(s.number, s.passed, s.reason) for s in report.stages]

    tpl = parse_template(doc)
    conditions = {"gap": 6, "a": 1, "v": sympy.Rational(7, 2)}
    with temporary(tpl):
        compiled_data = generate(
            "pursuit-scene", given=["a", "gap", "v"], find="t",
            conditions=conditions, difficulty="easy", seed=1,
        )
    assert compiled_data["find"]["exact"] == "3"
    compiled_aux_by_symbol = {a["symbol"]: a for a in compiled_data["auxiliary"]}
    assert compiled_aux_by_symbol[MEET_NAME]["exact"] == "21/2"

    # Behavioral parity by value against the hand-written topic under
    # identical conditions: same find answer, same meet-point value (the
    # hand-written template names its meet-point auxiliary "x", not "x_meet").
    hand_written_data = generate(
        "pursuit", given=["gap", "a", "v"], find="t",
        conditions=conditions, difficulty="easy", seed=1,
    )
    hand_written_aux_by_symbol = {a["symbol"]: a for a in hand_written_data["auxiliary"]}
    assert compiled_data["find"]["exact"] == hand_written_data["find"]["exact"]
    assert (
        compiled_aux_by_symbol[MEET_NAME]["exact"]
        == hand_written_aux_by_symbol["x"]["exact"]
    )


# --- Task 5: two-phase-ascent registered as a live engine topic ------------


def test_two_phase_ascent_registered_topic():
    assert "two-phase-ascent" in topics()


def test_two_phase_ascent_generates_exact_and_verifies():
    tpl = load_template("two-phase-ascent")
    data = generate(
        "two-phase-ascent", given=["a", "t1", "g"], find="H",
        conditions={"a": 8, "t1": 10, "g": 10}, difficulty="easy", seed=1,
    )
    assert data["find"]["exact"] == "720"
    assert verify_generic(data, tpl, difficulty="easy") is True


def test_two_phase_ascent_cli_verify_smoke():
    root = Path(__file__).resolve().parents[1]
    venv_python = root / ".venv" / "bin" / "python"
    exe = str(venv_python) if venv_python.exists() else sys.executable
    result = subprocess.run(
        [exe, "-m", "engine", "--topic", "two-phase-ascent",
         "--given", "a,t1,g", "--find", "H",
         "--condition", "a=8", "--condition", "t1=10", "--condition", "g=10",
         "--verify"],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "PASS" in result.stdout


# --- final-review hardening (unused-given and given-name validation) -------


def test_compile_unused_given_raises():
    # Important 1: a given no equation references must not silently ship as
    # a red-herring fact in generated problems.
    scene = _two_phase_ascent_scene()
    scene["given"]["zzz"] = {
        "unit": "m", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]},
    }
    with pytest.raises(SceneError, match="zzz.*declared but never used"):
        compile_scene(scene)


def test_compile_given_used_only_in_constraint_does_not_raise():
    # Open 1 (re-review): a given referenced only via scene.constraints (not
    # any equation) is spec-sanctioned -- constraints genuinely restrict
    # sampling -- and must not be flagged as unused.
    scene = _two_phase_ascent_scene()
    scene["given"]["k"] = {
        "unit": "m/s^2", "ranges": {"easy": [1, 5, False], "medium": [1, 5, False], "hard": [1, 5, False]},
    }
    scene["constraints"] = [{"var": "k", "op": ">", "value": 0}]
    doc = compile_scene(scene)  # must not raise
    assert "k" in doc["variables"]
    assert {"var": "k", "op": ">", "value": 0} in doc["constraints"]


def test_compile_non_identifier_given_name_raises():
    # Important 2: given names must be identifier-checked just like body and
    # sought names, or the compiler emits equations naming things it never
    # declared.
    scene = _two_phase_ascent_scene()
    scene["given"]["a*g"] = {
        "unit": "m", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]},
    }
    with pytest.raises(SceneError, match="valid Python identifier"):
        compile_scene(scene)


def test_compile_reserved_given_name_raises():
    # Important 2: parser-reserved names are valid identifiers but produce
    # cryptic downstream failures if used as a given name.
    scene = _two_phase_ascent_scene()
    scene["given"]["Eq"] = {
        "unit": "m", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]},
    }
    with pytest.raises(SceneError, match="reserved"):
        compile_scene(scene)


def test_compile_meet_event_same_body_twice_raises():
    # Minor 3: a meet event listing the same body twice must be rejected at
    # compile time rather than failing obscurely at gate stage 3.
    scene = {
        "topic": "two-car-meet-scene",
        "bodies": [
            {"name": "carA", "phases": [
                {"kind": "constant-velocity", "v": "va", "duration": "auto"},
            ]},
        ],
        "given": {
            "va": {"unit": "m/s", "ranges": {"easy": [6, 20, False], "medium": [6, 30, False], "hard": [6, 40, False]}},
            "gap": {"unit": "m", "ranges": {"easy": [0, 10, False], "medium": [0, 30, False], "hard": [0, 60, False]}},
        },
        "sought": {"quantity": "duration_of_phase", "body": "carA", "phase": 1, "name": "t",
                   "unit": "s", "ranges": {"easy": [1, 10, False], "medium": [1, 20, False], "hard": [1, 30, False]}},
        "events": [{"kind": "meet", "bodies": ["carA", "carA"],
                    "head_start": {"body": "carA", "given": "gap"}, "at_end_of_phase": 1}],
        "constraints": [],
        "golden_cases": [],
        "trust_state": "unverified",
    }
    with pytest.raises(SceneError, match="distinct"):
        compile_scene(scene)
