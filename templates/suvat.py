"""The SUVAT (kinematics) launch template — fully specified (build guide §8).

Kinematics is the launch topic: most regular, best early end-to-end win
(spec §8). This module encodes everything ``loop.generate`` needs for SUVAT —
variables and ranges, the five SUVAT relations, the single-equation solvability
map, the plausibility constraints, and the root-selection convention — without
any further decisions.

v1 is **single-equation only** (build guide §3): ``given`` is exactly three
variables and ``find`` is one distinct variable; the fifth variable is *unused*.
The equation that *excludes* the unused variable relates exactly
``given ∪ {find}``, so SymPy can solve it for ``find`` directly.
"""

from __future__ import annotations

import sympy

from .base import Template, VarSpec
from .diagrams import motion_1d

# -- symbols (real-valued; equality is by name so dict keys are stable) --------
u, v, a, t, s = sympy.symbols("u v a t s", real=True)
ALL_SYMS = {u, v, a, t, s}
SYMBOLS = {"u": u, "v": v, "a": a, "t": t, "s": s}

# -- the five SUVAT relations (build guide §8) ---------------------------------
# Each equation involves four of the five variables, i.e. each *excludes* exactly
# one. That excluded variable is the key to the single-equation solvability map.
E1 = sympy.Eq(v, u + a * t)                       # excludes s
E2 = sympy.Eq(s, u * t + a * t**2 / 2)            # excludes v
E3 = sympy.Eq(v**2, u**2 + 2 * a * s)             # excludes t
E4 = sympy.Eq(s, (u + v) * t / 2)                 # excludes a
E5 = sympy.Eq(s, v * t - a * t**2 / 2)            # excludes u

EQUATIONS = [E1, E2, E3, E4, E5]

# The excluded variable selects the equation (build guide §8).
EQUATION_BY_EXCLUDED = {s: E1, v: E2, t: E3, a: E4, u: E5}

# -- variables, units, and per-difficulty ranges (build guide §8) --------------
# (lo, hi, signed). "Derived" variables (v, s) carry ranges used both for
# sampling when they happen to be a `given`, and as a plausibility band on the
# solved value otherwise.
VARIABLES = {
    u: VarSpec("m/s", {"easy": (0, 20, False), "medium": (0, 40, False),
                       "hard": (0, 40, False)}),
    v: VarSpec("m/s", {"easy": (0, 30, False), "medium": (0, 60, False),
                       "hard": (0, 60, False)}),
    a: VarSpec("m/s^2", {"easy": (1, 10, False), "medium": (1, 15, True),
                         "hard": (1, 15, True)}),
    t: VarSpec("s", {"easy": (1, 10, False), "medium": (1, 20, False),
                     "hard": (1, 20, False)}),
    s: VarSpec("m", {"easy": (1, 50, False), "medium": (1, 150, False),
                     "hard": (1, 150, False)}),
}

# Plausibility magnitude cap for velocities — no everyday object at 5000 m/s
# (spec §6 plausibility example).
MAX_SPEED = 100


# -- solvability map (build guide §8) ------------------------------------------
def solvability(given, find):
    """Single-equation (v1) solvability map.

    ``given`` must be exactly three variables and ``find`` a distinct fourth.
    Returns ``(True, equation)`` with the SUVAT relation that relates
    ``given ∪ {find}``, or ``(False, reason)`` if the request is not a valid
    single-equation instance.
    """
    given = set(given)
    if len(given) != 3 or find in given:
        return (False, "v1 SUVAT expects exactly 3 distinct givens and a distinct find")
    used = given | {find}
    if not used <= ALL_SYMS:
        return (False, "unknown variable for the SUVAT template")
    unused = ALL_SYMS - used
    if len(unused) != 1:
        return (False, "could not isolate a single unused variable")
    eq = EQUATION_BY_EXCLUDED[next(iter(unused))]
    return (True, eq)


# -- root selection (build guide §3, §8) ---------------------------------------
def root_select(values, find, difficulty):
    """Pick the physical root from candidate solved values.

    Convention (locked in build guide §3, extended by the 2026-07-24 signed-
    fallback spec): evaluate all real roots at the sampled inputs, discard
    non-physical ones, and take the **smallest strictly positive real root**.
    When none exists: a lone non-negative root is allowed for ``u``/``s``/``v``
    (zero is legitimate), and at medium/hard a negative root (smallest
    magnitude) is allowed for the direction-carrying finds ``v``/``s``/``a``.
    Returns ``None`` (a failed roll) if none survive.
    """
    physical = []
    for val in values:
        val = sympy.nsimplify(val)
        if not (val.is_real and val.is_number):
            continue
        if not _is_physical_value(val, find, difficulty):
            continue
        physical.append(val)
    positive = [val for val in physical if val.is_positive]
    if positive:
        return min(positive)
    # `u` and `s` may legitimately be zero/positive; allow a lone non-negative
    # root when no strictly-positive one exists (e.g. u = 0 at easy).
    nonneg = [val for val in physical if val.is_nonnegative]
    if nonneg and find in (u, s, v):
        return min(nonneg)
    # Signed fallback (spec 2026-07-24): at medium/hard a direction-carrying
    # find may be negative when no positive root exists. `t` stays strictly
    # positive via _is_physical_value; easy stays all-positive.
    negative = [val for val in physical if val.is_negative]
    if negative and difficulty != "easy" and find in (v, s, a):
        return max(negative)  # smallest magnitude, exact comparison
    return None


def _is_physical_value(val, find, difficulty):
    """Per-variable physical admissibility of a single solved value."""
    if find is t and not val.is_positive:
        return False  # time is strictly positive
    if find in (u, v) and abs(val) > MAX_SPEED:
        return False  # implausible everyday speed
    if find is a and val == 0:
        return False  # degenerate when acceleration is the target
    if difficulty == "easy" and find in (u, v, s, a) and val.is_negative:
        return False  # easy = forward 1-D motion, non-negative magnitudes
    return True


# -- plausibility constraints (never loosened; build guide §8, spec §6) --------
def _c_time_positive(values, difficulty):
    return t not in values or values[t].is_positive


def _c_speed_bounded(values, difficulty):
    return all(
        abs(values[sym]) <= MAX_SPEED for sym in (u, v) if sym in values
    )


def _c_accel_nonzero(values, difficulty):
    return a not in values or values[a] != 0


def _c_easy_nonneg(values, difficulty):
    if difficulty != "easy":
        return True
    return all(
        not values[sym].is_negative for sym in (u, v, s) if sym in values
    )


CONSTRAINTS = [_c_time_positive, _c_speed_bounded, _c_accel_nonzero, _c_easy_nonneg]


# -- the diagram payload --------------------------------------------------------
def diagram_spec(ctx):
    """One forward segment carrying whichever of u/a/v/s/t this split uses."""
    return motion_1d(ctx, segments=[{
        "velocity_in": u, "acceleration": a, "velocity_out": v,
        "span": s, "duration": t,
    }])


# -- the template object -------------------------------------------------------
SUVAT = Template(
    topic="suvat",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((u, a, t), v),  # spec §8 worked example
    diagram_spec=diagram_spec,
)
