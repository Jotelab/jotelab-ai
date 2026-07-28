"""Shared diagram-spec builders (spec 2026-07-27, engine-owned TikZ).

A template declares an optional ``diagram_spec`` hook; these builders turn the
instance's values plus its split into the JSON-able payload carried at
``sympy_data["diagram"]``. The web app serializes that payload to TikZ — it
derives nothing and decides nothing beyond obeying ``role``.

**The answer-hiding rule lives in :meth:`DiagramContext.label` and nowhere
else.** An element bound to the find symbol is emitted without ``value`` or
``exact``, so no downstream bug can leak the answer: there is nothing to leak.
"""

from __future__ import annotations


def _numeric_forms():
    """``(to_display, to_exact)``, imported on use rather than at module scope.

    ``engine/__init__`` imports the loop, which imports the registry, which
    imports the code templates — and those import this module. A module-scope
    ``from engine.contract import …`` therefore re-enters this module while it
    is still initializing whenever ``templates.diagrams`` is the first thing
    imported (e.g. ``pytest tests/test_diagrams.py`` on its own), and fails.
    Deferring closes the cycle, mirroring the import of ``DiagramContext``
    inside ``engine.contract.build_sympy_data``.
    """
    from engine.contract import to_display, to_exact

    return to_display, to_exact


# Engine symbol name -> the TeX math label drawn in the figure. Math and Latin
# only: node-tikzjax embeds Computer Modern, and Thai would fail to compile.
TEX_LABELS = {
    "u": "v_0", "v": "v", "a": "a", "t": "t", "s": "s",
    "g": "g", "h": "h",
    "t1": "t_1", "t2": "t_2",
    "d1": "d_1", "d2": "d_2", "disp": r"\Delta x", "dist": "d",
    "sp": "v", "vavg": r"\bar{v}",
    "va": "v_A", "vb": "v_B", "vab": "v_{AB}",
}


class DiagramContext:
    """Everything a diagram builder needs about one generated instance.

    ``values`` holds ``given ∪ {find}`` (the solved answer included), ``given``
    is the set of sampled symbols, and ``find`` is the single target symbol.
    """

    def __init__(self, template, values, given, find):
        self.template = template
        self.values = dict(values)
        self.given = set(given)
        self.find = find

    def label(self, sym, tex=None):
        """One labelled quantity, or ``None`` if this instance has no such value.

        Returns a value-less dict when ``sym`` is the find target — see the
        module docstring. ``None`` tells the caller to omit the element rather
        than draw an unlabelled one.
        """
        if sym is None:
            return None
        out = {"symbol": sym.name, "label": tex or TEX_LABELS.get(sym.name, sym.name)}
        if sym == self.find:
            out["role"] = "find"
            return out
        if sym not in self.values:
            return None
        to_display, to_exact = _numeric_forms()
        out["role"] = "given" if sym in self.given else "derived"
        out["value"] = to_display(self.values[sym])
        out["exact"] = to_exact(self.values[sym])
        out["unit"] = self.template.unit_for(sym)
        return out


SEGMENT_ROLES = ("velocity_in", "acceleration", "velocity_out", "span", "duration")

# What a whole-figure quantity actually measures. The renderer draws each kind
# differently, so the distinction has to survive into the payload:
#   displacement — start of the first segment to the end of the last (a net,
#                  which for a there-and-back motion is NOT the path length)
#   path         — the summed length of every leg, ignoring direction
#   duration     — elapsed time across all segments
#   rate         — a quantity defined over the whole trip (an average speed)
TOTAL_MEASURES = ("displacement", "path", "duration", "rate")


def motion_1d(ctx, *, orientation="horizontal", segments, totals=()):
    """A 1-D motion figure: an oriented axis, ordered segments, whole-trip totals.

    Segments are ordered because ``upward-throw`` (up then down) and
    ``distance-displacement`` (out then back) reverse direction mid-problem;
    a flat element bag cannot express that. Roles whose symbol is absent from
    this instance are dropped, so the figure is variable-consistent — it draws
    only what the problem actually involves.

    ``totals`` carries the quantities that describe the motion *as a whole* —
    total elapsed time, net displacement, path length, an average rate. They
    are emitted beside the segments rather than inside one of them: attaching a
    whole-trip value to a single leg (the pre-2026-07-29 behaviour for
    ``average-speed``'s ``t`` and ``multi-stage-motion``'s ``s``) draws a
    bracket that claims the value covers only that leg, which is false. Each
    entry is ``{"symbol": Symbol, "measures": <one of TOTAL_MEASURES>}``.
    """
    built = []
    for seg in segments:
        out = {"direction": seg.get("direction", "forward")}
        for role in SEGMENT_ROLES:
            label = ctx.label(seg.get(role))
            if label is not None:
                out[role] = label
        built.append(out)
    spec = {"kind": "motion-1d", "orientation": orientation, "segments": built}

    built_totals = []
    for total in totals:
        measures = total["measures"]
        if measures not in TOTAL_MEASURES:
            raise ValueError(
                f"unknown measures {measures!r}; expected one of {TOTAL_MEASURES}"
            )
        label = ctx.label(total["symbol"])
        if label is None:
            continue
        built_totals.append({**label, "measures": measures})
    if totals:
        spec["totals"] = built_totals
    return spec


def plot_2d(ctx, *, axes, points):
    """A 2-D plot: labelled axes and a polyline.

    **The exception to the answer-hiding rule.** ``motion-graphs`` exists to
    produce graph-reading splits, where the student derives the slope (``a``) or
    the area under the polyline (``s``) *from the figure*. Withholding the
    polyline because the find is derivable from it would delete the question. So
    every point ships; what never ships is an *annotation* naming the find's
    value (no ``$a = 2$`` slope caption, no labelled shaded area).
    """
    to_display, to_exact = _numeric_forms()
    return {
        "kind": "plot-2d",
        "axes": axes,
        "points": [
            {"x": {"value": to_display(x), "exact": to_exact(x)},
             "y": {"value": to_display(y), "exact": to_exact(y)}}
            for x, y in points
        ],
    }


def actors(ctx, *, bodies):
    """Two or more named bodies with velocity arrows on a shared axis.

    The relative-velocity figure: the frame comparison is the point, so each
    body is named rather than positioned.
    """
    built = []
    for body in bodies:
        label = ctx.label(body["velocity"])
        if label is None:
            continue
        built.append({"name": body["name"], "velocity": label})
    return {"kind": "actors", "bodies": built}
