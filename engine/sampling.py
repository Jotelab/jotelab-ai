"""Seeded sampling of a template's ``given`` variables (build guide §6, §7).

Draws exact values for the ``given`` variables from the template's
per-difficulty ranges, using a seeded RNG so the whole run is reproducible from a
single integer (spec §5, §7). Sampled draws are SymPy ``Integer`` objects (for
range-based variables), never Python floats — floats reintroduce the rounding error
the project exists to avoid (build guide §6 "exact arithmetic note"). Pinned
conditions may be any exact SymPy number, never floats (e.g. ``Integer`` or
``Rational``).

``conditions`` lets the caller pin a variable (Advanced mode / chain links):
either an exact value (any ``nsimplify``-able number, e.g. ``5`` or ``"7/2"``),
or a ``(lo, hi)`` / ``(lo, hi, signed)`` range override. Conditions may be
keyed by the SymPy symbol or by its name.
"""

from __future__ import annotations

import random

import sympy


def sample(template, given, conditions, difficulty, seed):
    """Return ``{symbol: exact SymPy number}`` for each ``given`` variable.

    Integer for sampled draws; a pinned condition may be any exact value (e.g.
    Rational). Deterministic in ``seed``: the same seed reproduces the same draw.
    Variables are sampled in a fixed (name-sorted) order so the RNG stream is
    stable.
    """
    conditions = conditions or {}
    rng = random.Random(seed)
    inputs = {}
    for sym in sorted(given, key=lambda x: x.name):
        spec = _spec_for(sym, conditions, template, difficulty)
        if isinstance(spec, tuple):
            lo, hi, signed = spec
            mag = rng.randint(lo, hi)
            if signed and rng.random() < 0.5:
                mag = -mag
            inputs[sym] = sympy.Integer(mag)
        else:
            # An exact pinned value — nsimplify keeps integers Integer and
            # accepts exact non-integers (e.g. "7/2" from a chain link, ADR-005).
            inputs[sym] = sympy.nsimplify(spec)
    return inputs


def _spec_for(sym, conditions, template, difficulty):
    """Resolve the draw spec for ``sym``: ``(lo, hi, signed)`` or a pinned exact value."""
    cond = conditions.get(sym, conditions.get(sym.name))
    if cond is not None:
        if isinstance(cond, (tuple, list)) and len(cond) >= 2:
            signed = cond[2] if len(cond) > 2 else False
            return (cond[0], cond[1], signed)
        return cond  # exact pinned value
    return template.range_for(sym, difficulty)
