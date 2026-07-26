# System templates — design (composition layer, foundation)

- **Date:** 2026-07-27
- **Status:** approved (brainstorming dialogue; HTML presentation copy published alongside)
- **Series:** composition layer 1 of 2 — this foundation spec, then a scene-composition spec

## Motivation

The 55-problem exam-chapter audit showed the missed computational problems are not
20 scenario types but a few *composition patterns* over one primitive (a
uniform-acceleration stanza). The single blocker is the v1 single-equation
solvability contract: a split is valid only when ONE equation links
``given ∪ {find}``. That is why `multi_stage.py` hand-derives composite
equations and why pursuit (two bodies + a meet condition) is inexpressible.
This spec retires that restriction for declarative templates by letting a
template declare a small *simultaneous system* with internal unknowns.

Related work (see `related-work` report, 2026-07-27): Polozov et al. IJCAI'15
(equation model + constraints → generated word problems), Alvin et al. AAAI'14
(one declared scene → many verified given/goal variants), Andes/VanLehn
(scene + equation KB → solution graph; well-posedness gating), MathGAP ICLR'25
(compositional primitives; depth/width difficulty), GSM-Symbolic '24
(templated symbolic variants at scale).

## Locked decisions (dialogue)

1. **Scope:** foundation only (system templates); scene layer later, but its
   requirements bind this design as forward-constraints.
2. **Authoring:** today's JSON format + new optional `"auxiliary"` block;
   existing templates parse byte-identically.
3. **Solvability:** symbolic pre-derivation at parse/gate time; closed forms
   cached per root branch; generation substitutes numbers only.
4. **Contract:** minimal delta — optional `auxiliary` values array; steps stay
   single-step.

## Design

### 1. Authoring surface & discriminator

`"auxiliary"` (name → `{"unit": ...}`, no ranges) declares internal unknowns —
never given, never the find, never in `default_split`, ranges forbidden.
Presence of a non-empty `auxiliary` block switches the template onto the
system path; absence keeps the existing single-equation path untouched.
Equations may reference variables ∪ auxiliaries; the AST sandbox extends its
allow-list to auxiliary names, nothing else.

Proof-case document `templates/data/pursuit.json`:

```json
{
  "topic": "pursuit",
  "variables": {
    "gap": {"unit": "m",     "ranges": {"easy": [2, 20, false], "medium": [2, 60, false], "hard": [2, 100, false]}},
    "a":   {"unit": "m/s^2", "ranges": {"easy": [1, 4, false],  "medium": [1, 8, false],  "hard": [1, 10, false]}},
    "v":   {"unit": "m/s",   "ranges": {"easy": [2, 12, false], "medium": [2, 20, false], "hard": [2, 30, false]}},
    "t":   {"unit": "s",     "ranges": {"easy": [1, 10, false], "medium": [1, 20, false], "hard": [1, 30, false]}}
  },
  "auxiliary": {"x": {"unit": "m"}},
  "equations": ["Eq(x, v*t)", "Eq(x, gap + a*t**2/2)"],
  "root_policy": {"name": "smallest_positive_physical"},
  "constraints": [
    {"var": "t", "op": ">", "value": 0},
    {"var": "x", "op": ">", "value": 0},
    {"var": "v", "op": "abs<=", "value": 100}
  ],
  "default_split": {"given": ["gap", "a", "v"], "find": "t"},
  "golden_cases": [
    {"given": {"gap": 6, "a": 1, "v": "7/2"}, "find": "t", "difficulty": "easy", "expected": "3"}
  ],
  "trust_state": "unverified"
}
```

(Exact ranges above are the authoring starting point; tuning during
implementation is expected and does not require a spec change.)

### 2. Solvability semantics

**v1 restriction: system templates have no unused variables.** Every declared
variable is given or the find; auxiliaries are always solved. A candidate
split `(given, find)` is valid iff
`sympy.solve(equations, [find] + auxiliaries, dict=True)` — givens left
symbolic — returns ≥1 solution branch expressing the find in givens only.
Derived once at parse time; cached per branch: the find's closed form and
every auxiliary's closed form. `valid_splits()` enumerates find choices (rest
given), so pursuit auto-derives 4 splits (t, v, gap, a) with no authored
whitelist. Single-equation templates keep unused-variable support unchanged.
The scene compiler (later spec) emits exact active systems, so the
restriction is forward-compatible.

### 3. Generation loop

For system templates `_solve` substitutes the sampled givens into each cached
branch → candidate find values → existing named root policies select
(pursuit's t=3 over t=4 is `smallest_positive_physical` verbatim; the
signed-fallback keys compose unchanged). Auxiliaries are evaluated from the
**same branch** as the chosen find value — branches are never mixed. Two new
re-roll conditions in `_satisfies`:

- constraints may reference auxiliary names (`x > 0`);
- every auxiliary value must be an exact `Rational` (keeps the ADR-005
  fail-closed `exact()` parser sound; irrational auxiliary → re-roll).

Cleanliness policy applies to the find only, as today.

### 4. Contract delta

One optional, name-sorted array, emitted only by system templates:

```json
"auxiliary": [{"symbol": "x", "value": 10.5, "exact": "21/2", "unit": "m"}]
```

ADR-005 dual-form throughout. Steps stay a single step whose `expr_latex` is
the find's closed form in the givens. Zod: one optional field (web track).
`final_answer` unchanged — chains keep working with system-template parts.

### 5. Harness generalization

- **(a)** branches by kind: single-equation templates keep the
  linking-equation check verbatim; system templates assert **every**
  equation's residual is exactly 0 at the emitted values
  (given + find + auxiliaries).
- **(b)** stays the independent path: numeric whole-system solve from the
  givens, template root policy applied, compared against the emitted find
  **and** the emitted auxiliaries (same-branch consistency check).
- **(c)** canonical units extend to auxiliary entries; **(d)** constraints
  including auxiliary constraints; **(e)** display/exact consistency for
  auxiliary entries.

Generator uses parse-time closed forms; harness solves numerically at verify
time — two genuinely different code paths, as today.

### 6. Validation gate (same five stages)

1. **Parse & sandbox** — auxiliary block: units mandatory, names disjoint
   from variables, absent from `default_split`/golden givens; equations parse
   against variables ∪ auxiliaries.
2. **Dimensional homogeneity** — system checked with auxiliary units.
3. **Solvability derivation** — the symbolic pre-derivation; the default
   split must yield ≥1 closed form. Under/over-determined or symbolically
   unsolvable systems fail here with a typed `TemplateValidationError`.
4. **Golden-case replay** — unchanged; golden givens accept exact strings
   (`"7/2"`).
5. **Convergence + fidelity** — unchanged, through the real loop and the
   generalized oracle.

### 7. Error handling

No new generation-time failure modes: a bad branch or non-rational auxiliary
is a re-roll ending, at worst, in the existing `NoCleanInstanceError`. All new
structural failures are loud, typed, and happen at authoring time (gate
stages 1/3).

## Testing

- **Unit:** auxiliary parsing (accept/reject), split derivation incl. the 4
  pursuit splits, branch-consistent auxiliary evaluation, rational-auxiliary
  re-roll, sandbox rejection of undeclared names.
- **E2E (the audit's exam problems):**

  ```bash
  # PDF #15 — the bus problem, exact numbers (v = 7/2 via API/conditions file if CLI ints only)
  PYTHONPATH=. .venv/bin/python -m engine --topic pursuit --difficulty easy --verify
  PYTHONPATH=. .venv/bin/python -m templates.declarative templates/data/pursuit.json
  pytest tests/test_pursuit.py tests/test_system_templates.py
  ```

  The golden case pins `gap=6, a=1, v=7/2 → t=3 s`; a test asserts the t=4
  branch is present in the derivation and rejected by root selection.
- **Second system fixture:** a two-car meet document (#14 class) runs the gate
  end-to-end, proving the machinery is not pursuit-shaped by accident.
- **Harness negative test:** corrupting an emitted auxiliary must fail
  assertion (a).
- **Regression:** full suite green; `suvat.json` byte-parity untouched; gate
  PASS on all existing JSON templates.

## Out of scope (forward-constraints for the scene spec)

Segment primitives and the scene→system compiler; aggregates (total
distance, averages); multi-answer contract; graph synthesis from segment
lists; unused variables in systems; non-rational auxiliaries. The
`auxiliary` contract array is the designated vehicle for meet points and
phase boundaries in the scene layer.
