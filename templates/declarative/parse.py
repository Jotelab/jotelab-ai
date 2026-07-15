"""Safe declarative-doc -> Template parser (ADR-007 sub-decisions a, b; gate stage 1).

Equations arrive as *strings*. Before any evaluation, each string is checked against
a static allow-list on its parsed AST (only declared symbols, a small set of
functions, and arithmetic operators are permitted); anything else — attribute
access, calls to unknown names, dunders, subscripts, strings — is rejected. Only
then is the string handed to ``sympy.sympify``. This is deliberate: ``sympify``
itself will *execute* arbitrary Python (``__import__('os').system(...)`` runs), so it
is never fed an unvetted string. No user Python ever executes past the gate — this
is the DSL-with-static-validation pattern (ADR a).

``solvability`` is *auto-derived* (ADR b): for the v1 single-equation model, a split
``(given, find)`` is valid iff ``given ∪ {find}`` is related by the one equation that
excludes exactly one variable. The map is computed from the equation set, so an
author never writes solvability logic.
"""

from __future__ import annotations

import ast

import sympy

from engine.errors import TemplateValidationError
from templates.base import Template, VarSpec
from templates.declarative.constraints import compile_constraints
from templates.declarative.roots import make_root_select

# Callables an equation string may reference beyond the declared symbols.
_ALLOWED_FUNCS = {
    "Eq": sympy.Eq,
    "sqrt": sympy.sqrt,
    "Rational": sympy.Rational,
}

# AST node types permitted in an equation expression.
_ALLOWED_NODES = (
    ast.Expression, ast.Call, ast.Name, ast.Load, ast.Constant,
    ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.USub, ast.UAdd,
)


def _fail(reason):
    raise TemplateValidationError(1, "parse & sandbox", reason)


def _require(doc, key):
    if key not in doc:
        _fail(f"missing required key {key!r}")
    return doc[key]


def _build_symbols(variables):
    if not variables:
        _fail("template declares no variables")
    return {name: sympy.Symbol(name, real=True) for name in variables}


def _check_ast_safe(text, allowed_names):
    """Static allow-list check on the equation string's AST, before any eval."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        _fail(f"cannot parse equation {text!r}: {exc}")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            _fail(f"equation {text!r} uses a disallowed construct "
                  f"({type(node).__name__})")
        if isinstance(node, ast.Name):
            if "__" in node.id:
                _fail(f"equation {text!r} references a forbidden name {node.id!r}")
            if node.id not in allowed_names:
                _fail(f"equation {text!r} references undeclared name {node.id!r}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
                _fail(f"equation {text!r} calls a disallowed function")
            if node.keywords:
                _fail(f"equation {text!r} uses keyword arguments")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            _fail(f"equation {text!r} contains a non-numeric constant "
                  f"{node.value!r}")


def _sympify_equation(text, namespace):
    allowed_names = set(namespace)  # declared symbol names + allowed func names
    _check_ast_safe(text, allowed_names)
    try:
        expr = sympy.sympify(text, locals=namespace, evaluate=True)
    except (sympy.SympifyError, SyntaxError, TypeError, AttributeError) as exc:
        _fail(f"cannot parse equation {text!r}: {exc}")
    if not isinstance(expr, sympy.Equality):
        _fail(f"equation {text!r} is not an Eq(...) relation")
    return expr


def _var_specs(variables):
    specs = {}
    for name, spec in variables.items():
        if "unit" not in spec or "ranges" not in spec:
            _fail(f"variable {name!r} needs 'unit' and 'ranges'")
        ranges = {band: tuple(triple) for band, triple in spec["ranges"].items()}
        specs[name] = VarSpec(unit=spec["unit"], ranges=ranges)
    return specs


def _make_solvability(equations, all_syms):
    """Auto-derive the single-equation solvability map from the equation set.

    A split ``(given, find)`` is solvable iff some equation's variable set is
    *exactly* ``given ∪ {find}`` — i.e. the one relation that binds precisely those
    variables (for SUVAT, the equation that excludes the single unused variable).
    This is variable-count agnostic and matches SUVAT's own solvability exactly.
    """
    def solvability(given, find):
        given = set(given)
        if find in given:
            return (False, "find must be distinct from the given variables")
        used = given | {find}
        if not used <= all_syms:
            return (False, "unknown variable for this template")
        for eq in equations:
            fs = eq.free_symbols & all_syms
            if fs == used:
                return (True, eq)
        return (False, "no single equation relates exactly given ∪ {find}")

    return solvability


def trust_state_of(doc):
    """The template's provenance trust state (ADR-007 e); a carried field only."""
    return doc.get("trust_state", "unverified")


def parse_template(doc) -> Template:
    """Parse a declarative JSON doc into a ``templates.base.Template`` (stage 1)."""
    topic = _require(doc, "topic")
    variables = _require(doc, "variables")
    equations_raw = _require(doc, "equations")
    root_policy = _require(doc, "root_policy")
    constraints_raw = doc.get("constraints", [])
    split = _require(doc, "default_split")

    symbols = _build_symbols(variables)
    all_syms = set(symbols.values())
    namespace = dict(symbols)
    namespace.update(_ALLOWED_FUNCS)

    equations = [_sympify_equation(text, namespace) for text in equations_raw]
    var_specs = {symbols[n]: spec for n, spec in _var_specs(variables).items()}

    try:
        constraints = compile_constraints(constraints_raw, symbols)
        root_select = make_root_select(root_policy, constraints)
    except ValueError as exc:
        _fail(str(exc))

    if "given" not in split or "find" not in split:
        _fail("default_split needs 'given' and 'find'")
    try:
        given = tuple(symbols[n] for n in split["given"])
        find = symbols[split["find"]]
    except KeyError as exc:
        _fail(f"default_split references undeclared variable {exc}")

    return Template(
        topic=topic,
        symbols=symbols,
        variables=var_specs,
        equations=equations,
        solvability=_make_solvability(equations, all_syms),
        constraints=constraints.loop_predicates,
        root_select=root_select,
        default_split=(given, find),
        signed_answer=bool(doc.get("signed_answer", False)),
    )
