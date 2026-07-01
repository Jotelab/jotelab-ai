"""Declarative topic templates — data parsed into a :class:`Template` (ADR-007).

A topic template stops being executable Python and becomes a plain data document
(a ``dict``, trivially JSON/YAML-backed). :func:`load_declarative` parses it into
today's :class:`~templates.base.Template`, so the whole downstream engine
(``engine.loop``) is unchanged. This is what lets the userbase grow the topic
library without a developer while never running user code on the server.

Per ADR-007 §(b) the two most error-prone callables are *not* authored:

* **solvability** is *derived* from the equation set (:func:`_make_solvability`) —
  the single equation whose free symbols are exactly ``given ∪ {find}``.
* **root selection** is a *named policy* (:func:`_make_root_select`) driven by
  declarative rules, not hand-written selection logic.
* **constraints** are a small declarative predicate DSL (:func:`_make_constraint`).

The spec shape (see :data:`SUVAT_SPEC`)::

    {
      "topic": "suvat",
      "variables": [{"name","unit","ranges":{difficulty:[lo,hi,signed]}}, ...],
      "equations": ["v = u + a*t", ...],        # parsed against declared symbols only
      "constraints": [{"var","op","value","difficulty"?}, ...],
      "root_policy": {"select", "strict_positive_find", "magnitude_cap", ...},
      "default_split": {"given": [...], "find": "..."},
      "golden_cases": [{"given":{...}, "find","difficulty","expected"}, ...],
    }

The declarative SUVAT here is proven byte-for-byte equivalent to the hand-coded
``templates.suvat.SUVAT`` (the ADR-007 §(f) v1 exit gate; see
``tests/test_declarative.py``).
"""

from __future__ import annotations

import sympy
from sympy.parsing.sympy_parser import parse_expr

from .base import Template, VarSpec

# Comparison operators for the constraint DSL. Each maps a declared
# ``(var, op, value)`` rule to a boolean predicate on an exact SymPy value.
_OPS = {
    ">": lambda x, c: x > c,
    ">=": lambda x, c: x >= c,
    "<": lambda x, c: x < c,
    "<=": lambda x, c: x <= c,
    "==": lambda x, c: sympy.Eq(x, c),
    "!=": lambda x, c: sympy.Ne(x, c),
    "abs<=": lambda x, c: abs(x) <= c,
    "abs<": lambda x, c: abs(x) < c,
}


def load_declarative(spec: dict) -> Template:
    """Parse a declarative template ``spec`` into a :class:`Template` (ADR-007)."""
    symtab = {
        var["name"]: sympy.Symbol(var["name"], real=True)
        for var in spec["variables"]
    }
    symbols = dict(symtab)
    variables = {
        symtab[var["name"]]: VarSpec(
            var["unit"], {d: tuple(r) for d, r in var["ranges"].items()}
        )
        for var in spec["variables"]
    }
    equations = [_parse_equation(text, symtab) for text in spec["equations"]]
    constraints = [_make_constraint(rule, symtab) for rule in spec["constraints"]]
    solvability = _make_solvability(equations, symtab)
    root_select = _make_root_select(spec["root_policy"], symtab)
    split = spec["default_split"]
    default_split = (
        tuple(symtab[g] for g in split["given"]),
        symtab[split["find"]],
    )
    return Template(
        topic=spec["topic"],
        symbols=symbols,
        variables=variables,
        equations=equations,
        solvability=solvability,
        constraints=constraints,
        root_select=root_select,
        default_split=default_split,
    )


# -- equation parsing (ADR-007 §a sandbox) -------------------------------------
def _parse_equation(text: str, symtab: dict) -> sympy.Eq:
    """Parse ``"lhs = rhs"`` into a :class:`sympy.Eq`, sandboxed to declared symbols.

    Names are resolved *only* against ``symtab``; any other identifier parses to a
    stray auto-symbol and is rejected (fail closed), as are function calls.
    :func:`parse_expr` evaluates against SymPy's own namespace (which has no
    ``os``/``open``/``__import__``), and the post-parse checks below enforce that
    nothing but the declared symbols, numbers, and arithmetic survives.
    """
    if text.count("=") != 1:
        raise ValueError(f"equation must contain exactly one '=': {text!r}")
    lhs_text, rhs_text = text.split("=")
    lhs = _parse_side(lhs_text, symtab, text)
    rhs = _parse_side(rhs_text, symtab, text)
    eq = sympy.Eq(lhs, rhs)
    declared = set(symtab.values())
    unknown = eq.free_symbols - declared
    if unknown:
        names = ", ".join(sorted(str(sym) for sym in unknown))
        raise ValueError(f"equation {text!r} names undeclared symbol(s): {names}")
    if eq.atoms(sympy.Function):
        raise ValueError(f"equation {text!r} uses a function call, which is not allowed")
    return eq


def _parse_side(text: str, symtab: dict, whole: str):
    try:
        return parse_expr(text, local_dict=symtab, evaluate=True)
    except (SyntaxError, TypeError, ValueError) as exc:
        raise ValueError(f"could not parse equation side {text!r} in {whole!r}: {exc}")


# -- solvability, derived from the equation set (ADR-007 §b) --------------------
def _make_solvability(equations: list, symtab: dict):
    """Return a ``(given, find) -> (ok, eq_or_reason)`` derived from ``equations``.

    Single-equation (v1) rule: the instance is solvable iff exactly one declared
    equation's free symbols equal ``given ∪ {find}`` (so every other symbol in it is
    a given and ``find`` appears). This reproduces the hand-coded SUVAT map and
    rejects both under- and over-determined splits.
    """
    all_syms = set(symtab.values())

    def solvability(given, find):
        given = set(given)
        if find in given:
            return (False, "find must be distinct from given")
        wanted = given | {find}
        if not wanted <= all_syms:
            return (False, "unknown variable for this template")
        for eq in equations:
            fs = eq.free_symbols
            if find in fs and fs == wanted:
                return (True, eq)
        return (False, "no single equation relates exactly given ∪ {find}")

    return solvability


# -- constraint DSL (ADR-007 §b) -----------------------------------------------
def _make_constraint(rule: dict, symtab: dict):
    """Compile one declarative constraint rule into a plausibility predicate.

    A rule is ``{"var", "op", "value"}`` with an optional ``"difficulty"`` scope.
    The predicate holds vacuously when the variable is absent from the instance or
    the difficulty does not match — matching how the hand-coded constraints guard
    on ``sym in values``.
    """
    sym = symtab[rule["var"]]
    op = rule["op"]
    value = sympy.nsimplify(rule["value"])
    only_difficulty = rule.get("difficulty")
    if op not in _OPS:
        raise ValueError(f"unknown constraint op {op!r}; expected one of {sorted(_OPS)}")
    test = _OPS[op]

    def predicate(values, difficulty):
        if only_difficulty is not None and difficulty != only_difficulty:
            return True
        if sym not in values:
            return True
        return bool(test(values[sym], value))

    predicate.__name__ = f"c_{rule['var']}_{op}_{rule['value']}"
    return predicate


# -- root selection, a named policy (ADR-007 §b) -------------------------------
def _make_root_select(policy: dict, symtab: dict):
    """Build the ``smallest_positive_then_nonneg`` root policy from declared rules.

    Reproduces the hand-coded SUVAT convention: discard non-physical roots, take the
    smallest strictly-positive real, else fall back to the smallest non-negative real
    for the variables that may legitimately be zero.
    """
    strict_positive = set(policy.get("strict_positive_find", []))
    magnitude_cap = policy.get("magnitude_cap", {})
    nonzero = set(policy.get("nonzero_find", []))
    easy_nonneg = set(policy.get("easy_nonneg_find", []))
    nonneg_fallback = set(policy.get("nonneg_fallback_find", []))

    def _is_physical(val, find, difficulty):
        name = find.name
        if name in strict_positive and not val.is_positive:
            return False
        if name in magnitude_cap and abs(val) > magnitude_cap[name]:
            return False
        if name in nonzero and val == 0:
            return False
        if difficulty == "easy" and name in easy_nonneg and val.is_negative:
            return False
        return True

    def root_select(values, find, difficulty):
        physical = []
        for val in values:
            val = sympy.nsimplify(val)
            if not (val.is_real and val.is_number):
                continue
            if not _is_physical(val, find, difficulty):
                continue
            physical.append(val)
        positive = [val for val in physical if val.is_positive]
        if positive:
            return min(positive)
        nonneg = [val for val in physical if val.is_nonnegative]
        if nonneg and find.name in nonneg_fallback:
            return min(nonneg)
        return None

    return root_select


# -- the SUVAT launch topic, expressed declaratively ---------------------------
# Byte-parity with templates.suvat.SUVAT (ADR-007 §f v1 exit gate).
SUVAT_SPEC = {
    "topic": "suvat",
    "variables": [
        {"name": "u", "unit": "m/s",
         "ranges": {"easy": [0, 20, False], "medium": [0, 40, False], "hard": [0, 40, False]}},
        {"name": "v", "unit": "m/s",
         "ranges": {"easy": [0, 30, False], "medium": [0, 60, False], "hard": [0, 60, False]}},
        {"name": "a", "unit": "m/s^2",
         "ranges": {"easy": [1, 10, False], "medium": [1, 15, True], "hard": [1, 15, True]}},
        {"name": "t", "unit": "s",
         "ranges": {"easy": [1, 10, False], "medium": [1, 20, False], "hard": [1, 20, False]}},
        {"name": "s", "unit": "m",
         "ranges": {"easy": [1, 50, False], "medium": [1, 150, False], "hard": [1, 150, False]}},
    ],
    "equations": [
        "v = u + a*t",
        "s = u*t + a*t**2/2",
        "v**2 = u**2 + 2*a*s",
        "s = (u + v)*t/2",
        "s = v*t - a*t**2/2",
    ],
    "constraints": [
        {"var": "t", "op": ">", "value": 0},
        {"var": "u", "op": "abs<=", "value": 100},
        {"var": "v", "op": "abs<=", "value": 100},
        {"var": "a", "op": "!=", "value": 0},
        {"var": "u", "op": ">=", "value": 0, "difficulty": "easy"},
        {"var": "v", "op": ">=", "value": 0, "difficulty": "easy"},
        {"var": "s", "op": ">=", "value": 0, "difficulty": "easy"},
    ],
    "root_policy": {
        "select": "smallest_positive_then_nonneg",
        "strict_positive_find": ["t"],
        "magnitude_cap": {"u": 100, "v": 100},
        "nonzero_find": ["a"],
        "easy_nonneg_find": ["u", "v", "s", "a"],
        "nonneg_fallback_find": ["u", "s", "v"],
    },
    "default_split": {"given": ["u", "a", "t"], "find": "v"},
    "golden_cases": [
        {"given": {"u": 0, "a": 2, "t": 5}, "find": "v", "difficulty": "easy",
         "expected": "10"},
    ],
}
