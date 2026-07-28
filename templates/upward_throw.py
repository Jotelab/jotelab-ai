"""Upward throw — vertical motion under gravity, signed, up-positive.

The signed extension of the ``free-fall`` topic (which stays down-positive,
drop/thrown-down only). Here an object is launched straight up with speed
``u > 0``; **up is positive**, so gravity enters the relations with a minus
sign, the velocity ``v`` is positive while rising and negative while falling,
and ``h`` is the (non-negative) height above the launch point.

As in ``free-fall``, gravity is a dimensioned variable pinned to 10 and always
given — never solved for.

A **code template** because the split set must be a whitelist: solving for the
time (or velocity) at a *given height* has two physical roots — once rising,
once falling — which the v1 single-answer engine cannot express. Those splits
are excluded until multi-answer support lands (tracked follow-up); "time to
top" and "max height" remain expressible as the ``v = 0`` condition on the
linear relations.
"""

from __future__ import annotations

import sympy

from .diagrams import motion_1d
from .base import (Template, VarSpec, real_candidates, signed_smallest,
                   smallest_nonnegative, smallest_positive)

# -- symbols -------------------------------------------------------------------
u, v, g, t, h = sympy.symbols("u v g t h", real=True)
SYMBOLS = {"u": u, "v": v, "g": g, "t": t, "h": h}

# -- relations (up-positive: gravity pulls against the motion) -----------------
E_V = sympy.Eq(v, u - g * t)                    # velocity at time t
E_H_T = sympy.Eq(h, u * t - g * t**2 / 2)       # height at time t
E_V2 = sympy.Eq(v**2, u**2 - 2 * g * h)         # velocity-height (no time)
E_H_UV = sympy.Eq(h, (u + v) * t / 2)           # average-velocity form
EQUATIONS = [E_V, E_H_T, E_V2, E_H_UV]

# -- variables, units, per-difficulty ranges -----------------------------------
_U = {"easy": (10, 40, False), "medium": (10, 60, False), "hard": (10, 100, False)}
_V = {"easy": (0, 30, True), "medium": (0, 50, True), "hard": (0, 90, True)}
_G = {"easy": (10, 10, False), "medium": (10, 10, False), "hard": (10, 10, False)}
_T = {"easy": (1, 6, False), "medium": (1, 9, False), "hard": (1, 14, False)}
_H = {"easy": (0, 80, False), "medium": (0, 180, False), "hard": (0, 500, False)}

VARIABLES = {
    u: VarSpec("m/s", _U),
    v: VarSpec("m/s", _V),
    g: VarSpec("m/s^2", _G),
    t: VarSpec("s", _T),
    h: VarSpec("m", _H),
}

# -- split whitelist (all unique-answer; g always among the givens) ------------
_SPLITS = {
    (frozenset({u, g, t}), v): E_V,
    (frozenset({u, g, t}), h): E_H_T,
    (frozenset({u, v, g}), t): E_V,    # linear: t = (u - v)/g ("time to top" via v=0)
    (frozenset({u, v, g}), h): E_V2,   # linear in h ("max height" via v=0)
    (frozenset({v, g, t}), u): E_V,
}


def solvability(given, find):
    """Whitelisted unique-answer splits only.

    ``(u, g, h) -> t`` and ``(u, g, h) -> v`` are excluded on purpose: a height
    is reached twice (rising, then falling), so both solves have two physical
    roots — out of scope for the single-answer engine (multi-answer support is
    the tracked follow-up).
    """
    key = (frozenset(given), find)
    if key in _SPLITS:
        return (True, _SPLITS[key])
    if frozenset(given) == frozenset({u, g, h}):
        return (False, "time/velocity at a given height has two answers "
                       "(rising vs falling); needs multi-answer support")
    return (False, "not a whitelisted upward-throw split")


# -- root selection ------------------------------------------------------------
def root_select(values, find, difficulty):
    """Every whitelisted solve is linear — one real root; select physically.

    Time must be positive; height and launch speed non-negative (u > 0 is then
    enforced by constraint); the velocity keeps its sign — that is the point.
    """
    real = real_candidates(values)
    if not real:
        return None
    if find is t:
        return smallest_positive(real)
    if find in (h, u):
        return smallest_nonnegative(real)
    return signed_smallest(real)  # v: signed


# -- plausibility constraints --------------------------------------------------
def _c_gravity_is_ten(values, difficulty):
    return g not in values or values[g] == 10


def _c_time_positive(values, difficulty):
    return t not in values or values[t].is_positive


def _c_launch_upward(values, difficulty):
    return u not in values or values[u].is_positive


def _c_height_above_launch(values, difficulty):
    return h not in values or values[h].is_nonnegative


def _c_within_flight(values, difficulty):
    """|v| <= u — equivalent to h >= 0; catches beyond-return samples on
    splits where h never appears (e.g. find v from u, g, t)."""
    if u in values and v in values:
        return bool(abs(values[v]) <= values[u])
    return True


CONSTRAINTS = [_c_gravity_is_ten, _c_time_positive, _c_launch_upward,
               _c_height_above_launch, _c_within_flight]


# -- the diagram payload --------------------------------------------------------
def diagram_spec(ctx):
    """Rise then fall on a vertical axis, with g acting downward throughout.

    ``h`` is the height *at time t* (``h = u t − g t²/2``), i.e. the net rise
    from the launch point to where the body is when the clock stops — not the
    span of the upward leg — so it brackets the whole figure. ``t`` is likewise
    the total elapsed time. The reversal is drawn because it is the physics: the
    body is still moving up in segment 1 and already falling in segment 2.
    """
    return motion_1d(ctx, orientation="vertical", segments=[
        {"velocity_in": u, "acceleration": g},
        {"direction": "reverse", "velocity_out": v},
    ], totals=[
        {"symbol": h, "measures": "displacement"},
        {"symbol": t, "measures": "duration"},
    ])


# -- the template object -------------------------------------------------------
UPWARD_THROW = Template(
    topic="upward-throw",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((u, g, t), v),
    signed_answer=True,  # v is negative while falling — the sign is direction
    diagram_spec=diagram_spec,
)
