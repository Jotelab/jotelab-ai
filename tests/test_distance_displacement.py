"""Distance vs displacement over a two-segment path (code template).

Not a declarative topic (it needs Abs), so it doesn't go through the five-stage
gate — these tests are its gate: the two relations generate correctly, the
independent Data Fidelity oracle agrees (Abs and all), distance is always the
non-negative total path length while displacement is the signed net, and solving
back for a segment is refused.
"""

import sympy

from engine import registry
from engine.errors import UnsolvableError
from engine.loop import generate
from harness.verify import verify_generic
from templates.distance_displacement import DISTANCE_DISPLACEMENT as TPL


def test_distance_and_displacement_of_a_there_and_back_path():
    """8 m one way then 3 m back: displacement 5 m (net), distance 11 m (total)."""
    disp = generate("distance-displacement", given=("d1", "d2"), find="disp",
                    conditions={"d1": 8, "d2": -3}, difficulty="easy", seed=1)
    dist = generate("distance-displacement", given=("d1", "d2"), find="dist",
                    conditions={"d1": 8, "d2": -3}, difficulty="easy", seed=1)
    assert disp["find"]["exact"] == "5"
    assert dist["find"]["exact"] == "11"
    assert disp["find"]["unit"] == "m" and dist["find"]["unit"] == "m"


def test_displacement_can_be_negative_and_zero():
    # net motion in the -x direction
    neg = generate("distance-displacement", given=("d1", "d2"), find="disp",
                   conditions={"d1": 4, "d2": -10}, difficulty="easy", seed=1)
    assert neg["find"]["exact"] == "-6"
    # returns to start -> zero displacement, but distance is the full path
    zero = generate("distance-displacement", given=("d1", "d2"), find="disp",
                    conditions={"d1": 7, "d2": -7}, difficulty="easy", seed=1)
    back = generate("distance-displacement", given=("d1", "d2"), find="dist",
                    conditions={"d1": 7, "d2": -7}, difficulty="easy", seed=1)
    assert zero["find"]["exact"] == "0"
    assert back["find"]["exact"] == "14"


def test_distance_is_never_negative_and_at_least_abs_displacement():
    for seed in range(60):
        dist = generate("distance-displacement", given=("d1", "d2"), find="dist",
                        difficulty="hard", seed=seed)
        disp = generate("distance-displacement", given=("d1", "d2"), find="disp",
                        difficulty="hard", seed=seed)
        assert dist["find"]["value"] >= 0
        assert dist["find"]["value"] >= abs(disp["find"]["value"])


def test_both_finds_verify_across_bands():
    for find in ("disp", "dist"):
        for band in ("easy", "medium", "hard"):
            for seed in range(6):
                data = generate("distance-displacement", given=("d1", "d2"), find=find,
                                difficulty=band, seed=seed)
                assert verify_generic(data, TPL, difficulty=band) is True


def test_distance_equals_sum_of_absolute_segments():
    for seed in range(30):
        data = generate("distance-displacement", given=("d1", "d2"), find="dist",
                        difficulty="medium", seed=seed)
        g = {x["symbol"]: sympy.Rational(x["exact"]) for x in data["given"]}
        assert sympy.Rational(data["find"]["exact"]) == abs(g["d1"]) + abs(g["d2"])


def test_solving_back_for_a_segment_is_refused():
    """Inverting an absolute value is out of scope; the split must be rejected."""
    try:
        generate("distance-displacement", given=("d1", "dist"), find="d2",
                 difficulty="easy", seed=1)
        assert False, "expected an UnsolvableError for a back-solve split"
    except UnsolvableError:
        pass


def test_only_two_valid_splits():
    splits = sorted(
        (tuple(sorted(s.name for s in given)), find.name)
        for given, find in TPL.valid_splits()
    )
    assert splits == sorted([(("d1", "d2"), "disp"), (("d1", "d2"), "dist")])


def test_registered_and_loadable():
    assert "distance-displacement" in registry.topics()
    assert registry.load_template("distance-displacement").topic == "distance-displacement"


def test_diagram_draws_the_out_and_back_legs():
    """d1 out, d2 back: the reversal is exactly what makes distance differ
    from displacement, so the figure must show it."""
    data = generate("distance-displacement", given=("d1", "d2"), find="disp",
                    difficulty="easy", seed=9)
    segs = data["diagram"]["segments"]
    assert [s["direction"] for s in segs] == ["forward", "reverse"]
    assert segs[0]["span"]["symbol"] == "d1"
    assert segs[1]["span"]["symbol"] == "d2"


def test_diagram_distinguishes_net_displacement_from_path_length():
    """disp is the start-to-finish arrow; dist is the length walked. Drawing
    one as the other is the mislabel this role exists to prevent.

    Each split draws only its own quantity: asking for disp leaves dist out of
    the instance entirely, so it is dropped rather than drawn unlabelled.
    """
    net = generate("distance-displacement", given=("d1", "d2"), find="disp",
                   difficulty="easy", seed=9)
    totals = {t["symbol"]: t for t in net["diagram"]["totals"]}
    assert totals["disp"]["measures"] == "displacement"
    assert totals["disp"]["role"] == "find" and "value" not in totals["disp"]
    assert "dist" not in totals

    walked = generate("distance-displacement", given=("d1", "d2"), find="dist",
                      difficulty="easy", seed=9)
    totals = {t["symbol"]: t for t in walked["diagram"]["totals"]}
    assert totals["dist"]["measures"] == "path"
    assert totals["dist"]["role"] == "find" and "value" not in totals["dist"]
    assert "disp" not in totals
