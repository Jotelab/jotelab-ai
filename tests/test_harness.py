"""Verification-harness tests + the Gate 5 Data Fidelity batch (build guide §11).

Spec ties: §10/§11 — the harness catches a hand-corrupted instance, and a full
SUVAT seed batch reports Data Fidelity = 100%.
"""

import copy

import pytest

from engine.loop import generate
from harness.batches import WORKED_EXAMPLE, suvat_batch
from harness.verify import FidelityError, verify


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
    """Spec §10/§11: hand-corrupt the final answer; verify() must fail (assertion b)."""
    data = _gen(WORKED_EXAMPLE)
    corrupted = copy.deepcopy(data)
    corrupted["find"]["value"] = corrupted["find"]["value"] + 1
    corrupted["final_answer"]["value"] = corrupted["final_answer"]["value"] + 1
    with pytest.raises(FidelityError):
        verify(corrupted, difficulty="easy")


def test_harness_catches_unit_corruption():
    """Assertion (c): a wrong unit is caught."""
    data = _gen(WORKED_EXAMPLE)
    corrupted = copy.deepcopy(data)
    corrupted["find"]["unit"] = "kg"
    with pytest.raises(FidelityError):
        verify(corrupted, difficulty="easy")


def test_data_fidelity_100_percent():
    """Gate 5: a full SUVAT seed batch reports Data Fidelity = 100%."""
    batch = suvat_batch(n_seeds=12)
    passed = 0
    for req in batch:
        data = _gen(req)
        assert verify(data, difficulty=req["difficulty"]) is True
        passed += 1
    assert passed == len(batch)
    fidelity = passed / len(batch)
    assert fidelity == 1.0
