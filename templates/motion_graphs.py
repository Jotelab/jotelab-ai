"""Motion graphs — graph-reading questions over the two-phase v–t scenario.

Same physics as ``multi-stage-motion`` (imported, not duplicated); registered
as its own topic so the web app phrases questions *from the graph*: the slope
of phase 1 is the acceleration, the area under the polyline is the total
displacement. The engine emits the graph's polyline — exact values, ADR-005
style — in ``sympy_data["diagram"]`` via the ``diagram_spec`` hook; rendering
belongs to the web/TikZ track.

The whitelist is narrower than multi-stage's for two reasons: a drawable graph
needs both phase durations among the givens, and the harness's linking-equation
rule needs an equation whose free symbols are exactly ``given ∪ {find}``. The
classic slope split — find ``a`` from ``(u, v, t1)`` — fails the second test
once ``t2`` joins the givens, so it stays a (non-graph) multi-stage question
until a term-based linking check exists (tracked follow-up). The graph version
of the slope question is find ``a`` from ``(s, u, t1, t2)`` via the
acceleration form.
"""

from __future__ import annotations

import sympy

from .base import Template, real_candidates, signed_smallest
from .multi_stage import (CONSTRAINTS, E_S_A, E_S_V, EQUATIONS, SYMBOLS,
                          VARIABLES, a, s, t1, t2, u, v)
from .multi_stage import root_select as _multi_stage_root_select

# -- split whitelist (graph needs t1 and t2 given; exact-symbol-set equations) --
_SPLITS = {
    (frozenset({u, a, t1, t2}), s): E_S_A,   # area, acceleration form
    (frozenset({u, v, t1, t2}), s): E_S_V,   # area, trapezoid form
    (frozenset({s, u, t1, t2}), v): E_S_V,   # read the cruise level off the area
    (frozenset({s, v, t1, t2}), u): E_S_V,   # read the intercept off the area
    (frozenset({s, u, t1, t2}), a): E_S_A,   # slope of phase 1, via the area
}


def solvability(given, find):
    """Whitelisted graph-readable splits only (both phase durations given)."""
    key = (frozenset(given), find)
    if key in _SPLITS:
        return (True, _SPLITS[key])
    return (False, "not a whitelisted motion-graphs split "
                   "(a drawable graph needs t1 and t2 among the givens)")


# -- root selection ------------------------------------------------------------
def root_select(values, find, difficulty):
    """Delegate to multi-stage, except ``a`` — the slope is signed
    (deceleration graphs slope down)."""
    if find is a:
        real = real_candidates(values)
        return signed_smallest(real) if real else None
    return _multi_stage_root_select(values, find, difficulty)


# -- the diagram payload --------------------------------------------------------
from .diagrams import plot_2d


def diagram_spec(ctx):
    """The v–t polyline ``(0, u) -> (t1, v) -> (t1+t2, v)``, exact.

    ``ctx.values`` holds ``given ∪ {find}`` only, so on the acceleration-form
    splits the cruise velocity is absent — it is derived exactly here
    (``v = u + a*t1``, SymPy arithmetic): engine-computed, invariant-safe.

    Every point ships even when the find is derivable from the figure: this
    topic's whole purpose is graph-reading splits (slope -> a, area -> s).
    """
    values = ctx.values
    uu, tt1, tt2 = values[u], values[t1], values[t2]
    vv = values[v] if v in values else sympy.nsimplify(uu + values[a] * tt1)
    return plot_2d(
        ctx,
        axes={"x": {"symbol": "t", "unit": "s"},
              "y": {"symbol": "v", "unit": "m/s"}},
        points=[(0, uu), (tt1, vv), (tt1 + tt2, vv)],
    )


# -- the template object -------------------------------------------------------
MOTION_GRAPHS = Template(
    topic="motion-graphs",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((u, a, t1, t2), s),
    signed_answer=True,  # the slope find (a) is negative on deceleration graphs
    diagram_spec=diagram_spec,
)
