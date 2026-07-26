"""Dimensional-homogeneity checker (ADR-007 gate stage 2).

Maps each variable's declared unit string to a SymPy dimension and asserts every
equation is dimensionally homogeneous under the SI dimension system. Homogeneity is
a *necessary* condition for a physically meaningful equation: it catches
``v = u + a*t**2`` (an inhomogeneous sum raises) but cannot catch a dropped ``1/2``
(dimensionally valid).
"""

from __future__ import annotations

from sympy.physics.units import Dimension, length, time
from sympy.physics.units.systems.si import dimsys_SI

from engine.errors import TemplateValidationError

# Base high-school unit tokens -> SI dimension. Extend as topics need.
_BASE_UNITS = {
    "m": length,
    "s": time,
    "1": Dimension(1),
}


def _token_dim(token):
    token = token.strip().replace("**", "^")
    if "^" in token:
        base, _, exp = token.partition("^")
        return _token_dim(base) ** int(exp)
    if token not in _BASE_UNITS:
        raise TemplateValidationError(
            2, "dimensional homogeneity", f"unknown unit token {token!r}")
    return _BASE_UNITS[token]


def _mul_dims(group):
    dim = None
    for factor in group.split("*"):
        d = _token_dim(factor)
        dim = d if dim is None else dim * d
    return dim


def dimension_of(unit_str):
    """Parse a unit string like ``m/s^2`` into a SymPy dimension expression."""
    parts = unit_str.split("/")
    dim = _mul_dims(parts[0])
    for p in parts[1:]:
        dim = dim / _mul_dims(p)
    return dim


def _subs_dims(expr, sym_dim):
    """Replace each symbol in ``expr`` with its declared dimension."""
    return expr.xreplace({sym: sym_dim[sym] for sym in expr.free_symbols if sym in sym_dim})


def check_homogeneous(template):
    """Raise ``TemplateValidationError(2, ...)`` if any equation is inhomogeneous."""
    sym_dim = {sym: dimension_of(spec.unit) for sym, spec in template.variables.items()}
    for sym, unit in (template.auxiliaries or {}).items():
        sym_dim[sym] = dimension_of(unit)

    for eq in template.equations:
        lhs = _subs_dims(eq.lhs, sym_dim)
        rhs = _subs_dims(eq.rhs, sym_dim)
        try:
            lhs_d = dimsys_SI.get_dimensional_dependencies(lhs)
            rhs_d = dimsys_SI.get_dimensional_dependencies(rhs)
        except TypeError as exc:
            # "Only equivalent dimensions can be added or subtracted" — an
            # inhomogeneous sum inside one side of the equation.
            raise TemplateValidationError(
                2, "dimensional homogeneity",
                f"equation {eq} has an inhomogeneous term: {exc}")
        if lhs_d != rhs_d:
            raise TemplateValidationError(
                2, "dimensional homogeneity",
                f"equation {eq} is dimensionally inhomogeneous: {lhs_d} != {rhs_d}")
