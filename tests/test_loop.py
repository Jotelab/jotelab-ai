"""Bounded-loop, determinism, degradation, and exactness tests (build guide §11).

Spec ties: §5 (bounded loop, determinism), §6 (degradation, exact cleanliness),
§9 (loud failure).
"""

import sympy
import pytest

from engine import policy as policy_mod
from engine.errors import NoCleanInstanceError
from engine.loop import generate
from templates.suvat import a, t, u, v


def test_seed_determinism():
    """Spec §5, §7: the same seed reproduces byte-identical sympy_data."""
    kw = dict(topic="suvat", given=(u, a, t), find=v, difficulty="easy", seed=12345)
    assert generate(**kw) == generate(**kw)


def test_different_seeds_differ():
    """Sanity: different seeds generally produce different instances."""
    one = generate("suvat", given=(u, a, t), find=v, seed=1)
    two = generate("suvat", given=(u, a, t), find=v, seed=2)
    # At least the seed field differs; values very likely differ too.
    assert one["seed"] != two["seed"]


def test_bounded_loop_raises_not_hangs(monkeypatch):
    """Spec §5, §9: an unsatisfiable clean policy raises after <= MAX_ATTEMPTS."""
    monkeypatch.setattr(policy_mod.Policy, "is_clean", lambda self, value: False)
    with pytest.raises(NoCleanInstanceError):
        generate("suvat", given=(u, a, t), find=v, max_attempts=20, soft_limit=10)


def test_graceful_degradation_loosens_once(monkeypatch):
    """Spec §5, §6: the policy loosens once at SOFT_LIMIT before succeeding.

    is_clean accepts only a loosened policy (max_places >= 2). So every attempt
    before SOFT_LIMIT fails, the loop loosens at SOFT_LIMIT, and the next attempt
    succeeds — and policy_applied records the loosening.
    """
    def only_when_loosened(self, value):
        return self.max_places >= 2

    monkeypatch.setattr(policy_mod.Policy, "is_clean", only_when_loosened)
    data = generate(
        "suvat", given=(u, a, t), find=v, difficulty="easy",
        max_attempts=200, soft_limit=5,
    )
    assert data["policy_applied"] == "easy+loosened"


def test_exact_not_float_cleanliness():
    """Spec §6, §9: is_clean is exact — a value that only *looks* clean is rejected.

    1/3 rounds to a 'clean-looking' float (0.333…) but is not a terminating
    decimal; the easy tier (1 decimal, no fractions) must reject it.
    """
    easy = policy_mod.for_("suvat", "easy")
    assert easy.is_clean(sympy.Integer(10))
    assert easy.is_clean(sympy.Rational(105, 10))   # 10.5, one decimal
    assert not easy.is_clean(sympy.Rational(1, 3))  # 0.333… — not clean
    assert not easy.is_clean(sympy.Rational(101, 100))  # 1.01 — two decimals


def test_policy_loosen_increments_places():
    """Spec §5, §6: loosen() relaxes cleanliness (more decimal places)."""
    easy = policy_mod.for_("suvat", "easy")
    loosened = policy_mod.loosen(easy)
    assert loosened.max_places == easy.max_places + 1
    assert loosened.loosened is True
    assert loosened.is_clean(sympy.Rational(101, 100))  # now 2 decimals pass


# -- pivot re-roll (answer-first sampling for weak cells, 2026-07-31) ----------


def test_pivot_rescues_inverse_free_fall_split():
    """The weak-cell fix: {u,g,h}->t at medium used to fail ~15% of seeds
    (clean t needs h/(...) to be a perfect square under a random integer h).
    The pivot samples t from its own range and derives h, so every seed of
    this cell must now produce a verified instance with a clean answer."""
    for seed in range(1, 11):
        data = generate(
            "free-fall", given=("u", "g", "h"), find="t",
            difficulty="medium", seed=seed,
        )
        answer = sympy.nsimplify(data["final_answer"]["exact"])
        assert policy_mod.for_("free-fall", "medium").is_clean(answer)


def test_pivot_keeps_derived_given_sampler_shaped():
    """A pivot-derived given must be indistinguishable from a sampled one:
    integer and inside the per-difficulty range (spec §6 plausibility)."""
    from engine.registry import load_template

    template = load_template("free-fall")
    lo, hi, _ = template.range_for(template.symbol("h"), "medium")
    for seed in range(1, 11):
        data = generate(
            "free-fall", given=("u", "g", "h"), find="t",
            difficulty="medium", seed=seed,
        )
        h_given = next(g for g in data["given"] if g["symbol"] == "h")
        h_value = sympy.nsimplify(h_given["exact"])
        assert h_value.is_Integer
        assert lo <= h_value <= hi


def test_pivot_determinism():
    """Spec §5, §7 still hold with the pivot in play: same seed, same bytes."""
    kw = dict(
        topic="two-phase-ascent", given=("a", "g", "H"), find="t1",
        difficulty="hard", seed=7,
    )
    assert generate(**kw) == generate(**kw)


def test_pivot_never_derives_a_pinned_given():
    """A condition-pinned given keeps its pinned value: the pivot may only
    derive a *free* given (a pinned one is excluded from pivot plans)."""
    for seed in range(1, 6):
        data = generate(
            "free-fall", given=("u", "g", "h"), find="t",
            difficulty="medium", seed=seed, conditions={"u": 0},
        )
        u_given = next(g for g in data["given"] if g["symbol"] == "u")
        assert sympy.nsimplify(u_given["exact"]) == 0
