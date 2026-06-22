"""Assemble the locked ``sympy_data`` output contract (spec §7, build guide §6).

The engine emits a JSON-serializable object stored verbatim in
``QUESTIONS.sympy_data``. Its shape is the contract the Zod schema and the Data
Fidelity check depend on, so it is fixed here::

    {
      "topic": "suvat",
      "seed": 80421,
      "given": [{"symbol": "u", "value": 0, "unit": "m/s"}, ...],
      "find":  {"symbol": "v", "value": 10, "unit": "m/s"},
      "steps": [{"expr_latex": ..., "substituted_latex": ..., "result_latex": ...}],
      "final_answer": {"value": 10, "unit": "m/s", "latex": "10\\ \\text{m/s}"},
      "policy_applied": "easy",
      "plausible": true
    }

Numbers + units are first-class so the Data Fidelity check can compare them to the
LLM's rendered text programmatically — no prose parsing (spec §7). Exact SymPy
values are converted to a display number only here, at the final emit step
(build guide §6).
"""

from __future__ import annotations

import sympy


def to_display(value):
    """Convert an exact SymPy number to a JSON-friendly int/float.

    Integers stay ``int``; everything else becomes a ``float`` rounded to 6
    places (clean answers are ≤3 decimals, so this is exact for them and only
    trims float noise). The exact value is recoverable via ``exact()``.
    """
    val = sympy.nsimplify(value)
    if val.is_Integer:
        return int(val)
    return round(float(val), 6)


def exact(value):
    """Recover an exact SymPy ``Rational`` from a display number.

    Used by the verification harness to re-derive without reintroducing float
    error: ``Rational(str(10.5)) == 21/2`` exactly.
    """
    if isinstance(value, sympy.Basic):
        return sympy.nsimplify(value)
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
                     plausible):
    """Assemble the locked ``sympy_data`` dict (spec §7)."""
    given_out = [
        {
            "symbol": sym.name,
            "value": to_display(inputs[sym]),
            "unit": template.unit_for(sym),
        }
        for sym in sorted(given, key=lambda x: x.name)
    ]
    find_unit = template.unit_for(find)
    steps = [build_step(find, sym_expr, inputs, value, find_unit)]
    return {
        "topic": template.topic,
        "seed": seed,
        "given": given_out,
        "find": {"symbol": find.name, "value": to_display(value), "unit": find_unit},
        "steps": steps,
        "final_answer": {
            "value": to_display(value),
            "unit": find_unit,
            "latex": _unit_latex(value, find_unit),
        },
        "policy_applied": policy.label,
        "plausible": bool(plausible),
    }
