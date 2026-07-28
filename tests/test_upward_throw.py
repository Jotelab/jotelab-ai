"""Upward throw — free fall's signed extension, up-positive (code template).

Object thrown straight up: v = u - g*t, h = u*t - g*t^2/2, v^2 = u^2 - 2*g*h,
with g = 10 always given. v and h are signed relative to launch; flight is
constrained to h >= 0 (launch to return). Splits with two physical roots
(find t or v from a given height) are excluded — that needs multi-answer
support (tracked follow-up).
"""

import sympy

from engine import registry
from engine.errors import UnsolvableError
from engine.loop import generate
from harness.verify import verify_generic
from templates.upward_throw import UPWARD_THROW as TPL

G = {"g": 10}


def test_velocity_at_time_signs():
    """u=30: at t=2 still rising (v=+10); at t=4 falling (v=-10)."""
    up = generate("upward-throw", given=("u", "g", "t"), find="v",
                  conditions={"u": 30, "t": 2, **G}, difficulty="easy", seed=1)
    down = generate("upward-throw", given=("u", "g", "t"), find="v",
                    conditions={"u": 30, "t": 4, **G}, difficulty="easy", seed=1)
    assert up["find"]["exact"] == "10"
    assert down["find"]["exact"] == "-10"


def test_height_at_time():
    """u=30, t=2: h = 60 - 20 = 40 m above launch."""
    data = generate("upward-throw", given=("u", "g", "t"), find="h",
                    conditions={"u": 30, "t": 2, **G}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "40"
    assert data["find"]["unit"] == "m"


def test_time_to_top_via_v_zero():
    """Time to max height is the v=0 condition: u=30 -> t = 3 s."""
    data = generate("upward-throw", given=("u", "v", "g"), find="t",
                    conditions={"u": 30, "v": 0, **G}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "3"


def test_max_height_via_v_zero():
    """Max height is the v=0 condition on v^2 = u^2 - 2gh: u=30 -> h = 45 m."""
    data = generate("upward-throw", given=("u", "v", "g"), find="h",
                    conditions={"u": 30, "v": 0, **G}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "45"


def test_launch_speed_from_later_velocity():
    """v=-10 at t=4 -> u = v + g*t = 30."""
    data = generate("upward-throw", given=("v", "g", "t"), find="u",
                    conditions={"v": -10, "t": 4, **G}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "30"


def test_descending_velocities_occur_in_a_batch():
    negatives = 0
    for seed in range(40):
        data = generate("upward-throw", given=("u", "g", "t"), find="v",
                        difficulty="medium", seed=seed)
        if sympy.Rational(data["find"]["exact"]) < 0:
            negatives += 1
    assert negatives > 0


def test_speed_never_exceeds_launch_speed():
    """|v| <= u throughout flight (h >= 0)."""
    for seed in range(40):
        data = generate("upward-throw", given=("u", "g", "t"), find="v",
                        difficulty="hard", seed=seed)
        given = {x["symbol"]: sympy.Rational(x["exact"]) for x in data["given"]}
        assert abs(sympy.Rational(data["find"]["exact"])) <= given["u"]


def test_all_splits_verify_across_bands():
    splits = [(("u", "g", "t"), "v"), (("u", "g", "t"), "h"),
              (("u", "v", "g"), "t"), (("u", "v", "g"), "h"),
              (("v", "g", "t"), "u")]
    for given, find in splits:
        for band in ("easy", "medium", "hard"):
            for seed in range(4):
                data = generate("upward-throw", given=given, find=find,
                                difficulty=band, seed=seed)
                assert verify_generic(data, TPL, difficulty=band) is True


def test_two_root_splits_are_refused():
    """Time (or velocity) at a given height has two answers — rising and
    falling — which the single-answer engine cannot express."""
    for find in ("t", "v"):
        try:
            generate("upward-throw", given=("u", "g", "h"), find=find,
                     conditions={"u": 30, "h": 40, **G}, difficulty="easy", seed=1)
            assert False, f"expected UnsolvableError for (u,g,h) -> {find}"
        except UnsolvableError:
            pass


def test_exactly_five_valid_splits():
    splits = sorted(
        (tuple(sorted(s.name for s in given)), find.name)
        for given, find in TPL.valid_splits()
    )
    assert splits == sorted([
        (("g", "t", "u"), "v"), (("g", "t", "u"), "h"),
        (("g", "u", "v"), "t"), (("g", "u", "v"), "h"),
        (("g", "t", "v"), "u"),
    ])


def test_registered_and_loadable():
    assert "upward-throw" in registry.topics()


def test_diagram_is_vertical_with_an_up_then_down_reversal():
    """The projectile rises, then falls: two segments, opposite directions."""
    data = generate("upward-throw", given=("u", "g", "t"), find="v",
                    difficulty="easy", seed=8)
    spec = data["diagram"]
    assert spec["orientation"] == "vertical"
    assert [s["direction"] for s in spec["segments"]] == ["forward", "reverse"]
    assert spec["segments"][0]["velocity_in"]["symbol"] == "u"
    assert spec["segments"][1]["velocity_out"]["role"] == "find"


def test_diagram_brackets_height_and_time_across_the_whole_flight():
    """h is the height at time t, not the span of the rise, so it is a total."""
    data = generate("upward-throw", given=("u", "g", "t"), find="h",
                    difficulty="easy", seed=8)
    totals = {t["symbol"]: t for t in data["diagram"]["totals"]}
    assert totals["h"]["measures"] == "displacement"
    assert totals["h"]["role"] == "find" and "value" not in totals["h"]
    assert totals["t"]["measures"] == "duration"
    for seg in data["diagram"]["segments"]:
        assert "span" not in seg and "duration" not in seg
