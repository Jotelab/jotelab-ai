"""The shared diagram builders. The answer-hiding rule (find elements carry no
value/exact) is enforced in DiagramContext.label, so every topic inherits it."""

import sympy

from templates.diagrams import DiagramContext, actors, motion_1d, plot_2d
from templates.suvat import SUVAT


def _ctx(find_name="v"):
    u, a, t, v = (SUVAT.symbol(n) for n in ("u", "a", "t", "v"))
    values = {u: sympy.Integer(5), a: sympy.Integer(2),
              t: sympy.Integer(3), v: sympy.Integer(11)}
    return DiagramContext(SUVAT, values, given={u, a, t},
                          find=SUVAT.symbol(find_name))


def test_given_label_carries_both_numeric_forms_and_unit():
    label = _ctx().label(SUVAT.symbol("u"))
    assert label == {"symbol": "u", "label": "v_0", "role": "given",
                     "value": 5, "exact": "5", "unit": "m/s"}


def test_find_label_omits_value_and_exact():
    """The load-bearing invariant: the answer is never on the wire."""
    label = _ctx().label(SUVAT.symbol("v"))
    assert label == {"symbol": "v", "label": "v", "role": "find"}
    assert "value" not in label and "exact" not in label


def test_non_given_non_find_symbol_is_derived():
    """A value the engine computed that is not the answer is safe to show."""
    ctx = _ctx(find_name="s")
    ctx.values[SUVAT.symbol("v")] = sympy.Integer(11)
    label = ctx.label(SUVAT.symbol("v"))
    assert label["role"] == "derived"
    assert label["exact"] == "11"


def test_symbol_absent_from_the_instance_yields_none():
    """Callers drop the element entirely rather than drawing an empty arrow."""
    ctx = _ctx()
    del ctx.values[SUVAT.symbol("a")]
    assert ctx.label(SUVAT.symbol("a")) is None


def test_exact_form_survives_a_non_terminating_rational():
    """ADR-005: exact is authoritative; value may be a lossy round."""
    ctx = _ctx()
    ctx.values[SUVAT.symbol("u")] = sympy.Rational(1, 3)
    label = ctx.label(SUVAT.symbol("u"))
    assert label["exact"] == "1/3"
    assert label["value"] == 0.333333


def test_motion_1d_emits_kind_orientation_and_segments():
    ctx = _ctx()
    spec = motion_1d(ctx, segments=[{
        "velocity_in": SUVAT.symbol("u"),
        "acceleration": SUVAT.symbol("a"),
        "velocity_out": SUVAT.symbol("v"),
        "duration": SUVAT.symbol("t"),
    }])
    assert spec["kind"] == "motion-1d"
    assert spec["orientation"] == "horizontal"
    assert len(spec["segments"]) == 1
    seg = spec["segments"][0]
    assert seg["direction"] == "forward"
    assert seg["velocity_in"]["exact"] == "5"
    assert seg["velocity_out"] == {"symbol": "v", "label": "v", "role": "find"}


def test_motion_1d_drops_roles_absent_from_the_instance():
    """s is not in this split, so no displacement bracket is drawn."""
    ctx = _ctx()
    spec = motion_1d(ctx, segments=[{
        "velocity_in": SUVAT.symbol("u"),
        "span": SUVAT.symbol("s"),
    }])
    assert "span" not in spec["segments"][0]
    assert "velocity_in" in spec["segments"][0]


def test_motion_1d_carries_orientation_and_reverse_direction():
    """Vertical + reversal is the upward-throw / out-and-back shape."""
    ctx = _ctx()
    spec = motion_1d(ctx, orientation="vertical", segments=[
        {"velocity_in": SUVAT.symbol("u")},
        {"direction": "reverse", "velocity_out": SUVAT.symbol("v")},
    ])
    assert spec["orientation"] == "vertical"
    assert [s["direction"] for s in spec["segments"]] == ["forward", "reverse"]


def test_plot_2d_emits_two_form_points_and_shows_all_values():
    """plot-2d is the deliberate exception: the polyline IS the problem
    statement for graph-reading splits, so points are always shown."""
    ctx = _ctx(find_name="s")
    spec = plot_2d(
        ctx,
        axes={"x": {"symbol": "t", "unit": "s"},
              "y": {"symbol": "v", "unit": "m/s"}},
        points=[(sympy.Integer(0), sympy.Integer(4)),
                (sympy.Integer(3), sympy.Integer(10))],
    )
    assert spec["kind"] == "plot-2d"
    assert spec["axes"]["y"] == {"symbol": "v", "unit": "m/s"}
    assert spec["points"][1] == {"x": {"value": 3, "exact": "3"},
                                 "y": {"value": 10, "exact": "10"}}


def test_plot_2d_never_annotates_the_find_quantity():
    """Points stay; a caption of the answer does not."""
    ctx = _ctx(find_name="s")
    spec = plot_2d(ctx, axes={"x": {"symbol": "t", "unit": "s"},
                              "y": {"symbol": "v", "unit": "m/s"}},
                   points=[(sympy.Integer(0), sympy.Integer(4))])
    assert "annotations" not in spec


def test_actors_labels_each_body_velocity():
    ctx = _ctx()
    spec = actors(ctx, bodies=[{"name": "A", "velocity": SUVAT.symbol("u")},
                               {"name": "B", "velocity": SUVAT.symbol("v")}])
    assert spec["kind"] == "actors"
    assert spec["bodies"][0]["name"] == "A"
    assert spec["bodies"][0]["velocity"]["exact"] == "5"
    assert spec["bodies"][1]["velocity"]["role"] == "find"
