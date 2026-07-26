# System Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Declarative templates may declare a coupled equation system with internal (auxiliary) unknowns, solved jointly — proof case `pursuit.json`, the bus-chase problem.

**Architecture:** A new `templates/declarative/system.py` derives closed-form solution branches once at parse time (`sympy.solve` with givens symbolic); the loop evaluates cached branches and picks roots with the existing named policies; the contract gains an optional `auxiliary` array; the harness verifies system instances by asserting every equation holds at the emitted values plus an independent whole-system recompute. The `auxiliary` JSON block is the discriminator — absent it, every existing code path is byte-identical.

**Tech Stack:** Python 3.13, SymPy, pytest.

**Spec:** `docs/superpowers/specs/2026-07-27-system-templates-design.md` (committed on this branch).

## Global Constraints

- Templates without an `auxiliary` block must behave **byte-identically** to today (all 182 existing tests green, suvat byte-parity untouched, gate PASS on all existing JSON templates).
- **No unused variables** in system templates: a split is valid only when `given == all variables − {find}`; auxiliaries are always solved.
- Auxiliary values are evaluated from the **same solution branch** as the chosen find value — branches never mix.
- Every auxiliary value must be an exact `Rational`; a non-rational auxiliary is a failed roll (re-roll), never emitted.
- Root selection reuses the existing named policies unchanged (`smallest_positive_physical` picks pursuit's t=3 over t=4).
- Golden-case givens must accept exact strings (e.g. `"7/2"`) — the gate's current `int(v)` parse is a bug this plan fixes via `exact(v)`.
- Commands: `PY=/home/thanakorn/Projects/Jotelab-Project/jotelab-ai/jotelab-ai/.venv/bin/python`, cwd = `/home/thanakorn/Projects/Jotelab-Project/jotelab-ai/jotelab-ai/.claude/worktrees/system-templates`, run tests as `PYTHONPATH=. $PY -m pytest ...` (the worktree has no `.venv`).
- Commit trailer for every commit:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01GjymN4t2uXJZktgUSb3NBZ`

---

### Task 1: Branch derivation module + Template.auxiliaries

**Files:**
- Create: `templates/declarative/system.py`
- Modify: `templates/base.py:42-69` (Template dataclass + `unit_for`)
- Test: `tests/test_system_templates.py` (create)

**Interfaces:**
- Consumes: nothing new (pure SymPy + the existing `Template` dataclass).
- Produces (later tasks rely on these exact names):
  - `templates/declarative/system.py`: `Branch(find_expr, aux_exprs)` (frozen dataclass; `aux_exprs: dict[Symbol, Expr]`), `SystemSolution(branches: tuple)` (frozen dataclass), `derive_branches(equations, given, find, aux_syms) -> tuple[Branch, ...]`, `make_system_solvability(equations, var_syms, aux_syms) -> Callable[(given, find) -> (bool, SystemSolution|str)]`.
  - `templates/base.py`: `Template.auxiliaries: dict = None` (Symbol → unit string); `Template.unit_for(sym)` resolves auxiliaries too.
  - Protocol note: `SystemSolution` is detected downstream by `getattr(info, "branches", None)` — no imports of this module from `engine/` (avoids an import cycle through `templates.declarative.__init__` → `gate` → `engine.loop`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_system_templates.py`:

```python
"""System templates (spec 2026-07-27): branch derivation, parsing, loop, contract."""

import pytest
import sympy

from templates.base import Template, VarSpec
from templates.declarative.system import (Branch, SystemSolution,
                                          derive_branches,
                                          make_system_solvability)

gap, a, v, t, x = sympy.symbols("gap a v t x", real=True)
PURSUIT_EQS = [sympy.Eq(x, v * t), sympy.Eq(x, gap + a * t**2 / 2)]


def test_derive_branches_pursuit_two_branches():
    branches = derive_branches(PURSUIT_EQS, {gap, a, v}, t, {x})
    assert len(branches) == 2
    for b in branches:
        assert isinstance(b, Branch)
        assert b.find_expr.free_symbols <= {gap, a, v}
        assert set(b.aux_exprs) == {x}
        assert b.aux_exprs[x].free_symbols <= {gap, a, v}


def test_derive_branches_linear_single_branch():
    d, w, tt, p = sympy.symbols("d w tt p", real=True)
    eqs = [sympy.Eq(p, w * tt), sympy.Eq(p, d)]
    branches = derive_branches(eqs, {d, w}, tt, {p})
    assert len(branches) == 1
    assert sympy.simplify(branches[0].find_expr - d / w) == 0
    assert sympy.simplify(branches[0].aux_exprs[p] - d) == 0


def test_system_solvability_valid_split():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    ok, info = solv((gap, a, v), t)
    assert ok is True
    assert isinstance(info, SystemSolution)
    assert len(info.branches) == 2


def test_system_solvability_rejects_unused_variable():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    ok, reason = solv((gap, a), t)  # v unused
    assert ok is False
    assert "no unused variables" in reason


def test_system_solvability_rejects_find_in_given():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    ok, reason = solv((gap, a, v, t), t)
    assert ok is False


def test_system_solvability_rejects_unknown_symbol():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    z = sympy.Symbol("z", real=True)
    ok, reason = solv((gap, a, z), t)
    assert ok is False


def test_system_solvability_caches_derivation():
    solv = make_system_solvability(PURSUIT_EQS, {gap, a, v, t}, {x})
    _, info1 = solv((gap, a, v), t)
    _, info2 = solv((v, a, gap), t)  # same set, different order
    assert info1 is info2


def test_template_unit_for_resolves_auxiliaries():
    tpl = Template(
        topic="toy", symbols={"t": t}, variables={t: VarSpec("s", {})},
        equations=[], solvability=lambda g, f: (False, "n/a"),
        constraints=[], root_select=lambda vals, f, d: None,
        default_split=((), t), auxiliaries={x: "m"},
    )
    assert tpl.unit_for(t) == "s"
    assert tpl.unit_for(x) == "m"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py -v`
Expected: FAIL — `ModuleNotFoundError: templates.declarative.system` (and the Template test fails on the unknown `auxiliaries` kwarg).

- [ ] **Step 3: Implement `templates/declarative/system.py`**

```python
"""Simultaneous-system solvability for declarative templates (spec 2026-07-27).

A *system template* declares auxiliary (internal) unknowns and 2+ equations
that must be solved together. Solvability is derived **once, symbolically**:
``sympy.solve`` with the givens left symbolic yields closed-form solution
branches — the find and every auxiliary expressed in the givens. Generation
then only substitutes sampled numbers into cached expressions, so the bounded
re-roll loop stays as fast as the single-equation path, and the harness's
independent numeric re-solve remains a genuinely different code path.

v1 rule: **no unused variables** — a split is valid iff the given set is
exactly all declared variables minus the find. Auxiliaries are always solved,
never given, never the find (enforced at parse time).

``engine.loop`` detects a system split by duck-typing
(``getattr(info, "branches", None)``), NOT by importing this module — the
``templates.declarative`` package pulls in ``gate``, which imports
``engine.loop``, so a top-level import from the loop would cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

import sympy


@dataclass(frozen=True)
class Branch:
    """One solution branch: the find and every auxiliary, in the givens."""

    find_expr: object  # sympy expression over the given symbols
    aux_exprs: dict    # Symbol -> sympy expression over the given symbols


@dataclass(frozen=True)
class SystemSolution:
    """All closed-form branches for one (given, find) split."""

    branches: tuple  # tuple[Branch, ...]


def derive_branches(equations, given, find, aux_syms):
    """Symbolically solve the system for ``[find] + auxiliaries``.

    Returns a tuple of :class:`Branch` — one per solution branch whose every
    expression closes over the ``given`` symbols only. An unsolvable system
    (or one SymPy cannot solve in closed form) yields ``()``.
    """
    given = set(given)
    unknowns = [find] + sorted(aux_syms, key=lambda s: s.name)
    try:
        sols = sympy.solve(equations, unknowns, dict=True)
    except (NotImplementedError, ValueError):
        return ()
    branches = []
    for sol in sols:
        if find not in sol:
            continue
        find_expr = sol[find]
        if not find_expr.free_symbols <= given:
            continue
        aux_exprs = {}
        for aux in aux_syms:
            expr = sol.get(aux)
            if expr is None or not expr.free_symbols <= given:
                aux_exprs = None
                break
            aux_exprs[aux] = expr
        if aux_exprs is not None:
            branches.append(Branch(find_expr=find_expr, aux_exprs=aux_exprs))
    return tuple(branches)


def make_system_solvability(equations, var_syms, aux_syms):
    """Build the ``solvability(given, find)`` callable for a system template.

    Valid split: ``given == var_syms - {find}`` (no unused variables). The
    derivation is cached per split, so repeated calls (``valid_splits``, the
    loop, the gate) pay the symbolic solve once.
    """
    all_vars = frozenset(var_syms)
    aux_syms = frozenset(aux_syms)
    cache = {}

    def solvability(given, find):
        given_set = frozenset(given)
        if find in given_set:
            return (False, "find must be distinct from the given variables")
        if not (given_set | {find}) <= all_vars:
            return (False, "unknown variable for this template")
        if given_set != all_vars - {find}:
            return (False, "system templates have no unused variables: "
                           "given must be every variable except the find")
        key = (given_set, find)
        if key not in cache:
            cache[key] = SystemSolution(
                branches=derive_branches(equations, given_set, find, aux_syms))
        solution = cache[key]
        if not solution.branches:
            return (False, "system has no closed-form solution for this split")
        return (True, solution)

    return solvability
```

- [ ] **Step 4: Extend `templates/base.py`**

Add one field to the `Template` dataclass (after `graph_spec`):

```python
    auxiliaries: dict = None  # system templates: Symbol -> unit str (spec 2026-07-27)
```

Replace `unit_for` with:

```python
    def unit_for(self, sym):
        if self.auxiliaries and sym in self.auxiliaries:
            return self.auxiliaries[sym]
        return self.variables[sym].unit
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py tests/test_suvat.py -v`
Expected: all PASS (including the untouched suvat suite).

- [ ] **Step 6: Commit**

```bash
git add templates/declarative/system.py templates/base.py tests/test_system_templates.py
git commit -m "feat(system): branch derivation module + Template.auxiliaries"
```

---

### Task 2: Parse the auxiliary block

**Files:**
- Modify: `templates/declarative/parse.py:137-178` (`parse_template`; new helper above it)
- Test: `tests/test_system_templates.py` (append)

**Interfaces:**
- Consumes: `make_system_solvability(equations, var_syms, aux_syms)` and `Template.auxiliaries` from Task 1; existing `compile_constraints(specs, symbols)` (constraint `var` may now name an auxiliary).
- Produces: `parse_template(doc)` accepting an optional `"auxiliary"` top-level dict (`name -> {"unit": str}`). Validation failures raise stage-1 `TemplateValidationError` via the existing `_fail`. The parsed `Template` has `auxiliaries={Symbol: unit}` and system solvability wired; docs without the key parse exactly as before.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_system_templates.py`:

```python
from engine.errors import TemplateValidationError
from templates.declarative import parse_template


def _toy_doc(**overrides):
    doc = {
        "topic": "toy-meet",
        "variables": {
            "d": {"unit": "m",   "ranges": {"easy": [2, 20, False], "medium": [2, 40, False], "hard": [2, 60, False]}},
            "w": {"unit": "m/s", "ranges": {"easy": [1, 10, False], "medium": [1, 15, False], "hard": [1, 20, False]}},
            "t": {"unit": "s",   "ranges": {"easy": [1, 10, False], "medium": [1, 20, False], "hard": [1, 30, False]}},
        },
        "auxiliary": {"p": {"unit": "m"}},
        "equations": ["Eq(p, w*t)", "Eq(p, d)"],
        "root_policy": {"name": "smallest_positive_physical"},
        "constraints": [{"var": "t", "op": ">", "value": 0},
                        {"var": "p", "op": ">", "value": 0}],
        "default_split": {"given": ["d", "w"], "find": "t"},
        "golden_cases": [{"given": {"d": 12, "w": 3}, "find": "t",
                          "difficulty": "easy", "expected": "4"}],
        "trust_state": "unverified",
    }
    doc.update(overrides)
    return doc


def test_parse_toy_system_doc():
    tpl = parse_template(_toy_doc())
    assert set(s.name for s in tpl.auxiliaries) == {"p"}
    aux_p = next(iter(tpl.auxiliaries))
    assert tpl.unit_for(aux_p) == "m"
    ok, info = tpl.solvability(tpl.default_split[0], tpl.default_split[1])
    assert ok is True and len(info.branches) == 1


def test_parse_without_auxiliary_unchanged():
    doc = _toy_doc()
    del doc["auxiliary"]
    doc["equations"] = ["Eq(d, w*t)"]
    doc["constraints"] = [{"var": "t", "op": ">", "value": 0}]
    tpl = parse_template(doc)
    assert tpl.auxiliaries is None


def test_parse_valid_splits_derived_for_system():
    tpl = parse_template(_toy_doc())
    finds = {f.name for _, f in tpl.valid_splits()}
    assert finds == {"d", "w", "t"}


def test_parse_rejects_aux_overlapping_variable():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(auxiliary={"t": {"unit": "s"}}))


def test_parse_rejects_aux_without_unit():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(auxiliary={"p": {}}))


def test_parse_rejects_aux_with_ranges():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(
            auxiliary={"p": {"unit": "m", "ranges": {"easy": [1, 5, False]}}}))


def test_parse_rejects_empty_aux_block():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(auxiliary={}))


def test_parse_rejects_aux_in_default_split():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(
            default_split={"given": ["d", "p"], "find": "t"}))


def test_parse_rejects_aux_in_golden_given():
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(
            golden_cases=[{"given": {"d": 12, "p": 12}, "find": "t",
                           "difficulty": "easy", "expected": "4"}]))


def test_parse_equations_may_reference_aux():
    # covered by test_parse_toy_system_doc; here: undeclared names still rejected
    with pytest.raises(TemplateValidationError):
        parse_template(_toy_doc(equations=["Eq(q, w*t)", "Eq(q, d)"]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py -v -k parse`
Expected: FAIL — `parse_template` rejects the unknown `auxiliary` content (equations reference undeclared name `p`).

- [ ] **Step 3: Implement in `templates/declarative/parse.py`**

Add this helper above `parse_template` (import `make_system_solvability` at the top of the file: `from templates.declarative.system import make_system_solvability`):

```python
def _parse_auxiliary(doc, variables):
    """Validate the optional ``auxiliary`` block; return ``{name: unit}``.

    Auxiliaries are internal unknowns (spec 2026-07-27): unit is mandatory
    (dimensional gate), ranges are forbidden (never sampled), and names must
    not collide with declared variables.
    """
    aux = doc.get("auxiliary")
    if aux is None:
        return None
    if not isinstance(aux, dict) or not aux:
        _fail("auxiliary block must be a non-empty object when present")
    units = {}
    for name, spec in aux.items():
        if name in variables:
            _fail(f"auxiliary {name!r} collides with a declared variable")
        if not isinstance(spec, dict) or "unit" not in spec:
            _fail(f"auxiliary {name!r} needs a 'unit'")
        if "ranges" in spec:
            _fail(f"auxiliary {name!r} must not declare ranges (never sampled)")
        units[name] = spec["unit"]
    return units
```

Then modify `parse_template`. After `variables = _require(doc, "variables")` add:

```python
    aux_units = _parse_auxiliary(doc, variables)
```

After `symbols = _build_symbols(variables)` add:

```python
    aux_symbols = ({name: sympy.Symbol(name, real=True) for name in aux_units}
                   if aux_units else {})
    all_names = dict(symbols)
    all_names.update(aux_symbols)
```

Change the namespace to include auxiliaries (equations may reference them):

```python
    namespace = dict(all_names)
    namespace.update(_ALLOWED_FUNCS)
```

Change the constraints compilation to use `all_names` (so a constraint may
reference an auxiliary):

```python
        constraints = compile_constraints(constraints_raw, all_names)
        root_select = make_root_select(root_policy, constraints)
```

After the `default_split` given/find resolution add:

```python
    if aux_symbols:
        banned = set(aux_symbols)
        split_names = set(split["given"]) | {split["find"]}
        if split_names & banned:
            _fail("default_split must not reference auxiliary variables")
        for i, case in enumerate(doc.get("golden_cases", [])):
            if set(case.get("given", {})) & banned:
                _fail(f"golden case {i} pins an auxiliary variable")
```

Finally build solvability and the Template conditionally (replacing the
current `solvability=_make_solvability(...)` argument and adding
`auxiliaries=`):

```python
    if aux_symbols:
        solvability = make_system_solvability(
            equations, set(symbols.values()), set(aux_symbols.values()))
        auxiliaries = {aux_symbols[n]: aux_units[n] for n in aux_symbols}
    else:
        solvability = _make_solvability(equations, all_syms)
        auxiliaries = None

    return Template(
        topic=topic,
        symbols=symbols,
        variables=var_specs,
        equations=equations,
        solvability=solvability,
        constraints=constraints.loop_predicates,
        root_select=root_select,
        default_split=(given, find),
        signed_answer=bool(doc.get("signed_answer", False)),
        auxiliaries=auxiliaries,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py tests/test_declarative_parse.py tests/test_declarative_parity.py -v`
Expected: all PASS (existing declarative docs unaffected).

- [ ] **Step 5: Commit**

```bash
git add templates/declarative/parse.py tests/test_system_templates.py
git commit -m "feat(system): parse the auxiliary block into system templates"
```

---

### Task 3: Contract — emit auxiliary values

**Files:**
- Modify: `engine/contract.py:106-140` (`build_sympy_data`)
- Test: `tests/test_system_templates.py` (append)

**Interfaces:**
- Consumes: `Template.unit_for` (Task 1) resolving auxiliary symbols.
- Produces: `build_sympy_data(template, given, find, inputs, value, sym_expr, seed, policy, plausible, aux_values=None)`. When `aux_values` (dict Symbol → exact SymPy number) is non-empty, the returned dict gains `"auxiliary"`: a name-sorted list of `{"symbol", "value", "exact", "unit"}` entries (ADR-005 dual form). Absent/empty → key absent (byte-compat).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_system_templates.py`:

```python
from engine import contract as contract_mod


def test_contract_emits_sorted_auxiliary_array():
    tpl = parse_template(_toy_doc())
    d_sym, w_sym, t_sym = (tpl.symbol(n) for n in ("d", "w", "t"))
    p_sym = next(iter(tpl.auxiliaries))
    ok, info = tpl.solvability((d_sym, w_sym), t_sym)
    branch = info.branches[0]
    inputs = {d_sym: sympy.Integer(12), w_sym: sympy.Integer(3)}
    data = contract_mod.build_sympy_data(
        tpl, (d_sym, w_sym), t_sym, inputs, sympy.Integer(4),
        branch.find_expr, seed=0,
        policy=type("P", (), {"label": "easy"})(), plausible=True,
        aux_values={p_sym: sympy.Integer(12)},
    )
    assert data["auxiliary"] == [
        {"symbol": "p", "value": 12, "exact": "12", "unit": "m"}
    ]


def test_contract_without_aux_values_has_no_key():
    tpl = parse_template(_toy_doc())
    d_sym, w_sym, t_sym = (tpl.symbol(n) for n in ("d", "w", "t"))
    ok, info = tpl.solvability((d_sym, w_sym), t_sym)
    data = contract_mod.build_sympy_data(
        tpl, (d_sym, w_sym), t_sym,
        {d_sym: sympy.Integer(12), w_sym: sympy.Integer(3)},
        sympy.Integer(4), info.branches[0].find_expr, seed=0,
        policy=type("P", (), {"label": "easy"})(), plausible=True,
    )
    assert "auxiliary" not in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py -v -k contract`
Expected: FAIL — `build_sympy_data` got an unexpected keyword `aux_values`.

- [ ] **Step 3: Implement**

Change `build_sympy_data`'s signature to:

```python
def build_sympy_data(template, given, find, inputs, value, sym_expr, seed, policy,
                     plausible, aux_values=None):
```

And insert, immediately before the `if template.graph_spec is not None:` block:

```python
    if aux_values:
        # System templates (spec 2026-07-27): the internal unknowns of the
        # solved branch, exact-first like every other number (ADR-005).
        data["auxiliary"] = [
            {
                "symbol": sym.name,
                "value": to_display(val),
                "exact": to_exact(val),
                "unit": template.unit_for(sym),
            }
            for sym, val in sorted(aux_values.items(), key=lambda kv: kv[0].name)
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/contract.py tests/test_system_templates.py
git commit -m "feat(system): contract emits auxiliary values (ADR-005 dual form)"
```

---

### Task 4: Loop — solve system splits

**Files:**
- Modify: `engine/loop.py:63-109` (`generate` inner loop + `_solve`)
- Test: `tests/test_system_templates.py` (append)

**Interfaces:**
- Consumes: `SystemSolution`/`Branch` shape from Task 1 (duck-typed via `.branches` — **no import** of `templates.declarative.system` in `engine/loop.py`); `build_sympy_data(..., aux_values=...)` from Task 3.
- Produces: `_solve(info, find, inputs, template, difficulty) -> (value, sym_expr, aux_values) | None` — three-tuple now, `aux_values={}` on the single-equation path. `generate()` passes auxiliary values into constraint checking and the contract.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_system_templates.py`:

```python
from engine import registry
from engine.errors import NoCleanInstanceError
from engine.loop import generate
from harness.verify import verify_generic


def test_generate_system_template_end_to_end():
    tpl = parse_template(_toy_doc())
    with registry.temporary(tpl):
        data = generate("toy-meet", given=["d", "w"], find="t",
                        conditions={"d": 12, "w": 3}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "4"
    assert data["auxiliary"] == [
        {"symbol": "p", "value": 12, "exact": "12", "unit": "m"}
    ]


def test_generate_system_respects_aux_constraint():
    # p > 0 is declared; pin d < 0 so p = d violates it -> no clean instance.
    tpl = parse_template(_toy_doc())
    with registry.temporary(tpl):
        with pytest.raises(NoCleanInstanceError):
            generate("toy-meet", given=["d", "w"], find="t",
                     conditions={"d": -12, "w": 3}, difficulty="medium",
                     seed=1, max_attempts=10)


IRR_DOC = {
    "topic": "toy-irr",
    "variables": {
        "c": {"unit": "1", "ranges": {"easy": [2, 2, False], "medium": [2, 2, False], "hard": [2, 2, False]}},
        "t": {"unit": "1", "ranges": {"easy": [1, 10, False], "medium": [1, 10, False], "hard": [1, 10, False]}},
    },
    "auxiliary": {"q": {"unit": "1"}},
    "equations": ["Eq(q**2, c)", "Eq(t, c)"],
    "root_policy": {"name": "smallest_positive_physical"},
    "constraints": [],
    "default_split": {"given": ["c"], "find": "t"},
    "golden_cases": [{"given": {"c": 4}, "find": "t", "difficulty": "easy",
                      "expected": "4"}],
    "trust_state": "unverified",
}


def test_irrational_auxiliary_is_a_failed_roll():
    # c = 2 -> q = ±sqrt(2): find t=2 is clean but q is irrational -> re-roll
    # forever -> NoCleanInstanceError (spec: auxiliaries must be Rational).
    tpl = parse_template(IRR_DOC)
    with registry.temporary(tpl):
        with pytest.raises(NoCleanInstanceError):
            generate("toy-irr", given=["c"], find="t", conditions={"c": 2},
                     difficulty="easy", seed=1, max_attempts=10)


def test_rational_auxiliary_generates():
    tpl = parse_template(IRR_DOC)
    with registry.temporary(tpl):
        data = generate("toy-irr", given=["c"], find="t", conditions={"c": 4},
                        difficulty="easy", seed=1)
    assert data["find"]["exact"] == "4"
    assert data["auxiliary"][0]["exact"] in ("2", "-2")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py -v -k generate or -k auxiliary`
(Use: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py -v`)
Expected: the four new tests FAIL — `_solve` treats `SystemSolution` as an equation (`sympy.solve(SystemSolution, find)` raises → caught → returns None → `NoCleanInstanceError` where success was expected; the constraint/irrational tests may "pass" for the wrong reason — confirm the two success-path tests fail).

- [ ] **Step 3: Implement in `engine/loop.py`**

In `generate()`, replace the three lines that unpack and use the solve result:

```python
        solved = _solve(equation, find, inputs, template, difficulty)
        if solved is not None:
            value, sym_expr = solved
            values = dict(inputs)
            values[find] = value
```

with:

```python
        solved = _solve(equation, find, inputs, template, difficulty)
        if solved is not None:
            value, sym_expr, aux_values = solved
            values = dict(inputs)
            values[find] = value
            values.update(aux_values)
```

and pass the auxiliaries to the contract:

```python
                return contract.build_sympy_data(
                    template, given, find, inputs, value, sym_expr,
                    seed=seed, policy=pol, plausible=True,
                    aux_values=aux_values,
                )
```

Replace `_solve` with (note: three-tuple return, and the system path first):

```python
def _solve(info, find, inputs, template, difficulty):
    """Solve for ``find`` at ``inputs`` — exact, symbolic (spec §5).

    ``info`` is what ``solvability`` returned: a single linking equation, or a
    system-template solution object (duck-typed via ``.branches`` — see
    templates/declarative/system.py for why there is no import here). Returns
    ``(value, sym_expr, aux_values)`` — ``aux_values`` is ``{}`` on the
    single-equation path — or ``None`` for a failed roll.
    """
    branches = getattr(info, "branches", None)
    if branches is not None:
        return _solve_system(branches, find, inputs, template, difficulty)
    try:
        sym_sols = sympy.solve(info, find)
    except (ZeroDivisionError, NotImplementedError):
        return None
    candidates = []  # (value, sym_expr)
    for expr in sym_sols:
        try:
            val = sympy.nsimplify(expr.subs(inputs))
        except (ZeroDivisionError, ValueError):
            continue
        if val.is_real and val.is_number:
            candidates.append((val, expr))
    if not candidates:
        return None
    chosen = template.root_select([c[0] for c in candidates], find, difficulty)
    if chosen is None:
        return None
    for val, expr in candidates:
        if sympy.simplify(val - chosen) == 0:
            return chosen, expr, {}
    return None


def _solve_system(branches, find, inputs, template, difficulty):
    """Evaluate cached system branches; keep auxiliaries branch-consistent.

    The find candidates are root-selected exactly like single-equation roots;
    the auxiliaries are then evaluated from the SAME branch as the chosen
    value (spec 2026-07-27) and must all be exact rationals — anything else
    is a failed roll (ADR-005 keeps the exact() parser Rational-only).
    """
    candidates = []  # (value, branch)
    for branch in branches:
        try:
            val = sympy.nsimplify(branch.find_expr.subs(inputs))
        except (ZeroDivisionError, ValueError):
            continue
        if val.is_real and val.is_number:
            candidates.append((val, branch))
    if not candidates:
        return None
    chosen = template.root_select([c[0] for c in candidates], find, difficulty)
    if chosen is None:
        return None
    for val, branch in candidates:
        if sympy.simplify(val - chosen) != 0:
            continue
        aux_values = {}
        for aux_sym, expr in branch.aux_exprs.items():
            try:
                aval = sympy.nsimplify(expr.subs(inputs))
            except (ZeroDivisionError, ValueError):
                return None
            if not (aval.is_number and aval.is_rational):
                return None  # non-rational auxiliary -> re-roll
            aux_values[aux_sym] = aval
        return chosen, branch.find_expr, aux_values
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py tests/test_loop.py tests/test_chain.py -v`
Expected: all PASS (single-equation path unchanged through the 3-tuple).

- [ ] **Step 5: Commit**

```bash
git add engine/loop.py tests/test_system_templates.py
git commit -m "feat(system): loop solves cached system branches, branch-consistent auxiliaries"
```

---

### Task 5: Harness — verify system instances

**Files:**
- Modify: `harness/verify.py:55-174` (`verify_generic` + new helpers + two extended assertions)
- Test: `tests/test_system_templates.py` (append)

**Interfaces:**
- Consumes: emitted `sympy_data["auxiliary"]` (Task 3/4), `Template.auxiliaries` (Task 1).
- Produces: `verify_generic` verifying system instances: (a) every equation holds at emitted values, (b) independent whole-system numeric recompute matching find AND auxiliaries, (c)/(e) unit and display checks over auxiliary entries. Single-equation templates take the existing code paths verbatim.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_system_templates.py`:

```python
import copy

from harness.verify import FidelityError


def _toy_instance():
    tpl = parse_template(_toy_doc())
    with registry.temporary(tpl):
        data = generate("toy-meet", given=["d", "w"], find="t",
                        conditions={"d": 12, "w": 3}, difficulty="easy", seed=1)
    return tpl, data


def test_verify_system_instance_passes():
    tpl, data = _toy_instance()
    assert verify_generic(data, tpl, difficulty="easy") is True


def test_verify_catches_corrupted_auxiliary():
    tpl, data = _toy_instance()
    bad = copy.deepcopy(data)
    bad["auxiliary"][0]["exact"] = "99"
    bad["auxiliary"][0]["value"] = 99
    with pytest.raises(FidelityError, match=r"\(a\)"):
        verify_generic(bad, tpl, difficulty="easy")


def test_verify_catches_missing_auxiliary():
    tpl, data = _toy_instance()
    bad = copy.deepcopy(data)
    del bad["auxiliary"]
    with pytest.raises(FidelityError, match=r"\(a\)"):
        verify_generic(bad, tpl, difficulty="easy")


def test_verify_catches_aux_display_drift():
    tpl, data = _toy_instance()
    bad = copy.deepcopy(data)
    bad["auxiliary"][0]["value"] = 13  # exact stays "12"
    with pytest.raises(FidelityError, match=r"\(e\)"):
        verify_generic(bad, tpl, difficulty="easy")


def test_verify_catches_aux_unit_mismatch():
    tpl, data = _toy_instance()
    bad = copy.deepcopy(data)
    bad["auxiliary"][0]["unit"] = "s"
    with pytest.raises(FidelityError, match=r"\(c\)"):
        verify_generic(bad, tpl, difficulty="easy")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py -v -k verify`
Expected: `test_verify_system_instance_passes` FAILS — `_linking_equation` raises "(a) no equation relates exactly {...}" (a system has no single linking equation). The tamper tests fail for the same wrong reason — confirm the pass-path failure specifically.

- [ ] **Step 3: Implement in `harness/verify.py`**

In `verify_generic`, replace the two assertion calls for (a) and (b):

```python
    _assert_equation_holds(template, all_syms, given, find_sym, values)              # (a)
    _assert_independent_recompute(template, given, find_sym, find_val, difficulty)   # (b)
```

with a branch on template kind:

```python
    if template.auxiliaries:
        aux_vals = _emitted_auxiliaries(template, sympy_data)
        values.update(aux_vals)
        _assert_system_holds(template, values)                                     # (a)
        _assert_system_recompute(template, given, find_sym, find_val,
                                 aux_vals, difficulty)                             # (b)
    else:
        _assert_equation_holds(template, all_syms, given, find_sym, values)        # (a)
        _assert_independent_recompute(template, given, find_sym, find_val,
                                      difficulty)                                  # (b)
```

Add the three new helpers after `_assert_independent_recompute`:

```python
def _emitted_auxiliaries(template, sympy_data):
    """Parse and complete-check the emitted auxiliary values (system templates)."""
    by_name = {sym.name: sym for sym in template.auxiliaries}
    seen = {}
    for item in sympy_data.get("auxiliary", []):
        sym = by_name.get(item["symbol"])
        if sym is None:
            raise FidelityError(f"(a) unknown auxiliary {item['symbol']!r}")
        seen[sym] = exact(item["exact"])
    missing = sorted(s.name for s in set(by_name.values()) - set(seen))
    if missing:
        raise FidelityError(f"(a) auxiliary values missing for {', '.join(missing)}")
    return seen


def _assert_system_holds(template, values):
    """(a, system form) every declared equation holds at the emitted values."""
    for eq in template.equations:
        residual = sympy.simplify(eq.lhs.subs(values) - eq.rhs.subs(values))
        if residual != 0:
            raise FidelityError(
                f"(a) equation {eq} does not hold; residual={residual}")


def _assert_system_recompute(template, given, find_sym, find_val, aux_vals,
                             difficulty):
    """(b, system form) independent numeric whole-system solve, same branch."""
    aux_syms = sorted(template.auxiliaries, key=lambda s: s.name)
    eqs = [sympy.Eq(e.lhs.subs(given), e.rhs.subs(given))
           for e in template.equations]
    sols = sympy.solve(eqs, [find_sym] + aux_syms, dict=True)
    candidates = []
    for sol in sols:
        if find_sym in sol:
            val = sympy.nsimplify(sol[find_sym])
            if val.is_real and val.is_number:
                candidates.append((val, sol))
    chosen = template.root_select([c[0] for c in candidates], find_sym, difficulty)
    if chosen is None:
        raise FidelityError(f"(b) independent solve found no physical {find_sym}")
    if sympy.simplify(chosen - find_val) != 0:
        raise FidelityError(
            f"(b) final_answer {find_val} != independent recompute {chosen}")
    branch = next(sol for val, sol in candidates
                  if sympy.simplify(val - chosen) == 0)
    for sym in aux_syms:
        recomputed = sympy.nsimplify(branch[sym])
        if sympy.simplify(recomputed - aux_vals[sym]) != 0:
            raise FidelityError(
                f"(b) auxiliary {sym} {aux_vals[sym]} != independent "
                f"recompute {recomputed}")
```

Extend `_assert_units_consistent` — append at the end of the function:

```python
    aux_canonical = {sym.name: unit
                     for sym, unit in (template.auxiliaries or {}).items()}
    for item in sympy_data.get("auxiliary", []):
        if item["unit"] != aux_canonical.get(item["symbol"]):
            raise FidelityError(
                f"(c) unit mismatch for auxiliary {item['symbol']}")
```

Extend `_assert_display_consistent` — change the `items` list to:

```python
    items = (list(sympy_data["given"]) + list(sympy_data.get("auxiliary", []))
             + [sympy_data["find"], sympy_data["final_answer"]])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py tests/test_harness.py tests/test_verify_generic.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/verify.py tests/test_system_templates.py
git commit -m "feat(system): harness verifies system instances (a-e over auxiliaries)"
```

---

### Task 6: Gate fixes — exact golden givens + auxiliary dimensions

**Files:**
- Modify: `templates/declarative/gate.py:112` (`_replay_golden`)
- Modify: `templates/declarative/units.py:58-61` (`check_homogeneous`)
- Test: `tests/test_system_templates.py` (append)

**Interfaces:**
- Consumes: `Template.auxiliaries`, `exact()` (already imported in gate.py).
- Produces: golden-case givens parsed with `exact(v)` (accepts `12` and `"7/2"`, fails closed on non-rationals); dimensional stage covers auxiliary units. Both are prerequisites for `pursuit.json` (Task 7).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_system_templates.py`:

```python
from engine.errors import TemplateValidationError as TVE
from templates.declarative.gate import validate_template
from templates.declarative.units import check_homogeneous


def test_gate_accepts_fractional_golden_given():
    doc = _toy_doc(golden_cases=[
        {"given": {"d": 12, "w": 3}, "find": "t", "difficulty": "easy",
         "expected": "4"},
        {"given": {"d": "7/2", "w": 1}, "find": "t", "difficulty": "easy",
         "expected": "7/2"},
    ])
    report = validate_template(doc, n_smoke=2)
    assert report.passed, [(s.number, s.reason) for s in report.stages]


def test_dimensional_stage_covers_auxiliary_units():
    doc = _toy_doc(auxiliary={"p": {"unit": "s"}})  # wrong: p should be m
    tpl = parse_template(doc)
    with pytest.raises(TVE):
        check_homogeneous(tpl)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py -v -k "gate or dimensional"`
Expected: the fractional-golden test FAILS (`int("7/2")` → ValueError inside `_replay_golden`); the dimensional test FAILS (auxiliary symbol has no dimension mapping, so `p` stays symbolic and no error is raised).

- [ ] **Step 3: Implement**

In `templates/declarative/gate.py::_replay_golden`, replace:

```python
        conditions = {k: int(v) for k, v in case["given"].items()}
```

with:

```python
        # exact() accepts ints and exact strings like "7/2", and fails closed
        # on anything non-rational (ADR-005) — int() broke fractional goldens.
        conditions = {k: exact(v) for k, v in case["given"].items()}
```

In `templates/declarative/units.py::check_homogeneous`, replace:

```python
    sym_dim = {sym: dimension_of(spec.unit) for sym, spec in template.variables.items()}
```

with:

```python
    sym_dim = {sym: dimension_of(spec.unit) for sym, spec in template.variables.items()}
    for sym, unit in (template.auxiliaries or {}).items():
        sym_dim[sym] = dimension_of(unit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. $PY -m pytest tests/test_system_templates.py tests/test_validation_gate.py tests/test_declarative_units.py -v`
Expected: all PASS (existing integer goldens still work — `exact(12)` is `Integer(12)`, which `sampling._spec_for` pins exactly as before).

- [ ] **Step 5: Commit**

```bash
git add templates/declarative/gate.py templates/declarative/units.py tests/test_system_templates.py
git commit -m "fix(gate): exact() golden givens; dimensional check covers auxiliaries"
```

---

### Task 7: pursuit.json — register, tune, prove

**Files:**
- Create: `templates/data/pursuit.json`
- Modify: `engine/registry.py:81` (`_DECLARATIVE_TOPICS`)
- Test: `tests/test_pursuit.py` (create)

**Interfaces:**
- Consumes: everything above.
- Produces: registered topic `"pursuit"`; the audit's exam problem #15 generating with exact numbers and verifying.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pursuit.py`:

```python
"""Pursuit — the system-template proof case (spec 2026-07-27, exam problem #15)."""

import json
from pathlib import Path

import pytest
import sympy

from engine.loop import generate
from engine.registry import load_template, topics
from harness.verify import verify_generic
from templates.declarative.gate import validate_template

PURSUIT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "pursuit.json"


def test_pursuit_is_registered():
    assert "pursuit" in topics()
    tpl = load_template("pursuit")
    assert {s.name for s in tpl.auxiliaries} == {"x"}


def test_bus_problem_exact_numbers():
    # PDF #15: bus leaves with a = 1.0 m/s^2, man 6.0 m behind runs at 3.5 m/s.
    data = generate("pursuit", given=["gap", "a", "v"], find="t",
                    conditions={"gap": 6, "a": 1, "v": sympy.Rational(7, 2)},
                    difficulty="easy", seed=1)
    assert data["find"]["exact"] == "3"
    assert data["final_answer"]["unit"] == "s"
    assert data["auxiliary"] == [
        {"symbol": "x", "value": 10.5, "exact": "21/2", "unit": "m"}
    ]
    assert verify_generic(data, load_template("pursuit"),
                          difficulty="easy") is True


def test_second_root_derived_and_rejected():
    tpl = load_template("pursuit")
    g = tuple(tpl.symbol(n) for n in ("gap", "a", "v"))
    ok, sol = tpl.solvability(g, tpl.symbol("t"))
    assert ok and len(sol.branches) == 2
    vals = {tpl.symbol("gap"): sympy.Integer(6), tpl.symbol("a"): sympy.Integer(1),
            tpl.symbol("v"): sympy.Rational(7, 2)}
    roots = sorted(sympy.nsimplify(b.find_expr.subs(vals)) for b in sol.branches)
    assert roots == [3, 4]  # catches at 3 s; the re-pass at 4 s is rejected


def test_pursuit_derives_four_splits():
    tpl = load_template("pursuit")
    finds = {f.name for _, f in tpl.valid_splits()}
    assert finds == {"t", "v", "gap", "a"}


def test_pursuit_passes_the_gate():
    doc = json.loads(PURSUIT_JSON.read_text())
    report = validate_template(doc, n_smoke=3)
    assert report.passed, [(s.number, s.passed, s.reason) for s in report.stages]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. $PY -m pytest tests/test_pursuit.py -v`
Expected: FAIL — no `templates/data/pursuit.json`, topic not registered.

- [ ] **Step 3: Create `templates/data/pursuit.json`**

```json
{
  "topic": "pursuit",
  "variables": {
    "gap": {"unit": "m",     "ranges": {"easy": [2, 12, false], "medium": [2, 40, false], "hard": [2, 80, false]}},
    "a":   {"unit": "m/s^2", "ranges": {"easy": [1, 3, false],  "medium": [1, 6, false],  "hard": [1, 10, false]}},
    "v":   {"unit": "m/s",   "ranges": {"easy": [3, 12, false], "medium": [3, 25, false], "hard": [3, 40, false]}},
    "t":   {"unit": "s",     "ranges": {"easy": [1, 10, false], "medium": [1, 20, false], "hard": [1, 30, false]}}
  },
  "auxiliary": {"x": {"unit": "m"}},
  "equations": [
    "Eq(x, v*t)",
    "Eq(x, gap + a*t**2/2)"
  ],
  "root_policy": {"name": "smallest_positive_physical"},
  "constraints": [
    {"var": "t", "op": ">", "value": 0},
    {"var": "x", "op": ">", "value": 0},
    {"var": "a", "op": ">", "value": 0},
    {"var": "v", "op": "abs<=", "value": 100}
  ],
  "default_split": {"given": ["gap", "a", "v"], "find": "t"},
  "golden_cases": [
    {"given": {"gap": 6, "a": 1, "v": "7/2"}, "find": "t", "difficulty": "easy", "expected": "3"}
  ],
  "trust_state": "unverified"
}
```

- [ ] **Step 4: Register it**

In `engine/registry.py`, change:

```python
_DECLARATIVE_TOPICS = ("vectors_1d.json", "free_fall.json", "relative_velocity.json")
```

to:

```python
_DECLARATIVE_TOPICS = ("vectors_1d.json", "free_fall.json",
                       "relative_velocity.json", "pursuit.json")
```

- [ ] **Step 5: Tune ranges until the gate converges**

The chase equation only has real, clean roots for a minority of random draws
(needs `v² ≥ 2·a·gap` AND a clean t), so stage 5 convergence depends on the
ranges. Probe:

```bash
PYTHONPATH=. $PY - <<'EOF'
import json
from templates.declarative.gate import validate_template
doc = json.load(open("templates/data/pursuit.json"))
r = validate_template(doc, n_smoke=6)
print("passed:", r.passed)
for s in r.stages:
    print(s.number, s.name, s.passed, s.reason)
EOF
```

If stage 5 reports "did not converge", adjust the band's ranges (e.g. lower
`a`'s hi, raise `v`'s lo, lower `gap`'s hi — more rolls satisfy
`v² ≥ 2·a·gap`) and re-run. The spec explicitly allows range tuning without
a spec change. Keep the golden case exactly as written. Iterate until
`passed: True`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `PYTHONPATH=. $PY -m pytest tests/test_pursuit.py tests/test_cli.py -v`
Expected: all PASS.

Then the CLI spot-check (the spec's documented command):

```bash
PYTHONPATH=. $PY -m engine --topic pursuit --difficulty easy --verify
PYTHONPATH=. $PY -m templates.declarative templates/data/pursuit.json
```

Expected: a generated pursuit instance with `data-fidelity verify: PASS`, and a five-stage all-PASS gate report (exit 0).

- [ ] **Step 7: Commit**

```bash
git add templates/data/pursuit.json engine/registry.py tests/test_pursuit.py
git commit -m "feat(pursuit): the bus problem as a registered system template"
```

---

### Task 8: Second fixture + full-suite verification

**Files:**
- Create: `tests/fixtures/two_car_meet.json`
- Test: `tests/test_pursuit.py` (append)

**Interfaces:**
- Consumes: the full system-template machinery.
- Produces: proof the machinery generalizes beyond pursuit (audit problem #14's shape: both bodies moving, one accelerating), gate-validated but **not** registered.

- [ ] **Step 1: Create `tests/fixtures/two_car_meet.json`**

```json
{
  "topic": "two-car-meet",
  "variables": {
    "gap": {"unit": "m",     "ranges": {"easy": [0, 10, false], "medium": [0, 30, false], "hard": [0, 60, false]}},
    "va":  {"unit": "m/s",   "ranges": {"easy": [6, 20, false], "medium": [6, 30, false], "hard": [6, 40, false]}},
    "vb":  {"unit": "m/s",   "ranges": {"easy": [1, 5, false],  "medium": [1, 10, false], "hard": [1, 15, false]}},
    "ab":  {"unit": "m/s^2", "ranges": {"easy": [1, 4, false],  "medium": [1, 6, false],  "hard": [1, 8, false]}},
    "t":   {"unit": "s",     "ranges": {"easy": [1, 10, false], "medium": [1, 20, false], "hard": [1, 30, false]}}
  },
  "auxiliary": {"x": {"unit": "m"}},
  "equations": [
    "Eq(x, va*t)",
    "Eq(x, gap + vb*t + ab*t**2/2)"
  ],
  "root_policy": {"name": "smallest_positive_physical"},
  "constraints": [
    {"var": "t", "op": ">", "value": 0},
    {"var": "x", "op": ">", "value": 0}
  ],
  "default_split": {"given": ["gap", "va", "vb", "ab"], "find": "t"},
  "golden_cases": [
    {"given": {"gap": 0, "va": 20, "vb": 10, "ab": 4}, "find": "t", "difficulty": "easy", "expected": "5"}
  ],
  "trust_state": "unverified"
}
```

(Golden: `20t = 10t + 2t²` → roots t=0 and t=5; the `t > 0` constraint
rejects the trivial root, so the answer is 5 — a *different* multi-root
rejection than pursuit's, which is the point of the fixture.)

- [ ] **Step 2: Write the test**

Append to `tests/test_pursuit.py`:

```python
def test_two_car_fixture_passes_gate_but_is_not_registered():
    fixture = Path(__file__).resolve().parent / "fixtures" / "two_car_meet.json"
    doc = json.loads(fixture.read_text())
    report = validate_template(doc, n_smoke=2)
    assert report.passed, [(s.number, s.passed, s.reason) for s in report.stages]
    assert "two-car-meet" not in topics()
```

- [ ] **Step 3: Run it (tune the fixture's ranges if stage 5 does not converge, same probe as Task 7 Step 5 with the fixture path)**

Run: `PYTHONPATH=. $PY -m pytest tests/test_pursuit.py -v`
Expected: all PASS.

- [ ] **Step 4: Full-suite verification**

```bash
PYTHONPATH=. $PY -m pytest
PYTHONPATH=. $PY -m templates.declarative templates/data/suvat.json
PYTHONPATH=. $PY -m templates.declarative templates/data/pursuit.json
git status --short
```

Expected: full suite green (182 pre-existing + ~35 new), both gates all-PASS, clean tree.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/two_car_meet.json tests/test_pursuit.py
git commit -m "test(system): two-car-meet fixture proves the machinery generalizes"
```

---

## Self-Review (done at authoring time)

- **Spec coverage:** spec §1 authoring/discriminator → Tasks 1-2; §2 solvability/no-unused-vars → Tasks 1-2; §3 loop/branch-consistency/rational-aux → Task 4; §4 contract → Task 3; §5 harness (a)-(e) → Task 5; §6 gate stages (incl. the `"7/2"` golden fix) → Task 6; §7 error handling → Tasks 1/4 (typed stage failures, re-roll semantics); Testing section (bus numbers, t=4 rejection, second fixture, corrupted-auxiliary, regression) → Tasks 7-8 + Task 5.
- **Placeholder scan:** none — every step carries complete code, exact paths, expected outputs; the two tuning steps (7.5, 8.3) are bounded empirical iterations the spec explicitly authorizes.
- **Type consistency:** `_solve` returns a 3-tuple in both paths (Task 4) matching what `generate` unpacks; `Branch.find_expr`/`aux_exprs` names consistent across Tasks 1/4; `build_sympy_data(..., aux_values=None)` consistent across Tasks 3/4; `Template.auxiliaries` is `{Symbol: unit str}` everywhere (Tasks 1/2/5/6); duck-typed `.branches` protocol stated in Tasks 1 and 4.
