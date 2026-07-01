"""Declarative-template loader tests (ADR-007).

A topic template becomes declarative data parsed into the existing
:class:`~templates.base.Template`. These tests pin the loader's behaviour and,
above all, prove *fidelity parity*: a SUVAT built from the declarative spec must
emit byte-identical ``sympy_data`` to the hand-coded SUVAT template — the v1 exit
gate named in ADR-007 §(f).
"""

import pytest

from engine.loop import generate
from harness.batches import suvat_batch
from templates.declarative import SUVAT_SPEC, load_declarative
from templates.suvat import SUVAT, a, s, t, u, v


def test_generate_accepts_explicit_template_override():
    """ADR-007: generate() can run a Template that is not in the registry.

    The validator must replay golden cases through a *candidate* template before
    it is registered, so generate() takes an explicit ``template=`` that bypasses
    ``load_template``. Passing the code SUVAT explicitly must equal the registry
    path exactly.
    """
    via_registry = generate("suvat", given=(u, a, t), find=v,
                            conditions={u: 0, a: 2, t: 5}, seed=80421)
    via_override = generate(given=(u, a, t), find=v, template=SUVAT,
                            conditions={u: 0, a: 2, t: 5}, seed=80421)
    assert via_override == via_registry


def test_load_declarative_returns_populated_template():
    """The loader parses the declarative spec into a usable Template."""
    tpl = load_declarative(SUVAT_SPEC)
    assert tpl.topic == "suvat"
    assert len(tpl.equations) == 5
    assert {sym.name for sym in tpl.variables} == {"u", "v", "a", "t", "s"}
    assert tpl.unit_for(tpl.symbol("a")) == "m/s^2"


def test_auto_derived_solvability_matches_code_suvat():
    """ADR-007 §(b): solvability is derived from the equation set, not authored.

    The derived map must agree with the hand-coded SUVAT solvability on the same
    valid and invalid splits.
    """
    tpl = load_declarative(SUVAT_SPEC)
    # valid: unused = s -> the equation excluding s (E1) relates {u,a,t,v}
    ok, eq = tpl.solvability({u, a, t}, v)
    assert ok and eq is tpl.equations[0]
    # invalid: too few / too many givens, or find in given
    for given, find in [({u, a}, v), ({u, a, t, s}, v), ({u, a, t}, u)]:
        ok, reason = tpl.solvability(given, find)
        assert not ok and isinstance(reason, str)


def test_declarative_suvat_matches_code_suvat_across_batch():
    """v1 exit gate (ADR-007 §f): declarative SUVAT is byte-parity with the code one.

    For every request in a representative Data-Fidelity batch, generating through
    the declarative template must produce identical ``sympy_data`` to the hand-coded
    SUVAT template — numbers, steps, units, policy label, everything.
    """
    decl = load_declarative(SUVAT_SPEC)
    batch = suvat_batch(n_seeds=2)
    assert len(batch) == 42  # 3 difficulties x 7 splits x 2 seeds
    for req in batch:
        code_data = generate(req["topic"], given=req["given"], find=req["find"],
                             difficulty=req["difficulty"], seed=req["seed"])
        decl_data = generate(template=decl, given=req["given"], find=req["find"],
                             difficulty=req["difficulty"], seed=req["seed"])
        assert decl_data == code_data, f"parity broke on {req}"


def test_equation_with_undeclared_symbol_is_rejected():
    """ADR-007 §(a) sandbox: an equation naming a symbol not in the template's
    declared variables is rejected at load time, never silently accepted."""
    bad = dict(SUVAT_SPEC)
    bad["equations"] = list(SUVAT_SPEC["equations"]) + ["v = u + g*t"]  # g undeclared
    with pytest.raises(ValueError, match="g"):
        load_declarative(bad)
