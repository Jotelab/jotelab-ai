"""Verification-harness tests + the Gate 5 Data Fidelity batch (build guide §11).

Spec ties: §10/§11 — the harness catches a hand-corrupted instance, and a full
SUVAT seed batch reports Data Fidelity = 100%.
"""

import copy

import pytest
import sympy

from engine.contract import exact
from engine.loop import generate
from harness.batches import WORKED_EXAMPLE, suvat_batch
from harness.verify import FidelityError, verify


def test_exact_parses_rationals_and_fails_closed():
    """N1: contract.exact reloads any engine rational, but rejects non-rationals.

    Uses sympy.Rational (not the general sympify evaluator), so every clean answer
    round-trips exactly while a non-rational string fails closed rather than being
    silently evaluated.
    """
    assert exact("4/7") == sympy.Rational(4, 7)
    assert exact("-3/5") == sympy.Rational(-3, 5)
    assert exact("10") == sympy.Integer(10)
    with pytest.raises((TypeError, ValueError, SyntaxError)):
        exact("2**10")  # an expression, not a rational — must not evaluate to 1024


def _gen(req):
    return generate(
        req["topic"], given=req["given"], find=req["find"],
        difficulty=req["difficulty"], seed=req["seed"],
    )


def test_harness_passes_valid_instance():
    """A genuinely-correct instance passes all four assertions."""
    data = _gen(WORKED_EXAMPLE)
    assert verify(data, difficulty="easy") is True


def test_harness_catches_corruption():
    """Spec §10/§11: corrupt the authoritative answer; verify() must fail (assertion b).

    The harness now reasons on the exact value (ADR-005), so corruption is injected
    into the ``exact`` field (and the matching display value) — the worked example's
    answer is the integer 10, so we bump it to 11.
    """
    data = _gen(WORKED_EXAMPLE)
    corrupted = copy.deepcopy(data)
    corrupted["find"]["value"] += 1
    corrupted["find"]["exact"] = str(int(corrupted["find"]["exact"]) + 1)
    corrupted["final_answer"]["value"] += 1
    corrupted["final_answer"]["exact"] = corrupted["find"]["exact"]
    with pytest.raises(FidelityError):
        verify(corrupted, difficulty="easy")


def test_harness_catches_display_drift():
    """Assertion (e): a display ``value`` that drifts from its ``exact`` is caught.

    The display field is presentation-only, but the harness still guards it so a
    lossy/edited value can't silently disagree with the source of truth (ADR-005).
    """
    data = _gen(WORKED_EXAMPLE)
    corrupted = copy.deepcopy(data)
    corrupted["final_answer"]["value"] = corrupted["final_answer"]["value"] + 1  # exact untouched
    with pytest.raises(FidelityError):
        verify(corrupted, difficulty="easy")


def test_exact_carries_nonterminating_fraction():
    """ADR-005 / fix F1: a non-terminating clean answer is stored exactly, not lossily.

    medium {u,v,a}->s, seed 1, used to emit s=0.571429 (a truncated 4/7) and fail the
    harness. It must now carry exact '4/7', render it as a fraction, and verify.
    """
    from templates.suvat import a as _a, s as _s, u as _u, v as _v
    data = generate("suvat", given=(_u, _v, _a), find=_s, difficulty="medium", seed=1)
    assert data["final_answer"]["exact"] == "4/7"
    assert "frac{4}{7}" in data["final_answer"]["latex"]
    assert verify(data, difficulty="medium") is True


def test_harness_catches_unit_corruption():
    """Assertion (c): a wrong unit is caught."""
    data = _gen(WORKED_EXAMPLE)
    corrupted = copy.deepcopy(data)
    corrupted["find"]["unit"] = "kg"
    with pytest.raises(FidelityError):
        verify(corrupted, difficulty="easy")


def test_data_fidelity_100_percent():
    """Gate 5: a full SUVAT seed batch reports Data Fidelity = 100%.

    Now spans easy / medium / hard (fix F3): the fractional and non-positive
    answer paths — where F1/F2 used to hide — are gated too, not just integer easy.
    """
    batch = suvat_batch(n_seeds=12)
    passed = 0
    for req in batch:
        data = _gen(req)
        assert verify(data, difficulty=req["difficulty"]) is True
        passed += 1
    assert passed == len(batch)
    fidelity = passed / len(batch)
    assert fidelity == 1.0
