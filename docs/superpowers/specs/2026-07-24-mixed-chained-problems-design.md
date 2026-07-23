# Mixed (Chained) Single Problems — Design

**Date:** 2026-07-24
**Status:** Approved (chained-parts approach chosen over fused single-question)

## Goal

Let one generated problem instance span more than one topic template. A **mixed
problem** is an ordered chain of 2+ **parts**, each a normal single-topic
instance produced by the existing `engine.loop.generate`. The answer of part
*i* is pinned as one declared given of part *i+1* (the **link**).

Why chained (not fused): the Data Fidelity harness's linking-equation rule
requires one equation whose free symbols are exactly `given ∪ {find}`
(`harness/verify.py:_linking_equation`). Chaining keeps every part
single-equation, so the whole existing generate/verify machinery applies
unchanged per part; the chain layer only adds link validation, bounded
re-rolling, and link verification. Fused multi-topic questions remain the
hand-written composite-template pattern (`templates/multi_stage.py`).

## API — new module `engine/chain.py`

```python
def generate_chain(parts, difficulty="easy", seed=0,
                   max_chain_attempts=20) -> dict:
```

`parts` is a list of dicts:

```python
[{"topic": "free-fall"},                                            # part 1
 {"topic": "suvat", "given": ["u","a","t"], "find": "s",
  "receive": "u"}]                                                  # part 2+
]
```

* `topic` — required, any registered topic (code or declarative).
* `given` / `find` — optional; the template's `default_split` when omitted.
* `receive` — required on every part after the first (may be auto-resolved,
  see CLI): the given symbol that takes the previous part's answer.

### Validation (before any generation; loud, typed)

* Fewer than 2 parts → `ChainSpecError`.
* `receive` missing/not among that part's givens → `ChainSpecError`.
* Unit of `receive` ≠ unit of the previous part's find →
  `IncompatibleLinkError` (message names both units).

Both new errors live in `engine/errors.py` and subclass `EngineError`.

### Generation algorithm (bounded, deterministic)

For chain attempt `k` in `range(max_chain_attempts)`:

1. Generate part 1 with `generate(..., seed=derive(seed, k, 0))`.
2. For each subsequent part *i*: `generate(..., seed=derive(seed, k, i),
   conditions={receive: <exact answer of part i-1>})` merged over any caller
   conditions for that part.
3. If any part raises `NoCleanInstanceError`, abandon the chain attempt and
   re-roll from part 1 with the next derived seed.

`derive(seed, k, i)` is a fixed arithmetic mix (e.g. `seed + 1000*k + i`) so
the whole chain is reproducible from the single `seed`. After
`max_chain_attempts` failures, re-raise `NoCleanInstanceError` for the part
that failed last.

### Supporting change — exact pinned conditions

`engine/sampling.py` currently coerces pinned conditions with
`sympy.Integer(spec)`; a link value can be a non-integer exact number (e.g.
`7/2`). Change the coercion to `sympy.nsimplify(spec)`. Backwards compatible:
integers remain `sympy.Integer`.

## Emitted contract

```json
{"topic": "mixed", "topics": ["free-fall", "suvat"],
 "seed": 7, "policy_applied": "easy",
 "parts": [<sympy_data>, <sympy_data>],
 "links": [{"from_part": 0, "to_part": 1, "symbol": "u", "exact": "30"}],
 "final_answer": <parts[-1]["final_answer"]>}
```

Each element of `parts` is an **unmodified** per-topic `sympy_data`, so
existing consumers (web/TikZ rendering, per-part verification) work as-is.
The chain's `final_answer` is the last part's.

## Verification — `verify_chain` in `harness/verify.py`

1. For every part: `verify_generic(part, load_template(part["topic"]),
   difficulty)` — the full (a)–(e) fidelity battery.
2. For every link: the receiving given's `exact` in `parts[to_part]` equals
   `parts[from_part]["final_answer"]["exact"]` — compared symbolically
   (`sympy.simplify(a - b) == 0`), plus unit equality.
3. Raises `FidelityError` on any failure; returns `True` otherwise.

## CLI

Repeatable `--part` flag on `python -m engine` (mutually exclusive with
`--topic/--given/--find/--condition`):

```
--part TOPIC[:given,csv:find[:receive]]
```

* `--part free-fall --part suvat:u,a,t:s:u` — explicit split and link.
* Omitted split → template default split.
* Omitted `receive` → auto-picked when exactly one given of that part is
  unit-compatible with the previous find; otherwise a loud error listing the
  candidates.
* `--verify` runs `verify_chain`; `--json` prints the chain contract;
  human rendering prints each part (existing renderer) plus a link line
  between parts.

## Testing

New `tests/test_chain.py`:

* link value flows exactly (receiving given's exact == feeding answer's exact);
* unit-incompatible link → `IncompatibleLinkError` before generation;
* bad specs (1 part, unknown `receive`) → `ChainSpecError`;
* determinism: same seed → identical chain JSON;
* bounded failure: impossible downstream constraints raise
  `NoCleanInstanceError` after `max_chain_attempts`;
* generate+verify sweep across bands for at least two topic pairs
  (free-fall→suvat, upward-throw→average-speed or similar);
* CLI: `--part` happy path and ambiguity error.

How to test (also goes in README "Running"):

```bash
pytest tests/test_chain.py -v
python -m engine --part free-fall --part suvat:u,a,t:s:u --verify
python -m engine --part free-fall --part suvat:u,a,t:s:u --json
```

## Out of scope (v1)

* Branching chains (one answer feeding two parts) — linear chains only.
* Declarative JSON authoring of chain specs (chains are caller-specified;
  declarative *topics* participate as parts already).
* Fused single-question composition — stays the hand-written composite
  template pattern.
* Web-app schema/rendering of the `mixed` contract — engine + harness only.
