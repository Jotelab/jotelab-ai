"""Free-fall / vertical-motion topic: SUVAT relations with a fixed gravity g.

Free fall is uniformly-accelerated motion where the acceleration is not a free
choice — it is gravity. So `g` is modelled as a dimensioned variable (m/s^2)
pinned to 10 and always given, never solved for. Convention here is
down-positive with non-negative quantities (a dropped or thrown-down object);
upward throws (signed) are a future extension.
"""

import json
from pathlib import Path

from engine import registry
from engine.errors import NoCleanInstanceError
from engine.loop import generate
from harness.verify import verify_generic
from templates.declarative import parse_template, validate_template

FREE_FALL_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "free_fall.json"


def _doc():
    return json.loads(FREE_FALL_JSON.read_text())


def test_free_fall_json_passes_all_five_stages():
    report = validate_template(_doc(), n_smoke=4)
    assert report.passed, [(s.number, s.reason) for s in report.stages if not s.passed]
    assert [s.number for s in report.stages] == [1, 2, 3, 4, 5]


def test_drop_from_rest_final_velocity():
    """Dropped from rest (u=0), after t seconds v = g*t = 10t."""
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        data = generate("free-fall", given=("u", "g", "t"), find="v",
                        conditions={"u": 0, "g": 10, "t": 3}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "30"
    assert data["find"]["unit"] == "m/s"


def test_distance_fallen():
    """h = u*t + (1/2)g*t^2; u=5, t=2, g=10 -> 5*2 + 5*4 = 30 m."""
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        data = generate("free-fall", given=("u", "g", "t"), find="h",
                        conditions={"u": 5, "g": 10, "t": 2}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "30"
    assert data["find"]["unit"] == "m"


def test_gravity_always_appears_as_a_given_ten():
    """Every generated instance carries g = 10 m/s^2 among the givens."""
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        for seed in range(15):
            data = generate("free-fall", given=("u", "g", "t"), find="v",
                            difficulty="medium", seed=seed)
            g = next(x for x in data["given"] if x["symbol"] == "g")
            assert g["exact"] == "10" and g["unit"] == "m/s^2"


def test_physical_splits_generate_and_verify_across_bands():
    tpl = parse_template(_doc())
    # g is always given; the solvable, physically meaningful targets are u/v/h/t.
    splits = [
        (("u", "g", "t"), "v"),
        (("u", "g", "t"), "h"),
        (("v", "g", "t"), "h"),
        (("u", "v", "g"), "h"),
        (("v", "g", "t"), "u"),
        (("u", "v", "g"), "t"),
    ]
    with registry.temporary(tpl):
        for given, find in splits:
            for band in ("easy", "medium", "hard"):
                for seed in range(4):
                    data = generate("free-fall", given=given, find=find,
                                    difficulty=band, seed=seed)
                    assert verify_generic(data, tpl, difficulty=band) is True


def test_g_is_not_a_solve_target():
    """g is a known constant, not an unknown: solving *for* g must either fail to
    converge or (if it does) return exactly 10 — never a wrong-physics value."""
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        try:
            data = generate("free-fall", given=("u", "v", "t"), find="g",
                            difficulty="easy", seed=3)
            assert data["find"]["exact"] == "10"
        except NoCleanInstanceError:
            pass  # expected: g cannot be derived from independently-sampled u,v,t


def test_all_answers_nonnegative_downward_convention():
    tpl = parse_template(_doc())
    with registry.temporary(tpl):
        for seed in range(30):
            data = generate("free-fall", given=("u", "g", "t"), find="h",
                            difficulty="hard", seed=seed)
            assert data["find"]["value"] >= 0


def test_registered_and_loadable():
    assert "free-fall" in registry.topics()
    assert registry.load_template("free-fall").topic == "free-fall"


def test_diagram_is_vertical_and_hides_the_answer():
    data = generate("free-fall", given=("u", "g", "t"), find="v",
                    difficulty="easy", seed=2)
    assert data["diagram"]["orientation"] == "vertical"
    seg = data["diagram"]["segments"][0]
    assert seg["acceleration"]["symbol"] == "g"
    assert "exact" not in seg["velocity_out"]
