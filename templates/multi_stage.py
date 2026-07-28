"""Two-phase 1-D motion: uniform acceleration, then constant-velocity cruise.

Phase 1 accelerates from ``u`` with ``a`` for ``t1``, reaching ``v``; phase 2
cruises at ``v`` for ``t2``; ``s`` is the total displacement. Motion is kept
one-directional (``v > 0``), so distance equals displacement.

Blocked for declarative templates by the v1 single-equation solvability model;
written as a **code template** whose whitelisted splits each map to a
*composite* equation — the harness's linking-equation rule needs one equation
whose free symbols are exactly ``given ∪ {find}``:

* ``E_S_A`` links ``{s, u, a, t1, t2}`` (acceleration form)
* ``E_S_V`` links ``{s, u, v, t1, t2}`` (velocity/trapezoid form)
* ``E_V``   links ``{v, u, a, t1}``    (phase-1 SUVAT relation)

``E_S_V`` is ``E_S_A`` with ``a`` eliminated through ``E_V``, so the full
system stays consistent and uniquely determined from every allowed given-set
(what the fidelity harness's independent whole-system solve relies on).

Phase durations are narrative givens, never the unknown: solving ``E_S_A`` for
``t1`` is quadratic (two roots), and a pupil is told how long each phase lasts.
"""

from __future__ import annotations

import sympy

from .base import (Template, VarSpec, real_candidates, smallest_nonnegative,
                   smallest_positive)
from .diagrams import motion_1d

# -- symbols -------------------------------------------------------------------
u, a, t1, t2, v, s = sympy.symbols("u a t1 t2 v s", real=True)
SYMBOLS = {"u": u, "a": a, "t1": t1, "t2": t2, "v": v, "s": s}

# -- relations -----------------------------------------------------------------
E_V = sympy.Eq(v, u + a * t1)
E_S_A = sympy.Eq(s, u * t1 + a * t1**2 / 2 + (u + a * t1) * t2)
E_S_V = sympy.Eq(s, (u + v) * t1 / 2 + v * t2)
EQUATIONS = [E_V, E_S_A, E_S_V]

# -- variables, units, per-difficulty ranges -----------------------------------
_U = {"easy": (0, 20, False), "medium": (0, 30, False), "hard": (0, 50, False)}
_A = {"easy": (1, 5, False), "medium": (1, 8, True), "hard": (1, 12, True)}
_T = {"easy": (1, 6, False), "medium": (1, 8, False), "hard": (1, 12, False)}
_VC = {"easy": (2, 20, False), "medium": (2, 40, False), "hard": (2, 80, False)}
_S = {"easy": (20, 150, False), "medium": (20, 400, False), "hard": (20, 1000, False)}

VARIABLES = {
    u: VarSpec("m/s", _U),
    a: VarSpec("m/s^2", _A),
    t1: VarSpec("s", _T),
    t2: VarSpec("s", _T),
    v: VarSpec("m/s", _VC),
    s: VarSpec("m", _S),
}

# -- split whitelist -----------------------------------------------------------
_SPLITS = {
    (frozenset({u, a, t1, t2}), s): E_S_A,
    (frozenset({u, v, t1, t2}), s): E_S_V,
    (frozenset({s, u, t1, t2}), v): E_S_V,  # linear in v
    (frozenset({s, v, t1, t2}), u): E_S_V,  # linear in u
}


def solvability(given, find):
    """Whitelisted splits only — each with a composite linking equation.

    Phase durations (``t1``, ``t2``) are never the find: the acceleration form
    is quadratic in ``t1`` (two roots), and the phase structure is part of the
    problem narrative, not the unknown.
    """
    key = (frozenset(given), find)
    if key in _SPLITS:
        return (True, _SPLITS[key])
    if find in (t1, t2):
        return (False, "phase durations are narrative givens, not solvable finds")
    return (False, "not a whitelisted multi-stage split")


# -- root selection ------------------------------------------------------------
def root_select(values, find, difficulty):
    """All whitelisted solves are linear — one real root, selected physically.

    ``s`` and ``v`` must be positive (one-directional motion); ``u`` may be
    zero (start from rest).
    """
    real = real_candidates(values)
    if not real:
        return None
    if find is u:
        return smallest_nonnegative(real)
    return smallest_positive(real)


# -- plausibility constraints --------------------------------------------------
def _c_times_positive(values, difficulty):
    for sym in (t1, t2):
        if sym in values and not values[sym].is_positive:
            return False
    return True


def _c_start_nonneg(values, difficulty):
    return u not in values or values[u].is_nonnegative


def _c_cruise_forward(values, difficulty):
    """The cruise velocity stays positive — no direction reversal mid-story.

    ``v`` is not among the values on the acceleration-form splits, so it is
    reconstructed from ``u + a*t1`` there.
    """
    if v in values:
        return bool(values[v].is_positive)
    if all(x in values for x in (u, a, t1)):
        return bool(sympy.nsimplify(values[u] + values[a] * values[t1]).is_positive)
    return True


def _c_displacement_positive(values, difficulty):
    return s not in values or values[s].is_positive


CONSTRAINTS = [_c_times_positive, _c_start_nonneg, _c_cruise_forward,
               _c_displacement_positive]


# -- the diagram payload --------------------------------------------------------
def diagram_spec(ctx):
    """Phase 1 accelerates from u to the cruise velocity; phase 2 holds it.

    ``s`` is the displacement across *both* phases
    (``s = u t1 + a t1²/2 + v t2``), so it brackets the whole figure instead of
    riding on phase 2, which would claim it covers the cruise leg alone.
    """
    return motion_1d(ctx, segments=[
        {"velocity_in": u, "acceleration": a, "velocity_out": v,
         "duration": t1},
        {"velocity_in": v, "duration": t2},
    ], totals=[
        {"symbol": s, "measures": "displacement"},
    ])


# -- the template object -------------------------------------------------------
MULTI_STAGE = Template(
    topic="multi-stage-motion",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((u, a, t1, t2), s),
    diagram_spec=diagram_spec,
)
