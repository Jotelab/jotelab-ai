"""The shared diagram builders. The answer-hiding rule (find elements carry no
value/exact) is enforced in DiagramContext.label, so every topic inherits it."""

import sympy

from templates.diagrams import DiagramContext
from templates.suvat import SUVAT


def _ctx(find_name="v"):
    u, a, t, v = (SUVAT.symbol(n) for n in ("u", "a", "t", "v"))
    values = {u: sympy.Integer(5), a: sympy.Integer(2),
              t: sympy.Integer(3), v: sympy.Integer(11)}
    return DiagramContext(SUVAT, values, given={u, a, t},
                          find=SUVAT.symbol(find_name))


def test_given_label_carries_both_numeric_forms_and_unit():
    label = _ctx().label(SUVAT.symbol("u"))
    assert label == {"symbol": "u", "label": "v_0", "role": "given",
                     "value": 5, "exact": "5", "unit": "m/s"}


def test_find_label_omits_value_and_exact():
    """The load-bearing invariant: the answer is never on the wire."""
    label = _ctx().label(SUVAT.symbol("v"))
    assert label == {"symbol": "v", "label": "v", "role": "find"}
    assert "value" not in label and "exact" not in label


def test_non_given_non_find_symbol_is_derived():
    """A value the engine computed that is not the answer is safe to show."""
    ctx = _ctx(find_name="s")
    ctx.values[SUVAT.symbol("v")] = sympy.Integer(11)
    label = ctx.label(SUVAT.symbol("v"))
    assert label["role"] == "derived"
    assert label["exact"] == "11"


def test_symbol_absent_from_the_instance_yields_none():
    """Callers drop the element entirely rather than drawing an empty arrow."""
    ctx = _ctx()
    del ctx.values[SUVAT.symbol("a")]
    assert ctx.label(SUVAT.symbol("a")) is None


def test_exact_form_survives_a_non_terminating_rational():
    """ADR-005: exact is authoritative; value may be a lossy round."""
    ctx = _ctx()
    ctx.values[SUVAT.symbol("u")] = sympy.Rational(1, 3)
    label = ctx.label(SUVAT.symbol("u"))
    assert label["exact"] == "1/3"
    assert label["value"] == 0.333333
