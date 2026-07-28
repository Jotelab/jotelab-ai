"""SUVAT template + worked-example tests (build guide §11; spec §7, §8)."""

import sympy
import pytest

from engine.errors import UnsolvableError
from engine.loop import generate, _solve
from engine.registry import load_template
from templates.suvat import a, s, t, u, v, EQUATION_BY_EXCLUDED, solvability


def test_load_template_populated():
    """Gate 1: load_template('suvat') returns a populated Template."""
    tpl = load_template("suvat")
    assert tpl.topic == "suvat"
    assert len(tpl.equations) == 5
    assert set(tpl.variables) == {u, v, a, t, s}


def test_solvability_selects_correct_equation():
    """Gate 2: solvability returns the right equation for valid splits."""
    ok, eq = solvability({u, a, t}, v)
    assert ok and eq is EQUATION_BY_EXCLUDED[s]   # unused = s -> E1
    ok, eq = solvability({u, v, a}, s)
    assert ok and eq is EQUATION_BY_EXCLUDED[t]   # unused = t -> E3
    # find=a, given={u,v,t}: unused = s, so the equation excluding s (E1) is used
    # — it is the one that still *contains* a and can be solved for it.
    ok, eq = solvability({u, v, t}, a)
    assert ok and eq is EQUATION_BY_EXCLUDED[s]   # unused = s -> E1


@pytest.mark.parametrize(
    "given, find",
    [
        ({u, a}, v),          # too few givens
        ({u, a, t, s}, v),    # too many givens
        ({u, a, t}, u),       # find in given
    ],
)
def test_solvability_rejects_invalid(given, find):
    ok, reason = solvability(given, find)
    assert not ok and isinstance(reason, str)


def test_solve_worked_example_exact():
    """Spec §8: given {u,a,t}=0,2,5, find v -> v = u + a t = 10 m/s, exact."""
    tpl = load_template("suvat")
    eq = EQUATION_BY_EXCLUDED[s]  # E1
    inputs = {u: sympy.Integer(0), a: sympy.Integer(2), t: sympy.Integer(5)}
    value, sym_expr, aux_values = _solve(eq, v, inputs, tpl, "easy")
    assert value == 10
    assert value.is_Integer
    assert sympy.simplify(sym_expr - (u + a * t)) == 0
    assert aux_values == {}  # single-equation path emits empty dict


def test_worked_example_sympy_data_shape():
    """Spec §7: the worked example emits the locked sympy_data contract."""
    # Pin inputs via conditions so the example is exact regardless of the RNG.
    data = generate(
        "suvat", given=(u, a, t), find=v, difficulty="easy",
        conditions={u: 0, a: 2, t: 5}, seed=80421,
    )
    assert data["topic"] == "suvat"
    # find carries both the display value and the authoritative exact string (ADR-005).
    assert data["find"] == {"symbol": "v", "value": 10, "exact": "10", "unit": "m/s"}
    given = {g["symbol"]: g for g in data["given"]}
    assert given["u"]["value"] == 0 and given["u"]["exact"] == "0" and given["u"]["unit"] == "m/s"
    assert given["a"]["value"] == 2 and given["a"]["exact"] == "2" and given["a"]["unit"] == "m/s^2"
    assert given["t"]["value"] == 5 and given["t"]["exact"] == "5" and given["t"]["unit"] == "s"
    assert data["final_answer"]["value"] == 10
    assert data["final_answer"]["exact"] == "10"
    assert data["final_answer"]["unit"] == "m/s"
    assert data["policy_applied"] == "easy"
    assert data["plausible"] is True
    assert len(data["steps"]) == 1
    # expr_latex shows find = <symbolic solution> (SymPy's canonical term order).
    assert data["steps"][0]["expr_latex"] == f"v = {sympy.latex(u + a * t)}"
    # the substituted step plugs the sampled values in, unevaluated.
    assert "5" in data["steps"][0]["substituted_latex"]


def test_unsolvable_raises_before_loop():
    """Spec §3, §9: an unsolvable given->find is rejected at validation."""
    with pytest.raises(UnsolvableError):
        generate("suvat", given=(u, a), find=v)  # only 2 givens


def test_root_selection_smallest_positive():
    """Build guide §3, §8: quadratic-in-t returns the smallest strictly-positive root.

    s = u t + a t^2/2 with u=0, a=2, s=9 -> t^2 = 9 -> t = ±3; pick t = 3.
    """
    tpl = load_template("suvat")
    eq = EQUATION_BY_EXCLUDED[v]  # E2, excludes v -> solvable for t given {u,a,s}
    inputs = {u: sympy.Integer(0), a: sympy.Integer(2), s: sympy.Integer(9)}
    value, _, aux_values = _solve(eq, t, inputs, tpl, "easy")
    assert value == 3
    assert aux_values == {}  # single-equation path emits empty dict


def test_diagram_is_variable_consistent_and_hides_the_answer():
    """The figure draws the split's own quantities, and never the answer."""
    data = generate("suvat", given=("u", "a", "t"), find="v",
                    difficulty="easy", seed=7)
    seg = data["diagram"]["segments"][0]
    assert data["diagram"]["kind"] == "motion-1d"
    assert data["diagram"]["orientation"] == "horizontal"
    assert seg["velocity_in"]["role"] == "given"
    assert seg["velocity_out"] == {"symbol": "v", "label": "v", "role": "find"}
    assert "span" not in seg          # s is not in this split
    assert seg["duration"]["unit"] == "s"
