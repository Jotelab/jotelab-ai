"""Average speed vs average velocity over a 1-D two-segment path (rates).

The rate counterpart of ``distance-displacement``:

* **Average velocity** is a vector — net displacement over time,
  ``vavg = (d1 + d2)/t`` (signed: out-and-back gives 0).
* **Average speed** is a scalar — total path length over time,
  ``sp = (|d1| + |d2|)/t`` (always >= |vavg|, never negative).

A **code template** because it needs ``Abs`` (forbidden in the declarative
sandbox). Solvability is restricted to the two forward rate questions — never
solving back through an absolute value.
"""

from __future__ import annotations

import sympy

from .base import (Template, VarSpec, real_candidates, signed_smallest,
                   smallest_nonnegative)
from .diagrams import motion_1d

# -- symbols -------------------------------------------------------------------
d1, d2, t, sp, vavg = sympy.symbols("d1 d2 t sp vavg", real=True)
SYMBOLS = {"d1": d1, "d2": d2, "t": t, "sp": sp, "vavg": vavg}

# -- the two relations ---------------------------------------------------------
E_SPEED = sympy.Eq(sp, (sympy.Abs(d1) + sympy.Abs(d2)) / t)  # scalar rate
E_VAVG = sympy.Eq(vavg, (d1 + d2) / t)                       # vector rate
EQUATIONS = [E_SPEED, E_VAVG]

# -- variables, units, per-difficulty ranges -----------------------------------
_SEG = {"easy": (1, 10, True), "medium": (1, 30, True), "hard": (1, 60, True)}
_T = {"easy": (1, 6, False), "medium": (1, 10, False), "hard": (1, 15, False)}
_SP = {"easy": (0, 25, False), "medium": (0, 70, False), "hard": (0, 130, False)}
_VAVG = {"easy": (0, 25, True), "medium": (0, 70, True), "hard": (0, 130, True)}

VARIABLES = {
    d1: VarSpec("m", _SEG),
    d2: VarSpec("m", _SEG),
    t: VarSpec("s", _T),
    sp: VarSpec("m/s", _SP),
    vavg: VarSpec("m/s", _VAVG),
}

_GIVEN = {d1, d2, t}
_FIND_EQUATION = {sp: E_SPEED, vavg: E_VAVG}


# -- solvability map -----------------------------------------------------------
def solvability(given, find):
    """Only the two forward questions: given both segments and the time, find a rate.

    Back-solves are excluded: recovering a segment (or the time, when the speed
    is known) means inverting ``|d1| + |d2|`` — two branches, out of scope for
    the v1 single-answer engine (same rationale as distance-displacement).
    """
    if set(given) != _GIVEN:
        return (False, "average-speed takes exactly the segments d1, d2 and the time t")
    if find not in _FIND_EQUATION:
        return (False, "find must be the average speed (sp) or average velocity (vavg)")
    return (True, _FIND_EQUATION[find])


# -- root selection ------------------------------------------------------------
def root_select(values, find, difficulty):
    """Both relations isolate the find directly — a single real root each.

    Average speed is a non-negative scalar; average velocity is signed (the sign
    is the direction, out-and-back legitimately gives zero).
    """
    real = real_candidates(values)
    if not real:
        return None
    if find is sp:
        return smallest_nonnegative(real)
    return signed_smallest(real)


# -- plausibility constraints --------------------------------------------------
def _c_time_positive(values, difficulty):
    return t not in values or values[t].is_positive


def _c_speed_nonnegative(values, difficulty):
    return sp not in values or values[sp].is_nonnegative


CONSTRAINTS = [_c_time_positive, _c_speed_nonnegative]


# -- the diagram payload --------------------------------------------------------
def diagram_spec(ctx):
    """Two sequential legs on one line; the rate label rides on the whole trip.

    ``t`` is the time for the *whole* trip (``sp = (|d1| + |d2|) / t``), and both
    rates are defined over it, so all three are totals rather than segment-2
    annotations. Only the rate this split actually involves survives — the other
    is absent from ``values`` and is dropped by ``ctx.label``.
    """
    return motion_1d(ctx, segments=[
        {"span": d1},
        {"span": d2},
    ], totals=[
        {"symbol": t, "measures": "duration"},
        {"symbol": sp, "measures": "rate"},
        {"symbol": vavg, "measures": "rate"},
    ])


# -- the template object -------------------------------------------------------
AVERAGE_SPEED = Template(
    topic="average-speed",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((d1, d2, t), sp),
    signed_answer=True,  # average velocity carries a sign (direction)
    diagram_spec=diagram_spec,
)
