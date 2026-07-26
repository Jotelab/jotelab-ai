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
            value, sym_expr, aux_values = solved
            values = dict(inputs)
            values[find] = value
            values.update(aux_values)
            if _satisfies(values, find, template, pol, difficulty):
                return contract.build_sympy_data(
                    template, given, find, inputs, value, sym_expr,
                    seed=seed, policy=pol, plausible=True,
                    aux_values=aux_values,
                )
        if attempt == soft_limit:
            pol = policy_mod.loosen(pol)  # graceful degradation (spec §5, §6)

    raise NoCleanInstanceError(topic, find.name, attempts=max_attempts)


def _solve(info, find, inputs, template, difficulty):
    """Solve for ``find`` at ``inputs`` — exact, symbolic (spec §5).

    ``info`` is what ``solvability`` returned: a single linking equation, or a
    system-template solution object (duck-typed via ``.branches`` — see
    templates/declarative/system.py for why there is no import here). Returns
    ``(value, sym_expr, aux_values)`` — ``aux_values`` is ``{}`` on the
    single-equation path — or ``None`` for a failed roll.
    """
    branches = getattr(info, "branches", None)
    if branches is not None:
        return _solve_system(branches, find, inputs, template, difficulty)
    try:
        sym_sols = sympy.solve(info, find)
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
            return chosen, expr, {}
    return None


def _solve_system(branches, find, inputs, template, difficulty):
    """Evaluate cached system branches; keep auxiliaries branch-consistent.

    The find candidates are root-selected exactly like single-equation roots;
    the auxiliaries are then evaluated from the SAME branch as the chosen
    value (spec 2026-07-27) and must all be exact rationals — anything else
    is a failed roll (ADR-005 keeps the exact() parser Rational-only).

    Tied roots: two or more branches can yield the same chosen find value
    (e.g. ``Eq(q**2, c), Eq(t, c)`` -> t=c with q=±sqrt(c)). Every branch
    whose find value matches ``chosen`` is tried in turn; a branch that is
    not viable (irrational auxiliary, or a ``.subs`` failure) is skipped in
    favor of the next tied branch, and only the exhaustion of every matching
    branch counts as a failed roll. Known limitation: this only widens the
    *find/auxiliary* selection — a per-branch LOOP constraint is still
    checked post-selection in ``_satisfies``, so a template combining tied
    roots with an auxiliary constraint can still re-roll on a branch that
    would have passed had a different (also-tied) branch been returned
    instead; revisit in the scene layer if that combination is needed.
    """
    candidates = []  # (value, branch)
    for branch in branches:
        try:
            val = sympy.nsimplify(branch.find_expr.subs(inputs))
        except (ZeroDivisionError, ValueError):
            continue
        if val.is_real and val.is_number:
            candidates.append((val, branch))
    if not candidates:
        return None
    chosen = template.root_select([c[0] for c in candidates], find, difficulty)
    if chosen is None:
        return None
    for val, branch in candidates:
        if sympy.simplify(val - chosen) != 0:
            continue
        aux_values = {}
        viable = True
        for aux_sym, expr in branch.aux_exprs.items():
            try:
                aval = sympy.nsimplify(expr.subs(inputs))
            except (ZeroDivisionError, ValueError):
                viable = False
                break
            if not (aval.is_number and aval.is_rational):
                viable = False  # non-rational auxiliary -> try next tied branch
                break
            aux_values[aux_sym] = aval
        if not viable:
            continue
        return chosen, branch.find_expr, aux_values
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
