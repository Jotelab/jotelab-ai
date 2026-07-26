"""Graph-reading questions over the two-phase scenario: the engine emits the
piecewise v–t polyline (exact values) in sympy_data["diagram"]; rendering is the
web/TikZ track's job. Slope of phase 1 is a, area under the polyline is s."""

import sympy

from engine import registry
from engine.errors import UnsolvableError
from engine.loop import generate
from harness.verify import verify_generic
from templates.motion_graphs import MOTION_GRAPHS as TPL


def _exact_points(data):
    return [(sympy.Rational(p["x"]["exact"]), sympy.Rational(p["y"]["exact"]))
            for p in data["diagram"]["points"]]


def test_graph_payload_shape_and_values():
    """u=4, a=2, t1=3, t2=5: polyline (0,4) -> (3,10) -> (8,10)."""
    data = generate("motion-graphs", given=("u", "a", "t1", "t2"), find="s",
                    conditions={"u": 4, "a": 2, "t1": 3, "t2": 5},
                    difficulty="easy", seed=1)
    assert data["diagram"]["kind"] == "plot-2d"
    assert data["diagram"]["axes"] == {"x": {"symbol": "t", "unit": "s"},
                                       "y": {"symbol": "v", "unit": "m/s"}}
    assert _exact_points(data) == [(0, 4), (3, 10), (8, 10)]
    assert data["find"]["exact"] == "71"


def test_area_under_polyline_equals_displacement():
    """Trapezoid + rectangle area == the emitted total displacement s."""
    for seed in range(20):
        data = generate("motion-graphs", given=("u", "a", "t1", "t2"), find="s",
                        difficulty="medium", seed=seed)
        (x0, y0), (x1, y1), (x2, y2) = _exact_points(data)
        area = (y0 + y1) * (x1 - x0) / 2 + y1 * (x2 - x1)
        assert area == sympy.Rational(data["find"]["exact"])


def test_slope_of_phase_one_equals_acceleration():
    """Rise over run of the first segment == a (the find of the slope split)."""
    for seed in range(20):
        data = generate("motion-graphs", given=("s", "u", "t1", "t2"), find="a",
                        difficulty="medium", seed=seed)
        (x0, y0), (x1, y1), _ = _exact_points(data)
        assert (y1 - y0) / (x1 - x0) == sympy.Rational(data["find"]["exact"])


def test_deceleration_graph_slopes_down():
    """A negative-a story yields a first segment that falls: y1 < y0."""
    data = generate("motion-graphs", given=("u", "a", "t1", "t2"), find="s",
                    conditions={"u": 30, "a": -4, "t1": 5, "t2": 2},
                    difficulty="medium", seed=1)
    (_, y0), (_, y1), _ = _exact_points(data)
    assert y1 < y0
    assert data["find"]["exact"] == "120"


def test_all_splits_verify_and_carry_the_graph():
    splits = [(("u", "a", "t1", "t2"), "s"), (("u", "v", "t1", "t2"), "s"),
              (("s", "u", "t1", "t2"), "v"), (("s", "v", "t1", "t2"), "u"),
              (("s", "u", "t1", "t2"), "a")]
    for given, find in splits:
        for band in ("easy", "medium", "hard"):
            for seed in range(3):
                data = generate("motion-graphs", given=given, find=find,
                                difficulty=band, seed=seed)
                assert verify_generic(data, TPL, difficulty=band) is True
                assert len(data["diagram"]["points"]) == 3


def test_display_values_match_exact():
    from engine.contract import exact, to_display
    data = generate("motion-graphs", difficulty="medium", seed=7)
    for p in data["diagram"]["points"]:
        for axis in ("x", "y"):
            assert to_display(exact(p[axis]["exact"])) == p[axis]["value"]


def test_exactly_five_valid_splits():
    splits = sorted(
        (tuple(sorted(x.name for x in given)), find.name)
        for given, find in TPL.valid_splits()
    )
    assert splits == sorted([
        (("a", "t1", "t2", "u"), "s"), (("t1", "t2", "u", "v"), "s"),
        (("s", "t1", "t2", "u"), "v"), (("s", "t1", "t2", "v"), "u"),
        (("s", "t1", "t2", "u"), "a"),
    ])


def test_classic_slope_split_stays_with_multi_stage():
    """find a from (u, v, t1) has no exact-symbol linking equation once t2 must
    be given for the graph; it is refused here (documented follow-up)."""
    try:
        generate("motion-graphs", given=("u", "v", "t1"), find="a",
                 difficulty="easy", seed=1)
        assert False, "expected UnsolvableError"
    except UnsolvableError:
        pass


def test_registered_and_loadable():
    assert "motion-graphs" in registry.topics()
