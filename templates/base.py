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

    # -- convenience accessors -------------------------------------------------

    def symbol(self, name_or_symbol):
        """Normalize a name or symbol to this template's canonical symbol."""
        if isinstance(name_or_symbol, sympy.Symbol):
            return self.symbols[name_or_symbol.name]
        return self.symbols[str(name_or_symbol)]

    def range_for(self, sym, difficulty):
        return self.variables[sym].ranges[difficulty]

    def unit_for(self, sym):
        return self.variables[sym].unit
