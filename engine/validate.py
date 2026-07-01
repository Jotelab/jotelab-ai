"""The automated validation gate for user-authored templates (ADR-007 §c).

A declarative template (see :mod:`templates.declarative`) is admitted to the
registry only after passing every stage of this gate, in order:

1. **parse / sandbox** — the spec parses into a :class:`Template`; equations name
   only declared symbols and no function calls (:func:`load_declarative`).
2. **dimensional homogeneity** — every equation is dimensionally consistent under
   the declared units. A *necessary* condition for a physically meaningful
   equation; rejects e.g. ``v = u + a*t**2`` automatically. It cannot catch a
   dimensionally-valid-but-wrong law (a dropped ½) — that is stage 4's job.
3. **solvability derivation** — the derived solvability map admits at least one
   split, and the template's own default split is solvable.
4. **golden-case replay** — every author-supplied worked example is reproduced
   *exactly* by the engine (ADR-005 exact contract). This is the only stage that
   can catch a self-consistent wrong equation, and only if the author's expected
   answer is itself correct — the irreducible residue named in ADR-007 §d.

The gate never raises on a bad spec: it catches the failure and reports which
stage rejected it, short-circuiting after the first failure.
"""

from __future__ import annotations

from dataclasses import dataclass

import sympy

from engine import contract
from engine.loop import generate
from templates.declarative import load_declarative

# Base-dimension symbols for the dimensional check. Extend as new strands add
# units (mass ``kg`` -> M, charge, etc.); high-school SUVAT needs only L and T.
_BASE_DIMENSION = {
    "m": sympy.Symbol("L"),   # length
    "s": sympy.Symbol("T"),   # time
}


@dataclass(frozen=True)
class StageResult:
    """The outcome of one validation stage."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ValidationReport:
    """The ordered results of running the gate on a spec."""

    stages: list

    @property
    def ok(self) -> bool:
        return all(stage.passed for stage in self.stages)

    def failed_stage(self):
        """The first failing stage, or ``None`` if every stage passed."""
        for stage in self.stages:
            if not stage.passed:
                return stage
        return None


def validate_template(spec: dict) -> ValidationReport:
    """Run the ADR-007 validation gate over a declarative template ``spec``."""
    stages = []

    # -- stage 1: parse / sandbox ---------------------------------------------
    try:
        template = load_declarative(spec)
    except (ValueError, KeyError, TypeError) as exc:
        stages.append(StageResult("parse", False, str(exc)))
        return ValidationReport(stages)
    stages.append(StageResult("parse", True, "spec parses; symbols/functions sandboxed"))

    # -- stage 2: dimensional homogeneity -------------------------------------
    ok, detail = _check_dimensions(spec, template)
    stages.append(StageResult("dimensional", ok, detail))
    if not ok:
        return ValidationReport(stages)

    # -- stage 3: solvability derivation --------------------------------------
    ok, detail = _check_solvability(template)
    stages.append(StageResult("solvability", ok, detail))
    if not ok:
        return ValidationReport(stages)

    # -- stage 4: golden-case replay ------------------------------------------
    ok, detail = _check_golden(spec, template)
    stages.append(StageResult("golden", ok, detail))
    return ValidationReport(stages)


# -- stage 2 helpers -----------------------------------------------------------
def _unit_dimension(unit: str):
    """Map a unit string (``"m/s^2"``) to a dimension monomial in L, T.

    Grammar: factors joined by ``*`` in a numerator, optional ``/`` denominators,
    each factor ``base`` or ``base^exp``. Unknown base units raise.
    """
    dimension = sympy.Integer(1)
    for i, part in enumerate(unit.split("/")):
        sign = 1 if i == 0 else -1
        for factor in part.split("*"):
            factor = factor.strip()
            if not factor:
                continue
            if "^" in factor:
                base, exp_text = factor.split("^")
                exp = int(exp_text)
            else:
                base, exp = factor, 1
            base = base.strip()
            if base not in _BASE_DIMENSION:
                raise ValueError(f"unknown base unit {base!r} in {unit!r}")
            dimension *= _BASE_DIMENSION[base] ** (sign * exp)
    return dimension


def _check_dimensions(spec, template):
    """(Stage 2) Every equation's additive terms share one dimension."""
    try:
        dim_map = {
            template.symbol(var["name"]): _unit_dimension(var["unit"])
            for var in spec["variables"]
        }
    except ValueError as exc:
        return (False, str(exc))

    for eq in template.equations:
        terms = list(sympy.Add.make_args(sympy.expand(eq.lhs)))
        terms += list(sympy.Add.make_args(sympy.expand(eq.rhs)))
        dims = []
        for term in terms:
            d = sympy.simplify(term.subs(dim_map))
            if d == 0:
                continue
            dims.append((term, d))
        if not dims:
            continue
        ref = dims[0][1]
        for term, d in dims[1:]:
            ratio = sympy.simplify(d / ref)
            if not ratio.is_number:
                return (
                    False,
                    f"equation {eq} is dimensionally inconsistent: term {term} "
                    f"has dimension {d}, expected {ref}",
                )
    return (True, "all equations dimensionally homogeneous")


# -- stage 3 helper ------------------------------------------------------------
def _check_solvability(template):
    """(Stage 3) At least one split solvable, and the default split solvable."""
    splits = template.valid_splits()
    if not splits:
        return (False, "no solvable (given, find) split derivable from the equations")
    given, find = template.default_split
    ok, reason = template.solvability(given, find)
    if not ok:
        return (False, f"default split is not solvable: {reason}")
    return (True, f"{len(splits)} solvable split(s); default split solvable")


# -- stage 4 helper ------------------------------------------------------------
def _check_golden(spec, template):
    """(Stage 4) Every golden worked example is reproduced exactly."""
    cases = spec.get("golden_cases", [])
    if not cases:
        return (False, "no golden cases supplied; at least one is required")
    for case in cases:
        given = tuple(template.symbol(name) for name in case["given"])
        find = template.symbol(case["find"])
        conditions = {template.symbol(n): val for n, val in case["given"].items()}
        try:
            data = generate(
                template=template, given=given, find=find, conditions=conditions,
                difficulty=case.get("difficulty", "easy"), seed=0,
            )
        except Exception as exc:  # a failed golden case is a validation failure, not a crash
            return (False, f"golden case (find {case['find']}) did not generate: {exc}")
        got = data["final_answer"]["exact"]
        expected = contract.to_exact(contract.exact(str(case["expected"])))
        if got != expected:
            return (
                False,
                f"golden case (find {case['find']}): engine got {got}, "
                f"author expected {expected}",
            )
    return (True, f"{len(cases)} golden case(s) reproduced exactly")
