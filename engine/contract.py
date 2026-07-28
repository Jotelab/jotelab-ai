"""Assemble the locked ``sympy_data`` output contract (spec §7, build guide §6).

The engine emits a JSON-serializable object stored verbatim in
``QUESTIONS.sympy_data``. Its shape is the contract the Zod schema and the Data
Fidelity check depend on, so it is fixed here::

    {
      "topic": "suvat",
      "seed": 80421,
      "given": [{"symbol": "u", "value": 0, "exact": "0", "unit": "m/s"}, ...],
      "find":  {"symbol": "v", "value": 10, "exact": "10", "unit": "m/s"},
      "steps": [{"expr_latex": ..., "substituted_latex": ..., "result_latex": ...}],
      "final_answer": {"value": 10, "exact": "10", "unit": "m/s",
                       "latex": "10\\ \\text{m/s}"},
      "auxiliary": [{"symbol": "x", "value": 10.5, "exact": "21/2", "unit": "m"}],   # system templates only
      "policy_applied": "easy",
      "plausible": true
    }

Numbers + units are first-class so the Data Fidelity check can compare them to the
LLM's rendered text programmatically — no prose parsing (spec §7).

**Exactness (ADR-005).** Every numeric field carries two forms: ``exact`` — a
canonical, losslessly-reloadable string that is the *authoritative* value (e.g.
``"1/3"``) — and ``value`` — a JSON display number that is *presentation only* and
may be a lossy round of a non-terminating rational (``1/3 -> 0.333333``). The
verification harness, the Data Fidelity check, and the renderer use ``exact`` /
``latex``; nothing trusts ``value`` as the source of truth. Storing only a display
float (the pre-ADR-005 behaviour) silently corrupted non-terminating clean answers
and broke the engine's own Data Fidelity oracle on the ``medium`` band.
"""

from __future__ import annotations

import sympy


def to_display(value):
    """JSON-friendly **display** number — presentation only, *not* authoritative.

    Integers stay ``int``; every other rational becomes a ``float`` rounded to 6
    places. This is lossy for non-terminating rationals (``1/3 -> 0.333333``);
    the exact, authoritative value travels beside it as the ``exact`` string (see
    :func:`to_exact`). Renderers and the Data Fidelity check must use ``exact`` /
    ``latex``, never this field (ADR-005).
    """
    val = sympy.nsimplify(value)
    if val.is_Integer:
        return int(val)
    return round(float(val), 6)


def to_exact(value):
    """Canonical, losslessly-reloadable string for an exact SymPy number (ADR-005).

    ``1/3 -> "1/3"``, ``10 -> "10"``, ``21/2 -> "21/2"``. This — not
    :func:`to_display` — is the source of truth for every number in
    ``sympy_data``. Reload it with :func:`exact`.
    """
    return str(sympy.nsimplify(value))


def exact(value):
    """Recover the exact SymPy number from a contract ``exact`` string (ADR-005).

    ``exact("1/3") == Rational(1, 3)`` exactly — no float error. Accepts a SymPy
    object or an ``int`` unchanged. Callers must pass the authoritative ``exact``
    field, never the lossy display ``value``; a bare ``float`` is still parsed via
    its string form for safety but signals a misuse.

    The string form is parsed with :class:`sympy.Rational`, not the general
    ``sympify`` evaluator (review finding N1): every clean answer is a rational, so
    ``Rational`` is equivalent for all engine output yet **fails closed** on
    anything that is not a plain rational — hardening this verification-gate parser
    against untrusted/reconstructed ``sympy_data``.
    """
    if isinstance(value, sympy.Basic):
        return sympy.nsimplify(value)
    if isinstance(value, int):
        return sympy.Integer(value)
    if isinstance(value, str):
        return sympy.Rational(value)
    return sympy.Rational(str(value))


def _unit_latex(value, unit):
    return f"{sympy.latex(sympy.nsimplify(value))}\\ \\text{{{unit}}}"


def build_step(find, sym_expr, inputs, value, unit):
    """Build one derivation step: symbolic form → substituted → result (spec §7).

    * ``expr_latex``        — ``find = <symbolic solution>`` (e.g. ``v = u + a t``)
    * ``substituted_latex`` — the same with sampled values plugged in, kept
      unevaluated (e.g. ``v = 0 + 2 \\cdot 5``)
    * ``result_latex``      — the final value with its unit
    """
    uneval = {k: sympy.UnevaluatedExpr(v) for k, v in inputs.items()}
    substituted = sym_expr.xreplace(uneval)
    return {
        "expr_latex": f"{sympy.latex(find)} = {sympy.latex(sym_expr)}",
        "substituted_latex": f"{sympy.latex(find)} = {sympy.latex(substituted)}",
        "result_latex": f"{sympy.latex(find)} = {_unit_latex(value, unit)}",
    }


def build_sympy_data(template, given, find, inputs, value, sym_expr, seed, policy,
                     plausible, aux_values=None):
    """Assemble the locked ``sympy_data`` dict (spec §7)."""
    given_out = [
        {
            "symbol": sym.name,
            "value": to_display(inputs[sym]),
            "exact": to_exact(inputs[sym]),
            "unit": template.unit_for(sym),
        }
        for sym in sorted(given, key=lambda x: x.name)
    ]
    find_unit = template.unit_for(find)
    steps = [build_step(find, sym_expr, inputs, value, find_unit)]
    data = {
        "topic": template.topic,
        "seed": seed,
        "given": given_out,
        "find": {"symbol": find.name, "value": to_display(value),
                 "exact": to_exact(value), "unit": find_unit},
        "steps": steps,
        "final_answer": {
            "value": to_display(value),
            "exact": to_exact(value),
            "unit": find_unit,
            "latex": _unit_latex(value, find_unit),
        },
        "policy_applied": policy.label,
        "plausible": bool(plausible),
    }
    if aux_values:
        # System templates (spec 2026-07-27): the internal unknowns of the
        # solved branch, exact-first like every other number (ADR-005).
        data["auxiliary"] = [
            {
                "symbol": sym.name,
                "value": to_display(val),
                "exact": to_exact(val),
                "unit": template.unit_for(sym),
            }
            for sym, val in sorted(aux_values.items(), key=lambda kv: kv[0].name)
        ]
    if template.diagram_spec is not None:
        # Imported here, not at module scope: templates.diagrams imports
        # to_display/to_exact from this module, so a top-level import would
        # close an import cycle. Same deferral rationale as
        # registry._ensure_declarative_loaded.
        from templates.diagrams import DiagramContext

        values = dict(inputs)
        values[find] = value
        ctx = DiagramContext(template, values, given=set(given), find=find)
        data["diagram"] = template.diagram_spec(ctx)
    return data
