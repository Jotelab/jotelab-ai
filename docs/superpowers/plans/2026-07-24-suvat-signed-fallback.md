# SUVAT Signed-Fallback Root Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At medium/hard difficulty, SUVAT accepts a negative answer for direction-carrying finds (`v`, `s`, `a` — never `t`) when no positive root exists, in both the code template and its declarative JSON twin.

**Architecture:** Extend the existing `smallest_positive_physical` selection ladder (positive → non-negative fallback → **new: signed fallback** → None) in the two places it is implemented: `templates/suvat.py::root_select` (code path) and `templates/declarative/roots.py::_smallest_positive_physical` (declarative path, driven by two new optional policy keys). `templates/data/suvat.json` declares the keys to keep byte parity. Nothing else changes: the loop, policy tiers, contract, harness, and sampling are already negative-safe at medium/hard.

**Tech Stack:** Python 3.13 (`.venv/bin/python`), SymPy, pytest.

**Spec:** `docs/superpowers/specs/2026-07-24-suvat-signed-fallback-design.md`

## Global Constraints

- Absent the new policy keys, declarative behavior must be **byte-identical** to today; existing suvat.json golden case must replay unchanged.
- Positive root always wins when one exists; fallback fires only when there is no positive (and no applicable non-negative) root.
- Easy band never produces a negative answer; `t` is never negative at any band.
- Among multiple negative candidates pick smallest magnitude — `max(negatives)` — with exact SymPy comparison, no float keys.
- Run everything from the worktree root with `.venv/bin/python` (venv lives in the main checkout; use `PYTHONPATH=.` — see note below). All 156 existing tests must stay green.

**Command note:** the worktree has no `.venv`; every command below uses the main checkout's interpreter with the worktree on the path, e.g.
`PYTHONPATH=. /home/thanakorn/Projects/Jotelab-Project/jotelab-ai/jotelab-ai/.venv/bin/python -m pytest ...`
Abbreviated below as `$PY -m pytest ...` where `PY=/home/thanakorn/Projects/Jotelab-Project/jotelab-ai/jotelab-ai/.venv/bin/python` and cwd is the worktree root.

---

### Task 1: Code-path signed fallback (`templates/suvat.py`)

**Files:**
- Modify: `templates/suvat.py:85-108` (the `root_select` function)
- Test: `tests/test_suvat_signed_fallback.py` (create)

**Interfaces:**
- Consumes: `templates.suvat.root_select(values, find, difficulty)`, module symbols `u, v, a, t, s`.
- Produces: `root_select` returning a negative SymPy number at medium/hard for finds `v`/`s`/`a` when no positive root exists. Task 4's e2e tests and Task 3's parity cases rely on this exact behavior.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_suvat_signed_fallback.py`:

```python
"""Signed-fallback root selection for SUVAT (spec 2026-07-24)."""

import sympy

from templates.suvat import a, root_select, s, t, u, v


def test_lone_negative_v_accepted_at_medium():
    assert root_select([sympy.Integer(-8)], v, "medium") == -8


def test_lone_negative_s_accepted_at_hard():
    assert root_select([sympy.Integer(-150)], s, "hard") == -150


def test_lone_negative_a_accepted_at_medium():
    assert root_select([sympy.Integer(-10)], a, "medium") == -10


def test_negative_rejected_at_easy():
    assert root_select([sympy.Integer(-8)], v, "easy") is None


def test_negative_t_always_rejected():
    assert root_select([sympy.Integer(-3)], t, "medium") is None


def test_negative_u_not_eligible():
    # u is not a signed-fallback variable (a launch speed's sign is a
    # narrative choice, not a solved direction).
    assert root_select([sympy.Integer(-5)], u, "medium") is None


def test_positive_root_still_wins_over_negative():
    assert root_select([sympy.Integer(-8), sympy.Integer(3)], v, "medium") == 3


def test_smallest_magnitude_negative_picked():
    assert root_select([sympy.Integer(-8), sympy.Integer(-3)], v, "medium") == -3


def test_speed_cap_still_applies_to_negative_v():
    assert root_select([sympy.Integer(-500)], v, "medium") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$PY -m pytest tests/test_suvat_signed_fallback.py -v`
Expected: `test_lone_negative_v_accepted_at_medium`, `test_lone_negative_s_accepted_at_hard`, `test_lone_negative_a_accepted_at_medium`, `test_smallest_magnitude_negative_picked` FAIL (root_select returns None); the easy/t/u/positive/cap tests already PASS (they assert existing behavior).

- [ ] **Step 3: Implement the fallback**

In `templates/suvat.py`, replace the tail of `root_select` (currently the `nonneg` block followed by `return None`) with:

```python
    nonneg = [val for val in physical if val.is_nonnegative]
    if nonneg and find in (u, s, v):
        return min(nonneg)
    # Signed fallback (spec 2026-07-24): at medium/hard a direction-carrying
    # find may be negative when no positive root exists. `t` stays strictly
    # positive via _is_physical_value; easy stays all-positive.
    negative = [val for val in physical if val.is_negative]
    if negative and difficulty != "easy" and find in (v, s, a):
        return max(negative)  # smallest magnitude, exact comparison
    return None
```

Also update the `root_select` docstring's convention sentence to:

```python
    """Pick the physical root from candidate solved values.

    Convention (locked in build guide §3, extended by the 2026-07-24 signed-
    fallback spec): evaluate all real roots at the sampled inputs, discard
    non-physical ones, and take the **smallest strictly positive real root**.
    When none exists: a lone non-negative root is allowed for ``u``/``s``/``v``
    (zero is legitimate), and at medium/hard a negative root (smallest
    magnitude) is allowed for the direction-carrying finds ``v``/``s``/``a``.
    Returns ``None`` (a failed roll) if none survive.
    """
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_suvat_signed_fallback.py tests/test_suvat.py -v`
Expected: all PASS (including the existing suvat suite — no behavior change where a positive root exists).

- [ ] **Step 5: Commit**

```bash
git add templates/suvat.py tests/test_suvat_signed_fallback.py
git commit -m "feat(suvat): signed-fallback root selection at medium/hard"
```

---

### Task 2: Declarative-path signed fallback (`templates/declarative/roots.py`)

**Files:**
- Modify: `templates/declarative/roots.py:49-62` (`_smallest_positive_physical`; new config helper above it)
- Test: `tests/test_declarative_roots.py` (append)

**Interfaces:**
- Consumes: `make_root_select(policy, constraints)` (existing entry point; `parse.py` wraps its `ValueError` into a stage-1 `TemplateValidationError` — no parse.py change needed).
- Produces: two optional `root_policy` keys consumed by Task 3's `suvat.json`:
  - `"signed_fallback_vars"`: list of variable-name strings; eligible finds.
  - `"signed_fallback_difficulties"`: optional list ⊆ `["easy","medium","hard"]`; defaults to `["medium","hard"]` when vars are present. Invalid types/values raise `ValueError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_declarative_roots.py`:

```python
SIGNED_POLICY = {
    "name": "smallest_positive_physical",
    "nonneg_fallback_vars": ["u", "s", "v"],
    "signed_fallback_vars": ["v", "s", "a"],
    "signed_fallback_difficulties": ["medium", "hard"],
}


def _signed_rs(policy=None):
    return make_root_select(policy or SIGNED_POLICY,
                            compile_constraints(SPECS, SYMS))


def test_signed_fallback_lone_negative_v_at_medium():
    assert _signed_rs()([sympy.Integer(-8)], v, "medium") == -8


def test_signed_fallback_rejected_at_easy():
    assert _signed_rs()([sympy.Integer(-8)], v, "easy") is None


def test_signed_fallback_never_applies_to_t():
    assert _signed_rs()([sympy.Integer(-3)], t, "medium") is None


def test_signed_fallback_positive_still_wins():
    assert _signed_rs()([sympy.Integer(-8), sympy.Integer(3)], v, "medium") == 3


def test_signed_fallback_smallest_magnitude():
    assert _signed_rs()([sympy.Integer(-8), sympy.Integer(-3)], v, "medium") == -3


def test_signed_fallback_absent_keys_keeps_old_behavior():
    assert _rs()([sympy.Integer(-8)], v, "medium") is None


def test_signed_fallback_difficulties_default_medium_hard():
    policy = {k: val for k, val in SIGNED_POLICY.items()
              if k != "signed_fallback_difficulties"}
    rs = _signed_rs(policy)
    assert rs([sympy.Integer(-8)], v, "medium") == -8
    assert rs([sympy.Integer(-8)], v, "easy") is None


def test_signed_fallback_vars_must_be_string_list():
    with pytest.raises(ValueError):
        _signed_rs({**SIGNED_POLICY, "signed_fallback_vars": "v"})


def test_signed_fallback_bad_difficulty_rejected():
    with pytest.raises(ValueError):
        _signed_rs({**SIGNED_POLICY,
                    "signed_fallback_difficulties": ["extreme"]})


def test_signed_fallback_difficulties_require_vars():
    policy = {"name": "smallest_positive_physical",
              "signed_fallback_difficulties": ["medium"]}
    with pytest.raises(ValueError):
        _signed_rs(policy)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$PY -m pytest tests/test_declarative_roots.py -v`
Expected: the new `test_signed_fallback_lone_negative_v_at_medium`, `test_signed_fallback_smallest_magnitude`, `test_signed_fallback_difficulties_default_medium_hard`, and all three validation tests FAIL; existing tests and the absent-keys/easy/t/positive tests PASS.

- [ ] **Step 3: Implement config parsing + fallback**

In `templates/declarative/roots.py`, add below the imports:

```python
_DIFFICULTIES = {"easy", "medium", "hard"}


def _signed_fallback_config(policy):
    """Validate and normalize the optional signed-fallback policy keys."""
    names = policy.get("signed_fallback_vars")
    if names is None:
        if "signed_fallback_difficulties" in policy:
            raise ValueError(
                "signed_fallback_difficulties requires signed_fallback_vars")
        return set(), set()
    if (not isinstance(names, list) or not names
            or not all(isinstance(n, str) for n in names)):
        raise ValueError(
            "signed_fallback_vars must be a non-empty list of variable names")
    bands = policy.get("signed_fallback_difficulties", ["medium", "hard"])
    if (not isinstance(bands, list) or not bands
            or not set(bands) <= _DIFFICULTIES):
        raise ValueError("signed_fallback_difficulties must be a non-empty "
                         "subset of easy/medium/hard")
    return set(names), set(bands)
```

Replace `_smallest_positive_physical` with:

```python
def _smallest_positive_physical(policy, constraints):
    fallback = set(policy.get("nonneg_fallback_vars", []))
    signed_vars, signed_bands = _signed_fallback_config(policy)

    def root_select(values, find, difficulty):
        physical = _physical_candidates(values, find, difficulty, constraints)
        positive = [x for x in physical if x.is_positive]
        if positive:
            return min(positive)
        nonneg = [x for x in physical if x.is_nonnegative]
        if nonneg and find.name in fallback:
            return min(nonneg)
        # Signed fallback (spec 2026-07-24): a direction-carrying find may be
        # negative in the declared bands when no positive root exists.
        negative = [x for x in physical if x.is_negative]
        if negative and find.name in signed_vars and difficulty in signed_bands:
            return max(negative)  # smallest magnitude, exact comparison
        return None

    return root_select
```

Update the module docstring's `smallest_positive_physical` bullet by appending:

```
  Optional signed fallback (spec 2026-07-24): with ``signed_fallback_vars``
  (and ``signed_fallback_difficulties``, default medium+hard) a declared
  find may take a negative root — smallest magnitude — when no positive
  root exists.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$PY -m pytest tests/test_declarative_roots.py tests/test_declarative_parse.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/declarative/roots.py tests/test_declarative_roots.py
git commit -m "feat(declarative): signed_fallback_vars root-policy keys"
```

---

### Task 3: Declare keys in `suvat.json` + parity for negative finds

**Files:**
- Modify: `templates/data/suvat.json:17` (the `root_policy` line)
- Test: `tests/test_declarative_parity.py` (append)

**Interfaces:**
- Consumes: Task 1's code-path fallback and Task 2's policy keys — both must pick identical roots for identical inputs.
- Produces: a `suvat.json` whose parsed template is behaviorally identical to `templates.suvat.SUVAT` including negative finds; Task 4 relies on the registered code template only, so no cross-task type contract beyond the JSON file itself.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_declarative_parity.py`:

```python
def test_parity_holds_for_negative_finds():
    # The three exam-problem shapes the signed fallback exists for
    # (spec 2026-07-24): a = -10, v = -8, s = -150.
    data_tpl = parse_template(json.loads(SUVAT_JSON.read_text()))
    cases = [
        (["u", "v", "t"], "a", {"u": 30, "v": 10, "t": 2}, "-10"),
        (["a", "s", "t"], "v", {"a": -10, "s": 4, "t": 2}, "-8"),
        (["u", "a", "t"], "s", {"u": 5, "a": -10, "t": 6}, "-150"),
    ]
    for given, find, conds, expected in cases:
        code_out = generate("suvat", given=given, find=find, conditions=conds,
                            difficulty="medium", seed=7)
        with registry.temporary(data_tpl):
            data_out = generate("suvat", given=given, find=find,
                                conditions=conds, difficulty="medium", seed=7)
        assert code_out["final_answer"]["exact"] == expected
        assert (json.dumps(code_out, sort_keys=True)
                == json.dumps(data_out, sort_keys=True))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PY -m pytest tests/test_declarative_parity.py::test_parity_holds_for_negative_finds -v`
Expected: FAIL — the code path already returns `-10`/`-8`/`-150` (Task 1) but the JSON template (keys not yet declared) raises `NoCleanInstanceError` inside `registry.temporary`, or the byte comparison fails.

- [ ] **Step 3: Declare the keys**

In `templates/data/suvat.json` replace the `root_policy` line with:

```json
  "root_policy": {"name": "smallest_positive_physical", "nonneg_fallback_vars": ["u", "s", "v"], "signed_fallback_vars": ["v", "s", "a"], "signed_fallback_difficulties": ["medium", "hard"]},
```

- [ ] **Step 4: Run tests + the five-stage gate**

Run: `$PY -m pytest tests/test_declarative_parity.py tests/test_suvat_json_loads.py tests/test_validation_gate.py -v`
Expected: all PASS (full-batch byte parity, golden-case replay, gate stages).

Run: `PYTHONPATH=. $PY -m templates.declarative templates/data/suvat.json`
Expected: per-stage PASS report, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add templates/data/suvat.json tests/test_declarative_parity.py
git commit -m "feat(suvat.json): declare signed-fallback policy keys, parity-tested"
```

---

### Task 4: End-to-end exam-problem regressions

**Files:**
- Test: `tests/test_signed_fallback_e2e.py` (create)

**Interfaces:**
- Consumes: `engine.loop.generate`, `harness.verify.verify_generic`, `engine.registry.load_template` — all unchanged public APIs; Task 1's fallback behavior.
- Produces: regression coverage tying the feature to the three real entrance-exam problems (PDF #6/#28/#29).

- [ ] **Step 1: Write the tests**

Create `tests/test_signed_fallback_e2e.py`:

```python
"""The three entrance-exam problems the signed fallback recovers.

Each generates with the problem's exact numbers at medium difficulty and must
pass the full Data-Fidelity battery (a)-(e). Source: coverage audit of a
55-problem linear-motion chapter (spec 2026-07-24, Motivation).
"""

import pytest

from engine.loop import generate
from engine.registry import load_template
from harness.verify import verify_generic


CASES = [
    # (label, given, find, conditions, expected exact answer, unit)
    ("average deceleration", ["u", "v", "t"], "a",
     {"u": 30, "v": 10, "t": 2}, "-10", "m/s^2"),
    ("catch velocity", ["a", "s", "t"], "v",
     {"a": -10, "s": 4, "t": 2}, "-8", "m/s"),
    ("rooftop displacement", ["u", "a", "t"], "s",
     {"u": 5, "a": -10, "t": 6}, "-150", "m"),
]


@pytest.mark.parametrize("label,given,find,conds,expected,unit", CASES)
def test_exam_problem_generates_and_verifies(label, given, find, conds,
                                             expected, unit):
    data = generate("suvat", given=given, find=find, conditions=conds,
                    difficulty="medium", seed=1)
    assert data["final_answer"]["exact"] == expected, label
    assert data["final_answer"]["unit"] == unit, label
    assert verify_generic(data, load_template("suvat"),
                          difficulty="medium") is True, label


def test_easy_band_still_refuses_negative_finds():
    from engine.errors import NoCleanInstanceError
    with pytest.raises(NoCleanInstanceError):
        generate("suvat", given=["a", "s", "t"], find="v",
                 conditions={"a": -10, "s": 4, "t": 2},
                 difficulty="easy", seed=1, max_attempts=25)
```

- [ ] **Step 2: Run the tests**

Run: `$PY -m pytest tests/test_signed_fallback_e2e.py -v`
Expected: all PASS (Tasks 1-3 already landed the behavior; this task pins it to the exam problems).

- [ ] **Step 3: Spot-check the CLI (the spec's documented commands)**

```bash
PYTHONPATH=. $PY -m engine --given u,v,t --find a --condition u=30 --condition v=10 --condition t=2 --difficulty medium --verify
PYTHONPATH=. $PY -m engine --given a,s,t --find v --condition a=-10 --condition s=4 --condition t=2 --difficulty medium --verify
PYTHONPATH=. $PY -m engine --given u,a,t --find s --condition u=5 --condition a=-10 --condition t=6 --difficulty medium --verify
```

Expected: answers `-10 m/s^2`, `-8 m/s`, `-150 m`, each with `data-fidelity verify: PASS`, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add tests/test_signed_fallback_e2e.py
git commit -m "test: e2e regressions for the three signed-fallback exam problems"
```

---

### Task 5: Full-suite verification

**Files:** none (verification only).

**Interfaces:**
- Consumes: everything above.
- Produces: a green tree ready for push/PR.

- [ ] **Step 1: Run the full test suite**

Run: `$PY -m pytest`
Expected: all tests pass (156 pre-existing + ~24 new), 0 failures.

- [ ] **Step 2: Run the gate one final time**

Run: `PYTHONPATH=. $PY -m templates.declarative templates/data/suvat.json`
Expected: five-stage PASS report, exit 0.

- [ ] **Step 3: Confirm clean tree**

Run: `git status --short`
Expected: empty (all work committed in Tasks 1-4).

---

## Self-Review (done at authoring time)

- **Spec coverage:** design §1 → Task 1; §2 → Task 2; §3 → Task 2 (validation lives in `make_root_select`, wrapped by parse's existing `ValueError` → stage-1 path — `parse.py` needs no diff, matching the spec's "accept and type-check" intent); §4 → Task 3; Testing section → Tasks 1-5 inclusive (unit both paths, e2e exact numbers, parity, suite + gate).
- **Placeholder scan:** none — every step carries complete code/commands.
- **Type consistency:** `root_select(values, find, difficulty)` signature identical across both paths; policy keys spelled `signed_fallback_vars` / `signed_fallback_difficulties` everywhere; expected exacts `-10`/`-8`/`-150` consistent across Tasks 3-4.
