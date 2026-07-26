"""1-D vectors / direction topic: average velocity v = s/t with signed quantities.

This is the first Linear-Motion strand beyond SUVAT. Its purpose is *direction*:
displacement and average velocity are signed (the sign is the direction), so the
engine must be able to emit and verify negative answers — which SUVAT's
positive-only root policy and clean-answer tier deliberately forbid. These tests
pin down that the signed path (signed_physical root policy + signed_answer flag)
works end to end, and that time stays strictly positive.
"""

import json
from pathlib import Path

import pytest

from engine import registry
from engine.loop import generate
from harness.verify import verify_generic
from templates.declarative import parse_template, validate_template

VECTORS_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "vectors_1d.json"


def _doc():
    return json.loads(VECTORS_JSON.read_text())


def test_vectors_json_passes_all_five_stages():
    report = validate_template(_doc(), n_smoke=4)
    assert report.passed, [(s.number, s.reason) for s in report.stages if not s.passed]
    assert [s.number for s in report.stages] == [1, 2, 3, 4, 5]


def test_negative_displacement_gives_negative_velocity():
    """The core of vector nature: a negative (leftward) displacement must yield a
    negative average velocity — the direction survives into the answer."""
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        data = generate("vectors-1d", given=("s", "t"), find="v",
                        conditions={"s": -12, "t": 4}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "-3"
    assert data["final_answer"]["value"] == -3
    assert data["find"]["unit"] == "m/s"


def test_positive_displacement_still_works():
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        data = generate("vectors-1d", given=("s", "t"), find="v",
                        conditions={"s": 30, "t": 5}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "6"


def test_negative_answers_actually_occur_across_a_batch():
    """Signed sampling + signed policy must produce genuinely negative answers,
    not just tolerate them — otherwise 'direction' is theoretical."""
    tpl = parse_template(_doc())
    signs = set()
    with registry.temporary(tpl):
        for seed in range(40):
            data = generate("vectors-1d", given=("s", "t"), find="v",
                            difficulty="easy", seed=seed)
            signs.add(data["find"]["value"] < 0)
    assert signs == {True, False}, "expected both negative and positive answers"


def test_all_splits_generate_and_verify_across_bands():
    tpl = parse_template(_doc())
    splits = [("s", "t", "v"), ("v", "t", "s"), ("v", "s", "t")]
    with registry.temporary(tpl):
        for g1, g2, find in splits:
            for band in ("easy", "medium", "hard"):
                for seed in range(5):
                    data = generate("vectors-1d", given=(g1, g2), find=find,
                                    difficulty=band, seed=seed)
                    assert verify_generic(data, tpl, difficulty=band) is True


def test_time_is_always_strictly_positive():
    """Solving for t must never return a negative time even when v and s have
    opposing signs (the t > 0 constraint drives the re-roll)."""
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        for seed in range(60):
            data = generate("vectors-1d", given=("v", "s"), find="t",
                            difficulty="hard", seed=seed)
            assert data["find"]["value"] > 0


def test_three_solvable_splits():
    tpl = parse_template(_doc())
    splits = sorted(
        (tuple(sorted(s.name for s in given)), find.name)
        for given, find in tpl.valid_splits()
    )
    assert splits == sorted([
        (("s", "t"), "v"),
        (("t", "v"), "s"),
        (("s", "v"), "t"),
    ])


def test_registered_and_loadable():
    assert "vectors-1d" in registry.topics()
    assert registry.load_template("vectors-1d").topic == "vectors-1d"


def test_signed_answer_flag_is_set():
    assert parse_template(_doc()).signed_answer is True


def test_declarative_diagram_key_produces_a_motion_1d_spec():
    data = generate("vectors-1d", given=("s", "t"), find="v",
                    difficulty="easy", seed=4)
    seg = data["diagram"]["segments"][0]
    assert data["diagram"]["kind"] == "motion-1d"
    assert seg["span"]["symbol"] == "s"
    assert seg["velocity_out"]["role"] == "find"
    assert "value" not in seg["velocity_out"]
