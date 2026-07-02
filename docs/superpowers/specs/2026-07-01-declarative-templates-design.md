# Declarative Templates + 5-Stage Validation Gate — Design (ADR-007, engine side)

**Date:** 2026-07-01
**Status:** Approved (design)
**Implements:** ADR-007 (User-authored topic templates are declarative data validated by an automated gate)
**Repo:** `jotelab-ai` (SymPy engine only)

## Goal

Make a topic template **declarative JSON data** — never user-supplied Python — parsed by
the engine into today's `templates.base.Template` and admitted to the registry only after
passing a fixed, five-stage automated validation gate. Prove the design by re-expressing the
`suvat` topic as declarative data and showing **byte-for-byte fidelity parity** with the
existing code template.

This is the engine-side scope of ADR-007 sub-decisions (a), (b), (c), and (f). The
`TEMPLATES` database table, trust-state promotion rules, and authoring UI (parts of (e) and
the open questions) live in the separate `physics-jotelab` app and are **out of scope** here;
`trust_state` is parsed and carried as a field only.

## Core principle: the hot path is untouched

`Template` (the frozen dataclass), `engine/loop.py`, `engine/contract.py`,
`engine/sampling.py`, and `engine/policy.py` stay **exactly as they are**. The new layer
*compiles* a declarative JSON document into today's `Template` object — generating the
`solvability`, `root_select`, and `constraints` callables from declarative fields. No user
Python ever executes (ADR sub-decision (a)).

## Approaches considered

- **A — Declarative layer that compiles to the existing `Template` (chosen).** New
  `templates/declarative/` subpackage; `Template`/`loop` unchanged; the harness gains a
  topic-generic verification path.
- **B — Extend `Template` to natively hold declarative fields.** Rejected: mutates the
  dataclass and the loop; violates ADR (a) ("the dataclass and the whole downstream loop are
  unchanged").
- **C — One monolithic parser module.** Rejected: the unit checker, constraint DSL,
  root-policy enum, and 5-stage gate are naturally separate units; one file would grow
  unfocused.

## Component layout

```
templates/declarative/
  __init__.py      # public API: parse_template(doc)->Template, validate_template(doc)->Report
  parse.py         # Stage 1: safe sympify of equation strings against declared symbols
                   #          + operator/function allow-list; builds the Template.
                   #          Auto-derives solvability (ADR b) via single-equation enumeration.
  units.py         # Stage 2: unit-string -> sympy.physics dimension; equation homogeneity
  constraints.py   # constraint DSL ({"var","op","value","difficulty?","scope?"}) -> predicates
  roots.py         # named root-policy enum (v1: "smallest_positive_physical")
  gate.py          # the 5-stage validator; returns a per-stage pass/fail Report
templates/data/
  suvat.json       # SUVAT re-expressed as declarative data (the parity target)
harness/verify.py  # add verify_generic(sympy_data, template, difficulty); suvat.verify delegates
engine/errors.py   # add TemplateValidationError (typed, with failing stage + reason)
tests/
  test_declarative_parse.py    # stage 1 parsing + sandbox rejection
  test_declarative_units.py    # stage 2 dimensional homogeneity
  test_validation_gate.py      # full 5-stage gate: accepts suvat.json, rejects bad templates
  test_declarative_parity.py   # THE exit gate: byte-for-byte parity vs code SUVAT
```

## The declarative schema (JSON, canonical)

```json
{
  "topic": "suvat",
  "variables": {
    "u": {"unit": "m/s",   "ranges": {"easy": [0,20,false], "medium": [0,40,false], "hard": [0,40,false]}},
    "v": {"unit": "m/s",   "ranges": {"easy": [0,30,false], "medium": [0,60,false], "hard": [0,60,false]}},
    "a": {"unit": "m/s^2", "ranges": {"easy": [1,10,false], "medium": [1,15,true],  "hard": [1,15,true]}},
    "t": {"unit": "s",     "ranges": {"easy": [1,10,false], "medium": [1,20,false], "hard": [1,20,false]}},
    "s": {"unit": "m",     "ranges": {"easy": [1,50,false], "medium": [1,150,false],"hard": [1,150,false]}}
  },
  "equations": [
    "Eq(v, u + a*t)",
    "Eq(s, u*t + a*t**2/2)",
    "Eq(v**2, u**2 + 2*a*s)",
    "Eq(s, (u + v)*t/2)",
    "Eq(s, v*t - a*t**2/2)"
  ],
  "root_policy": {"name": "smallest_positive_physical", "nonneg_fallback_vars": ["u", "s", "v"]},
  "constraints": [
    {"var": "t", "op": ">",     "value": 0},
    {"var": "u", "op": "abs<=", "value": 100},
    {"var": "v", "op": "abs<=", "value": 100},
    {"var": "a", "op": "!=",    "value": 0},
    {"var": "u", "op": ">=",    "value": 0, "difficulty": "easy"},
    {"var": "v", "op": ">=",    "value": 0, "difficulty": "easy"},
    {"var": "s", "op": ">=",    "value": 0, "difficulty": "easy"},
    {"var": "a", "op": ">=",    "value": 0, "difficulty": "easy", "scope": "root"}
  ],
  "default_split": {"given": ["u", "a", "t"], "find": "v"},
  "golden_cases": [
    {"given": {"u": 0, "a": 2, "t": 5}, "find": "v", "difficulty": "easy", "expected": "10"}
  ],
  "trust_state": "unverified"
}
```

### Field notes

- **`variables`** — maps directly onto `VarSpec(unit, ranges)`. `ranges` values are
  `[lo, hi, signed]`. Units are **mandatory** (input to stage 2).
- **`equations`** — SymPy relation **strings**, parsed with `sympy.sympify` against a
  namespace containing only the declared symbols plus an allow-list.
- **`root_policy`** — a named enum, not code. v1 offers `smallest_positive_physical`, which
  reproduces SUVAT's convention ("smallest strictly-positive physical real, with a
  non-negative fallback for the declared vars").
- **`constraints`** — the predicate DSL (below). Replaces both the template's `constraints`
  list and the per-`find` physical filter (`_is_physical_value`) in `templates/suvat.py`.
- **`default_split`** — Basic-mode split; must be a valid derived split (stage 3).
- **`golden_cases`** — author-supplied worked examples for stage 4.
- **`trust_state`** — `"unverified"` | `"verified"`, carried as a field only; promotion is
  app-side.

## Constraint DSL — `constraints.py`

Each constraint is `{"var": <name>, "op": <op>, "value": <number>, "difficulty"?: <band>, "scope"?: <scope>}`.

- **Ops:** `>`, `>=`, `<`, `<=`, `==`, `!=`, `abs<=`, `abs<`, `abs>=`, `abs>`.
- **`difficulty`** (optional) — the constraint only applies at that band (default: all bands).
- **`scope`** (optional, default `"both"`) — where the predicate applies:
  - `"loop"`  — the loop's post-hoc plausibility check (`template.constraints`), evaluated on
    the full `values` dict.
  - `"root"`  — the per-`find` physical filter used by the root policy when choosing among
    candidate roots (mirrors `_is_physical_value`).
  - `"both"`  — both (the common case).

The `scope` flag exists to capture the **one asymmetry** between SUVAT's `_is_physical_value`
and its `CONSTRAINTS`: `_is_physical_value` rejects a negative `a` on the `easy` band when `a`
is the `find`, but `_c_easy_nonneg` (the loop constraint) does not include `a`. That single
predicate is `scope: "root"`; every other SUVAT constraint is `scope: "both"`.

Compilation produces two things:
1. A `constraints` list of `predicate(values, difficulty) -> bool` callables (the `loop`/`both`
   predicates) — the exact shape `Template.constraints` expects.
2. A per-`find` physical filter `is_physical(value, find, difficulty) -> bool` (the `root`/`both`
   predicates) — consumed by the root policy.

## Root policy — `roots.py`

`smallest_positive_physical(nonneg_fallback_vars)` builds a `root_select(values, find,
difficulty)` callable that reproduces `templates/suvat.py::root_select` exactly:

1. `nsimplify` each candidate; keep real numbers.
2. Drop candidates failing the per-`find` physical filter (from the constraint DSL, `root`/`both` scope).
3. If any strictly-positive candidate remains, return the smallest.
4. Else, if `find` ∈ `nonneg_fallback_vars` and a non-negative candidate remains, return the
   smallest such.
5. Else return `None` (failed roll).

## Parser — `parse.py` (Stage 1 machinery)

`parse_template(doc) -> Template`:

1. Validate the doc shape (required keys, types).
2. Build the symbol table: one `sympy.Symbol(name, real=True)` per declared variable.
3. `sympify` each equation string against a namespace of **only** those symbols plus an
   allow-list (`Eq`, `sqrt`, and the arithmetic operators `+ - * / **`). Any unknown
   name/attribute/callable → `TemplateValidationError` (stage 1 failure). No `eval`.
4. Build `VarSpec`s from `variables`.
5. Compile the constraint DSL and root policy.
6. **Auto-derive `solvability` (ADR b):** the callable enumerates the single-equation split
   (given ∪ {find} relates via the equation that excludes the one unused variable), matching
   SUVAT's v1 single-equation semantics. Reuses the same idea as `Template.valid_splits()`.
7. Assemble and return the `Template`.

## The 5-stage gate — `gate.py`

`validate_template(doc) -> Report` runs all stages, collecting per-stage pass/fail + reason,
and only reports overall-pass when **every** stage passes. `register_declarative(doc)` calls
it and registers the parsed `Template` on all-pass, else raises `TemplateValidationError`
naming the failing stage.

| # | Stage | Implementation | Proves / cannot prove |
|---|-------|----------------|-----------------------|
| 1 | Parse & sandbox | `parse.py` (above). | Input is safe + well-formed. Not that it is physics. |
| 2 | Dimensional homogeneity | `units.py`: map each var's unit → `sympy.physics.units` dimension; assert each `Eq` is dimensionally homogeneous. | Necessary condition. Catches `v = u + a·t²`; cannot catch a dropped ½. |
| 3 | Solvability derivation | Compute valid splits; require `default_split` ∈ them. Reuses `Template.valid_splits()`. | The template can generate. |
| 4 | Golden-case replay | For each golden case, solve at the exact inputs via the same engine path and assert the answer equals `expected` **exactly** (ADR-005 `exact()`). | Catches dimensionally-valid-but-wrong — only if the author's expected answer is itself right. |
| 5 | Convergence + fidelity | Generate N instances/band through the real `loop.generate()`; assert no `NoCleanInstanceError` and `verify_generic()` → 100%. | Re-roll converges; self-consistency. Not physical truth. |

## Unit / dimension checking — `units.py`

- A small unit-string parser maps declared unit strings (`"m/s"`, `"m/s^2"`, `"m"`, `"s"`) to
  `sympy.physics.units` quantities/dimensions. Supports `*`, `/`, `^`/`**` and the base
  high-school units needed for SUVAT (metre, second) plus derived combinations.
- For each equation, substitute each symbol with a unit-carrying quantity of its declared
  dimension and assert both sides reduce to the same dimension (dimensionally homogeneous).
- Unknown/unparseable units → stage-2 failure with a clear message.

## Generic Data-Fidelity verification — `harness/verify.py`

Add `verify_generic(sympy_data, template, difficulty)` that generalizes today's SUVAT-specific
`verify()` to any parsed `Template`:

- **(a)** the linking equation holds for the emitted values (found from the template's equations);
- **(b)** an independent recompute — solve the full equation system for `find`, apply the
  template's `root_select` — a path independent of the generator's single-equation solve;
- **(c)** units match the template's declared canonical units;
- **(d)** the template's plausibility constraints hold;
- **(e)** display `value` agrees with the authoritative `exact` string, and
  `final_answer.exact == find.exact` (ADR-005).

The existing `suvat.verify()` delegates to `verify_generic(..., load_template("suvat"))`, so
its behavior and all current tests are preserved.

## The parity exit gate — `test_declarative_parity.py`

The single test that ratifies ADR-007 v1:

1. Load the code `SUVAT` (from `templates.suvat`) and the parsed `suvat.json`.
2. Run the **entire** `harness.batches.suvat_batch()` (every valid split × every difficulty ×
   many seeds) through `loop.generate()` against **both** templates, using identical
   seeds/splits/difficulties.
3. Assert the emitted `sympy_data` dicts are **byte-for-byte identical** (equal JSON).
4. Assert `verify_generic()` → 100% on the data-template batch.

Byte-for-byte identity requires the declarative `root_select` and `constraints` to reproduce
SUVAT's exact selection algorithm — including the non-negative fallback and the per-`find`
physical filter. Reproducing these precisely is the core correctness task; the `scope` flag in
the constraint DSL is what makes it expressible.

## Errors

`engine/errors.py` gains `TemplateValidationError(EngineError)` carrying the failing stage
number/name and a human-readable reason, so the (future) orchestrator can surface exactly why
a submitted template was rejected.

## Narrowed invariant (ADR d)

ADR-007 narrows the ADR-001 invariant from "correct physics" to "arithmetically-exact solution
of a dimensionally-consistent, golden-verified equation set". The full doc updates (ADR-001
status note, System Design, PRD, benchmark plan) live in the docs repo and are follow-ups
there. In *this* repo, add a one-line note to `README.md` pointing at the narrowing so the
engine's own headline blurb does not overstate the guarantee for user-authored templates.

## Explicitly out of scope (belongs to `physics-jotelab`)

- The `TEMPLATES` database table and threading `trust_state` through persistence.
- `unverified` → `verified` promotion rules (evidence, quorum, credit economy).
- Any authoring UI / equation editor / guided form.
- Public template library, moderation, spam/abuse handling.
- YAML front-end (JSON is canonical; a YAML loader can be added app-side later).

## Testing strategy

- **TDD per component:** parse (+ sandbox rejection), units (homogeneity + failure), each gate
  stage, then the parity test last as the integrating exit gate.
- **Regression:** all 27 existing tests must continue to pass unchanged (the hot path is
  untouched; `suvat.verify()` delegates).
- **Gate red-team:** the gate must *reject* a template with a dimensionally-inconsistent
  equation (`Eq(v, u + a*t**2)`), a golden case that doesn't replay, an unknown symbol/callable
  in an equation, and a `default_split` that isn't derivable.
```
