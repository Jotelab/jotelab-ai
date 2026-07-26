"""Data Fidelity oracle — independent re-derivation (spec §11, build guide §10).

Built alongside the engine, not after. For each emitted ``sympy_data`` instance
the harness re-derives the answer **independently of the generator** and asserts
five things:

* **(a)** the equation linking ``given ∪ {find}`` holds for the emitted values;
* **(b)** ``final_answer`` matches an independent recomputation — solving the
  *whole* equation system, a different code path from the generator's
  single-equation solve, so a generator bug cannot agree with itself;
* **(c)** units are consistent across given / find / final answer;
* **(d)** the template's plausibility constraints hold;
* **(e)** each display ``value`` agrees with its authoritative ``exact`` string, and
  ``final_answer.exact`` equals ``find.exact`` (ADR-005 — guards against the lossy
  display field drifting from the source of truth).

All math is done on the **exact** values (ADR-005); the display ``value`` is never
trusted as the source of truth, only checked for consistency in (e).

The core, :func:`verify_generic`, works for **any** parsed :class:`Template`
(ADR-007): every topic-specific source — symbols, equations, canonical units,
constraints, root policy — is read from the passed template, not imported from a
particular topic module. :func:`verify` keeps the SUVAT-specific public entry point
and delegates to the generic core, so existing callers are unchanged.

:func:`verify_chain` extends the oracle to chained mixed instances: every part
runs through :func:`verify_generic`, then each link is asserted exact.
"""

from __future__ import annotations

import sympy

from engine.contract import exact, to_display
from engine.registry import load_template


class FidelityError(AssertionError):
    """A ``sympy_data`` instance failed an independent Data Fidelity assertion."""


# -- public entry points -------------------------------------------------------
def verify(sympy_data, difficulty="easy"):
    """SUVAT Data-Fidelity check (delegates to the topic-generic core).

    Returns ``True`` when the instance is faithful. Only the SUVAT topic is wired
    to this convenience entry point; other topics call :func:`verify_generic`
    directly with their parsed template.
    """
    if sympy_data["topic"] != "suvat":
        raise NotImplementedError(f"no harness for topic {sympy_data['topic']!r}")
    return verify_generic(sympy_data, load_template("suvat"), difficulty)


def verify_generic(sympy_data, template, difficulty="easy"):
    """Independent Data-Fidelity re-derivation for any parsed Template (ADR-007).

    Raises :class:`FidelityError` on any (a)–(e) failure; returns ``True`` when the
    instance is faithful. Topic-specific data is read from ``template``.
    """
    symbols = template.symbols
    all_syms = set(symbols.values())
    given = {symbols[g["symbol"]]: exact(g["exact"]) for g in sympy_data["given"]}
    find_sym = symbols[sympy_data["find"]["symbol"]]
    find_val = exact(sympy_data["find"]["exact"])
    values = dict(given)
    values[find_sym] = find_val

    if template.auxiliaries:
        aux_vals = _emitted_auxiliaries(template, sympy_data)
        values.update(aux_vals)
        _assert_system_holds(template, values)                                     # (a)
        _assert_system_recompute(template, given, find_sym, find_val,
                                 aux_vals, difficulty)                             # (b)
    else:
        _assert_equation_holds(template, all_syms, given, find_sym, values)        # (a)
        _assert_independent_recompute(template, given, find_sym, find_val,
                                      difficulty)                                  # (b)
    _assert_units_consistent(template, sympy_data)                                  # (c)
    _assert_plausible(template, values, difficulty)                                 # (d)
    _assert_display_consistent(sympy_data)                                          # (e)
    return True


# -- assertions ----------------------------------------------------------------
def _linking_equation(template, all_syms, given, find_sym):
    """The single equation whose variables are exactly ``given ∪ {find}``."""
    used = set(given) | {find_sym}
    for eq in template.equations:
        if (eq.free_symbols & all_syms) == used:
            return eq
    raise FidelityError(f"(a) no equation relates exactly {used}")


def _assert_equation_holds(template, all_syms, given, find_sym, values):
    """(a) The linking relation holds exactly for the emitted values."""
    eq = _linking_equation(template, all_syms, given, find_sym)
    residual = sympy.simplify(eq.lhs.subs(values) - eq.rhs.subs(values))
    if residual != 0:
        raise FidelityError(f"(a) equation {eq} does not hold; residual={residual}")


def independent_solve(template, given, find_sym, difficulty="easy"):
    """Re-derive ``find`` by solving the *full* equation system (build guide §10).

    Substitutes the givens into every relation and solves the resulting system for
    the remaining unknowns — deliberately a different path from the generator's
    single-equation solve. Applies the template's own physical root selection at the
    requested ``difficulty`` (ADR-005 / fix F2: without the band the recompute could
    disagree with the generator on ``medium`` / ``hard``).
    """
    all_syms = set(template.symbols.values())
    eqs = [sympy.Eq(e.lhs.subs(given), e.rhs.subs(given)) for e in template.equations]
    unknowns = sorted(all_syms - set(given), key=lambda s: s.name)
    sols = sympy.solve(eqs, unknowns, dict=True)
    candidates = []
    for sol in sols:
        if find_sym in sol:
            val = sympy.nsimplify(sol[find_sym])
            if val.is_real and val.is_number:
                candidates.append(val)
    return template.root_select(candidates, find_sym, difficulty)


def _assert_independent_recompute(template, given, find_sym, find_val, difficulty):
    """(b) Re-solve the whole system — a path independent of the generator."""
    recomputed = independent_solve(template, given, find_sym, difficulty)
    if recomputed is None:
        raise FidelityError(f"(b) independent solve found no physical {find_sym}")
    if sympy.simplify(recomputed - find_val) != 0:
        raise FidelityError(
            f"(b) final_answer {find_val} != independent recompute {recomputed}"
        )


def _emitted_auxiliaries(template, sympy_data):
    """Parse and complete-check the emitted auxiliary values (system templates)."""
    by_name = {sym.name: sym for sym in template.auxiliaries}
    seen = {}
    for item in sympy_data.get("auxiliary", []):
        sym = by_name.get(item["symbol"])
        if sym is None:
            raise FidelityError(f"(a) unknown auxiliary {item['symbol']!r}")
        seen[sym] = exact(item["exact"])
    missing = sorted(s.name for s in set(by_name.values()) - set(seen))
    if missing:
        raise FidelityError(f"(a) auxiliary values missing for {', '.join(missing)}")
    return seen


def _assert_system_holds(template, values):
    """(a, system form) every declared equation holds at the emitted values."""
    for eq in template.equations:
        residual = sympy.simplify(eq.lhs.subs(values) - eq.rhs.subs(values))
        if residual != 0:
            raise FidelityError(
                f"(a) equation {eq} does not hold; residual={residual}")


def _assert_system_recompute(template, given, find_sym, find_val, aux_vals,
                             difficulty):
    """(b, system form) independent numeric whole-system solve, same branch.

    Branch selection matches on the *find* value AND every emitted auxiliary
    (not find alone) — with tied find roots (spec F1: e.g. ``q**2 = c``), a
    branch whose find value happens to match ``chosen`` but whose auxiliary
    disagrees with what the generator emitted is not the branch the emitted
    instance actually came from, and must not be accepted as a fidelity match.
    """
    aux_syms = sorted(template.auxiliaries, key=lambda s: s.name)
    eqs = [sympy.Eq(e.lhs.subs(given), e.rhs.subs(given))
           for e in template.equations]
    try:
        sols = sympy.solve(eqs, [find_sym] + aux_syms, dict=True)
    except (NotImplementedError, TypeError) as exc:
        raise FidelityError(f"(b) independent system solve failed: {exc}")
    candidates = []
    for sol in sols:
        if find_sym in sol:
            val = sympy.nsimplify(sol[find_sym])
            if val.is_real and val.is_number:
                candidates.append((val, sol))
    chosen = template.root_select([c[0] for c in candidates], find_sym, difficulty)
    if chosen is None:
        raise FidelityError(f"(b) independent solve found no physical {find_sym}")
    if sympy.simplify(chosen - find_val) != 0:
        raise FidelityError(
            f"(b) final_answer {find_val} != independent recompute {chosen}")
    branch = None
    for val, sol in candidates:
        if sympy.simplify(val - chosen) != 0:
            continue
        if all(sym in sol and sympy.simplify(sympy.nsimplify(sol[sym]) - aux_vals[sym]) == 0
               for sym in aux_syms):
            branch = sol
            break
    if branch is None:
        raise FidelityError(
            "(b) no independent solution branch matches the emitted auxiliaries")


def _assert_units_consistent(template, sympy_data):
    """(c) Every emitted unit matches the canonical unit for its symbol."""
    canonical = {sym.name: template.variables[sym].unit for sym in template.variables}
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
    aux_canonical = {sym.name: unit
                     for sym, unit in (template.auxiliaries or {}).items()}
    for item in sympy_data.get("auxiliary", []):
        if item["unit"] != aux_canonical.get(item["symbol"]):
            raise FidelityError(
                f"(c) unit mismatch for auxiliary {item['symbol']}")


def _assert_plausible(template, values, difficulty):
    """(d) The template's plausibility constraints hold."""
    for c in template.constraints:
        if not c(values, difficulty):
            raise FidelityError(
                f"(d) plausibility constraint {getattr(c, '__name__', c)} failed"
            )


def _assert_display_consistent(sympy_data):
    """(e) Display ``value`` agrees with authoritative ``exact`` (ADR-005).

    Catches drift in the lossy presentation field and any mismatch between
    ``final_answer`` and ``find`` — the display number must be exactly the
    :func:`~engine.contract.to_display` of the exact value it claims to show.
    """
    items = (list(sympy_data["given"]) + list(sympy_data.get("auxiliary", []))
             + [sympy_data["find"], sympy_data["final_answer"]])
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


def verify_chain(chain_data, difficulty="easy"):
    """Data-Fidelity check for a chained mixed instance (chain design doc).

    Every part must pass the full (a)–(e) :func:`verify_generic` battery with
    its own template, and every link must carry the previous part's answer
    exactly: the receiving given's ``exact`` equals the feeding part's
    ``final_answer.exact`` (compared symbolically), units agree, and the
    recorded link ``exact`` matches. Raises :class:`FidelityError` on any
    failure; returns ``True`` when the whole chain is faithful.
    """
    for part in chain_data["parts"]:
        verify_generic(part, load_template(part["topic"]), difficulty)
    for link in chain_data["links"]:
        feed = chain_data["parts"][link["from_part"]]["final_answer"]
        receiving = chain_data["parts"][link["to_part"]]
        recv = next(
            (g for g in receiving["given"] if g["symbol"] == link["symbol"]),
            None,
        )
        if recv is None:
            raise FidelityError(
                f"(link) part {link['to_part'] + 1} has no given "
                f"{link['symbol']!r}"
            )
        if sympy.simplify(exact(recv["exact"]) - exact(feed["exact"])) != 0:
            raise FidelityError(
                f"(link) received {recv['exact']!r} != fed answer "
                f"{feed['exact']!r}"
            )
        if recv["unit"] != feed["unit"]:
            raise FidelityError(
                f"(link) unit {recv['unit']} != fed unit {feed['unit']}"
            )
        if link["exact"] != feed["exact"]:
            raise FidelityError(
                f"(link) recorded link exact {link['exact']!r} != "
                f"final_answer.exact {feed['exact']!r}"
            )
    return True
