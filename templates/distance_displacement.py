"""Distance vs displacement over a 1-D two-segment path (vectors, part 2).

The canonical scalar-vs-vector lesson the ``vectors-1d`` topic set up:

* **Displacement** is a vector — the *net* change in position, ``disp = d1 + d2``
  (signed: direction matters, and it can be zero if the object returns to start).
* **Distance** is a scalar — the *total path length*, ``dist = |d1| + |d2|``
  (always >= 0, and >= |displacement|).

Written as a **code template**, not a declarative JSON one, because it needs
``Abs``: the declarative equation sandbox forbids ``Abs`` and the units gate
cancels a same-dimension subtraction. Here the equations are built directly in
Python. Solvability is deliberately restricted to the two physical questions —
find the distance or the displacement from the two segments — never solving
*back* for a segment, which would mean inverting an absolute value.
"""

from __future__ import annotations

import sympy

from .base import Template, VarSpec

# -- symbols (real; the two path segments and the two derived quantities) ------
d1, d2, disp, dist = sympy.symbols("d1 d2 disp dist", real=True)
SYMBOLS = {"d1": d1, "d2": d2, "disp": disp, "dist": dist}

# -- the two relations ---------------------------------------------------------
E_DISP = sympy.Eq(disp, d1 + d2)                     # net displacement (vector)
E_DIST = sympy.Eq(dist, sympy.Abs(d1) + sympy.Abs(d2))  # total distance (scalar)
EQUATIONS = [E_DISP, E_DIST]

# -- variables, units, per-difficulty ranges -----------------------------------
# Segments are signed (each leg can go either direction). The derived quantities
# carry ranges used as plausibility bands when they happen to be a `given` (they
# never are here) — kept generous so they never gate a legitimate result.
_SEG = {"easy": (1, 10, True), "medium": (1, 30, True), "hard": (1, 60, True)}
_DISP = {"easy": (0, 20, True), "medium": (0, 60, True), "hard": (0, 120, True)}
_DIST = {"easy": (2, 20, False), "medium": (2, 60, False), "hard": (2, 120, False)}

VARIABLES = {
    d1: VarSpec("m", _SEG),
    d2: VarSpec("m", _SEG),
    disp: VarSpec("m", _DISP),
    dist: VarSpec("m", _DIST),
}

_SEGMENTS = {d1, d2}
_FIND_EQUATION = {disp: E_DISP, dist: E_DIST}


# -- solvability map -----------------------------------------------------------
def solvability(given, find):
    """Only two valid questions: given both segments, find distance or displacement.

    The reverse (solve for a segment) is excluded on purpose — recovering ``d1``
    from ``dist = |d1| + |d2|`` means inverting an absolute value (two branches),
    which this v1 single-answer engine does not model.
    """
    if set(given) != _SEGMENTS:
        return (False, "distance-displacement takes exactly the two segments d1, d2 as given")
    if find not in _FIND_EQUATION:
        return (False, "find must be the displacement (disp) or the distance (dist)")
    return (True, _FIND_EQUATION[find])


# -- root selection ------------------------------------------------------------
def root_select(values, find, difficulty):
    """Both relations isolate the find directly, so there is a single real root.

    Distance is a non-negative scalar; displacement is signed. No positivity is
    imposed on displacement (that is the whole point — it carries direction).
    """
    real = []
    for val in values:
        val = sympy.nsimplify(val)
        if val.is_real and val.is_number:
            real.append(val)
    if not real:
        return None
    if find is dist:
        nonneg = [v for v in real if v.is_nonnegative]
        return min(nonneg) if nonneg else None
    return min(real, key=lambda x: (abs(float(x)), float(x)))


# -- plausibility constraints --------------------------------------------------
def _c_distance_nonnegative(values, difficulty):
    return dist not in values or values[dist].is_nonnegative


CONSTRAINTS = [_c_distance_nonnegative]


# -- the template object -------------------------------------------------------
DISTANCE_DISPLACEMENT = Template(
    topic="distance-displacement",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((d1, d2), disp),
    signed_answer=True,  # displacement carries a sign (direction)
)
