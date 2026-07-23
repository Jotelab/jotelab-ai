"""Tests for chained mixed problems (engine/chain.py + harness verify_chain).

Spec: docs/superpowers/specs/2026-07-24-mixed-chained-problems-design.md.
"""

import sympy

from engine import sampling
from engine.registry import load_template


def _suvat_syms(*names):
    template = load_template("suvat")
    return template, tuple(template.symbol(n) for n in names)


def test_pinned_condition_accepts_exact_noninteger():
    """A link value like 7/2 must flow through `conditions` without rounding."""
    template, (u, a, t) = _suvat_syms("u", "a", "t")
    inputs = sampling.sample(template, (u, a, t), {"u": "7/2"}, "easy", seed=1)
    assert inputs[u] == sympy.Rational(7, 2)


def test_pinned_integer_condition_stays_integer():
    """Backwards compatibility: integer pins remain sympy.Integer."""
    template, (u, a, t) = _suvat_syms("u", "a", "t")
    inputs = sampling.sample(template, (u, a, t), {"u": 5}, "easy", seed=1)
    assert inputs[u] == sympy.Integer(5)
    assert inputs[u].is_Integer


from engine.errors import ChainSpecError, EngineError, IncompatibleLinkError


def test_chain_errors_are_typed_engine_errors():
    assert issubclass(ChainSpecError, EngineError)
    assert issubclass(IncompatibleLinkError, EngineError)
    err = IncompatibleLinkError("suvat", "t", "s", "m/s")
    assert err.topic == "suvat" and err.symbol == "t"
    assert "expects s" in str(err) and "m/s" in str(err)


# -- tests for generate_chain ---------------------------------------------------

import json

import pytest

from engine.chain import generate_chain
from engine.errors import NoCleanInstanceError

# free-fall default split is (u, g, t) -> v [m/s]; suvat's u is m/s-compatible.
PARTS = [
    {"topic": "free-fall"},
    {"topic": "suvat", "given": ["u", "a", "t"], "find": "s", "receive": "u"},
]


def test_link_value_flows_exactly():
    data = generate_chain(PARTS, difficulty="easy", seed=7)
    feed = data["parts"][0]["final_answer"]["exact"]
    recv = next(g for g in data["parts"][1]["given"] if g["symbol"] == "u")
    assert recv["exact"] == feed
    assert data["links"] == [
        {"from_part": 0, "to_part": 1, "symbol": "u", "exact": feed}
    ]


def test_chain_contract_shape():
    data = generate_chain(PARTS, seed=3)
    assert data["topic"] == "mixed"
    assert data["topics"] == ["free-fall", "suvat"]
    assert data["policy_applied"] == "easy"
    assert data["seed"] == 3
    assert len(data["parts"]) == 2
    assert data["parts"][0]["topic"] == "free-fall"   # unmodified sympy_data
    assert data["final_answer"] == data["parts"][-1]["final_answer"]


def test_chain_deterministic_from_seed():
    one = generate_chain(PARTS, seed=11)
    two = generate_chain(PARTS, seed=11)
    assert json.dumps(one) == json.dumps(two)


def test_three_part_chain():
    parts = [
        {"topic": "free-fall"},
        {"topic": "suvat", "given": ["u", "a", "t"], "find": "v", "receive": "u"},
        {"topic": "upward-throw", "given": ["u", "g", "t"], "find": "h",
         "receive": "u"},
    ]
    data = generate_chain(parts, difficulty="easy", seed=2)
    assert data["topics"] == ["free-fall", "suvat", "upward-throw"]
    assert [(l["from_part"], l["to_part"]) for l in data["links"]] == [(0, 1), (1, 2)]


def test_single_part_rejected():
    with pytest.raises(ChainSpecError, match="at least 2 parts"):
        generate_chain([{"topic": "suvat"}])


def test_missing_receive_rejected():
    with pytest.raises(ChainSpecError, match="receive"):
        generate_chain([{"topic": "free-fall"}, {"topic": "suvat"}])


def test_unknown_receive_rejected():
    with pytest.raises(ChainSpecError, match="zz"):
        generate_chain([{"topic": "free-fall"},
                        {"topic": "suvat", "receive": "zz"}])


def test_receive_not_among_givens_rejected():
    # suvat default split given is (u, a, t); s is a valid symbol but not a given.
    with pytest.raises(ChainSpecError, match="not among"):
        generate_chain([{"topic": "free-fall"},
                        {"topic": "suvat", "receive": "s"}])


def test_incompatible_units_rejected():
    # free-fall find v is m/s; suvat's t is s.
    with pytest.raises(IncompatibleLinkError):
        generate_chain([{"topic": "free-fall"},
                        {"topic": "suvat", "receive": "t"}])


def test_bounded_failure_raises_no_clean_instance():
    """A downstream part whose pinned condition violates plausibility always
    (t = -5 breaks time-positivity) fails loudly after the bounded re-rolls."""
    parts = [
        {"topic": "free-fall"},
        {"topic": "suvat", "given": ["u", "a", "t"], "find": "v",
         "receive": "u", "conditions": {"t": -5}},
    ]
    with pytest.raises(NoCleanInstanceError):
        generate_chain(parts, seed=1, max_chain_attempts=2, max_attempts=5)
