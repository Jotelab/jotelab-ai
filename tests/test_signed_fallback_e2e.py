"""The three entrance-exam problems the signed fallback recovers.

Each generates with the problem's exact numbers at medium difficulty and must
pass the full Data-Fidelity battery (a)-(e). Source: coverage audit of a
55-problem linear-motion chapter (spec 2026-07-24, Motivation).
"""

import pytest

from engine.loop import generate
from engine.registry import load_template
from harness.verify import verify_generic


CASES = [
    # (label, given, find, conditions, expected exact answer, unit)
    ("average deceleration", ["u", "v", "t"], "a",
     {"u": 30, "v": 10, "t": 2}, "-10", "m/s^2"),
    ("catch velocity", ["a", "s", "t"], "v",
     {"a": -10, "s": 4, "t": 2}, "-8", "m/s"),
    ("rooftop displacement", ["u", "a", "t"], "s",
     {"u": 5, "a": -10, "t": 6}, "-150", "m"),
]


@pytest.mark.parametrize("label,given,find,conds,expected,unit", CASES)
def test_exam_problem_generates_and_verifies(label, given, find, conds,
                                             expected, unit):
    data = generate("suvat", given=given, find=find, conditions=conds,
                    difficulty="medium", seed=1)
    assert data["final_answer"]["exact"] == expected, label
    assert data["final_answer"]["unit"] == unit, label
    assert verify_generic(data, load_template("suvat"),
                          difficulty="medium") is True, label


def test_easy_band_still_refuses_negative_finds():
    from engine.errors import NoCleanInstanceError
    with pytest.raises(NoCleanInstanceError):
        generate("suvat", given=["a", "s", "t"], find="v",
                 conditions={"a": -10, "s": 4, "t": 2},
                 difficulty="easy", seed=1, max_attempts=25)
