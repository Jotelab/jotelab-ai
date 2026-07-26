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

from engine.contract import to_display, to_exact

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
        out["role"] = "given" if sym in self.given else "derived"
        out["value"] = to_display(self.values[sym])
        out["exact"] = to_exact(self.values[sym])
        out["unit"] = self.template.unit_for(sym)
        return out


SEGMENT_ROLES = ("velocity_in", "acceleration", "velocity_out", "span", "duration")


def motion_1d(ctx, *, orientation="horizontal", segments):
    """A 1-D motion figure: an oriented axis plus ordered segments.

    Segments are ordered because ``upward-throw`` (up then down) and
    ``distance-displacement`` (out then back) reverse direction mid-problem;
    a flat element bag cannot express that. Roles whose symbol is absent from
    this instance are dropped, so the figure is variable-consistent — it draws
    only what the problem actually involves.
    """
    built = []
    for seg in segments:
        out = {"direction": seg.get("direction", "forward")}
        for role in SEGMENT_ROLES:
            label = ctx.label(seg.get(role))
            if label is not None:
                out[role] = label
        built.append(out)
    return {"kind": "motion-1d", "orientation": orientation, "segments": built}
