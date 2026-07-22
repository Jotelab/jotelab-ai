# Linear Motion completion — average-speed, upward-throw, multi-stage, motion-graphs

**Date:** 2026-07-23 · **Branch:** `worktree-linear-motion-completion` (stacked on
`worktree-linear-motion-vectors`, which holds the unmerged distance-displacement topic)

## Goal

Close the remaining gaps in the การเคลื่อนที่ในแนวตรง (Linear Motion) engine coverage
(`Documents/linear-motion-coverage.html`, 2026-07-15). After this work every sub-topic is either
implemented or explicitly documented as out of scope for the v1 single-answer engine:

| Sub-topic | This spec delivers |
| --- | --- |
| Average speed (scalar) | `average-speed` topic — two-segment path, speed vs velocity contrast |
| Free fall, upward throw | `upward-throw` topic — signed, up-positive, unique-answer splits only |
| Multi-stage motion | `multi-stage-motion` topic — two-phase (accelerate, then cruise) |
| Motion graphs | `motion-graphs` topic — piecewise v–t data in the contract + graph-reading questions |

All four are **code templates** (the `distance_displacement.py` pattern), not declarative JSON:
each needs something the declarative sandbox cannot express — `Abs` (average-speed), a split
whitelist that excludes two-root questions (upward-throw), composite per-split equations
(multi-stage, motion-graphs), or a contract extension (motion-graphs).

## Constraints the design honors

1. **Harness assertion (a)** (`harness/verify.py::_linking_equation`) requires, for every allowed
   split, one equation in `template.equations` whose free symbols are *exactly*
   `given ∪ {find}`. Multi-symbol topics therefore carry composite equations per split.
2. **Single-answer engine**: any (given, find) pair whose solve has two physical roots is
   excluded via the solvability whitelist and documented, per the coverage doc's known
   limitation. No multi-answer contract work in this spec.
3. **Signed machinery** (`signed_answer`, `signed_physical` roots) is reused as-is from the
   vectors-1d work; no engine/policy changes are needed for topics 1–3.
4. **Fidelity harness (b)** re-solves the *full* equation system, so every topic's equation set
   must be mutually consistent and uniquely determine the find from each allowed given-set.

## Topic 1 — `average-speed` (`templates/average_speed.py`)

The scalar-vs-vector *rate* lesson, completing what distance-displacement did for path length.

- Symbols: `d1, d2` (signed segments, m), `t` (total time, s, > 0), `sp` (average speed, m/s),
  `vavg` (average velocity, m/s).
- Equations: `Eq(sp, (Abs(d1) + Abs(d2))/t)` and `Eq(vavg, (d1 + d2)/t)`.
- Solvability: given exactly `{d1, d2, t}`, find `sp` or `vavg`. Nothing else (inverting `Abs`
  is the same two-branch problem distance-displacement excludes).
- `signed_answer=True` (vavg carries direction; out-and-back gives `vavg = 0` while `sp > 0`).
- Constraints: `t > 0`, `sp ≥ 0`, and `sp ≥ |vavg|` (invariant, mirrors dist ≥ |disp|).
- Ranges mirror `_SEG` from distance-displacement; `t` mirrors vectors-1d's time bands.

## Topic 2 — `upward-throw` (`templates/upward_throw.py`)

Free fall's signed extension: object thrown straight up. **Up-positive** convention (the
existing `free-fall` topic stays down-positive and untouched).

- Symbols: `u` (launch speed, > 0), `v` (signed velocity), `g` (= 10, always given, never
  solved), `t` (> 0), `h` (height above launch, ≥ 0).
- Equations: `Eq(v, u - g*t)`, `Eq(h, u*t - g*t**2/2)`, `Eq(v**2, u**2 - 2*g*h)`,
  `Eq(h, (u + v)*t/2)`.
- Split whitelist (all unique-answer):
  - given `{u, g, t}` find `v` (linear) — velocity at time t, sign = direction
  - given `{u, g, t}` find `h` — height at time t
  - given `{u, v, g}` find `t` (linear: `t = (u−v)/g`) — includes *time to top* via condition `v=0`
  - given `{u, v, g}` find `h` (linear in `h`) — includes *max height* via condition `v=0`
  - given `{v, g, t}` find `u` (linear)
  - **Excluded**: find `t` or `v` from `{u, g, h}` — two roots (rising vs falling); needs
    multi-answer support (tracked follow-up, unchanged from the coverage doc).
- Constraints: `g == 10`, `u > 0`, `t > 0`, `h ≥ 0` (within flight, launch to return),
  `|v| ≤ u` (energy bound; equivalent to `h ≥ 0`, cheap redundancy for the harness).
- `signed_answer=True`; root policy keeps signed `v`, enforces `t > 0` via constraints.
- Subtlety: `v` may be sampled as a *given* (e.g. find `t`); its range must allow negative
  draws (`signed=True`) so descending cases occur, while `u`'s draws stay positive.

## Topic 3 — `multi-stage-motion` (`templates/multi_stage.py`)

Two-phase 1-D motion: phase 1 accelerates uniformly from `u` with `a` for `t1`, phase 2 cruises
at the reached velocity `v` for `t2`. One-directional (`v > 0`, `u ≥ 0`) so distance =
displacement and the story stays unambiguous.

- Symbols: `u, a, t1, t2, v, s` (s = total displacement).
- Equations (composites give the harness its exact-symbol-set linking equations):
  - `E_V`: `Eq(v, u + a*t1)`
  - `E_S_A`: `Eq(s, u*t1 + a*t1**2/2 + (u + a*t1)*t2)` — links `{s, u, a, t1, t2}`
  - `E_S_V`: `Eq(s, (u + v)*t1/2 + v*t2)` — links `{s, u, v, t1, t2}`
- Split whitelist: find `s` from `{u,a,t1,t2}` (E_S_A) or `{u,v,t1,t2}` (E_S_V); find `v` from
  `{u,a,t1}` (E_V); find `u` from `{s,v,t1,t2}` (E_S_V, linear); find `a` from `{u,v,t1}`
  (E_V, linear). Finding `t1`/`t2` from the composites is excluded (quadratic in `t1`, and
  pedagogically the phase durations are narrative givens).
- Constraints: `t1 > 0`, `t2 > 0`, `u ≥ 0`, `v > 0`, `s > 0`. `a` signed at medium+
  (deceleration stories) — the `v > 0` constraint re-rolls any sample that reverses direction.
- Consistency: E_S_V is E_S_A with `a` eliminated via E_V, so harness (b)'s full-system solve
  is uniquely determined from every allowed given-set.

## Topic 4 — `motion-graphs` (`templates/motion_graphs.py` + contract extension)

Graph-*reading* questions over the same two-phase scenario; the engine emits the graph's data,
the web/TikZ track renders it (per scope decision — no TikZ generated here).

- Template: same symbols/equations as `multi-stage-motion` (imported from `multi_stage.py`,
  not duplicated), registered as its own topic so the web app can phrase questions as
  "from the v–t graph…" (slope = a, area = s).
- Whitelist — narrower than multi-stage, for two reasons: a drawable graph needs both phase
  durations among the givens, and harness (a) needs an exact-symbol-set linking equation.
  Five splits qualify, all linear/unique: find `s` from `{u,a,t1,t2}` (E_S_A) or
  `{u,v,t1,t2}` (E_S_V); find `v` from `{s,u,t1,t2}` (E_S_V); find `u` from `{s,v,t1,t2}`
  (E_S_V); find `a` from `{s,u,t1,t2}` (E_S_A). The classic slope split — find `a` from
  `{u,v,t1}` — has no exact-match equation once `t2` joins the givens, so it stays a
  `multi-stage-motion` (non-graph) question; noted as a follow-up for a term-based harness.
- Contract extension (additive, backward-compatible):
  - `Template` gains `graph_spec: Callable | None = None` (default None — no other topic
    changes).
  - `contract.build_sympy_data` emits `sympy_data["graph"] = template.graph_spec(values)`
    when the hook is set; the key is absent for every other topic, so the existing web Zod
    schema and all persisted rows are unaffected.
  - `motion_graphs.graph_spec(values)` returns
    `{"kind": "v-t", "axes": {"x": {"symbol": "t", "unit": "s"}, "y": {"symbol": "v", "unit": "m/s"}}, "points": [[0, u], [t1, v], [t1+t2, v]]}`
    with exact-string values (ADR-005 style: exact strings, display floats derived).
  - Note: `values` at build time holds `given ∪ {find}` only, so `v` is absent for e.g.
    find `s` from `{u,a,t1,t2}`. `graph_spec` derives the cruise velocity exactly
    (`v = u + a·t1`, SymPy arithmetic) when it is not in `values` — engine-computed, so the
    invariant (every emitted number originates in the symbolic layer) holds.
- Harness: a topic-specific check asserts the emitted points satisfy `points[1][1] - points[0][1] = a·t1`
  and that the trapezoid+rectangle area equals `s` — done in the topic's pytest file (the
  generic harness stays generic).

## Registration & files

- `engine/registry.py`: import and register the four templates (code templates register like
  SUVAT/distance-displacement — direct entries in `_REGISTRY`).
- New: `templates/average_speed.py`, `templates/upward_throw.py`, `templates/multi_stage.py`,
  `templates/motion_graphs.py`; `tests/test_average_speed.py`, `tests/test_upward_throw.py`,
  `tests/test_multi_stage.py`, `tests/test_motion_graphs.py`.
- Touched: `templates/base.py` (one optional field), `engine/contract.py` (one guarded emit),
  `engine/registry.py`.
- Docs: update the coverage table in `Documents/linear-motion-coverage.html` at the end
  (all-green except the documented two-root exclusions), including how-to-test commands.

## Testing

Each topic's pytest file follows `test_distance_displacement.py`: every whitelisted split
generated and `verify_generic`-fidelity-checked across all three difficulty bands; sign
correctness (negative `v` after apex, `vavg = 0` out-and-back, deceleration stories);
constraint enforcement (times positive, `h ≥ 0`, `sp ≥ |vavg|`); excluded splits raise
`UnsolvableError`. Motion-graphs adds the graph-consistency checks (slope/area) and asserts
`"graph" not in sympy_data` for other topics (contract regression).

How to test (from the worktree, venv active):

```
python -m pytest tests/test_average_speed.py tests/test_upward_throw.py \
                 tests/test_multi_stage.py tests/test_motion_graphs.py -v
python -m pytest -q                          # full suite — SUVAT et al. stay green
python -m engine --topic upward-throw --verify    # live generation + fidelity PASS
python -m engine --topic motion-graphs --json     # inspect the emitted graph field
```

## Out of scope (documented follow-ups, unchanged)

- Multi-answer support (time/velocity at height h on the way up vs down).
- TikZ rendering of the graph (web track; the engine emits data only).
- Average speed over *n* > 2 segments; three-phase motion.
- The units-gate subtraction fix and fraction-rendering polish (tracked separately).

## Delivery

Two draft PRs against `Jotelab/jotelab-ai`:
1. `worktree-linear-motion-vectors` → `main` — distance-displacement (already pushed).
2. `worktree-linear-motion-completion` → `worktree-linear-motion-vectors` (stacked) — this spec.

Each topic lands as its own commit in feasibility order (average-speed → upward-throw →
multi-stage → motion-graphs), so whatever is reviewed by the 2026-07-30 freeze can ship.
