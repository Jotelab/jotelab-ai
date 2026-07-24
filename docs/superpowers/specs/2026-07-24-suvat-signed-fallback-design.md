# SUVAT signed-fallback root selection — design

- **Date:** 2026-07-24
- **Status:** approved (brainstorming dialogue, this session)
- **Sub-project:** 1 of 3 (engine restrictions: signed finds → irrational answers → multi-answer)

## Motivation

A coverage audit against a real university-entrance chapter (55 linear-motion
problems) showed the engine fully recreates 4. Three more (#6 average
deceleration a = −10, #28 catch velocity v = −8, #29 rooftop displacement
s = −150) are blocked by exactly one mechanism: SUVAT's root selection
discards every negative candidate, even at medium/hard where the sampled
*givens* may already be negative and the clean-answer policy already permits
negative values (`require_positive=False`). The physical filter
(`_is_physical_value`) admits negative candidates at medium/hard today; the
selection ladder (smallest positive → non-negative fallback → give up) is the
sole blocker.

## Decision

**Signed fallback, opt-in, medium/hard only.** For direction-carrying finds
(`v`, `s`, `a` — never `t`), when *no* positive root exists, accept the
negative candidate with the smallest magnitude. Easy stays all-positive.
Where a positive root exists it still always wins, so every instance the
engine generates today is generated identically after this change.

Rejected alternatives:

- *Fully signed selection (`signed_physical`) at medium/hard* — changes the
  pick where ± roots coexist (e.g. `v² = u² + 2as`), where the sign is
  genuinely narrative-ambiguous; risks golden cases and the fine-tune corpus.
- *Per-split opt-in flag* — most precise, but grows the template schema and
  every future author's burden for marginal benefit.

## Design

### 1. Code path — `templates/suvat.py::root_select`

After the existing non-negative fallback branch:

```python
negative = [val for val in physical if val.is_negative]
if negative and difficulty != "easy" and find in (v, s, a):
    return max(negative)   # smallest magnitude; exact SymPy comparison
```

`max` of negatives is the smallest-magnitude pick — deterministic, no float
key. Linear solves (the only splits that reach the fallback in practice)
yield a single candidate. `t` keeps strict positivity via
`_is_physical_value`, unchanged.

### 2. Declarative path — `templates/declarative/roots.py`

`_smallest_positive_physical` gains the same fallback, driven by two new
**optional** policy keys:

```json
"root_policy": {
  "name": "smallest_positive_physical",
  "nonneg_fallback_vars": ["u", "s", "v"],
  "signed_fallback_vars": ["v", "s", "a"],
  "signed_fallback_difficulties": ["medium", "hard"]
}
```

- `signed_fallback_vars` — find names eligible for a negative answer.
- `signed_fallback_difficulties` — bands where the fallback is active;
  defaults to `["medium", "hard"]` when `signed_fallback_vars` is present.
- Both keys absent → byte-identical behavior to today (all existing JSON
  templates unaffected).

### 3. Schema — `templates/declarative/parse.py`

Accept (and type-check) the two new optional `root_policy` keys. No gate
changes: the five stages re-run as-is.

### 4. Data — `templates/data/suvat.json`

Declare the two new keys so the JSON twin keeps behavioral parity with
`suvat.py`.

## What deliberately does not change

- `engine/loop.py`, `engine/policy.py` — medium/hard tiers already set
  `require_positive=False`; easy never reaches the fallback.
- `engine/contract.py` — `Rational("-8")` round-trips exactly (ADR-005 holds).
- `harness/verify.py` — assertion (b) calls `template.root_select` itself, so
  the independent recompute inherits the fallback automatically.
- Sampling ranges — Basic mode already reaches negative finds via signed `a`
  draws at medium/hard; negative *givens* stay Advanced-mode pins.
- `free-fall` (down-positive by construction), `upward-throw` (already
  signed), and the easy band.

## Error handling

No new failure modes. When the fallback also finds nothing, selection returns
`None` → re-roll → existing `NoCleanInstanceError`.

## Testing

- **Unit (both root-select implementations):** lone negative root accepted at
  medium/hard for `v`/`s`/`a`; rejected at easy; rejected for `t`; positive
  root still wins when present; smallest-magnitude pick among two negatives.
- **End-to-end regression (the three exam problems, exact numbers):**

  ```bash
  python -m engine --given u,v,t --find a --condition u=30 --condition v=10 --condition t=2 --difficulty medium --verify   # a = -10
  python -m engine --given a,s,t --find v --condition a=-10 --condition s=4 --condition t=2 --difficulty medium --verify   # v = -8
  python -m engine --given u,a,t --find s --condition u=5  --condition a=-10 --condition t=6 --difficulty medium --verify  # s = -150
  ```

  Each must print the expected answer and `data-fidelity verify: PASS`.
- **Parity:** extend the code-vs-JSON parity suite with seeded medium
  negative-find cases; `suvat.py` and `suvat.json` must produce identical
  `sympy_data`.
- **Suite + gate:**

  ```bash
  pytest                                                   # full suite green
  python -m templates.declarative templates/data/suvat.json  # 5-stage gate all-pass
  ```

## Out of scope

Irrational (√) answers (sub-project 2), multi-answer contract (sub-project 3),
Thai phrasing of negative values (LLM track), negative sampled ranges for
`s`/`u`/`v`.
