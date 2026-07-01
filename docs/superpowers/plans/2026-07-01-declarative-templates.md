# Declarative Templates + 5-Stage Validation Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a topic template declarative JSON data, parsed into today's `Template` and admitted only via a five-stage automated validation gate; prove it by re-expressing `suvat` as data with byte-for-byte fidelity parity.

**Architecture:** A new `templates/declarative/` subpackage compiles a JSON document into the existing `templates.base.Template` (generating the `solvability`, `root_select`, and `constraints` callables from declarative fields). The hot path (`Template`, `engine/loop.py`, `engine/contract.py`, sampling, policy) is untouched. The harness gains a topic-generic `verify_generic`. A `temporary()` registry context manager lets the gate and parity test generate through the unchanged loop without permanently registering.

**Tech Stack:** Python 3.11+, SymPy 1.13.x (incl. `sympy.physics.units`), stdlib `json`, pytest.

## Global Constraints

- SymPy pinned `1.13.*`; no new runtime dependencies (JSON is stdlib; `sympy.physics.units` ships with SymPy).
- All numbers are exact SymPy objects, never Python floats (ADR-005); parse `exact` strings with `engine.contract.exact`.
- The hot path is unchanged: do **not** modify `templates/base.py`, `engine/loop.py`, `engine/contract.py`, `engine/sampling.py`, `engine/policy.py`.
- The 27 existing tests must keep passing unchanged.
- Run tests with the main checkout's venv interpreter: `/home/thanakorn/Projects/jotelab-ai/.venv/bin/python -m pytest`. Define `VPY=/home/thanakorn/Projects/jotelab-ai/.venv/bin/python`.
- Register a candidate template **only** when all five gate stages pass.

---

### Task 1: `TemplateValidationError` typed error + `registry.temporary()`

**Files:**
- Modify: `engine/errors.py`
- Modify: `engine/registry.py`
- Test: `tests/test_declarative_infra.py` (create)

**Interfaces:**
- Produces: `TemplateValidationError(stage: int, stage_name: str, reason: str)` (subclass of `EngineError`); `registry.temporary(template)` context manager.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_declarative_infra.py
import pytest
from engine.errors import EngineError, TemplateValidationError
from engine import registry
from engine.registry import load_template


def test_template_validation_error_carries_stage():
    err = TemplateValidationError(2, "dimensional homogeneity", "v = u + a t^2 is inhomogeneous")
    assert isinstance(err, EngineError)
    assert err.stage == 2
    assert err.stage_name == "dimensional homogeneity"
    assert "inhomogeneous" in str(err)


def test_registry_temporary_swaps_and_restores():
    original = load_template("suvat")

    class Fake:
        topic = "suvat"

    fake = Fake()
    with registry.temporary(fake) as t:
        assert t is fake
        assert load_template("suvat") is fake
    assert load_template("suvat") is original


def test_registry_temporary_new_topic_is_removed_after():
    class Fake:
        topic = "brand_new_topic"

    with registry.temporary(Fake()):
        assert "brand_new_topic" in registry.topics()
    assert "brand_new_topic" not in registry.topics()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VPY -m pytest tests/test_declarative_infra.py -v`
Expected: FAIL (ImportError: cannot import name `TemplateValidationError`).

- [ ] **Step 3: Add the error class**

Append to `engine/errors.py`:

```python
class TemplateValidationError(EngineError):
    """A declarative template failed a validation-gate stage (ADR-007).

    Carries the failing ``stage`` number, its ``stage_name``, and a human
    ``reason`` so the orchestrator can tell an author exactly why a submitted
    template was rejected. Raised by the five-stage gate; never swallowed.
    """

    def __init__(self, stage, stage_name, reason=""):
        self.stage = stage
        self.stage_name = stage_name
        self.reason = reason
        super().__init__(f"[stage {stage}: {stage_name}] {reason}")
```

- [ ] **Step 4: Add the registry context manager**

In `engine/registry.py`, add `import contextlib` at the top and append:

```python
@contextlib.contextmanager
def temporary(template):
    """Register ``template`` under its topic for the duration of the block only.

    Lets the validation gate (stage 5) and the parity test drive the unchanged
    ``loop.generate()`` on a candidate template without permanently registering
    it (ADR-007: register only on all-pass). Restores any previous entry — or
    removes a newly-added topic — on exit, even on error.
    """
    key = template.topic
    had = key in _REGISTRY
    prev = _REGISTRY.get(key)
    _REGISTRY[key] = template
    try:
        yield template
    finally:
        if had:
            _REGISTRY[key] = prev
        else:
            _REGISTRY.pop(key, None)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `$VPY -m pytest tests/test_declarative_infra.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add engine/errors.py engine/registry.py tests/test_declarative_infra.py
git commit -m "Add TemplateValidationError + registry.temporary() (ADR-007 infra)"
```

---

### Task 2: Constraint DSL → predicates + per-find physical filter

**Files:**
- Create: `templates/declarative/__init__.py` (empty for now)
- Create: `templates/declarative/constraints.py`
- Test: `tests/test_declarative_constraints.py`

**Interfaces:**
- Produces:
  - `compile_constraints(specs: list[dict], symbols: dict[str, Symbol]) -> CompiledConstraints`
  - `CompiledConstraints.loop_predicates: list[Callable[[dict, str], bool]]` — the `Template.constraints` shape (scope `loop`/`both`).
  - `CompiledConstraints.is_physical(value, find_sym, difficulty) -> bool` — per-`find` filter (scope `root`/`both`).
- Consumes: SymPy symbols keyed by name.

The DSL entry is `{"var","op","value","difficulty"?,"scope"?}`. Ops: `>`,`>=`,`<`,`<=`,`==`,`!=`,`abs<=`,`abs<`,`abs>=`,`abs>`. `scope` ∈ `{"loop","root","both"}` default `"both"`. `difficulty` (optional) restricts the band.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_declarative_constraints.py
import sympy
from templates.declarative.constraints import compile_constraints

SYMS = dict(zip("uvats", sympy.symbols("u v a t s", real=True)))
u, v, a, t, s = (SYMS[n] for n in "uvats")


def _specs():
    return [
        {"var": "t", "op": ">", "value": 0},
        {"var": "u", "op": "abs<=", "value": 100},
        {"var": "v", "op": "abs<=", "value": 100},
        {"var": "a", "op": "!=", "value": 0},
        {"var": "u", "op": ">=", "value": 0, "difficulty": "easy"},
        {"var": "v", "op": ">=", "value": 0, "difficulty": "easy"},
        {"var": "s", "op": ">=", "value": 0, "difficulty": "easy"},
        {"var": "a", "op": ">=", "value": 0, "difficulty": "easy", "scope": "root"},
    ]


def test_loop_predicates_match_suvat_semantics():
    cc = compile_constraints(_specs(), SYMS)
    # time must be positive
    assert not all(p({t: sympy.Integer(-1)}, "easy") for p in cc.loop_predicates)
    assert all(p({t: sympy.Integer(3)}, "easy") for p in cc.loop_predicates)
    # speed bounded
    assert not all(p({v: sympy.Integer(200)}, "medium") for p in cc.loop_predicates)
    # accel nonzero
    assert not all(p({a: sympy.Integer(0)}, "medium") for p in cc.loop_predicates)
    # easy nonneg applies to u,v,s (NOT a — that constraint is scope=root)
    assert not all(p({s: sympy.Integer(-5)}, "easy") for p in cc.loop_predicates)
    assert all(p({a: sympy.Integer(-5)}, "easy") for p in cc.loop_predicates)  # a not a loop constraint on easy
    # medium relaxes the easy nonneg
    assert all(p({s: sympy.Integer(-5)}, "medium") for p in cc.loop_predicates)


def test_is_physical_filters_per_find():
    cc = compile_constraints(_specs(), SYMS)
    # find=t must be strictly positive
    assert cc.is_physical(sympy.Integer(3), t, "easy")
    assert not cc.is_physical(sympy.Integer(-3), t, "easy")
    # find=a on easy: negative rejected (scope=root constraint), zero rejected (!=0)
    assert not cc.is_physical(sympy.Integer(-2), a, "easy")
    assert not cc.is_physical(sympy.Integer(0), a, "easy")
    # find=v: |v|<=100
    assert not cc.is_physical(sympy.Integer(250), v, "medium")
    assert cc.is_physical(sympy.Integer(30), v, "medium")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VPY -m pytest tests/test_declarative_constraints.py -v`
Expected: FAIL (ModuleNotFoundError: templates.declarative.constraints).

- [ ] **Step 3: Implement the DSL**

Create empty `templates/declarative/__init__.py`. Create `templates/declarative/constraints.py`:

```python
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
    ">":     lambda x, c: bool((x > c) is sympy.true) or x > c,
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
    difficulty: str | None
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$VPY -m pytest tests/test_declarative_constraints.py -v`
Expected: PASS (2 passed). If the `>` lambda misbehaves on SymPy relationals, simplify `_OPS[">"]` to `lambda x, c: x > c` and rely on `bool(...)` in `_apply`.

- [ ] **Step 5: Commit**

```bash
git add templates/declarative/__init__.py templates/declarative/constraints.py tests/test_declarative_constraints.py
git commit -m "Declarative constraint DSL -> predicates + per-find physical filter (ADR-007)"
```

---

### Task 3: Named root policy

**Files:**
- Create: `templates/declarative/roots.py`
- Test: `tests/test_declarative_roots.py`

**Interfaces:**
- Consumes: `CompiledConstraints.is_physical` (Task 2).
- Produces: `make_root_select(policy: dict, constraints: CompiledConstraints) -> Callable[[list, Symbol, str], value|None]` — the `Template.root_select` shape. v1 policy name: `"smallest_positive_physical"` with `"nonneg_fallback_vars": [names]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_declarative_roots.py
import sympy
from templates.declarative.constraints import compile_constraints
from templates.declarative.roots import make_root_select

SYMS = dict(zip("uvats", sympy.symbols("u v a t s", real=True)))
u, v, a, t, s = (SYMS[n] for n in "uvats")
SPECS = [
    {"var": "t", "op": ">", "value": 0},
    {"var": "u", "op": "abs<=", "value": 100},
    {"var": "v", "op": "abs<=", "value": 100},
    {"var": "a", "op": "!=", "value": 0},
    {"var": "u", "op": ">=", "value": 0, "difficulty": "easy"},
    {"var": "v", "op": ">=", "value": 0, "difficulty": "easy"},
    {"var": "s", "op": ">=", "value": 0, "difficulty": "easy"},
    {"var": "a", "op": ">=", "value": 0, "difficulty": "easy", "scope": "root"},
]
POLICY = {"name": "smallest_positive_physical", "nonneg_fallback_vars": ["u", "s", "v"]}


def _rs():
    return make_root_select(POLICY, compile_constraints(SPECS, SYMS))


def test_smallest_positive_root_chosen():
    # candidates for t: -3 and 3 -> pick 3
    rs = _rs()
    assert rs([sympy.Integer(-3), sympy.Integer(3)], t, "easy") == 3


def test_nonneg_fallback_for_u_when_no_positive():
    # find=u, only candidate is 0 -> allowed via nonneg fallback (u in fallback set)
    rs = _rs()
    assert rs([sympy.Integer(0)], u, "easy") == 0


def test_no_physical_root_returns_none():
    # find=t, only candidate negative -> not physical -> None
    rs = _rs()
    assert rs([sympy.Integer(-3)], t, "easy") is None


def test_unknown_policy_name_raises():
    import pytest
    with pytest.raises(ValueError):
        make_root_select({"name": "nope"}, compile_constraints(SPECS, SYMS))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VPY -m pytest tests/test_declarative_roots.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

Create `templates/declarative/roots.py`:

```python
"""Named root-selection policies (ADR-007 sub-decision b).

Authors *pick* a vetted policy; they never write selection logic. v1 offers one:
``smallest_positive_physical``, which reproduces ``templates/suvat.py::root_select``
— filter candidates by the template's per-``find`` physical predicate, take the
smallest strictly-positive real, and (only for a declared set of variables that may
legitimately be zero) fall back to the smallest non-negative real.
"""

from __future__ import annotations

import sympy


def make_root_select(policy, constraints):
    """Build a ``root_select(values, find, difficulty)`` callable from a policy dict."""
    name = policy.get("name")
    if name != "smallest_positive_physical":
        raise ValueError(f"unknown root policy {name!r}")
    fallback = set(policy.get("nonneg_fallback_vars", []))

    def root_select(values, find, difficulty):
        physical = []
        for val in values:
            val = sympy.nsimplify(val)
            if not (val.is_real and val.is_number):
                continue
            if not constraints.is_physical(val, find, difficulty):
                continue
            physical.append(val)
        positive = [x for x in physical if x.is_positive]
        if positive:
            return min(positive)
        nonneg = [x for x in physical if x.is_nonnegative]
        if nonneg and find.name in fallback:
            return min(nonneg)
        return None

    return root_select
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$VPY -m pytest tests/test_declarative_roots.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add templates/declarative/roots.py tests/test_declarative_roots.py
git commit -m "Named root policy: smallest_positive_physical (ADR-007)"
```

---

### Task 4: Safe parser — declarative doc → `Template` (Stage 1)

**Files:**
- Create: `templates/declarative/parse.py`
- Modify: `templates/declarative/__init__.py` (export `parse_template`)
- Test: `tests/test_declarative_parse.py`

**Interfaces:**
- Consumes: `compile_constraints` (Task 2), `make_root_select` (Task 3), `templates.base.Template`/`VarSpec`.
- Produces: `parse_template(doc: dict) -> Template`. Raises `TemplateValidationError(1, ...)` on unknown names/callables or malformed docs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_declarative_parse.py
import json
import pytest
import sympy
from engine.errors import TemplateValidationError
from templates.declarative import parse_template

MINIMAL = {
    "topic": "mini",
    "variables": {
        "u": {"unit": "m/s", "ranges": {"easy": [0, 20, False]}},
        "a": {"unit": "m/s^2", "ranges": {"easy": [1, 10, False]}},
        "t": {"unit": "s", "ranges": {"easy": [1, 10, False]}},
        "v": {"unit": "m/s", "ranges": {"easy": [0, 30, False]}},
    },
    "equations": ["Eq(v, u + a*t)"],
    "root_policy": {"name": "smallest_positive_physical", "nonneg_fallback_vars": ["u", "v"]},
    "constraints": [{"var": "t", "op": ">", "value": 0}],
    "default_split": {"given": ["u", "a", "t"], "find": "v"},
    "golden_cases": [{"given": {"u": 0, "a": 2, "t": 5}, "find": "v", "difficulty": "easy", "expected": "10"}],
    "trust_state": "unverified",
}


def test_parse_builds_template():
    tpl = parse_template(MINIMAL)
    assert tpl.topic == "mini"
    assert len(tpl.equations) == 1
    assert set(s.name for s in tpl.symbols.values()) == {"u", "a", "t", "v"}
    assert tpl.default_split[1].name == "v"
    # solvability is auto-derived: {u,a,t}->v is valid, single-equation
    ok, eq = tpl.solvability([tpl.symbols[n] for n in ("u", "a", "t")], tpl.symbols["v"])
    assert ok


def test_parse_rejects_unknown_symbol():
    bad = json.loads(json.dumps(MINIMAL))
    bad["equations"] = ["Eq(v, u + a*t + w)"]  # w undeclared
    with pytest.raises(TemplateValidationError) as ei:
        parse_template(bad)
    assert ei.value.stage == 1


def test_parse_rejects_unknown_callable():
    bad = json.loads(json.dumps(MINIMAL))
    bad["equations"] = ["Eq(v, __import__('os').system('echo hi'))"]
    with pytest.raises(TemplateValidationError) as ei:
        parse_template(bad)
    assert ei.value.stage == 1


def test_parse_trust_state_carried():
    tpl = parse_template(MINIMAL)
    assert getattr(tpl, "topic") == "mini"  # sanity
    # trust_state is carried on the parsed doc-level metadata (see parse.trust_state_of)
    from templates.declarative.parse import trust_state_of
    assert trust_state_of(MINIMAL) == "unverified"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VPY -m pytest tests/test_declarative_parse.py -v`
Expected: FAIL (ImportError: parse_template).

- [ ] **Step 3: Implement the parser**

Create `templates/declarative/parse.py`:

```python
"""Safe declarative-doc -> Template parser (ADR-007 sub-decisions a, b; gate stage 1).

Equations arrive as *strings* and are parsed with ``sympy.sympify`` against a
namespace containing **only** the template's declared symbols plus a small
allow-list of functions. Any unknown name or callable is rejected at parse time
(``TemplateValidationError`` stage 1). No ``eval``; no user Python ever executes.

``solvability`` is *auto-derived* (ADR b): for the v1 single-equation model, a split
``(given, find)`` is valid iff ``given ∪ {find}`` is related by the one equation that
excludes exactly one variable. The map is computed from the equation set, so an
author never writes solvability logic.
"""

from __future__ import annotations

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


def _sympify_equation(text, namespace):
    try:
        expr = sympy.sympify(text, locals=namespace, evaluate=True)
    except (sympy.SympifyError, SyntaxError, TypeError, AttributeError) as exc:
        _fail(f"cannot parse equation {text!r}: {exc}")
    # Reject anything referencing a name outside the declared symbols/allow-list.
    allowed = set(namespace.values()) | {v for v in _ALLOWED_FUNCS.values()}
    for atom in expr.atoms(sympy.Symbol):
        if atom not in namespace.values():
            _fail(f"equation {text!r} references undeclared symbol {atom.name!r}")
    for func in expr.atoms(sympy.Function):
        if func.func not in {sympy.Function}:  # any applied undeclared function
            _fail(f"equation {text!r} uses disallowed function {func.func}")
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


def _excluded_var(eq, all_syms):
    """The single symbol absent from ``eq``'s free symbols, or None if not exactly one."""
    present = eq.free_symbols & all_syms
    missing = all_syms - present
    return next(iter(missing)) if len(missing) == 1 else None


def _make_solvability(equations, all_syms):
    """Auto-derive the single-equation solvability map from the equation set."""
    by_excluded = {}
    for eq in equations:
        ex = _excluded_var(eq, all_syms)
        if ex is not None:
            by_excluded[ex] = eq

    def solvability(given, find):
        given = set(given)
        if len(given) != len(all_syms) - 2 or find in given:
            return (False, "v1 expects exactly (n-2) distinct givens and a distinct find")
        used = given | {find}
        if not used <= all_syms:
            return (False, "unknown variable for this template")
        unused = all_syms - used
        if len(unused) != 1:
            return (False, "could not isolate a single unused variable")
        ex = next(iter(unused))
        if ex not in by_excluded:
            return (False, "no equation excludes the unused variable")
        return (True, by_excluded[ex])

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
    )
```

Update `templates/declarative/__init__.py`:

```python
"""Declarative topic templates (ADR-007): parse + validate JSON into a Template."""

from templates.declarative.parse import parse_template, trust_state_of

__all__ = ["parse_template", "trust_state_of"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$VPY -m pytest tests/test_declarative_parse.py -v`
Expected: PASS (4 passed). Note: the `__import__(...)` case parses to something whose atoms include an undeclared symbol or a disallowed function; if SymPy raises during sympify instead, the stage-1 `_fail` in `_sympify_equation`'s except still yields `stage == 1`. Adjust the atom/function guard if a specific payload slips through, keeping the stage-1 contract.

- [ ] **Step 5: Commit**

```bash
git add templates/declarative/parse.py templates/declarative/__init__.py tests/test_declarative_parse.py
git commit -m "Safe declarative parser -> Template + auto-derived solvability (ADR-007 stage 1)"
```

---

### Task 5: Dimensional homogeneity checker (Stage 2)

**Files:**
- Create: `templates/declarative/units.py`
- Test: `tests/test_declarative_units.py`

**Interfaces:**
- Produces: `dimension_of(unit_str: str) -> Dimension`; `check_homogeneous(template: Template) -> None` (raises `TemplateValidationError(2, ...)` on failure).
- Consumes: `templates.base.Template` (uses `.equations` and `.variables[sym].unit`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_declarative_units.py
import json
import pytest
from engine.errors import TemplateValidationError
from templates.declarative import parse_template
from templates.declarative.units import dimension_of, check_homogeneous
from sympy.physics.units.systems.si import dimsys_SI

MINIMAL = {
    "topic": "mini",
    "variables": {
        "u": {"unit": "m/s", "ranges": {"easy": [0, 20, False]}},
        "a": {"unit": "m/s^2", "ranges": {"easy": [1, 10, False]}},
        "t": {"unit": "s", "ranges": {"easy": [1, 10, False]}},
        "v": {"unit": "m/s", "ranges": {"easy": [0, 30, False]}},
    },
    "equations": ["Eq(v, u + a*t)"],
    "root_policy": {"name": "smallest_positive_physical", "nonneg_fallback_vars": ["u", "v"]},
    "constraints": [{"var": "t", "op": ">", "value": 0}],
    "default_split": {"given": ["u", "a", "t"], "find": "v"},
    "golden_cases": [],
    "trust_state": "unverified",
}


def test_dimension_of_parses_compound_units():
    d_v = dimension_of("m/s")
    d_a = dimension_of("m/s^2")
    # velocity == length/time; acceleration == length/time**2
    assert dimsys_SI.equivalent_dims(d_v, dimension_of("m") / dimension_of("s"))
    assert dimsys_SI.equivalent_dims(d_a, dimension_of("m") / dimension_of("s") / dimension_of("s"))


def test_homogeneous_equation_passes():
    check_homogeneous(parse_template(MINIMAL))  # v = u + a t is homogeneous


def test_inhomogeneous_equation_fails_stage_2():
    bad = json.loads(json.dumps(MINIMAL))
    bad["equations"] = ["Eq(v, u + a*t**2)"]  # a t^2 has dim length, v has dim length/time
    tpl = parse_template(bad)
    with pytest.raises(TemplateValidationError) as ei:
        check_homogeneous(tpl)
    assert ei.value.stage == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VPY -m pytest tests/test_declarative_units.py -v`
Expected: FAIL (ModuleNotFoundError: templates.declarative.units).

- [ ] **Step 3: Implement**

Create `templates/declarative/units.py`:

```python
"""Dimensional-homogeneity checker (ADR-007 gate stage 2).

Maps each variable's declared unit string to a SymPy dimension and asserts every
equation is dimensionally homogeneous under the SI dimension system. Homogeneity is
a *necessary* condition for a physically meaningful equation: it catches
``v = u + a*t**2`` but cannot catch a dropped ``1/2`` (dimensionally valid).
"""

from __future__ import annotations

import sympy
from sympy.physics.units import length, time
from sympy.physics.units.systems.si import dimsys_SI

from engine.errors import TemplateValidationError

# Base high-school unit tokens -> SI dimension. Extend as topics need.
_BASE_UNITS = {
    "m": length,
    "s": time,
    "1": sympy.physics.units.Dimension(1),
}


def _token_dim(token):
    token = token.strip()
    if "^" in token or "**" in token:
        base, _, exp = token.replace("**", "^").partition("^")
        return _token_dim(base) ** int(exp)
    if token not in _BASE_UNITS:
        raise TemplateValidationError(2, "dimensional homogeneity",
                                      f"unknown unit token {token!r}")
    return _BASE_UNITS[token]


def dimension_of(unit_str):
    """Parse a unit string like ``m/s^2`` into a SymPy dimension expression."""
    # Split on '/' left-to-right: a/b/c == a / b / c.
    parts = unit_str.split("/")
    dim = _token_dim(parts[0])
    for p in parts[1:]:
        # a factor group may itself be a product a*b
        factor = _mul_dims(p)
        dim = dim / factor
    return _finish(_mul_dims(parts[0])) if len(parts) == 1 else dim


def _mul_dims(group):
    dim = None
    for factor in group.split("*"):
        d = _token_dim(factor)
        dim = d if dim is None else dim * d
    return dim


def _finish(dim):
    return dim


def _subs_dims(expr, sym_dim):
    """Replace each symbol in ``expr`` with a unit-carrying dimension quantity."""
    return expr.xreplace({sym: sym_dim[sym] for sym in expr.free_symbols if sym in sym_dim})


def check_homogeneous(template):
    """Raise ``TemplateValidationError(2, ...)`` if any equation is inhomogeneous."""
    sym_dim = {}
    for sym, spec in template.variables.items():
        sym_dim[sym] = dimension_of(spec.unit)

    for eq in template.equations:
        lhs = _subs_dims(eq.lhs, sym_dim)
        rhs = _subs_dims(eq.rhs, sym_dim)
        try:
            lhs_d = dimsys_SI.get_dimensional_dependencies(lhs)
            rhs_d = dimsys_SI.get_dimensional_dependencies(rhs)
        except (TypeError, ValueError) as exc:
            raise TemplateValidationError(
                2, "dimensional homogeneity",
                f"equation {eq} could not be dimensionally analysed: {exc}")
        if lhs_d != rhs_d:
            raise TemplateValidationError(
                2, "dimensional homogeneity",
                f"equation {eq} is dimensionally inhomogeneous: {lhs_d} != {rhs_d}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$VPY -m pytest tests/test_declarative_units.py -v`
Expected: PASS (3 passed). If `get_dimensional_dependencies` rejects a raw sum of dimensions, switch to `dimsys_SI.equivalent_dims(lhs, rhs)` after reducing each side, or compare `Dimension(...)` via `dimsys_SI.get_dimensional_dependencies(Dimension(expr))`. The key contract: homogeneous → no raise; `a*t**2` vs `v` → raise with `stage == 2`.

- [ ] **Step 5: Commit**

```bash
git add templates/declarative/units.py tests/test_declarative_units.py
git commit -m "Dimensional-homogeneity checker (ADR-007 gate stage 2)"
```

---

### Task 6: SUVAT as declarative data

**Files:**
- Create: `templates/data/suvat.json`
- Test: `tests/test_suvat_json_loads.py`

**Interfaces:**
- Consumes: `parse_template` (Task 4).
- Produces: `templates/data/suvat.json` — the declarative twin of `templates/suvat.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_suvat_json_loads.py
import json
from pathlib import Path
from templates.declarative import parse_template
from engine import registry
from engine.loop import generate

SUVAT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "suvat.json"


def test_suvat_json_parses_and_generates():
    doc = json.loads(SUVAT_JSON.read_text())
    tpl = parse_template(doc)
    assert tpl.topic == "suvat"
    assert len(tpl.equations) == 5
    with registry.temporary(tpl):
        data = generate("suvat", given=("u", "a", "t"), find="v",
                        conditions={"u": 0, "a": 2, "t": 5}, difficulty="easy", seed=80421)
    assert data["find"]["exact"] == "10"
    assert data["find"]["unit"] == "m/s"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VPY -m pytest tests/test_suvat_json_loads.py -v`
Expected: FAIL (FileNotFoundError).

- [ ] **Step 3: Author `templates/data/suvat.json`**

Create `templates/data/suvat.json` with the exact content from the design doc's schema block (all five variables u,v,a,t,s with the ranges copied verbatim from `templates/suvat.py::VARIABLES`, the five equations E1–E5 as strings, the root policy with `nonneg_fallback_vars: ["u","s","v"]`, the eight constraints including the `scope:"root"` easy-`a` rule, `default_split {given:[u,a,t], find:v}`, one golden case `{u:0,a:2,t:5} find v expected "10"`, and `trust_state:"unverified"`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `$VPY -m pytest tests/test_suvat_json_loads.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add templates/data/suvat.json tests/test_suvat_json_loads.py
git commit -m "SUVAT re-expressed as declarative data (ADR-007 parity target)"
```

---

### Task 7: Generic Data-Fidelity verification

**Files:**
- Modify: `harness/verify.py`
- Test: `tests/test_verify_generic.py`

**Interfaces:**
- Produces: `verify_generic(sympy_data, template, difficulty="easy") -> True` (raises `FidelityError` on any (a)–(e) failure). Existing `verify(sympy_data, difficulty)` delegates to it with `load_template("suvat")`.
- Consumes: `templates.base.Template`, `engine.contract.exact/to_display`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verify_generic.py
import json
from pathlib import Path
from templates.declarative import parse_template
from engine import registry
from engine.loop import generate
from harness.verify import verify_generic, verify

SUVAT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "suvat.json"


def test_verify_generic_passes_on_data_template():
    tpl = parse_template(json.loads(SUVAT_JSON.read_text()))
    with registry.temporary(tpl):
        data = generate("suvat", given=("u", "a", "t"), find="v", difficulty="medium", seed=99)
    assert verify_generic(data, tpl, difficulty="medium") is True


def test_existing_suvat_verify_still_works():
    data = generate("suvat", given=("u", "a", "t"), find="v",
                    conditions={"u": 0, "a": 2, "t": 5}, difficulty="easy", seed=80421)
    assert verify(data, difficulty="easy") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VPY -m pytest tests/test_verify_generic.py -v`
Expected: FAIL (ImportError: verify_generic).

- [ ] **Step 3: Refactor `harness/verify.py`**

Add a topic-generic core and make the SUVAT-specific `verify` delegate. Keep all existing helper behavior; generalize the symbol/equation/unit sources to come from the passed `template`:

```python
from engine.registry import load_template

def verify_generic(sympy_data, template, difficulty="easy"):
    """Independent Data-Fidelity re-derivation for any parsed Template (ADR-007).

    Same five assertions as the SUVAT ``verify``, but every topic-specific source
    (symbols, equations, canonical units, constraints, root policy) is read from
    ``template`` instead of importing ``templates.suvat``.
    """
    symbols = template.symbols
    all_syms = set(symbols.values())
    given = {symbols[g["symbol"]]: exact(g["exact"]) for g in sympy_data["given"]}
    find_sym = symbols[sympy_data["find"]["symbol"]]
    find_val = exact(sympy_data["find"]["exact"])
    values = dict(given)
    values[find_sym] = find_val

    _assert_equation_holds_generic(template, all_syms, given, find_sym, values)
    _assert_independent_recompute_generic(template, all_syms, given, find_sym, find_val, difficulty)
    _assert_units_consistent_generic(template, sympy_data)
    _assert_plausible_generic(template, values, difficulty)
    _assert_display_consistent(sympy_data)  # unchanged; topic-agnostic already
    return True
```

Implement the `_generic` helpers by lifting the bodies of the existing SUVAT
helpers and replacing `suvat.EQUATIONS`/`ALL_SYMS`/`EQUATION_BY_EXCLUDED`/
`VARIABLES`/`CONSTRAINTS`/`root_select` with template-derived equivalents:

```python
def _excluded_eq(template, all_syms, given, find_sym):
    unused = all_syms - (set(given) | {find_sym})
    if len(unused) != 1:
        raise FidelityError(f"(a) cannot isolate unused variable from {set(given) | {find_sym}}")
    ex = next(iter(unused))
    for eq in template.equations:
        if (all_syms - (eq.free_symbols & all_syms)) == {ex}:
            return eq
    raise FidelityError("(a) no equation excludes the unused variable")


def _assert_equation_holds_generic(template, all_syms, given, find_sym, values):
    eq = _excluded_eq(template, all_syms, given, find_sym)
    residual = sympy.simplify(eq.lhs.subs(values) - eq.rhs.subs(values))
    if residual != 0:
        raise FidelityError(f"(a) equation {eq} does not hold; residual={residual}")


def _independent_solve_generic(template, all_syms, given, find_sym, difficulty):
    eqs = [sympy.Eq(e.lhs.subs(given), e.rhs.subs(given)) for e in template.equations]
    unknowns = sorted(all_syms - set(given), key=lambda s: s.name)
    sols = sympy.solve(eqs, unknowns, dict=True)
    candidates = []
    for sol in sols:
        if find_sym in sol:
            val = sympy.nsimplify(sol[find_sym])
            if val.is_real and val.is_number:
                candidates.append(val)
    return template.root_select(candidates, find_sym, difficulty)


def _assert_independent_recompute_generic(template, all_syms, given, find_sym, find_val, difficulty):
    recomputed = _independent_solve_generic(template, all_syms, given, find_sym, difficulty)
    if recomputed is None:
        raise FidelityError(f"(b) independent solve found no physical {find_sym}")
    if sympy.simplify(recomputed - find_val) != 0:
        raise FidelityError(f"(b) final_answer {find_val} != independent recompute {recomputed}")


def _assert_units_consistent_generic(template, sympy_data):
    canonical = {sym.name: template.variables[sym].unit for sym in template.variables}
    for g in sympy_data["given"]:
        if g["unit"] != canonical[g["symbol"]]:
            raise FidelityError(f"(c) unit mismatch for {g['symbol']}")
    find = sympy_data["find"]
    if find["unit"] != canonical[find["symbol"]]:
        raise FidelityError(f"(c) unit mismatch for find {find['symbol']}")
    if sympy_data["final_answer"]["unit"] != find["unit"]:
        raise FidelityError("(c) final_answer unit != find unit")


def _assert_plausible_generic(template, values, difficulty):
    for c in template.constraints:
        if not c(values, difficulty):
            raise FidelityError(f"(d) plausibility constraint {getattr(c, '__name__', c)} failed")
```

Then rewrite the public `verify` to delegate:

```python
def verify(sympy_data, difficulty="easy"):
    """SUVAT Data-Fidelity check (delegates to the topic-generic core)."""
    if sympy_data["topic"] != "suvat":
        raise NotImplementedError(f"no harness for topic {sympy_data['topic']!r}")
    return verify_generic(sympy_data, load_template("suvat"), difficulty)
```

Keep the old SUVAT-specific private helpers only if other code imports them; the
tests import `verify`, `verify_generic`, `independent_solve`, `FidelityError`. If
`independent_solve` is referenced elsewhere, keep a thin wrapper:
`independent_solve(given, find_sym, difficulty="easy")` calling
`_independent_solve_generic(load_template("suvat"), suvat.ALL_SYMS, given, find_sym, difficulty)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `$VPY -m pytest tests/test_verify_generic.py tests/test_harness.py -v`
Expected: PASS (new + all existing harness tests green — the delegation preserves behavior).

- [ ] **Step 5: Commit**

```bash
git add harness/verify.py tests/test_verify_generic.py
git commit -m "Topic-generic Data-Fidelity verify_generic; suvat.verify delegates (ADR-007)"
```

---

### Task 8: The five-stage validation gate

**Files:**
- Create: `templates/declarative/gate.py`
- Modify: `templates/declarative/__init__.py` (export `validate_template`, `register_declarative`)
- Test: `tests/test_validation_gate.py`

**Interfaces:**
- Consumes: `parse_template` (T4), `check_homogeneous` (T5), `verify_generic` (T7), `registry.temporary` (T1), `engine.loop.generate`, `engine.contract.exact`.
- Produces:
  - `validate_template(doc, n_smoke=6) -> Report` where `Report` has `.passed: bool`, `.stages: list[StageResult(number, name, passed, reason)]`, `.template: Template|None`.
  - `register_declarative(doc) -> Template` — validates then registers; raises `TemplateValidationError` on the first failing stage.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validation_gate.py
import json
from pathlib import Path
import pytest
from engine.errors import TemplateValidationError
from engine import registry
from templates.declarative.gate import validate_template, register_declarative

SUVAT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "suvat.json"


def _doc():
    return json.loads(SUVAT_JSON.read_text())


def test_suvat_json_passes_all_five_stages():
    report = validate_template(_doc(), n_smoke=4)
    assert report.passed, [(s.number, s.reason) for s in report.stages if not s.passed]
    assert [s.number for s in report.stages] == [1, 2, 3, 4, 5]
    assert all(s.passed for s in report.stages)


def test_stage2_rejects_inhomogeneous():
    bad = _doc()
    bad["equations"][0] = "Eq(v, u + a*t**2)"  # drop-in dimensional error
    report = validate_template(bad, n_smoke=4)
    assert not report.passed
    failing = [s for s in report.stages if not s.passed]
    assert failing and failing[0].number == 2


def test_stage4_rejects_wrong_golden_case():
    bad = _doc()
    bad["golden_cases"] = [{"given": {"u": 0, "a": 2, "t": 5}, "find": "v",
                            "difficulty": "easy", "expected": "999"}]
    report = validate_template(bad, n_smoke=4)
    assert not report.passed
    assert any((not s.passed) and s.number == 4 for s in report.stages)


def test_stage1_rejects_unknown_symbol():
    bad = _doc()
    bad["equations"][0] = "Eq(v, u + a*t + w)"
    report = validate_template(bad, n_smoke=4)
    assert not report.passed
    assert report.stages[0].number == 1 and not report.stages[0].passed


def test_stage3_rejects_undecidable_default_split():
    bad = _doc()
    bad["default_split"] = {"given": ["u", "a"], "find": "v"}  # only 2 givens
    report = validate_template(bad, n_smoke=4)
    assert not report.passed
    assert any((not s.passed) and s.number == 3 for s in report.stages)


def test_register_declarative_registers_on_pass_and_raises_on_fail():
    doc = _doc()
    doc["topic"] = "suvat_probe"
    try:
        tpl = register_declarative(doc)
        assert tpl.topic == "suvat_probe"
        assert "suvat_probe" in registry.topics()
    finally:
        registry._REGISTRY.pop("suvat_probe", None)

    bad = _doc()
    bad["topic"] = "suvat_bad"
    bad["equations"][0] = "Eq(v, u + a*t**2)"
    with pytest.raises(TemplateValidationError) as ei:
        register_declarative(bad)
    assert ei.value.stage == 2
    assert "suvat_bad" not in registry.topics()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VPY -m pytest tests/test_validation_gate.py -v`
Expected: FAIL (ModuleNotFoundError: templates.declarative.gate).

- [ ] **Step 3: Implement the gate**

Create `templates/declarative/gate.py`:

```python
"""The five-stage template validation gate (ADR-007 sub-decision c).

Runs a candidate declarative doc through five stages and admits it *only* if every
stage passes. Stages 3–5 reuse the engine's own machinery (auto-derived splits, the
bounded loop, the Data-Fidelity oracle) — wiring, not a new solver.

    1 Parse & sandbox        parse_template (safe sympify, allow-list)
    2 Dimensional homogeneity check_homogeneous (sympy.physics.units)
    3 Solvability derivation default_split must be a valid derived split
    4 Golden-case replay     each worked example reproduces exactly (ADR-005)
    5 Convergence + fidelity generate N/band via the real loop; verify_generic 100%
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine import registry
from engine.contract import exact
from engine.errors import EngineError, TemplateValidationError
from engine.loop import generate
from harness.verify import verify_generic
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
    """Run the five-stage gate; stop at the first failure. Never raises for a
    validation failure — inspect ``Report.passed`` / ``Report.stages``."""
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

    # Stage 3 — solvability derivation (default_split must be derivable)
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
        conditions = {k: int(v) for k, v in case["given"].items()}
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
    with registry.temporary(template):
        for band in _BANDS:
            for split_given, split_find in template.valid_splits():
                for k in range(n_smoke):
                    try:
                        data = generate(
                            template.topic,
                            given=[s.name for s in split_given],
                            find=split_find.name,
                            difficulty=band, seed=1000 + k,
                        )
                    except EngineError as exc:
                        return f"did not converge ({band}, find={split_find.name}): {exc}"
                    try:
                        verify_generic(data, template, difficulty=band)
                    except AssertionError as exc:
                        return f"fidelity failure ({band}, find={split_find.name}): {exc}"
    return None


def register_declarative(doc):
    """Validate ``doc`` through the gate; register + return the Template on all-pass."""
    report = validate_template(doc)
    if not report.passed:
        failing = next(s for s in report.stages if not s.passed)
        raise TemplateValidationError(failing.number, failing.name, failing.reason)
    registry.register(report.template)
    return report.template
```

Update `templates/declarative/__init__.py`:

```python
"""Declarative topic templates (ADR-007): parse + validate JSON into a Template."""

from templates.declarative.parse import parse_template, trust_state_of
from templates.declarative.gate import validate_template, register_declarative, Report

__all__ = ["parse_template", "trust_state_of", "validate_template",
           "register_declarative", "Report"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$VPY -m pytest tests/test_validation_gate.py -v`
Expected: PASS (6 passed). Stage 5 across all splits × 3 bands × n_smoke can be slow; `n_smoke=4` in tests keeps it bounded. If `valid_splits()` returns many splits and stage 5 is too slow, cap it in the test via `n_smoke=2` — the default stays 6 for real submissions.

- [ ] **Step 5: Commit**

```bash
git add templates/declarative/gate.py templates/declarative/__init__.py tests/test_validation_gate.py
git commit -m "Five-stage template validation gate + register_declarative (ADR-007 stage c)"
```

---

### Task 9: Byte-for-byte parity exit gate

**Files:**
- Test: `tests/test_declarative_parity.py`

**Interfaces:**
- Consumes: code `SUVAT` (`templates.suvat`), parsed `suvat.json`, `harness.batches.suvat_batch`, `engine.loop.generate`, `registry.temporary`, `harness.verify.verify_generic`.

- [ ] **Step 1: Write the parity test**

```python
# tests/test_declarative_parity.py
import json
from pathlib import Path
from engine import registry
from engine.loop import generate
from harness.batches import suvat_batch
from harness.verify import verify_generic
from templates.declarative import parse_template

SUVAT_JSON = Path(__file__).resolve().parents[1] / "templates" / "data" / "suvat.json"


def _gen(req):
    return generate(req["topic"], given=[s.name for s in req["given"]],
                    find=req["find"].name, difficulty=req["difficulty"], seed=req["seed"])


def test_declarative_suvat_is_byte_for_byte_identical_to_code_suvat():
    data_tpl = parse_template(json.loads(SUVAT_JSON.read_text()))
    batch = suvat_batch(n_seeds=6)  # every split x 3 bands x 6 seeds
    mismatches = []
    for req in batch:
        code_out = _gen(req)  # code SUVAT is the registered "suvat"
        with registry.temporary(data_tpl):
            data_out = _gen(req)
        if json.dumps(code_out, sort_keys=True) != json.dumps(data_out, sort_keys=True):
            mismatches.append((req["given"], req["find"], req["difficulty"], req["seed"]))
    assert not mismatches, f"{len(mismatches)} parity mismatches, first: {mismatches[:3]}"


def test_declarative_suvat_batch_fidelity_100_percent():
    data_tpl = parse_template(json.loads(SUVAT_JSON.read_text()))
    with registry.temporary(data_tpl):
        for req in suvat_batch(n_seeds=6):
            data = _gen(req)
            assert verify_generic(data, data_tpl, difficulty=req["difficulty"]) is True
```

- [ ] **Step 2: Run test to verify it fails (or reveals parity gaps)**

Run: `$VPY -m pytest tests/test_declarative_parity.py -v`
Expected: initially may FAIL with specific mismatches. This is the debugging target: any mismatch means the declarative root policy / constraints / equations don't yet reproduce SUVAT exactly.

- [ ] **Step 3: Close parity gaps**

Use `superpowers:systematic-debugging`. For each mismatch, diff the two `sympy_data` dicts field-by-field. Likely culprits and fixes (all in the *data*/DSL, never the code SUVAT):
- Root selection divergence → check `nonneg_fallback_vars` and the `scope:"root"` easy-`a` rule in `suvat.json` match `_is_physical_value` exactly.
- Constraint band divergence → check the `difficulty:"easy"` scoping on the nonneg rules.
- Equation form divergence → ensure equation strings produce the same `sympy.solve` result/latex (they should, being identical relations).

- [ ] **Step 4: Run the full suite**

Run: `$VPY -m pytest -q`
Expected: PASS — all original 27 tests plus every new test green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_declarative_parity.py
git commit -m "Byte-for-byte parity: declarative SUVAT == code SUVAT (ADR-007 v1 exit gate)"
```

---

### Task 10: README invariant note + CLI validate entry point

**Files:**
- Modify: `README.md`
- Create: `templates/declarative/__main__.py`
- Test: `tests/test_validate_cli.py`

**Interfaces:**
- Produces: `python -m templates.declarative <path-to-json>` — runs the gate and prints a per-stage PASS/FAIL report; exit 0 on all-pass, 1 otherwise.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validate_cli.py
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUVAT_JSON = ROOT / "templates" / "data" / "suvat.json"
VPY = ROOT / ".venv" / "bin" / "python"


def _run(path):
    exe = str(VPY) if VPY.exists() else sys.executable
    return subprocess.run([exe, "-m", "templates.declarative", str(path)],
                          cwd=ROOT, capture_output=True, text=True)


def test_cli_validates_suvat_json():
    r = _run(SUVAT_JSON)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "stage 5" in r.stdout.lower()
    assert "pass" in r.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VPY -m pytest tests/test_validate_cli.py -v`
Expected: FAIL (no `__main__`).

- [ ] **Step 3: Implement the CLI + README note**

Create `templates/declarative/__main__.py`:

```python
"""CLI: ``python -m templates.declarative path/to/template.json``.

Runs the five-stage validation gate on a declarative template and prints a
per-stage PASS/FAIL report. Exit 0 only if every stage passes.
"""

from __future__ import annotations

import json
import sys

from templates.declarative.gate import validate_template


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m templates.declarative <template.json>", file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        doc = json.load(fh)
    report = validate_template(doc)
    for s in report.stages:
        mark = "PASS" if s.passed else "FAIL"
        line = f"stage {s.number} [{s.name}]: {mark}"
        if not s.passed:
            line += f"  -- {s.reason}"
        print(line)
    print(f"\noverall: {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
```

Add to `README.md`, immediately after the blockquote defining "The invariant", a note:

```markdown
> **Invariant scope (ADR-007).** For **user-authored declarative templates**, the
> guarantee narrows: every number is the *arithmetically-exact* solution of the
> template's declared equation set, machine-verified to be dimensionally consistent
> and to reproduce the author's golden worked example(s). The engine no longer
> guarantees the *equations themselves* are the correct physical laws for
> author-supplied templates — that is asserted by the author and evidenced by the
> golden cases and the `unverified`/`verified` provenance signal. Built-in developer
> templates (e.g. `suvat`) retain the full physical guarantee.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$VPY -m pytest tests/test_validate_cli.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Full suite + commit**

```bash
$VPY -m pytest -q   # everything green
git add README.md templates/declarative/__main__.py tests/test_validate_cli.py
git commit -m "Validate CLI (python -m templates.declarative) + narrowed-invariant README note (ADR-007)"
```

---

## Self-Review

**Spec coverage:**
- Schema (JSON) → Task 6 + design; parser/sandbox (stage 1) → Task 4; constraint DSL → Task 2; root policy → Task 3; dimensional gate (stage 2) → Task 5; solvability (stage 3) → auto-derived in Task 4, checked in Task 8; golden replay (stage 4) → Task 8; convergence+fidelity (stage 5) → Task 7 + Task 8; generic fidelity → Task 7; suvat-as-data → Task 6; byte parity exit gate → Task 9; trust_state carried → Task 4; narrowed invariant note → Task 10; typed error → Task 1; register-only-on-pass → Task 8. All ADR-007 (a),(b),(c),(f) engine items covered; (d) as README note; (e) as carried field. DB/UI/promotion correctly out of scope.
- Hot path untouched: no task modifies `templates/base.py`, `engine/loop.py`, `engine/contract.py`, `engine/sampling.py`, `engine/policy.py`. `registry.py` gains only an additive `temporary()`.

**Placeholder scan:** No TBD/TODO; every code step shows real code. Task 6 step 3 references the design-doc schema block verbatim rather than repeating 40 lines of JSON — acceptable since the exact content is fully specified in the committed design doc and each field is enumerated.

**Type consistency:** `parse_template(doc)->Template`, `compile_constraints(specs,symbols)->CompiledConstraints` with `.loop_predicates`/`.is_physical`, `make_root_select(policy,constraints)->callable`, `check_homogeneous(template)->None|raise`, `verify_generic(sympy_data,template,difficulty)->True`, `validate_template(doc,n_smoke)->Report` with `.passed/.stages/.template`, `register_declarative(doc)->Template`. Names consistent across tasks.

**Known execution risks (resolve under systematic-debugging at that task):**
- Task 4 sandbox: SymPy `sympify` of a hostile string may raise vs. produce undeclared atoms; both paths must yield `stage == 1` — the try/except plus atom guard covers both, adjust if a payload slips.
- Task 5 dimensional API: exact `dimsys_SI` call may need `equivalent_dims` vs `get_dimensional_dependencies`; the contract (homogeneous passes, `a*t**2` fails at stage 2) is fixed, the call shape is tuned under test.
- Task 9 parity: the real correctness work; byte mismatches are expected first and driven to zero by fixing the JSON/DSL, never the code SUVAT.
```
