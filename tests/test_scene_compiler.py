"""Scene compiler ontology (spec 2026-07-29, Task 1): names, units, rendering."""

import pytest

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
