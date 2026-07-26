"""The five-stage template validation gate (ADR-007 sub-decision c).

Runs a candidate declarative doc through five stages and admits it *only* if every
stage passes. Stages 3–5 reuse the engine's own machinery (auto-derived splits, the
bounded loop, the Data-Fidelity oracle) — wiring, not a new solver.

    1 Parse & sandbox         parse_template (safe AST allow-list + sympify)
    2 Dimensional homogeneity check_homogeneous (sympy.physics.units)
    3 Solvability derivation  default_split must be a valid derived split
    4 Golden-case replay      each worked example reproduces exactly (ADR-005)
    5 Convergence + fidelity  generate N/band via the real loop; verify_generic 100%

The gate never *raises* for a validation failure — it returns a :class:`Report` whose
``passed`` flag and per-stage results say exactly what failed and why. The thin
wrapper :func:`register_declarative` turns a failure into a typed
:class:`~engine.errors.TemplateValidationError` and registers on all-pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine import registry
from engine.contract import exact
from engine.errors import EngineError, TemplateValidationError
from engine.loop import generate
from harness.verify import FidelityError, verify_generic
from templates.declarative.parse import parse_template
from templates.declarative.units import check_homogeneous

_BANDS = ("easy", "medium", "hard")


@dataclass
class StageResult:
    number: int
    name: str
    passed: bool
    reason: str = ""


@dataclass
class Report:
    stages: list = field(default_factory=list)
    template: object = None

    @property
    def passed(self):
        return bool(self.stages) and all(s.passed for s in self.stages)

    def _add(self, number, name, passed, reason=""):
        self.stages.append(StageResult(number, name, passed, reason))
        return passed


def validate_template(doc, n_smoke=6) -> Report:
    """Run the five-stage gate, stopping at the first failure.

    Never raises for a validation failure — inspect ``Report.passed`` /
    ``Report.stages``. ``n_smoke`` is the number of instances generated per
    (split, difficulty) in stage 5.
    """
    report = Report()

    # Stage 1 — parse & sandbox
    try:
        template = parse_template(doc)
    except TemplateValidationError as exc:
        report._add(1, "parse & sandbox", False, exc.reason)
        return report
    report._add(1, "parse & sandbox", True)

    # Stage 2 — dimensional homogeneity
    try:
        check_homogeneous(template)
    except TemplateValidationError as exc:
        report._add(2, "dimensional homogeneity", False, exc.reason)
        return report
    report._add(2, "dimensional homogeneity", True)

    # Stage 3 — solvability derivation (the default split must be derivable)
    given, find = template.default_split
    ok, info = template.solvability(given, find)
    if not ok:
        report._add(3, "solvability derivation", False,
                    f"default_split not derivable: {info}")
        return report
    report._add(3, "solvability derivation", True)

    # Stage 4 — golden-case replay
    reason = _replay_golden(template, doc.get("golden_cases", []))
    if reason is not None:
        report._add(4, "golden-case replay", False, reason)
        return report
    report._add(4, "golden-case replay", True)

    # Stage 5 — convergence + fidelity smoke test
    reason = _smoke(template, n_smoke)
    if reason is not None:
        report._add(5, "convergence + fidelity", False, reason)
        return report
    report._add(5, "convergence + fidelity", True)

    report.template = template
    return report


def _replay_golden(template, cases):
    if not cases:
        return "no golden cases supplied (stage 4 requires >= 1)"
    for i, case in enumerate(cases):
        # exact() accepts ints and exact strings like "7/2", and fails closed
        # on anything non-rational (ADR-005) — int() broke fractional goldens.
        conditions = {k: exact(v) for k, v in case["given"].items()}
        given = tuple(case["given"].keys())
        difficulty = case.get("difficulty", "easy")
        try:
            with registry.temporary(template):
                data = generate(template.topic, given=given, find=case["find"],
                                conditions=conditions, difficulty=difficulty, seed=0)
        except EngineError as exc:
            return f"golden case {i} did not generate: {exc}"
        got = data["find"]["exact"]
        want = str(exact(case["expected"]))
        if got != want:
            return f"golden case {i}: expected {want}, engine produced {got}"
    return None


def _smoke(template, n_smoke):
    """Generate ``n_smoke`` instances per band on the default split and verify each.

    A smoke test (ADR-007 stage 5: "generates N instances across easy/medium/hard")
    proving the re-roll loop converges and the Data-Fidelity oracle passes on the
    primary path — not an exhaustive sweep of every split (that is what the
    ``suvat`` parity test does, and it would make a live gate cost minutes).
    """
    given, find = template.default_split
    given_names = [s.name for s in given]
    with registry.temporary(template):
        for band in _BANDS:
            for k in range(n_smoke):
                try:
                    data = generate(template.topic, given=given_names, find=find.name,
                                    difficulty=band, seed=1000 + k)
                except EngineError as exc:
                    return f"did not converge ({band}): {exc}"
                try:
                    verify_generic(data, template, difficulty=band)
                except FidelityError as exc:
                    return f"fidelity failure ({band}): {exc}"
    return None


def register_declarative(doc):
    """Validate ``doc`` through the gate; register + return the Template on all-pass.

    Raises :class:`~engine.errors.TemplateValidationError` naming the first failing
    stage otherwise; the registry is left untouched on any failure.
    """
    report = validate_template(doc)
    if not report.passed:
        failing = next(s for s in report.stages if not s.passed)
        raise TemplateValidationError(failing.number, failing.name, failing.reason)
    registry.register(report.template)
    return report.template
