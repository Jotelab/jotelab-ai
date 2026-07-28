"""Scene compiler ontology (spec 2026-07-29, Task 1): names, units, rendering.

Also covers Task 2 (principle KB, per-phase equation emission)."""

import pytest

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
