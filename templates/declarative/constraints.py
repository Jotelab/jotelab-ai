"""Declarative constraint DSL -> predicates (ADR-007 sub-decision b).

A constraint is ``{"var","op","value","difficulty"?,"scope"?}``. It compiles to
two things the engine already understands:

* **loop predicates** — ``predicate(values, difficulty) -> bool`` callables, the
  exact shape ``Template.constraints`` expects (constraints with scope
  ``loop``/``both``), evaluated on the full ``values`` dict.
* **is_physical** — a per-``find`` filter ``(value, find_sym, difficulty) -> bool``
  used by the root policy to drop non-physical candidate roots (constraints with
  scope ``root``/``both``). This reproduces ``templates/suvat.py::_is_physical_value``.

The ``scope`` flag captures the one asymmetry between SUVAT's ``_is_physical_value``
and its ``CONSTRAINTS``: the easy-band negativity rejection for ``a`` exists only in
the root filter, so it is authored ``scope: "root"``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import sympy

# op name -> function(lhs_value, threshold) -> bool. Values are exact SymPy numbers.
_OPS = {
    ">":     lambda x, c: x > c,
    ">=":    lambda x, c: x >= c,
    "<":     lambda x, c: x < c,
    "<=":    lambda x, c: x <= c,
    "==":    lambda x, c: x == c,
    "!=":    lambda x, c: x != c,
    "abs<=": lambda x, c: abs(x) <= c,
    "abs<":  lambda x, c: abs(x) < c,
    "abs>=": lambda x, c: abs(x) >= c,
    "abs>":  lambda x, c: abs(x) > c,
}


def _apply(op, x, c):
    x = sympy.nsimplify(x)
    return bool(_OPS[op](x, sympy.nsimplify(c)))


@dataclass(frozen=True)
class _Rule:
    var: str
    op: str
    value: object
    difficulty: object  # str | None
    scope: str

    def active(self, difficulty):
        return self.difficulty is None or self.difficulty == difficulty

    def holds(self, value):
        return _apply(self.op, value, self.value)


@dataclass(frozen=True)
class CompiledConstraints:
    loop_predicates: list  # list[Callable[[dict, str], bool]]
    _rules: list  # list[_Rule] (all rules, for is_physical)

    def is_physical(self, value, find_sym, difficulty) -> bool:
        """Per-``find`` physical admissibility of one candidate root value."""
        name = find_sym.name
        for r in self._rules:
            if r.scope in ("root", "both") and r.var == name and r.active(difficulty):
                if not r.holds(value):
                    return False
        return True


def _make_loop_predicate(rule: _Rule, symbols) -> Callable:
    sym = symbols[rule.var]

    def predicate(values, difficulty, _rule=rule, _sym=sym):
        if not _rule.active(difficulty):
            return True
        if _sym not in values:
            return True
        return _rule.holds(values[_sym])

    predicate.__name__ = f"c_{rule.var}_{rule.op}".replace("<", "le").replace(">", "ge")
    return predicate


def compile_constraints(specs, symbols) -> CompiledConstraints:
    """Compile DSL constraint dicts into loop predicates + an is_physical filter."""
    rules = []
    for spec in specs:
        if spec["op"] not in _OPS:
            raise ValueError(f"unknown constraint op {spec['op']!r}")
        if spec["var"] not in symbols:
            raise ValueError(f"constraint references unknown var {spec['var']!r}")
        rules.append(
            _Rule(
                var=spec["var"],
                op=spec["op"],
                value=spec["value"],
                difficulty=spec.get("difficulty"),
                scope=spec.get("scope", "both"),
            )
        )
    loop = [
        _make_loop_predicate(r, symbols) for r in rules if r.scope in ("loop", "both")
    ]
    return CompiledConstraints(loop_predicates=loop, _rules=rules)
