"""The constraint-based re-roll loop — ``generate()`` (spec §5, build guide §7).

The engine generates by *reverse engineering*: it samples inputs, solves
**symbolically** (SymPy ``solve``), and only keeps instances whose answer
satisfies every constraint — re-rolling otherwise. The loop is **bounded** so it
can never hang, and degrades gracefully (loosens the clean-answer tier once at
``SOFT_LIMIT``) before raising a typed failure.

Invariants baked in (each traceable to the spec):

* **Bounded** — the attempt range is finite; the loop can never hang (spec §5).
* **Solve is symbolic** — ``sympy.solve`` then evaluate; no float-guessing
  (spec §2, §5).
* **Deterministic** — ``seed + attempt`` makes the whole run reproducible from a
  single integer (spec §5, §7).
* **Plausibility is sacred** — ``loosen()`` relaxes *cleanliness* only, never the
  template's physical constraints (spec §6).
* **Failure is loud** — every dead end raises a typed error (spec §9).
"""

from __future__ import annotations

import sympy

from engine import contract, policy as policy_mod, sampling
from engine.errors import NoCleanInstanceError, OverDeterminedError, UnsolvableError
from engine.registry import load_template

# Bounded-loop limits (build guide §3 — starting values, tune empirically).
MAX_ATTEMPTS = 200
SOFT_LIMIT = 120


def generate(topic, given=None, find=None, conditions=None, difficulty="easy",
             seed=0, max_attempts=MAX_ATTEMPTS, soft_limit=SOFT_LIMIT):
    """Generate one fully-solved problem instance as ``sympy_data`` (spec §5, §7).

    Basic mode: pass only ``topic`` (+ ``difficulty``) and the template's default
    given/find split is used. Advanced mode: pass ``given`` (3 symbols/names) and
    ``find`` (1). ``conditions`` pins variables (see :mod:`engine.sampling`).

    Raises :class:`UnsolvableError` / :class:`OverDeterminedError` at validation,
    or :class:`NoCleanInstanceError` if no clean instance is found in
    ``max_attempts``.
    """
    template = load_template(topic)
    given, find = _resolve_split(template, given, find)

    # -- validation (spec §3, §9): reject before entering the loop -------------
    ok, info = template.solvability(given, find)
    if not ok:
        raise UnsolvableError(topic, _names(given), find.name, reason=info)
    equation = info
    if len(set(given)) != len(given):
        raise OverDeterminedError(
            topic, _names(given), find.name, reason="duplicate given variable"
        )

    pol = policy_mod.for_(topic, difficulty)
    if template.signed_answer:
        pol = policy_mod.permit_sign(pol)  # vector topics: keep the direction sign

    for attempt in range(1, max_attempts + 1):
        inputs = sampling.sample(template, given, conditions, difficulty, seed + attempt)
        solved = _solve(equation, find, inputs, template, difficulty)
        if solved is not None:
            value, sym_expr = solved
            values = dict(inputs)
            values[find] = value
            if _satisfies(values, find, template, pol, difficulty):
                return contract.build_sympy_data(
                    template, given, find, inputs, value, sym_expr,
                    seed=seed, policy=pol, plausible=True,
                )
        if attempt == soft_limit:
            pol = policy_mod.loosen(pol)  # graceful degradation (spec §5, §6)

    raise NoCleanInstanceError(topic, find.name, attempts=max_attempts)


def _solve(equation, find, inputs, template, difficulty):
    """Solve ``equation`` for ``find`` at ``inputs`` — exact, symbolic (spec §5).

    Returns ``(value, sym_expr)`` where ``value`` is the chosen physical root
    (exact SymPy number) and ``sym_expr`` is the symbolic solution that produced
    it (for step rendering). Returns ``None`` for a failed roll (no physical root,
    or a degenerate/zero-division sample — treated as re-roll, spec §9).
    """
    try:
        sym_sols = sympy.solve(equation, find)
    except (ZeroDivisionError, NotImplementedError):
        return None
    candidates = []  # (value, sym_expr)
    for expr in sym_sols:
        try:
            val = sympy.nsimplify(expr.subs(inputs))
        except (ZeroDivisionError, ValueError):
            continue
        if val.is_real and val.is_number:
            candidates.append((val, expr))
    if not candidates:
        return None
    chosen = template.root_select([c[0] for c in candidates], find, difficulty)
    if chosen is None:
        return None
    for val, expr in candidates:
        if sympy.simplify(val - chosen) == 0:
            return chosen, expr
    return None


def _satisfies(values, find, template, pol, difficulty):
    """Plausibility constraints (always) AND clean-answer policy (spec §5, §6)."""
    if not all(c(values, difficulty) for c in template.constraints):
        return False
    return pol.is_clean(values[find])


def _resolve_split(template, given, find):
    """Normalize the given/find split, defaulting to the template's (Basic mode)."""
    if given is None or find is None:
        given, find = template.default_split
    given = tuple(template.symbol(g) for g in given)
    find = template.symbol(find)
    return given, find


def _names(syms):
    return [s.name for s in syms]
