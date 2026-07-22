# Linear Motion Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the four remaining Linear Motion topics — `average-speed`, `upward-throw`, `multi-stage-motion`, `motion-graphs` — to the jotelab-ai symbolic engine, per `docs/superpowers/specs/2026-07-23-linear-motion-completion-design.md`.

**Architecture:** Each topic is a code template (the `templates/distance_displacement.py` pattern): a `Template` dataclass instance with explicit split whitelists, registered directly in `engine/registry.py`. Motion-graphs additionally adds an optional `graph_spec` hook to `Template` and one guarded emit in `engine/contract.py` — additive, no other topic changes shape.

**Tech Stack:** Python 3.13, SymPy, pytest. No new dependencies.

## Global Constraints

- Every emitted number originates in the symbolic layer (project invariant). `graph_spec` values are computed with SymPy exact arithmetic only.
- Harness rule: every whitelisted `(given, find)` split must have exactly one equation in `template.equations` whose free symbols equal `given ∪ {find}` (`harness/verify.py::_linking_equation`).
- Single-answer engine: any split whose solve has two physical roots is excluded via the solvability whitelist (no multi-answer work).
- Exactness (ADR-005): tests compare `exact` strings / SymPy rationals, never display floats, except when testing the display field itself.
- Work happens in worktree `.claude/worktrees/linear-motion-completion`, branch `worktree-linear-motion-completion`. Never push to main.
- Commit format: end commit messages with the Co-Authored-By/Claude-Session trailer used by earlier commits on this branch.

**One-time setup (before Task 1):** from the worktree root:
```bash
uv venv .venv && . .venv/bin/activate && uv pip install -r requirements.txt
python -m pytest -q   # baseline: 100 passed (92 main + 8 distance-displacement)
```

---

### Task 1: `average-speed` topic

**Files:**
- Create: `templates/average_speed.py`
- Create: `tests/test_average_speed.py`
- Modify: `engine/registry.py` (import + `_REGISTRY` entry)

**Interfaces:**
- Consumes: `templates.base.Template`, `templates.base.VarSpec` (existing).
- Produces: `templates.average_speed.AVERAGE_SPEED` (a `Template`, topic name `"average-speed"`, symbols `d1 d2 t sp vavg`). Registered in the registry; no later task depends on it.

- [ ] **Step 1: Write the failing tests**

`tests/test_average_speed.py`:

```python
"""Average speed vs average velocity over a two-segment path (code template).

The rate counterpart of distance-displacement: average speed is total path
length over time (scalar, >= 0); average velocity is net displacement over time
(signed). Needs Abs, so it is a code template; these tests are its gate.
"""

import sympy

from engine import registry
from engine.errors import UnsolvableError
from engine.loop import generate
from harness.verify import verify_generic
from templates.average_speed import AVERAGE_SPEED as TPL


def test_out_and_back_speed_vs_velocity():
    """10 m out, 4 m back in 2 s: speed (10+4)/2 = 7, velocity (10-4)/2 = 3."""
    sp = generate("average-speed", given=("d1", "d2", "t"), find="sp",
                  conditions={"d1": 10, "d2": -4, "t": 2}, difficulty="easy", seed=1)
    vavg = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                    conditions={"d1": 10, "d2": -4, "t": 2}, difficulty="easy", seed=1)
    assert sp["find"]["exact"] == "7"
    assert vavg["find"]["exact"] == "3"
    assert sp["find"]["unit"] == "m/s" and vavg["find"]["unit"] == "m/s"


def test_full_return_zero_velocity_nonzero_speed():
    """6 m out and 6 m back in 3 s: velocity 0 (vector), speed 4 (scalar)."""
    vavg = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                    conditions={"d1": 6, "d2": -6, "t": 3}, difficulty="easy", seed=1)
    sp = generate("average-speed", given=("d1", "d2", "t"), find="sp",
                  conditions={"d1": 6, "d2": -6, "t": 3}, difficulty="easy", seed=1)
    assert vavg["find"]["exact"] == "0"
    assert sp["find"]["exact"] == "4"


def test_velocity_carries_direction():
    """Net motion in -x: the average velocity is negative."""
    vavg = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                    conditions={"d1": 4, "d2": -10, "t": 3}, difficulty="easy", seed=1)
    assert vavg["find"]["exact"] == "-2"


def test_speed_is_never_negative_and_at_least_abs_velocity():
    for seed in range(40):
        sp = generate("average-speed", given=("d1", "d2", "t"), find="sp",
                      difficulty="hard", seed=seed)
        vavg = generate("average-speed", given=("d1", "d2", "t"), find="vavg",
                        difficulty="hard", seed=seed)
        assert sympy.Rational(sp["find"]["exact"]) >= 0
        assert sympy.Rational(sp["find"]["exact"]) >= abs(sympy.Rational(vavg["find"]["exact"]))


def test_both_finds_verify_across_bands():
    for find in ("sp", "vavg"):
        for band in ("easy", "medium", "hard"):
            for seed in range(6):
                data = generate("average-speed", given=("d1", "d2", "t"), find=find,
                                difficulty=band, seed=seed)
                assert verify_generic(data, TPL, difficulty=band) is True


def test_back_solving_a_segment_or_time_is_refused():
    for given, find in ((("d1", "d2", "sp"), "t"), (("d1", "t", "sp"), "d2")):
        try:
            generate("average-speed", given=given, find=find, difficulty="easy", seed=1)
            assert False, f"expected UnsolvableError for {given} -> {find}"
        except UnsolvableError:
            pass


def test_only_two_valid_splits():
    splits = sorted(
        (tuple(sorted(s.name for s in given)), find.name)
        for given, find in TPL.valid_splits()
    )
    assert splits == sorted([(("d1", "d2", "t"), "sp"), (("d1", "d2", "t"), "vavg")])


def test_registered_and_loadable():
    assert "average-speed" in registry.topics()
    assert registry.load_template("average-speed").topic == "average-speed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_average_speed.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'templates.average_speed'`

- [ ] **Step 3: Write the template**

`templates/average_speed.py`:

```python
"""Average speed vs average velocity over a 1-D two-segment path (rates).

The rate counterpart of ``distance-displacement``:

* **Average velocity** is a vector — net displacement over time,
  ``vavg = (d1 + d2)/t`` (signed: out-and-back gives 0).
* **Average speed** is a scalar — total path length over time,
  ``sp = (|d1| + |d2|)/t`` (always >= |vavg|, never negative).

A **code template** because it needs ``Abs`` (forbidden in the declarative
sandbox). Solvability is restricted to the two forward rate questions — never
solving back through an absolute value.
"""

from __future__ import annotations

import sympy

from .base import Template, VarSpec

# -- symbols -------------------------------------------------------------------
d1, d2, t, sp, vavg = sympy.symbols("d1 d2 t sp vavg", real=True)
SYMBOLS = {"d1": d1, "d2": d2, "t": t, "sp": sp, "vavg": vavg}

# -- the two relations ---------------------------------------------------------
E_SPEED = sympy.Eq(sp, (sympy.Abs(d1) + sympy.Abs(d2)) / t)  # scalar rate
E_VAVG = sympy.Eq(vavg, (d1 + d2) / t)                       # vector rate
EQUATIONS = [E_SPEED, E_VAVG]

# -- variables, units, per-difficulty ranges -----------------------------------
_SEG = {"easy": (1, 10, True), "medium": (1, 30, True), "hard": (1, 60, True)}
_T = {"easy": (1, 6, False), "medium": (1, 10, False), "hard": (1, 15, False)}
_SP = {"easy": (0, 25, False), "medium": (0, 70, False), "hard": (0, 130, False)}
_VAVG = {"easy": (0, 25, True), "medium": (0, 70, True), "hard": (0, 130, True)}

VARIABLES = {
    d1: VarSpec("m", _SEG),
    d2: VarSpec("m", _SEG),
    t: VarSpec("s", _T),
    sp: VarSpec("m/s", _SP),
    vavg: VarSpec("m/s", _VAVG),
}

_GIVEN = {d1, d2, t}
_FIND_EQUATION = {sp: E_SPEED, vavg: E_VAVG}


# -- solvability map -----------------------------------------------------------
def solvability(given, find):
    """Only the two forward questions: given both segments and the time, find a rate.

    Back-solves are excluded: recovering a segment (or the time, when the speed
    is known) means inverting ``|d1| + |d2|`` — two branches, out of scope for
    the v1 single-answer engine (same rationale as distance-displacement).
    """
    if set(given) != _GIVEN:
        return (False, "average-speed takes exactly the segments d1, d2 and the time t")
    if find not in _FIND_EQUATION:
        return (False, "find must be the average speed (sp) or average velocity (vavg)")
    return (True, _FIND_EQUATION[find])


# -- root selection ------------------------------------------------------------
def root_select(values, find, difficulty):
    """Both relations isolate the find directly — a single real root each.

    Average speed is a non-negative scalar; average velocity is signed (the sign
    is the direction, out-and-back legitimately gives zero).
    """
    real = []
    for val in values:
        val = sympy.nsimplify(val)
        if val.is_real and val.is_number:
            real.append(val)
    if not real:
        return None
    if find is sp:
        nonneg = [x for x in real if x.is_nonnegative]
        return min(nonneg) if nonneg else None
    return min(real, key=lambda x: (abs(float(x)), float(x)))


# -- plausibility constraints --------------------------------------------------
def _c_time_positive(values, difficulty):
    return t not in values or values[t].is_positive


def _c_speed_nonnegative(values, difficulty):
    return sp not in values or values[sp].is_nonnegative


CONSTRAINTS = [_c_time_positive, _c_speed_nonnegative]


# -- the template object -------------------------------------------------------
AVERAGE_SPEED = Template(
    topic="average-speed",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((d1, d2, t), sp),
    signed_answer=True,  # average velocity carries a sign (direction)
)
```

- [ ] **Step 4: Register the topic**

In `engine/registry.py`, extend the imports and `_REGISTRY`:

```python
from templates.average_speed import AVERAGE_SPEED
from templates.base import Template
from templates.distance_displacement import DISTANCE_DISPLACEMENT
from templates.suvat import SUVAT

_REGISTRY = {
    SUVAT.topic: SUVAT,
    DISTANCE_DISPLACEMENT.topic: DISTANCE_DISPLACEMENT,
    AVERAGE_SPEED.topic: AVERAGE_SPEED,
}
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_average_speed.py -v`
Expected: 8 passed. If `test_both_finds_verify_across_bands` hits `NoCleanInstanceError`, widen `_T`'s lower bounds are already 1 — instead loosen by narrowing segment magnitudes (e.g. hard `(1, 40, True)`); re-run until green.

- [ ] **Step 6: Full-suite regression**

Run: `python -m pytest -q`
Expected: 108 passed (baseline 100 + 8), nothing else broken.

- [ ] **Step 7: Commit**

```bash
git add templates/average_speed.py tests/test_average_speed.py engine/registry.py
git commit -m "feat(engine): add average-speed topic (scalar rate vs signed average velocity)"
```

---

### Task 2: `upward-throw` topic

**Files:**
- Create: `templates/upward_throw.py`
- Create: `tests/test_upward_throw.py`
- Modify: `engine/registry.py`

**Interfaces:**
- Consumes: `templates.base.Template`, `VarSpec`.
- Produces: `templates.upward_throw.UPWARD_THROW` (topic `"upward-throw"`, symbols `u v g t h`). No later task depends on it.

- [ ] **Step 1: Write the failing tests**

`tests/test_upward_throw.py`:

```python
"""Upward throw — free fall's signed extension, up-positive (code template).

Object thrown straight up: v = u - g*t, h = u*t - g*t^2/2, v^2 = u^2 - 2*g*h,
with g = 10 always given. v and h are signed relative to launch; flight is
constrained to h >= 0 (launch to return). Splits with two physical roots
(find t or v from a given height) are excluded — that needs multi-answer
support (tracked follow-up).
"""

import sympy

from engine import registry
from engine.errors import UnsolvableError
from engine.loop import generate
from harness.verify import verify_generic
from templates.upward_throw import UPWARD_THROW as TPL

G = {"g": 10}


def test_velocity_at_time_signs():
    """u=30: at t=2 still rising (v=+10); at t=4 falling (v=-10)."""
    up = generate("upward-throw", given=("u", "g", "t"), find="v",
                  conditions={"u": 30, "t": 2, **G}, difficulty="easy", seed=1)
    down = generate("upward-throw", given=("u", "g", "t"), find="v",
                    conditions={"u": 30, "t": 4, **G}, difficulty="easy", seed=1)
    assert up["find"]["exact"] == "10"
    assert down["find"]["exact"] == "-10"


def test_height_at_time():
    """u=30, t=2: h = 60 - 20 = 40 m above launch."""
    data = generate("upward-throw", given=("u", "g", "t"), find="h",
                    conditions={"u": 30, "t": 2, **G}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "40"
    assert data["find"]["unit"] == "m"


def test_time_to_top_via_v_zero():
    """Time to max height is the v=0 condition: u=30 -> t = 3 s."""
    data = generate("upward-throw", given=("u", "v", "g"), find="t",
                    conditions={"u": 30, "v": 0, **G}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "3"


def test_max_height_via_v_zero():
    """Max height is the v=0 condition on v^2 = u^2 - 2gh: u=30 -> h = 45 m."""
    data = generate("upward-throw", given=("u", "v", "g"), find="h",
                    conditions={"u": 30, "v": 0, **G}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "45"


def test_launch_speed_from_later_velocity():
    """v=-10 at t=4 -> u = v + g*t = 30."""
    data = generate("upward-throw", given=("v", "g", "t"), find="u",
                    conditions={"v": -10, "t": 4, **G}, difficulty="easy", seed=1)
    assert data["find"]["exact"] == "30"


def test_descending_velocities_occur_in_a_batch():
    negatives = 0
    for seed in range(40):
        data = generate("upward-throw", given=("u", "g", "t"), find="v",
                        difficulty="medium", seed=seed)
        if sympy.Rational(data["find"]["exact"]) < 0:
            negatives += 1
    assert negatives > 0


def test_speed_never_exceeds_launch_speed():
    """|v| <= u throughout flight (h >= 0)."""
    for seed in range(40):
        data = generate("upward-throw", given=("u", "g", "t"), find="v",
                        difficulty="hard", seed=seed)
        given = {x["symbol"]: sympy.Rational(x["exact"]) for x in data["given"]}
        assert abs(sympy.Rational(data["find"]["exact"])) <= given["u"]


def test_all_splits_verify_across_bands():
    splits = [(("u", "g", "t"), "v"), (("u", "g", "t"), "h"),
              (("u", "v", "g"), "t"), (("u", "v", "g"), "h"),
              (("v", "g", "t"), "u")]
    for given, find in splits:
        for band in ("easy", "medium", "hard"):
            for seed in range(4):
                data = generate("upward-throw", given=given, find=find,
                                difficulty=band, seed=seed)
                assert verify_generic(data, TPL, difficulty=band) is True


def test_two_root_splits_are_refused():
    """Time (or velocity) at a given height has two answers — rising and
    falling — which the single-answer engine cannot express."""
    for find in ("t", "v"):
        try:
            generate("upward-throw", given=("u", "g", "h"), find=find,
                     conditions={"u": 30, "h": 40, **G}, difficulty="easy", seed=1)
            assert False, f"expected UnsolvableError for (u,g,h) -> {find}"
        except UnsolvableError:
            pass


def test_exactly_five_valid_splits():
    splits = sorted(
        (tuple(sorted(s.name for s in given)), find.name)
        for given, find in TPL.valid_splits()
    )
    assert splits == sorted([
        (("g", "t", "u"), "v"), (("g", "t", "u"), "h"),
        (("g", "u", "v"), "t"), (("g", "u", "v"), "h"),
        (("g", "t", "v"), "u"),
    ])


def test_registered_and_loadable():
    assert "upward-throw" in registry.topics()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_upward_throw.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'templates.upward_throw'`

- [ ] **Step 3: Write the template**

`templates/upward_throw.py`:

```python
"""Upward throw — vertical motion under gravity, signed, up-positive.

The signed extension of the ``free-fall`` topic (which stays down-positive,
drop/thrown-down only). Here an object is launched straight up with speed
``u > 0``; **up is positive**, so gravity enters the relations with a minus
sign, the velocity ``v`` is positive while rising and negative while falling,
and ``h`` is the (non-negative) height above the launch point.

As in ``free-fall``, gravity is a dimensioned variable pinned to 10 and always
given — never solved for.

A **code template** because the split set must be a whitelist: solving for the
time (or velocity) at a *given height* has two physical roots — once rising,
once falling — which the v1 single-answer engine cannot express. Those splits
are excluded until multi-answer support lands (tracked follow-up); "time to
top" and "max height" remain expressible as the ``v = 0`` condition on the
linear relations.
"""

from __future__ import annotations

import sympy

from .base import Template, VarSpec

# -- symbols -------------------------------------------------------------------
u, v, g, t, h = sympy.symbols("u v g t h", real=True)
SYMBOLS = {"u": u, "v": v, "g": g, "t": t, "h": h}

# -- relations (up-positive: gravity pulls against the motion) -----------------
E_V = sympy.Eq(v, u - g * t)                    # velocity at time t
E_H_T = sympy.Eq(h, u * t - g * t**2 / 2)       # height at time t
E_V2 = sympy.Eq(v**2, u**2 - 2 * g * h)         # velocity-height (no time)
E_H_UV = sympy.Eq(h, (u + v) * t / 2)           # average-velocity form
EQUATIONS = [E_V, E_H_T, E_V2, E_H_UV]

# -- variables, units, per-difficulty ranges -----------------------------------
_U = {"easy": (10, 40, False), "medium": (10, 60, False), "hard": (10, 100, False)}
_V = {"easy": (0, 30, True), "medium": (0, 50, True), "hard": (0, 90, True)}
_G = {"easy": (10, 10, False), "medium": (10, 10, False), "hard": (10, 10, False)}
_T = {"easy": (1, 6, False), "medium": (1, 9, False), "hard": (1, 14, False)}
_H = {"easy": (0, 80, False), "medium": (0, 180, False), "hard": (0, 500, False)}

VARIABLES = {
    u: VarSpec("m/s", _U),
    v: VarSpec("m/s", _V),
    g: VarSpec("m/s^2", _G),
    t: VarSpec("s", _T),
    h: VarSpec("m", _H),
}

# -- split whitelist (all unique-answer; g always among the givens) ------------
_SPLITS = {
    (frozenset({u, g, t}), v): E_V,
    (frozenset({u, g, t}), h): E_H_T,
    (frozenset({u, v, g}), t): E_V,    # linear: t = (u - v)/g ("time to top" via v=0)
    (frozenset({u, v, g}), h): E_V2,   # linear in h ("max height" via v=0)
    (frozenset({v, g, t}), u): E_V,
}


def solvability(given, find):
    """Whitelisted unique-answer splits only.

    ``(u, g, h) -> t`` and ``(u, g, h) -> v`` are excluded on purpose: a height
    is reached twice (rising, then falling), so both solves have two physical
    roots — out of scope for the single-answer engine (multi-answer support is
    the tracked follow-up).
    """
    key = (frozenset(given), find)
    if key in _SPLITS:
        return (True, _SPLITS[key])
    if frozenset(given) == frozenset({u, g, h}):
        return (False, "time/velocity at a given height has two answers "
                       "(rising vs falling); needs multi-answer support")
    return (False, "not a whitelisted upward-throw split")


# -- root selection ------------------------------------------------------------
def root_select(values, find, difficulty):
    """Every whitelisted solve is linear — one real root; select physically.

    Time must be positive; height and launch speed non-negative (u > 0 is then
    enforced by constraint); the velocity keeps its sign — that is the point.
    """
    real = []
    for val in values:
        val = sympy.nsimplify(val)
        if val.is_real and val.is_number:
            real.append(val)
    if not real:
        return None
    if find is t:
        pos = [x for x in real if x.is_positive]
        return min(pos) if pos else None
    if find in (h, u):
        nonneg = [x for x in real if x.is_nonnegative]
        return min(nonneg) if nonneg else None
    return min(real, key=lambda x: (abs(float(x)), float(x)))  # v: signed


# -- plausibility constraints --------------------------------------------------
def _c_gravity_is_ten(values, difficulty):
    return g not in values or values[g] == 10


def _c_time_positive(values, difficulty):
    return t not in values or values[t].is_positive


def _c_launch_upward(values, difficulty):
    return u not in values or values[u].is_positive


def _c_height_above_launch(values, difficulty):
    return h not in values or values[h].is_nonnegative


def _c_within_flight(values, difficulty):
    """|v| <= u — equivalent to h >= 0; catches beyond-return samples on
    splits where h never appears (e.g. find v from u, g, t)."""
    if u in values and v in values:
        return bool(abs(values[v]) <= values[u])
    return True


CONSTRAINTS = [_c_gravity_is_ten, _c_time_positive, _c_launch_upward,
               _c_height_above_launch, _c_within_flight]


# -- the template object -------------------------------------------------------
UPWARD_THROW = Template(
    topic="upward-throw",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((u, g, t), v),
    signed_answer=True,  # v is negative while falling — the sign is direction
)
```

- [ ] **Step 4: Register** — add to `engine/registry.py` imports and `_REGISTRY`:

```python
from templates.upward_throw import UPWARD_THROW
# in _REGISTRY:
    UPWARD_THROW.topic: UPWARD_THROW,
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_upward_throw.py -v`
Expected: 11 passed. Watch `test_all_splits_verify_across_bands`: the constraint `_c_within_flight` re-rolls out-of-flight samples, so generation may take more attempts on hard — if a seed exhausts 200 attempts, bump that seed range down (documented tolerance: 4 seeds/band suffice).

Note on `test_velocity_at_time_signs`: `v = -10` with condition-pinned givens must satisfy `_c_within_flight` (10 ≤ 30 ✓) and `t=4 ≤` flight time (h(4) = 120 − 80 = 40 ≥ 0 — but h is not in values for this split, the `|v| ≤ u` bound is what admits it ✓).

- [ ] **Step 6: Full-suite regression**

Run: `python -m pytest -q`
Expected: 119 passed (108 + 11).

- [ ] **Step 7: Commit**

```bash
git add templates/upward_throw.py tests/test_upward_throw.py engine/registry.py
git commit -m "feat(engine): add upward-throw topic (signed vertical motion, up-positive)"
```

---

### Task 3: `multi-stage-motion` topic

**Files:**
- Create: `templates/multi_stage.py`
- Create: `tests/test_multi_stage.py`
- Modify: `engine/registry.py`

**Interfaces:**
- Consumes: `templates.base.Template`, `VarSpec`.
- Produces: `templates.multi_stage.MULTI_STAGE` (topic `"multi-stage-motion"`, symbols `u a t1 t2 v s`). **Task 5 imports from this module:** `SYMBOLS`, `VARIABLES`, `EQUATIONS`, `E_S_A`, `E_S_V`, `CONSTRAINTS`, `root_select`, and the symbols `u, a, t1, t2, v, s`.

- [ ] **Step 1: Write the failing tests**

`tests/test_multi_stage.py`:

```python
"""Two-phase 1-D motion: accelerate from u for t1, then cruise at v for t2.

Blocked for declarative templates by the single-equation solvability model;
here each whitelisted split maps to a composite equation whose free symbols are
exactly given ∪ {find} (the harness's linking-equation rule). Motion is
one-directional (v > 0), so distance equals displacement and the narrative
stays unambiguous.
"""

import sympy

from engine import registry
from engine.errors import NoCleanInstanceError, UnsolvableError
from engine.loop import generate
from harness.verify import verify_generic
from templates.multi_stage import MULTI_STAGE as TPL


def test_total_displacement_from_acceleration_form():
    """u=4, a=2, t1=3 (v reaches 10), cruise 5 s: s = 12 + 9 + 50 = 71 m."""
    data = generate("multi-stage-motion", given=("u", "a", "t1", "t2"), find="s",
                    conditions={"u": 4, "a": 2, "t1": 3, "t2": 5},
                    difficulty="easy", seed=1)
    assert data["find"]["exact"] == "71"
    assert data["find"]["unit"] == "m"


def test_total_displacement_from_velocity_form():
    """Same journey stated via v: u=4, v=10, t1=3, t2=5 -> s = 21 + 50 = 71 m."""
    data = generate("multi-stage-motion", given=("u", "v", "t1", "t2"), find="s",
                    conditions={"u": 4, "v": 10, "t1": 3, "t2": 5},
                    difficulty="easy", seed=1)
    assert data["find"]["exact"] == "71"


def test_deceleration_story():
    """u=30, a=-4 for 5 s (v=10), cruise 2 s: s = 150 - 50 + 20 = 120 m."""
    data = generate("multi-stage-motion", given=("u", "a", "t1", "t2"), find="s",
                    conditions={"u": 30, "a": -4, "t1": 5, "t2": 2},
                    difficulty="medium", seed=1)
    assert data["find"]["exact"] == "120"


def test_back_solves_for_v_and_u():
    v = generate("multi-stage-motion", given=("s", "u", "t1", "t2"), find="v",
                 conditions={"s": 71, "u": 4, "t1": 3, "t2": 5},
                 difficulty="easy", seed=1)
    u = generate("multi-stage-motion", given=("s", "v", "t1", "t2"), find="u",
                 conditions={"s": 71, "v": 10, "t1": 3, "t2": 5},
                 difficulty="easy", seed=1)
    assert v["find"]["exact"] == "10"
    assert u["find"]["exact"] == "4"


def test_direction_reversal_is_rerolled_not_emitted():
    """A deceleration that would reverse direction (v <= 0) violates the
    one-directional constraint; with everything pinned the loop must fail loudly
    rather than emit the unphysical story."""
    try:
        generate("multi-stage-motion", given=("u", "a", "t1", "t2"), find="s",
                 conditions={"u": 2, "a": -3, "t1": 4, "t2": 2},
                 difficulty="medium", seed=1)
        assert False, "expected NoCleanInstanceError (v = 2 - 12 < 0)"
    except NoCleanInstanceError:
        pass


def test_all_splits_verify_across_bands():
    splits = [(("u", "a", "t1", "t2"), "s"), (("u", "v", "t1", "t2"), "s"),
              (("s", "u", "t1", "t2"), "v"), (("s", "v", "t1", "t2"), "u")]
    for given, find in splits:
        for band in ("easy", "medium", "hard"):
            for seed in range(4):
                data = generate("multi-stage-motion", given=given, find=find,
                                difficulty=band, seed=seed)
                assert verify_generic(data, TPL, difficulty=band) is True


def test_phase_times_are_narrative_givens():
    """Solving for a phase duration is excluded (quadratic in t1; and the phase
    structure is the story, not the unknown)."""
    try:
        generate("multi-stage-motion", given=("s", "u", "a", "t2"), find="t1",
                 difficulty="easy", seed=1)
        assert False, "expected UnsolvableError for a phase-duration solve"
    except UnsolvableError:
        pass


def test_exactly_four_valid_splits():
    splits = sorted(
        (tuple(sorted(x.name for x in given)), find.name)
        for given, find in TPL.valid_splits()
    )
    assert splits == sorted([
        (("a", "t1", "t2", "u"), "s"), (("t1", "t2", "u", "v"), "s"),
        (("s", "t1", "t2", "u"), "v"), (("s", "t1", "t2", "v"), "u"),
    ])


def test_registered_and_loadable():
    assert "multi-stage-motion" in registry.topics()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_multi_stage.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'templates.multi_stage'`

- [ ] **Step 3: Write the template**

`templates/multi_stage.py`:

```python
"""Two-phase 1-D motion: uniform acceleration, then constant-velocity cruise.

Phase 1 accelerates from ``u`` with ``a`` for ``t1``, reaching ``v``; phase 2
cruises at ``v`` for ``t2``; ``s`` is the total displacement. Motion is kept
one-directional (``v > 0``), so distance equals displacement.

Blocked for declarative templates by the v1 single-equation solvability model;
written as a **code template** whose whitelisted splits each map to a
*composite* equation — the harness's linking-equation rule needs one equation
whose free symbols are exactly ``given ∪ {find}``:

* ``E_S_A`` links ``{s, u, a, t1, t2}`` (acceleration form)
* ``E_S_V`` links ``{s, u, v, t1, t2}`` (velocity/trapezoid form)
* ``E_V``   links ``{v, u, a, t1}``    (phase-1 SUVAT relation)

``E_S_V`` is ``E_S_A`` with ``a`` eliminated through ``E_V``, so the full
system stays consistent and uniquely determined from every allowed given-set
(what the fidelity harness's independent whole-system solve relies on).

Phase durations are narrative givens, never the unknown: solving ``E_S_A`` for
``t1`` is quadratic (two roots), and a pupil is told how long each phase lasts.
"""

from __future__ import annotations

import sympy

from .base import Template, VarSpec

# -- symbols -------------------------------------------------------------------
u, a, t1, t2, v, s = sympy.symbols("u a t1 t2 v s", real=True)
SYMBOLS = {"u": u, "a": a, "t1": t1, "t2": t2, "v": v, "s": s}

# -- relations -----------------------------------------------------------------
E_V = sympy.Eq(v, u + a * t1)
E_S_A = sympy.Eq(s, u * t1 + a * t1**2 / 2 + (u + a * t1) * t2)
E_S_V = sympy.Eq(s, (u + v) * t1 / 2 + v * t2)
EQUATIONS = [E_V, E_S_A, E_S_V]

# -- variables, units, per-difficulty ranges -----------------------------------
_U = {"easy": (0, 20, False), "medium": (0, 30, False), "hard": (0, 50, False)}
_A = {"easy": (1, 5, False), "medium": (1, 8, True), "hard": (1, 12, True)}
_T = {"easy": (1, 6, False), "medium": (1, 8, False), "hard": (1, 12, False)}
_VC = {"easy": (2, 20, False), "medium": (2, 40, False), "hard": (2, 80, False)}
_S = {"easy": (20, 150, False), "medium": (20, 400, False), "hard": (20, 1000, False)}

VARIABLES = {
    u: VarSpec("m/s", _U),
    a: VarSpec("m/s^2", _A),
    t1: VarSpec("s", _T),
    t2: VarSpec("s", _T),
    v: VarSpec("m/s", _VC),
    s: VarSpec("m", _S),
}

# -- split whitelist -----------------------------------------------------------
_SPLITS = {
    (frozenset({u, a, t1, t2}), s): E_S_A,
    (frozenset({u, v, t1, t2}), s): E_S_V,
    (frozenset({s, u, t1, t2}), v): E_S_V,  # linear in v
    (frozenset({s, v, t1, t2}), u): E_S_V,  # linear in u
}


def solvability(given, find):
    """Whitelisted splits only — each with a composite linking equation.

    Phase durations (``t1``, ``t2``) are never the find: the acceleration form
    is quadratic in ``t1`` (two roots), and the phase structure is part of the
    problem narrative, not the unknown.
    """
    key = (frozenset(given), find)
    if key in _SPLITS:
        return (True, _SPLITS[key])
    if find in (t1, t2):
        return (False, "phase durations are narrative givens, not solvable finds")
    return (False, "not a whitelisted multi-stage split")


# -- root selection ------------------------------------------------------------
def root_select(values, find, difficulty):
    """All whitelisted solves are linear — one real root, selected physically.

    ``s`` and ``v`` must be positive (one-directional motion); ``u`` may be
    zero (start from rest).
    """
    real = []
    for val in values:
        val = sympy.nsimplify(val)
        if val.is_real and val.is_number:
            real.append(val)
    if not real:
        return None
    if find is u:
        nonneg = [x for x in real if x.is_nonnegative]
        return min(nonneg) if nonneg else None
    pos = [x for x in real if x.is_positive]
    return min(pos) if pos else None


# -- plausibility constraints --------------------------------------------------
def _c_times_positive(values, difficulty):
    for sym in (t1, t2):
        if sym in values and not values[sym].is_positive:
            return False
    return True


def _c_start_nonneg(values, difficulty):
    return u not in values or values[u].is_nonnegative


def _c_cruise_forward(values, difficulty):
    """The cruise velocity stays positive — no direction reversal mid-story.

    ``v`` is not among the values on the acceleration-form splits, so it is
    reconstructed from ``u + a*t1`` there.
    """
    if v in values:
        return bool(values[v].is_positive)
    if all(x in values for x in (u, a, t1)):
        return bool(sympy.nsimplify(values[u] + values[a] * values[t1]).is_positive)
    return True


def _c_displacement_positive(values, difficulty):
    return s not in values or values[s].is_positive


CONSTRAINTS = [_c_times_positive, _c_start_nonneg, _c_cruise_forward,
               _c_displacement_positive]


# -- the template object -------------------------------------------------------
MULTI_STAGE = Template(
    topic="multi-stage-motion",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((u, a, t1, t2), s),
)
```

- [ ] **Step 4: Register** — add to `engine/registry.py`:

```python
from templates.multi_stage import MULTI_STAGE
# in _REGISTRY:
    MULTI_STAGE.topic: MULTI_STAGE,
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_multi_stage.py -v`
Expected: 9 passed. The risky one is `test_all_splits_verify_across_bands` on the back-solve splits (`s` is sampled as a given there): if seeds exhaust attempts (`NoCleanInstanceError`), tighten `_S` (e.g. easy `(20, 100)`) so sampled totals stay reachable, and re-run.

- [ ] **Step 6: Full-suite regression**

Run: `python -m pytest -q`
Expected: 128 passed (119 + 9).

- [ ] **Step 7: Commit**

```bash
git add templates/multi_stage.py tests/test_multi_stage.py engine/registry.py
git commit -m "feat(engine): add multi-stage-motion topic (two-phase: accelerate then cruise)"
```

---

### Task 4: `graph_spec` contract extension

**Files:**
- Modify: `templates/base.py` (one field on `Template`)
- Modify: `engine/contract.py:106-135` (`build_sympy_data`)
- Test: `tests/test_graph_contract.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `Template.graph_spec: Callable | None = None`; when set, `build_sympy_data` emits `sympy_data["graph"] = template.graph_spec(values)` where `values = inputs ∪ {find: value}` (keys are SymPy symbols, values exact SymPy numbers). The key is absent when the hook is `None`. Task 5 relies on exactly this.

- [ ] **Step 1: Write the failing test**

`tests/test_graph_contract.py`:

```python
"""The optional graph_spec hook: a template may attach engine-computed graph
data to sympy_data; every hook-less topic's contract is byte-identical to
before (no "graph" key)."""

import dataclasses

from engine import registry
from engine.loop import generate


def test_topics_without_hook_emit_no_graph_key():
    data = generate("suvat", difficulty="easy", seed=3)
    assert "graph" not in data


def test_hooked_template_emits_graph_payload():
    base = registry.load_template("suvat")
    seen = {}

    def spec(values):
        seen.update(values)
        return {"kind": "test", "n": len(values)}

    hooked = dataclasses.replace(base, graph_spec=spec)
    with registry.temporary(hooked):
        data = generate("suvat", difficulty="easy", seed=3)
    assert data["graph"] == {"kind": "test", "n": 4}  # 3 givens + the find
    find_sym = base.symbol(data["find"]["symbol"])
    assert find_sym in seen  # the hook sees the solved find, not just givens
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_graph_contract.py -v`
Expected: FAIL — `dataclasses.replace` raises `TypeError` (`graph_spec` is not a field) or the first test passes and the second errors.

- [ ] **Step 3: Add the field and the guarded emit**

In `templates/base.py`, after the `signed_answer` field of `Template`:

```python
    signed_answer: bool = False  # vector/direction topics: allow a negative answer
    graph_spec: Callable = None  # optional: values -> JSON-able graph payload ("graph" key)
```

In `engine/contract.py`, `build_sympy_data` — build the dict, emit the hook's payload only when present, then return:

```python
    data = {
        "topic": template.topic,
        "seed": seed,
        "given": given_out,
        "find": {"symbol": find.name, "value": to_display(value),
                 "exact": to_exact(value), "unit": find_unit},
        "steps": steps,
        "final_answer": {
            "value": to_display(value),
            "exact": to_exact(value),
            "unit": find_unit,
            "latex": _unit_latex(value, find_unit),
        },
        "policy_applied": policy.label,
        "plausible": bool(plausible),
    }
    if template.graph_spec is not None:
        values = dict(inputs)
        values[find] = value
        data["graph"] = template.graph_spec(values)
    return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_graph_contract.py -v`
Expected: 2 passed.

- [ ] **Step 5: Full-suite regression + commit**

Run: `python -m pytest -q` — Expected: 130 passed.

```bash
git add templates/base.py engine/contract.py tests/test_graph_contract.py
git commit -m "feat(contract): optional graph_spec hook on Template (additive 'graph' key)"
```

---

### Task 5: `motion-graphs` topic

**Files:**
- Create: `templates/motion_graphs.py`
- Create: `tests/test_motion_graphs.py`
- Modify: `engine/registry.py`

**Interfaces:**
- Consumes: from `templates.multi_stage`: `SYMBOLS`, `VARIABLES`, `E_S_A`, `E_S_V`, `EQUATIONS`, `CONSTRAINTS`, `root_select`, symbols `u, a, t1, t2, v, s`. From Task 4: `Template.graph_spec` + the `"graph"` contract key. From `engine.contract`: `to_display`, `to_exact`.
- Produces: `templates.motion_graphs.MOTION_GRAPHS` (topic `"motion-graphs"`). Emits `sympy_data["graph"]` shaped:
  `{"kind": "v-t", "axes": {"x": {"symbol": "t", "unit": "s"}, "y": {"symbol": "v", "unit": "m/s"}}, "points": [{"x": {"value", "exact"}, "y": {"value", "exact"}}, ...]}` — three points `(0, u), (t1, v), (t1+t2, v)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_motion_graphs.py`:

```python
"""Graph-reading questions over the two-phase scenario: the engine emits the
piecewise v–t polyline (exact values) in sympy_data["graph"]; rendering is the
web/TikZ track's job. Slope of phase 1 is a, area under the polyline is s."""

import sympy

from engine import registry
from engine.errors import UnsolvableError
from engine.loop import generate
from harness.verify import verify_generic
from templates.motion_graphs import MOTION_GRAPHS as TPL


def _exact_points(data):
    return [(sympy.Rational(p["x"]["exact"]), sympy.Rational(p["y"]["exact"]))
            for p in data["graph"]["points"]]


def test_graph_payload_shape_and_values():
    """u=4, a=2, t1=3, t2=5: polyline (0,4) -> (3,10) -> (8,10)."""
    data = generate("motion-graphs", given=("u", "a", "t1", "t2"), find="s",
                    conditions={"u": 4, "a": 2, "t1": 3, "t2": 5},
                    difficulty="easy", seed=1)
    assert data["graph"]["kind"] == "v-t"
    assert data["graph"]["axes"] == {"x": {"symbol": "t", "unit": "s"},
                                     "y": {"symbol": "v", "unit": "m/s"}}
    assert _exact_points(data) == [(0, 4), (3, 10), (8, 10)]
    assert data["find"]["exact"] == "71"


def test_area_under_polyline_equals_displacement():
    """Trapezoid + rectangle area == the emitted total displacement s."""
    for seed in range(20):
        data = generate("motion-graphs", given=("u", "a", "t1", "t2"), find="s",
                        difficulty="medium", seed=seed)
        (x0, y0), (x1, y1), (x2, y2) = _exact_points(data)
        area = (y0 + y1) * (x1 - x0) / 2 + y1 * (x2 - x1)
        assert area == sympy.Rational(data["find"]["exact"])


def test_slope_of_phase_one_equals_acceleration():
    """Rise over run of the first segment == a (the find of the slope split)."""
    for seed in range(20):
        data = generate("motion-graphs", given=("s", "u", "t1", "t2"), find="a",
                        difficulty="medium", seed=seed)
        (x0, y0), (x1, y1), _ = _exact_points(data)
        assert (y1 - y0) / (x1 - x0) == sympy.Rational(data["find"]["exact"])


def test_deceleration_graph_slopes_down():
    """A negative-a story yields a first segment that falls: y1 < y0."""
    data = generate("motion-graphs", given=("u", "a", "t1", "t2"), find="s",
                    conditions={"u": 30, "a": -4, "t1": 5, "t2": 2},
                    difficulty="medium", seed=1)
    (_, y0), (_, y1), _ = _exact_points(data)
    assert y1 < y0
    assert data["find"]["exact"] == "120"


def test_all_splits_verify_and_carry_the_graph():
    splits = [(("u", "a", "t1", "t2"), "s"), (("u", "v", "t1", "t2"), "s"),
              (("s", "u", "t1", "t2"), "v"), (("s", "v", "t1", "t2"), "u"),
              (("s", "u", "t1", "t2"), "a")]
    for given, find in splits:
        for band in ("easy", "medium", "hard"):
            for seed in range(3):
                data = generate("motion-graphs", given=given, find=find,
                                difficulty=band, seed=seed)
                assert verify_generic(data, TPL, difficulty=band) is True
                assert len(data["graph"]["points"]) == 3


def test_display_values_match_exact(subtests=None):
    from engine.contract import exact, to_display
    data = generate("motion-graphs", difficulty="medium", seed=7)
    for p in data["graph"]["points"]:
        for axis in ("x", "y"):
            assert to_display(exact(p[axis]["exact"])) == p[axis]["value"]


def test_exactly_five_valid_splits():
    splits = sorted(
        (tuple(sorted(x.name for x in given)), find.name)
        for given, find in TPL.valid_splits()
    )
    assert splits == sorted([
        (("a", "t1", "t2", "u"), "s"), (("t1", "t2", "u", "v"), "s"),
        (("s", "t1", "t2", "u"), "v"), (("s", "t1", "t2", "v"), "u"),
        (("s", "t1", "t2", "u"), "a"),
    ])


def test_classic_slope_split_stays_with_multi_stage():
    """find a from (u, v, t1) has no exact-symbol linking equation once t2 must
    be given for the graph; it is refused here (documented follow-up)."""
    try:
        generate("motion-graphs", given=("u", "v", "t1"), find="a",
                 difficulty="easy", seed=1)
        assert False, "expected UnsolvableError"
    except UnsolvableError:
        pass


def test_registered_and_loadable():
    assert "motion-graphs" in registry.topics()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_motion_graphs.py -v`
Expected: ERROR `ModuleNotFoundError: No module named 'templates.motion_graphs'`

- [ ] **Step 3: Write the template**

`templates/motion_graphs.py`:

```python
"""Motion graphs — graph-reading questions over the two-phase v–t scenario.

Same physics as ``multi-stage-motion`` (imported, not duplicated); registered
as its own topic so the web app phrases questions *from the graph*: the slope
of phase 1 is the acceleration, the area under the polyline is the total
displacement. The engine emits the graph's polyline — exact values, ADR-005
style — in ``sympy_data["graph"]`` via the ``graph_spec`` hook; rendering
belongs to the web/TikZ track.

The whitelist is narrower than multi-stage's for two reasons: a drawable graph
needs both phase durations among the givens, and the harness's linking-equation
rule needs an equation whose free symbols are exactly ``given ∪ {find}``. The
classic slope split — find ``a`` from ``(u, v, t1)`` — fails the second test
once ``t2`` joins the givens, so it stays a (non-graph) multi-stage question
until a term-based linking check exists (tracked follow-up). The graph version
of the slope question is find ``a`` from ``(s, u, t1, t2)`` via the
acceleration form.
"""

from __future__ import annotations

import sympy

from engine.contract import to_display, to_exact

from .base import Template
from .multi_stage import (CONSTRAINTS, E_S_A, E_S_V, EQUATIONS, SYMBOLS,
                          VARIABLES, a, s, t1, t2, u, v)
from .multi_stage import root_select as _multi_stage_root_select

# -- split whitelist (graph needs t1 and t2 given; exact-symbol-set equations) --
_SPLITS = {
    (frozenset({u, a, t1, t2}), s): E_S_A,   # area, acceleration form
    (frozenset({u, v, t1, t2}), s): E_S_V,   # area, trapezoid form
    (frozenset({s, u, t1, t2}), v): E_S_V,   # read the cruise level off the area
    (frozenset({s, v, t1, t2}), u): E_S_V,   # read the intercept off the area
    (frozenset({s, u, t1, t2}), a): E_S_A,   # slope of phase 1, via the area
}


def solvability(given, find):
    """Whitelisted graph-readable splits only (both phase durations given)."""
    key = (frozenset(given), find)
    if key in _SPLITS:
        return (True, _SPLITS[key])
    return (False, "not a whitelisted motion-graphs split "
                   "(a drawable graph needs t1 and t2 among the givens)")


# -- root selection ------------------------------------------------------------
def root_select(values, find, difficulty):
    """Delegate to multi-stage, except ``a`` — the slope is signed
    (deceleration graphs slope down)."""
    if find is a:
        real = []
        for val in values:
            val = sympy.nsimplify(val)
            if val.is_real and val.is_number:
                real.append(val)
        if not real:
            return None
        return min(real, key=lambda x: (abs(float(x)), float(x)))
    return _multi_stage_root_select(values, find, difficulty)


# -- the graph payload ---------------------------------------------------------
def _point(x, y):
    return {"x": {"value": to_display(x), "exact": to_exact(x)},
            "y": {"value": to_display(y), "exact": to_exact(y)}}


def graph_spec(values):
    """The v–t polyline ``(0, u) -> (t1, v) -> (t1+t2, v)``, exact.

    ``values`` holds ``given ∪ {find}`` only, so on the acceleration-form
    splits the cruise velocity is absent — it is derived exactly here
    (``v = u + a*t1``, SymPy arithmetic): engine-computed, invariant-safe.
    """
    uu, tt1, tt2 = values[u], values[t1], values[t2]
    vv = values[v] if v in values else sympy.nsimplify(uu + values[a] * tt1)
    return {
        "kind": "v-t",
        "axes": {"x": {"symbol": "t", "unit": "s"},
                 "y": {"symbol": "v", "unit": "m/s"}},
        "points": [_point(0, uu), _point(tt1, vv), _point(tt1 + tt2, vv)],
    }


# -- the template object -------------------------------------------------------
MOTION_GRAPHS = Template(
    topic="motion-graphs",
    symbols=SYMBOLS,
    variables=VARIABLES,
    equations=EQUATIONS,
    solvability=solvability,
    constraints=CONSTRAINTS,
    root_select=root_select,
    default_split=((u, a, t1, t2), s),
    signed_answer=True,  # the slope find (a) is negative on deceleration graphs
    graph_spec=graph_spec,
)
```

- [ ] **Step 4: Register** — add to `engine/registry.py`:

```python
from templates.motion_graphs import MOTION_GRAPHS
# in _REGISTRY:
    MOTION_GRAPHS.topic: MOTION_GRAPHS,
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_motion_graphs.py -v`
Expected: 10 passed. `test_all_splits_verify_and_carry_the_graph` includes the find-`a` split — the harness's `independent_solve` applies `TPL.root_select` (signed for `a`), which must agree with the generator; if (b) mismatches appear, the root policies diverged — fix `root_select`, not the test.

- [ ] **Step 6: Full-suite regression**

Run: `python -m pytest -q`
Expected: 140 passed (130 + 10).

- [ ] **Step 7: Live CLI smoke**

```bash
python -m engine --topic upward-throw --verify
python -m engine --topic motion-graphs --json | python -c "import json,sys; d=json.load(sys.stdin); print(d['graph'])"
```
Expected: first prints a problem with `data-fidelity verify: PASS`; second prints the three-point graph payload.

- [ ] **Step 8: Commit**

```bash
git add templates/motion_graphs.py tests/test_motion_graphs.py engine/registry.py
git commit -m "feat(engine): add motion-graphs topic (v-t polyline data + graph-reading splits)"
```

---

### Task 6: Coverage doc, push, PRs

**Files:**
- Modify: `../../../../Documents/linear-motion-coverage.html` (workspace `Documents/` — outside this repo; if edits there are rejected, write the updated copy to `docs/linear-motion-coverage.html` inside the repo instead and say so)
- Modify: `README.md` (repo layout section: mention the new templates)

- [ ] **Step 1: Update the coverage table** — statuses: Average speed → Done (`average-speed`), Free fall upward extension → Done except two-root splits (`upward-throw`), Multi-stage → Done for two-phase forward/back-solve splits (`multi-stage-motion`), Motion graphs → Done engine-side (`motion-graphs`, data + questions; rendering with the TikZ track). Update the "at a glance" percentages and add a "What was just added" entry per topic **including the how-to-test commands** (pytest per topic + `python -m engine --topic <t> --verify`).

- [ ] **Step 2: Full suite one last time**

Run: `python -m pytest -q` — Expected: 140 passed.

- [ ] **Step 3: Commit docs, push branch**

```bash
git add -A && git commit -m "docs: linear-motion coverage updated for the four new topics"
git push -u origin worktree-linear-motion-completion
```

- [ ] **Step 4: PRs** — `gh` is unavailable; report both compare URLs to the user:
- distance-displacement: `https://github.com/Jotelab/jotelab-ai/compare/main...worktree-linear-motion-vectors`
- this work (stacked): `https://github.com/Jotelab/jotelab-ai/compare/worktree-linear-motion-vectors...worktree-linear-motion-completion`

---

## Self-review notes (resolved)

- Spec coverage: Topic 1 → Task 1, Topic 2 → Task 2, Topic 3 → Task 3, contract extension → Task 4, Topic 4 → Task 5, docs/delivery → Task 6. Baseline test count verified in setup.
- Type consistency: Task 5 imports exactly what Task 3's module defines (`SYMBOLS, VARIABLES, EQUATIONS, E_S_A, E_S_V, CONSTRAINTS, root_select`, symbols). Task 5 relies on Task 4's `values = inputs ∪ {find: value}` contract, stated in both Interfaces blocks.
- Two-root exclusions are enforced *and tested* (`test_two_root_splits_are_refused`, `test_phase_times_are_narrative_givens`, `test_classic_slope_split_stays_with_multi_stage`).
