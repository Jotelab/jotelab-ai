"""Scene compiler principle KB (spec 2026-07-29, Task 2): per-phase equations.

``phase_equations`` is the pure function that, given one body's phase and the
context the compiler (Task 3) has already resolved for it, emits the
equation strings and auxiliary declarations that phase contributes.

Equation forms (verbatim from the plan's "Equations emitted per phase"
section):

* ``constant-velocity``, duration D, speed V: ``Eq(s_b_i, V*D)``; if
  ``vend`` needed: ``Eq(vend_b_i, V)``.
* ``constant-acceleration``, duration D, initial U, accel A:
  ``Eq(s_b_i, U*D + A*D**2/2)``; if ``vend`` needed:
  ``Eq(vend_b_i, U + A*D)``.

This function does not decide whether a duration is "auto" or resolve
cross-phase chaining (e.g. ``u: "auto"`` pulling the previous phase's end
velocity) — the caller (the compiler) resolves both of those and passes the
results in already-rendered: ``phase["duration"]`` and ``u_expr``. The only
value this function renders itself is the phase's own speed/acceleration
field (``v`` or ``a``), via :func:`templates.scenes.ontology.render`, since
that requires no context beyond ``given_names``.
"""

from __future__ import annotations

from .ontology import UNITS, SceneError, displacement_name, render, vend_name


def phase_equations(body, i, phase, u_expr, needs_vend, given_names):
    """Emit the equations and auxiliaries for one body's phase ``i``.

    Returns ``(equations, aux)`` where ``equations`` is a list of ``Eq(...)``
    strings and ``aux`` maps each auxiliary name this phase introduces to its
    unit. ``u_expr`` is the already-rendered initial-velocity fragment (used
    only for ``"constant-acceleration"``; pass ``None`` for
    ``"constant-velocity"``). ``needs_vend`` forces emission of the end
    velocity even when nothing else in this phase alone requires it.

    Raises :class:`SceneError` for any phase kind other than
    ``"constant-velocity"`` or ``"constant-acceleration"``.
    """
    kind = phase.get("kind")
    duration = phase["duration"]
    s_name = displacement_name(body, i)
    equations = []
    aux = {s_name: UNITS["displacement"]}

    if kind == "constant-velocity":
        v_expr = render(phase["v"], given_names)
        equations.append(f"Eq({s_name}, {v_expr}*{duration})")
        if needs_vend:
            vend = vend_name(body, i)
            equations.append(f"Eq({vend}, {v_expr})")
            aux[vend] = UNITS["velocity"]
    elif kind == "constant-acceleration":
        a_expr = render(phase["a"], given_names)
        equations.append(
            f"Eq({s_name}, {u_expr}*{duration} + {a_expr}*{duration}**2/2)"
        )
        if needs_vend:
            vend = vend_name(body, i)
            equations.append(f"Eq({vend}, {u_expr} + {a_expr}*{duration})")
            aux[vend] = UNITS["velocity"]
    else:
        raise SceneError(f"unknown phase kind: {kind!r}")

    return equations, aux
