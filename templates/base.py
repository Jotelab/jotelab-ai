"""Topic-template data structures (build guide §6, spec §4).

A topic is modeled once as a parameterized :class:`Template`, then reused for
every generated instance. A template declares four things (spec §4):

* **Variables** — symbols, units, and per-difficulty sampling ranges.
* **Equation set** — the SymPy relations binding the variables.
* **Solvability map** — which ``find`` targets are derivable from which
  ``given`` subsets.
* **Constraints** — physical plausibility predicates plus the topic's
  root-selection convention.

This template-per-topic structure is what lets the engine grow strand by strand
without re-architecting (spec §4, build guide §5). Each new template is a
self-contained module under ``templates/``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable

import sympy


@dataclass(frozen=True)
class VarSpec:
    """A single physical variable: its unit and per-difficulty sampling ranges.

    ``ranges`` maps a difficulty name (``"easy"``/``"medium"``/``"hard"``) to a
    ``(lo, hi, signed)`` tuple. ``signed`` allows a randomly negative draw
    (used e.g. for acceleration at medium+). For variables that are normally
    *derived* (solved, not sampled) the range still doubles as a plausibility
    band on the solved value (build guide §8).
    """

    unit: str
    ranges: dict  # difficulty -> (lo, hi, signed)


@dataclass(frozen=True)
class Template:
    """A self-contained topic template (build guide §6)."""

    topic: str
    symbols: dict  # name -> sympy.Symbol
    variables: dict  # sympy.Symbol -> VarSpec
    equations: list  # list[sympy.Eq]
    solvability: Callable  # (given, find) -> (ok: bool, eq_or_reason)
    constraints: list  # list[predicate(values: dict, difficulty: str) -> bool]
    root_select: Callable  # (values: list, find, difficulty) -> chosen value | None
    default_split: tuple  # (given_symbols, find_symbol) for Basic mode
    signed_answer: bool = False  # vector/direction topics: allow a negative answer
    # values -> JSON-able diagram payload ("diagram" key). Supersedes the former
    # graph_spec hook: the engine owns every glyph in a figure (spec 2026-07-27).
    diagram_spec: Callable = None
    auxiliaries: dict = None  # system templates: Symbol -> unit str (spec 2026-07-27)

    # -- convenience accessors -------------------------------------------------

    def symbol(self, name_or_symbol):
        """Normalize a name or symbol to this template's canonical symbol."""
        if isinstance(name_or_symbol, sympy.Symbol):
            return self.symbols[name_or_symbol.name]
        return self.symbols[str(name_or_symbol)]

    def range_for(self, sym, difficulty):
        return self.variables[sym].ranges[difficulty]

    def unit_for(self, sym):
        if self.auxiliaries and sym in self.auxiliaries:
            return self.auxiliaries[sym]
        return self.variables[sym].unit

    def valid_splits(self):
        """Every ``(given, find)`` split this topic can solve.

        Enumerated from the template's own :attr:`solvability` map, so it stays
        correct per topic (e.g. SUVAT v1 yields only the 3-given / 1-find splits).
        Used by the CLI to pick a fresh random problem when no split is requested.
        """
        syms = list(self.symbols.values())
        splits = []
        for size in range(1, len(syms)):
            for given in itertools.combinations(syms, size):
                for find in syms:
                    if find in given:
                        continue
                    ok, _ = self.solvability(given, find)
                    if ok:
                        splits.append((given, find))
        return splits


# -- shared root-selection primitives ------------------------------------------
# Every code template's `root_select` composes the same three moves: normalize
# the solver's candidates to exact real numbers, then pick by the topic's sign
# convention. (The declarative path has its own copies in
# ``templates/declarative/roots.py``, kept separate on purpose — that module is
# part of the sandboxed JSON contract.)

def real_candidates(values):
    """Normalize solver output to exact real numeric candidates (nsimplify)."""
    real = []
    for val in values:
        val = sympy.nsimplify(val)
        if val.is_real and val.is_number:
            real.append(val)
    return real


def smallest_positive(reals):
    """Smallest strictly-positive candidate, or ``None`` (a failed roll)."""
    pos = [x for x in reals if x.is_positive]
    return min(pos) if pos else None


def smallest_nonnegative(reals):
    """Smallest non-negative candidate, or ``None`` (a failed roll)."""
    nonneg = [x for x in reals if x.is_nonnegative]
    return min(nonneg) if nonneg else None


def signed_smallest(reals):
    """Signed pick: smallest magnitude, negative before positive on a tie."""
    return min(reals, key=lambda x: (abs(float(x)), float(x)))
