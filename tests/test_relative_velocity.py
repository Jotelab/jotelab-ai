"""1-D relative velocity: velocity of A relative to B, v_AB = v_A - v_B.

Written in the algebraically-equivalent addition form Eq(va, vab + vb) so the
homogeneity gate doesn't cancel `va - vb` (two same-dimension variables) to a
dimensionless zero. Velocities are signed (direction), so this reuses the
signed_physical root policy + signed_answer flag from the vectors work.
"""

import json
from pathlib import Path

from engine import registry
from engine.loop import generate
from harness.verify import verify_generic
from templates.declarative import parse_template, validate_template

REL_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "relative_velocity.json"


def _doc():
    return json.loads(REL_JSON.read_text())


def test_relative_velocity_json_passes_all_five_stages():
    report = validate_template(_doc(), n_smoke=4)
    assert report.passed, [(s.number, s.reason) for s in report.stages if not s.passed]
    assert [s.number for s in report.stages] == [1, 2, 3, 4, 5]


def test_same_direction_relative_velocity():
    """Two objects moving the same way: A at 20, B at 12 -> A relative to B = +8."""
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        data = generate("relative-velocity", given=("va", "vb"), find="vab",
                        conditions={"va": 20, "vb": 12}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "8"
    assert data["find"]["unit"] == "m/s"


def test_opposing_velocities_give_signed_relative():
    """A moving -10 (one way), B moving +5 (the other): v_AB = -10 - 5 = -15."""
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        data = generate("relative-velocity", given=("va", "vb"), find="vab",
                        conditions={"va": -10, "vb": 5}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "-15"


def test_recover_va_from_relative_and_vb():
    """Inverse: va = vab + vb. Given vab and vb, recover va."""
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        data = generate("relative-velocity", given=("vab", "vb"), find="va",
                        conditions={"vab": 8, "vb": 12}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "20"


def test_all_splits_generate_and_verify_across_bands():
    tpl = parse_template(_doc())
    splits = [("va", "vb", "vab"), ("vab", "vb", "va"), ("va", "vab", "vb")]
    with registry.temporary(tpl):
        for g1, g2, find in splits:
            for band in ("easy", "medium", "hard"):
                for seed in range(5):
                    data = generate("relative-velocity", given=(g1, g2), find=find,
                                    difficulty=band, seed=seed)
                    assert verify_generic(data, tpl, difficulty=band) is True


def test_negative_relative_velocities_occur():
    tpl = parse_template(_doc())
    signs = set()
    with registry.temporary(tpl):
        for seed in range(40):
            data = generate("relative-velocity", given=("va", "vb"), find="vab",
                            difficulty="easy", seed=seed)
            signs.add(data["find"]["value"] < 0)
    assert signs == {True, False}


def test_registered_and_loadable():
    assert "relative-velocity" in registry.topics()
    assert registry.load_template("relative-velocity").topic == "relative-velocity"


def test_diagram_names_both_bodies():
    data = generate("relative-velocity", given=("va", "vb"), find="vab",
                    difficulty="easy", seed=5)
    assert data["diagram"]["kind"] == "actors"
    assert [b["name"] for b in data["diagram"]["bodies"]] == ["A", "B"]
    assert data["diagram"]["bodies"][0]["velocity"]["role"] == "given"
