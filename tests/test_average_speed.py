"""Average speed vs average velocity over a two-segment path (code template).

The rate counterpart of distance-displacement: average speed is total path
length over time (scalar, >= 0); average velocity is net displacement over time
(signed). Needs Abs, so it is a code template; these tests are its gate.
"""

import sympy

from engine import registry
from engine.errors import UnsolvableError
from engine.loop import generate
from harness.verify import verify_generic
from templates.average_speed import AVERAGE_SPEED as TPL


def test_out_and_back_speed_vs_velocity():
    """10 m out, 4 m back in 2 s: speed (10+4)/2 = 7, velocity (10-4)/2 = 3."""
    sp = generate("average-speed", given=("d1", "d2", "t"), find="sp",
                  conditions={"d1": 10, "d2": -4, "t": 2}, difficulty="easy", seed=1)
    vavg = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                    conditions={"d1": 10, "d2": -4, "t": 2}, difficulty="easy", seed=1)
    assert sp["find"]["exact"] == "7"
    assert vavg["find"]["exact"] == "3"
    assert sp["find"]["unit"] == "m/s" and vavg["find"]["unit"] == "m/s"


def test_full_return_zero_velocity_nonzero_speed():
    """6 m out and 6 m back in 3 s: velocity 0 (vector), speed 4 (scalar)."""
    vavg = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                    conditions={"d1": 6, "d2": -6, "t": 3}, difficulty="easy", seed=1)
    sp = generate("average-speed", given=("d1", "d2", "t"), find="sp",
                  conditions={"d1": 6, "d2": -6, "t": 3}, difficulty="easy", seed=1)
    assert vavg["find"]["exact"] == "0"
    assert sp["find"]["exact"] == "4"


def test_velocity_carries_direction():
    """Net motion in -x: the average velocity is negative."""
    vavg = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                    conditions={"d1": 4, "d2": -10, "t": 3}, difficulty="easy", seed=1)
    assert vavg["find"]["exact"] == "-2"


def test_speed_is_never_negative_and_at_least_abs_velocity():
    """Within one instance: sp = (|d1|+|d2|)/t >= |d1+d2|/t = |vavg|.

    Checked against the instance's own givens — two generate() calls with the
    same seed but different finds may accept different re-roll attempts, so
    they are not the same journey.
    """
    for seed in range(40):
        data = generate("average-speed", given=("d1", "d2", "t"), find="sp",
                        difficulty="hard", seed=seed)
        g = {x["symbol"]: sympy.Rational(x["exact"]) for x in data["given"]}
        sp_val = sympy.Rational(data["find"]["exact"])
        assert sp_val >= 0
        assert sp_val >= abs(g["d1"] + g["d2"]) / g["t"]


def test_both_finds_verify_across_bands():
    for find in ("sp", "vavg"):
        for band in ("easy", "medium", "hard"):
            for seed in range(6):
                data = generate("average-speed", given=("d1", "d2", "t"), find=find,
                                difficulty=band, seed=seed)
                assert verify_generic(data, TPL, difficulty=band) is True


def test_back_solving_a_segment_or_time_is_refused():
    for given, find in ((("d1", "d2", "sp"), "t"), (("d1", "t", "sp"), "d2")):
        try:
            generate("average-speed", given=given, find=find, difficulty="easy", seed=1)
            assert False, f"expected UnsolvableError for {given} -> {find}"
        except UnsolvableError:
            pass


def test_only_two_valid_splits():
    splits = sorted(
        (tuple(sorted(s.name for s in given)), find.name)
        for given, find in TPL.valid_splits()
    )
    assert splits == sorted([(("d1", "d2", "t"), "sp"), (("d1", "d2", "t"), "vavg")])


def test_registered_and_loadable():
    assert "average-speed" in registry.topics()
    assert registry.load_template("average-speed").topic == "average-speed"


def test_diagram_draws_both_legs():
    data = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                    difficulty="easy", seed=6)
    segs = data["diagram"]["segments"]
    assert len(segs) == 2
    assert segs[0]["span"]["symbol"] == "d1"
    assert segs[1]["span"]["symbol"] == "d2"
    assert all(s["direction"] == "forward" for s in segs)


def test_diagram_brackets_the_trip_time_and_rate_rather_than_leg_two():
    """t is the whole trip's time (sp = (|d1| + |d2|) / t), so it must not be
    drawn as segment 2's duration — and the rate rides on the trip too."""
    data = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                    difficulty="easy", seed=6)
    spec = data["diagram"]
    assert all("duration" not in s for s in spec["segments"])
    totals = {t["symbol"]: t for t in spec["totals"]}
    assert totals["t"]["measures"] == "duration"
    assert totals["vavg"]["measures"] == "rate"
    assert totals["vavg"]["role"] == "find" and "value" not in totals["vavg"]
    assert "sp" not in totals  # absent from this split, so not drawn
