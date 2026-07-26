"""Simultaneous-system solvability for declarative templates (spec 2026-07-27).

A *system template* declares auxiliary (internal) unknowns and 2+ equations
that must be solved together. Solvability is derived **once, symbolically**:
``sympy.solve`` with the givens left symbolic yields closed-form solution
branches — the find and every auxiliary expressed in the givens. Generation
then only substitutes sampled numbers into cached expressions, so the bounded
re-roll loop stays as fast as the single-equation path, and the harness's
independent numeric re-solve remains a genuinely different code path.

v1 rule: **no unused variables** — a split is valid iff the given set is
exactly all declared variables minus the find. Auxiliaries are always solved,
never given, never the find (enforced at parse time).

``engine.loop`` detects a system split by duck-typing
(``getattr(info, "branches", None)``), NOT by importing this module — the
``templates.declarative`` package pulls in ``gate``, which imports
``engine.loop``, so a top-level import from the loop would cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

import sympy


@dataclass(frozen=True)
class Branch:
    """One solution branch: the find and every auxiliary, in the givens."""

    find_expr: object  # sympy expression over the given symbols
    aux_exprs: dict    # Symbol -> sympy expression over the given symbols


@dataclass(frozen=True)
class SystemSolution:
    """All closed-form branches for one (given, find) split."""

    branches: tuple  # tuple[Branch, ...]


def derive_branches(equations, given, find, aux_syms):
    """Symbolically solve the system for ``[find] + auxiliaries``.

    Returns a tuple of :class:`Branch` — one per solution branch whose every
    expression closes over the ``given`` symbols only. An unsolvable system
    (or one SymPy cannot solve in closed form) yields ``()``.
    """
    given = set(given)
    unknowns = [find] + sorted(aux_syms, key=lambda s: s.name)
    try:
        sols = sympy.solve(equations, unknowns, dict=True)
    except (NotImplementedError, ValueError, TypeError):
        return ()
    branches = []
    for sol in sols:
        if find not in sol:
            continue
        find_expr = sol[find]
        if not find_expr.free_symbols <= given:
            continue
        aux_exprs = {}
        for aux in aux_syms:
            expr = sol.get(aux)
            if expr is None or not expr.free_symbols <= given:
                aux_exprs = None
                break
            aux_exprs[aux] = expr
        if aux_exprs is not None:
            branches.append(Branch(find_expr=find_expr, aux_exprs=aux_exprs))
    return tuple(branches)


def make_system_solvability(equations, var_syms, aux_syms):
    """Build the ``solvability(given, find)`` callable for a system template.

    Valid split: ``given == var_syms - {find}`` (no unused variables). The
    derivation is cached per split, so repeated calls (``valid_splits``, the
    loop, the gate) pay the symbolic solve once.
    """
    all_vars = frozenset(var_syms)
    aux_syms = frozenset(aux_syms)
    cache = {}

    def solvability(given, find):
        given_set = frozenset(given)
        if find in given_set:
            return (False, "find must be distinct from the given variables")
        if not (given_set | {find}) <= all_vars:
            return (False, "unknown variable for this template")
        if given_set != all_vars - {find}:
            return (False, "system templates have no unused variables: "
                           "given must be every variable except the find")
        key = (given_set, find)
        if key not in cache:
            cache[key] = SystemSolution(
                branches=derive_branches(equations, given_set, find, aux_syms))
        solution = cache[key]
        if not solution.branches:
            return (False, "system has no closed-form solution for this split")
        return (True, solution)

    return solvability
