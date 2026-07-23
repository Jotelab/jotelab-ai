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
