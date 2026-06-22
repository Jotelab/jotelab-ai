"""Data Fidelity oracle — independent re-derivation (spec §11, build guide §10).

Built alongside the engine, not after. For each emitted ``sympy_data`` instance
the harness re-derives the answer **independently of the generator** and asserts
four things:

* **(a)** the SUVAT equation linking ``given ∪ {find}`` holds for the emitted
  values;
* **(b)** ``final_answer`` matches an independent recomputation — solving the
  *whole* SUVAT system, a different code path from the generator's single-equation
  solve, so a generator bug cannot agree with itself;
* **(c)** units are consistent across given / find / final answer;
* **(d)** the template's plausibility constraints hold;
* **(e)** each display ``value`` agrees with its authoritative ``exact`` string,
  and ``final_answer.exact`` equals ``find.exact`` (ADR-005 — guards against the
  lossy display field drifting from the source of truth).

All math is done on the **exact** values (ADR-005); the display ``value`` is never
trusted as the source of truth, only checked for consistency in (e).

This harness gates every change to a template and is the engine-side ground truth
for the Data Fidelity benchmark metric (spec §11).
"""

from __future__ import annotations

import sympy

from engine.contract import exact, to_display
from templates import suvat
from templates.suvat import ALL_SYMS, EQUATION_BY_EXCLUDED, SYMBOLS


class FidelityError(AssertionError):
    """A ``sympy_data`` instance failed an independent Data Fidelity assertion."""


def verify(sympy_data, difficulty="easy"):
    """Raise :class:`FidelityError` if ``sympy_data`` fails any of (a)–(d).

    Returns ``True`` when the instance is faithful. Only the SUVAT topic is
    supported at launch (build guide §8); other topics raise ``NotImplementedError``.
    """
    if sympy_data["topic"] != "suvat":
        raise NotImplementedError(f"no harness for topic {sympy_data['topic']!r}")

    given = {SYMBOLS[g["symbol"]]: exact(g["exact"]) for g in sympy_data["given"]}
    find_sym = SYMBOLS[sympy_data["find"]["symbol"]]
    find_val = exact(sympy_data["find"]["exact"])
    values = dict(given)
    values[find_sym] = find_val

    _assert_equation_holds(given, find_sym, values)                      # (a)
    _assert_independent_recompute(given, find_sym, find_val, difficulty)  # (b)
    _assert_units_consistent(sympy_data)                                 # (c)
    _assert_plausible(values, difficulty)                                # (d)
    _assert_display_consistent(sympy_data)                               # (e)
    return True


def _assert_equation_holds(given, find_sym, values):
    """(a) The linking SUVAT relation holds exactly for the emitted values."""
    unused = ALL_SYMS - (set(given) | {find_sym})
    if len(unused) != 1:
        raise FidelityError(f"(a) cannot isolate unused variable from {set(values)}")
    eq = EQUATION_BY_EXCLUDED[next(iter(unused))]
    residual = sympy.simplify(eq.lhs.subs(values) - eq.rhs.subs(values))
    if residual != 0:
        raise FidelityError(f"(a) equation {eq} does not hold; residual={residual}")


def _assert_independent_recompute(given, find_sym, find_val, difficulty):
    """(b) Re-solve the whole SUVAT system — a path independent of the generator.

    The ``difficulty`` is forwarded to :func:`independent_solve` so the oracle uses
    the *same* physical root-selection rule as the generator at this band (ADR-005
    / fix F2). Without it the recompute silently fell back to ``easy`` selection
    and disagreed with the generator on ``medium`` / ``hard`` (e.g. negative roots).
    """
    recomputed = independent_solve(given, find_sym, difficulty)
    if recomputed is None:
        raise FidelityError(f"(b) independent solve found no physical {find_sym}")
    if sympy.simplify(recomputed - find_val) != 0:
        raise FidelityError(
            f"(b) final_answer {find_val} != independent recompute {recomputed}"
        )


def independent_solve(given, find_sym, difficulty="easy"):
    """Re-derive ``find`` by solving the *full* SUVAT system (build guide §10).

    Substitutes the givens into all five relations and solves the resulting
    system for the remaining unknowns — deliberately a different path from the
    generator's single-equation solve. Applies the same physical root selection.
    """
    eqs = [sympy.Eq(e.lhs.subs(given), e.rhs.subs(given)) for e in suvat.EQUATIONS]
    unknowns = sorted(ALL_SYMS - set(given), key=lambda s: s.name)
    sols = sympy.solve(eqs, unknowns, dict=True)
    candidates = []
    for sol in sols:
        if find_sym in sol:
            val = sympy.nsimplify(sol[find_sym])
            if val.is_real and val.is_number:
                candidates.append(val)
    return suvat.root_select(candidates, find_sym, difficulty)


def _assert_units_consistent(sympy_data):
    """(c) Every emitted unit matches the canonical unit for its symbol."""
    canonical = {sym.name: suvat.VARIABLES[sym].unit for sym in suvat.VARIABLES}
    for g in sympy_data["given"]:
        if g["unit"] != canonical[g["symbol"]]:
            raise FidelityError(
                f"(c) unit mismatch for {g['symbol']}: {g['unit']} != "
                f"{canonical[g['symbol']]}"
            )
    find = sympy_data["find"]
    if find["unit"] != canonical[find["symbol"]]:
        raise FidelityError(f"(c) unit mismatch for find {find['symbol']}")
    if sympy_data["final_answer"]["unit"] != find["unit"]:
        raise FidelityError("(c) final_answer unit != find unit")


def _assert_plausible(values, difficulty):
    """(d) The template's plausibility constraints hold."""
    for c in suvat.CONSTRAINTS:
        if not c(values, difficulty):
            raise FidelityError(f"(d) plausibility constraint {c.__name__} failed")


def _assert_display_consistent(sympy_data):
    """(e) Display ``value`` agrees with authoritative ``exact`` (ADR-005).

    Catches drift in the lossy presentation field and any mismatch between
    ``final_answer`` and ``find`` — the display number must be exactly the
    :func:`~engine.contract.to_display` of the exact value it claims to show.
    """
    items = list(sympy_data["given"]) + [
        sympy_data["find"],
        sympy_data["final_answer"],
    ]
    for it in items:
        if to_display(exact(it["exact"])) != it["value"]:
            raise FidelityError(
                f"(e) display value {it['value']!r} != exact {it['exact']!r}"
            )
    if sympy_data["final_answer"]["exact"] != sympy_data["find"]["exact"]:
        raise FidelityError(
            f"(e) final_answer.exact {sympy_data['final_answer']['exact']!r} != "
            f"find.exact {sympy_data['find']['exact']!r}"
        )
