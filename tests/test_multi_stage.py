"""Two-phase 1-D motion: accelerate from u for t1, then cruise at v for t2.

Blocked for declarative templates by the single-equation solvability model;
here each whitelisted split maps to a composite equation whose free symbols are
exactly given ∪ {find} (the harness's linking-equation rule). Motion is
one-directional (v > 0), so distance equals displacement and the narrative
stays unambiguous.
"""

import sympy

from engine import registry
from engine.errors import NoCleanInstanceError, UnsolvableError
from engine.loop import generate
from harness.verify import verify_generic
from templates.multi_stage import MULTI_STAGE as TPL


def test_total_displacement_from_acceleration_form():
    """u=4, a=2, t1=3 (v reaches 10), cruise 5 s: s = 12 + 9 + 50 = 71 m."""
    data = generate("multi-stage-motion", given=("u", "a", "t1", "t2"), find="s",
                    conditions={"u": 4, "a": 2, "t1": 3, "t2": 5},
                    difficulty="easy", seed=1)
    assert data["find"]["exact"] == "71"
    assert data["find"]["unit"] == "m"


def test_total_displacement_from_velocity_form():
    """Same journey stated via v: u=4, v=10, t1=3, t2=5 -> s = 21 + 50 = 71 m."""
    data = generate("multi-stage-motion", given=("u", "v", "t1", "t2"), find="s",
                    conditions={"u": 4, "v": 10, "t1": 3, "t2": 5},
                    difficulty="easy", seed=1)
    assert data["find"]["exact"] == "71"


def test_deceleration_story():
    """u=30, a=-4 for 5 s (v=10), cruise 2 s: s = 150 - 50 + 20 = 120 m."""
    data = generate("multi-stage-motion", given=("u", "a", "t1", "t2"), find="s",
                    conditions={"u": 30, "a": -4, "t1": 5, "t2": 2},
                    difficulty="medium", seed=1)
    assert data["find"]["exact"] == "120"


def test_back_solves_for_v_and_u():
    v = generate("multi-stage-motion", given=("s", "u", "t1", "t2"), find="v",
                 conditions={"s": 71, "u": 4, "t1": 3, "t2": 5},
                 difficulty="easy", seed=1)
    u = generate("multi-stage-motion", given=("s", "v", "t1", "t2"), find="u",
                 conditions={"s": 71, "v": 10, "t1": 3, "t2": 5},
                 difficulty="easy", seed=1)
    assert v["find"]["exact"] == "10"
    assert u["find"]["exact"] == "4"


def test_direction_reversal_is_rerolled_not_emitted():
    """A deceleration that would reverse direction (v <= 0) violates the
    one-directional constraint; with everything pinned the loop must fail loudly
    rather than emit the unphysical story."""
    try:
        generate("multi-stage-motion", given=("u", "a", "t1", "t2"), find="s",
                 conditions={"u": 2, "a": -3, "t1": 4, "t2": 2},
                 difficulty="medium", seed=1)
        assert False, "expected NoCleanInstanceError (v = 2 - 12 < 0)"
    except NoCleanInstanceError:
        pass


def test_all_splits_verify_across_bands():
    splits = [(("u", "a", "t1", "t2"), "s"), (("u", "v", "t1", "t2"), "s"),
              (("s", "u", "t1", "t2"), "v"), (("s", "v", "t1", "t2"), "u")]
    for given, find in splits:
        for band in ("easy", "medium", "hard"):
            for seed in range(4):
                data = generate("multi-stage-motion", given=given, find=find,
                                difficulty=band, seed=seed)
                assert verify_generic(data, TPL, difficulty=band) is True


def test_phase_times_are_narrative_givens():
    """Solving for a phase duration is excluded (quadratic in t1; and the phase
    structure is the story, not the unknown)."""
    try:
        generate("multi-stage-motion", given=("s", "u", "a", "t2"), find="t1",
                 difficulty="easy", seed=1)
        assert False, "expected UnsolvableError for a phase-duration solve"
    except UnsolvableError:
        pass


def test_exactly_four_valid_splits():
    splits = sorted(
        (tuple(sorted(x.name for x in given)), find.name)
        for given, find in TPL.valid_splits()
    )
    assert splits == sorted([
        (("a", "t1", "t2", "u"), "s"), (("t1", "t2", "u", "v"), "s"),
        (("s", "t1", "t2", "u"), "v"), (("s", "t1", "t2", "v"), "u"),
    ])


def test_registered_and_loadable():
    assert "multi-stage-motion" in registry.topics()


def test_diagram_draws_the_two_phases_with_their_own_durations():
    data = generate("multi-stage-motion", given=("u", "a", "t1", "t2"), find="s",
                    difficulty="easy", seed=6)
    segs = data["diagram"]["segments"]
    assert len(segs) == 2
    assert segs[0]["acceleration"]["symbol"] == "a"
    assert segs[0]["duration"]["symbol"] == "t1"
    assert segs[1]["duration"]["symbol"] == "t2"
    assert "acceleration" not in segs[1]   # phase 2 is constant-velocity


def test_diagram_brackets_total_displacement_across_both_phases():
    """s spans both phases (s = u t1 + a t1²/2 + v t2), so attaching it to the
    cruise segment would claim it covers that leg alone."""
    data = generate("multi-stage-motion", given=("u", "a", "t1", "t2"), find="s",
                    difficulty="easy", seed=6)
    spec = data["diagram"]
    assert all("span" not in s for s in spec["segments"])
    total = spec["totals"][0]
    assert total["symbol"] == "s" and total["measures"] == "displacement"
    assert total["role"] == "find" and "value" not in total
