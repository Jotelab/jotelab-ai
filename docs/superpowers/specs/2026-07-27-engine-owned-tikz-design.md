# Engine-Owned TikZ Diagrams — Design

**Date:** 2026-07-27
**Status:** Approved (engine-authored diagram spec; no web-side fallback)
**Scope:** All nine linear-motion topics
**Spans:** `jotelab-ai` (this repo) + `physics-jotelab` (web)

## Goal

Move authorship of diagram geometry and every glyph in it from the LLM to the
symbolic engine. After this change the LLM owns **Thai prose only**; the engine
owns every number a student sees, in the solution *and* in the figure.

This deletes the second half of the stated invariant
(`DEVELOPMENT_PLAN.md:21`, `README.md:9`): *"the LLM never computes — it only
phrases Thai text and emits TikZ."* The clause "and emits TikZ" goes away, and
with it the Phase 3.1 fine-tune target `sympy_data → Thai prose + TikZ`.

### Why this is smaller than it sounds

The shipped web code already refuses LLM-authored diagrams:
`modelCalculationOutputSchema` (`features/generate/schemas.ts:163`) strips
`tikz_code`, and the diagram is a deterministic TypeScript template
(`lib/tikz/templates/suvat.ts`) derived from `sympy_data` on read (ADR-007).

So the live change is **relocating the authoring seam** from TypeScript into
Python, not inverting runtime behaviour. What genuinely changes for a student:
diagrams gain **real numeric labels**, and eight topics that had no diagram get
one.

## Decision 1 — the contract: `sympy_data["diagram"]`

The engine emits a small structured **diagram spec**, not TikZ source. The web
app serializes that spec to TikZ deterministically and compiles it with the
existing ADR-006 pipeline.

Delivery mirrors the existing `graph_spec` hook exactly
(`templates/base.py:55`, `Callable  # values -> JSON-able payload`):

```python
@dataclass(frozen=True)
class Template:
    ...
    # graph_spec is REMOVED (see Decision 5); diagram_spec replaces it.
    diagram_spec: Callable = None  # values, given, find -> JSON-able payload
```

`engine/contract.py:build_sympy_data` gains the sibling of its existing graph
branch:

```python
if template.diagram_spec is not None:
    values = dict(inputs)
    values[find] = value
    data["diagram"] = template.diagram_spec(values, given=given, find=find)
```

Note the extra `given` / `find` arguments — unlike `graph_spec`, the diagram
builder must know **which symbol is the answer** in order to withhold it
(Decision 3).

### Why a spec, not raw TikZ

| | spec inside `sympy_data` | raw `tikz_code` |
| --- | --- | --- |
| DB migration | **none** — `sympy_data` is already persisted whole | none if nested, but ~8 KB of TeX in a 32 KB question JSON |
| Renderer freedom | web can restyle, rescale, re-theme without an engine release | layout frozen at generation time |
| Testability | assert on a dict; no TeX in Python tests | golden-string diffing |
| Engine owns values? | **yes — fully** | yes |

The persistence property is decisive: nesting inside `sympy_data` needs **no DB
allowlist migration**, which is the precise reason ADR-007 deferred LLM-authored
TikZ in the first place.

## Decision 2 — three element kinds cover all nine topics

Nine bespoke figure generators would be unmaintainable. A shared vocabulary in a
new `templates/diagrams.py` keeps each topic's hook to a few lines.

| kind | shape | topics |
| --- | --- | --- |
| `motion-1d` | oriented axis (horizontal or vertical) + ordered segments; each segment carries optional velocity-in/out arrows, an acceleration arrow, and span/duration brackets | `suvat`, `vectors-1d`, `free-fall`, `upward-throw`, `multi-stage-motion`, `distance-displacement`, `average-speed` |
| `plot-2d` | labelled axes + polyline | `motion-graphs` |
| `actors` | two named bodies with velocity arrows on a shared axis | `relative-velocity` |

### Payload shape

```python
{
  "kind": "motion-1d",
  "orientation": "horizontal",          # or "vertical" (free-fall, upward-throw)
  "segments": [
    {
      "direction": "forward",           # or "reverse" — see below
      "velocity_in":  {"symbol": "u", "label": "v_0", "role": "given",
                       "value": "5", "exact": "5", "unit": "m/s"},
      "acceleration": {"symbol": "a", "label": "a",   "role": "given",
                       "value": "2", "exact": "2", "unit": "m/s^2"},
      "velocity_out": {"symbol": "v", "label": "v",   "role": "find"},
      "span":         {"symbol": "s", "label": "s",   "role": "derived",
                       "value": "21", "exact": "21", "unit": "m"},
      "duration":     {"symbol": "t", "label": "t",   "role": "given",
                       "value": "3", "exact": "3", "unit": "s"}
    }
  ]
}
```

Every numeric label carries `value` / `exact` / `unit`, matching the ADR-005
two-form convention used everywhere else in `sympy_data`: `exact` is
authoritative, `value` is presentation-only. The renderer displays `value`;
nothing downstream treats it as truth.

### The one piece of real modelling difficulty

`upward-throw` and `distance-displacement` involve **direction reversal** —
up-then-down, and out-and-back. This is why `motion-1d` is a *list* of segments
with a per-segment `direction`, rather than a flat element bag. `average-speed`
and `multi-stage-motion` are the easy two-segment case (both `forward`);
reversal is the hard case and must be covered by tests.

## Decision 3 — answer-hiding by omission

Today's template shows symbols only, so the answer cannot leak. Once real values
appear, hiding becomes a correctness requirement rather than a side effect.

Two mechanisms, deliberately redundant:

1. **Role tagging.** Every label carries `role: "given" | "find" | "derived"`.
   The renderer prints `label = value unit` for `given` and `derived`, and
   `label = ?` for `find`.
2. **Omission at the source.** The engine **omits `value` / `exact` entirely**
   on any element whose `role` is `"find"`. A renderer bug therefore cannot leak
   the answer — there is nothing to leak.

Mechanism 2 is the load-bearing one; mechanism 1 is presentation. A test asserts
the invariant directly: for every `motion-1d` / `actors` topic and every valid
split, no element carrying the find symbol has a `value` or `exact` key.

`derived` covers engine-computed intermediates that are *not* the answer — e.g.
the cruise velocity in `motion-graphs`, already derived exactly inside the
current `graph_spec`. These are safe to show.

### `plot-2d` is the deliberate exception

The rule above applies to `motion-1d` and `actors`. It must **not** be applied
naively to `plot-2d`.

For `motion-graphs` the plot *is the problem statement*: the topic exists to
produce "graph-reading splits" (`templates/motion_graphs.py:7`), where the
student reads the slope to get `a` or the area under the polyline to get `s`
(`docs/superpowers/plans/2026-07-23-linear-motion-completion.md:1025`). Suppressing the
polyline because the find is derivable from it would delete the question.

So for `plot-2d`: **the polyline and its axis values are always shown** — they
are given data. The omission rule narrows to a single requirement: the find
quantity is never *annotated* on the figure (no `$a = 2$` slope label, no shaded
area labelled `$s = 21$`). Points stay; captions of the answer do not.

### Fonts

Labels are math symbols, digits, and units only (`m/s`, `m/s^2`, `s`, `m`) —
all Latin/math, all inside node-tikzjax's embedded Computer Modern families. **No
Thai string ever reaches TikZ**, so ADR-007's font constraint continues to hold.
The engine formats units through its existing `_unit_latex` helper
(`engine/contract.py:131`) so the web app never hand-rolls TeX.

## Decision 4 — declarative topics need the hook too

`vectors-1d`, `free-fall`, and `relative-velocity` are authored as JSON
(`templates/data/*.json`) and parsed by `templates/declarative/parse.py`. That
is a third of the scope, so the diagram hook cannot be Python-only.

`parse_template` gains an optional `"diagram"` key that compiles into the same
`diagram_spec` callable — declaring which shared builder to use and how the
topic's symbols map onto its roles:

```json
"diagram": {
  "kind": "motion-1d",
  "orientation": "vertical",
  "segments": [
    {"direction": "forward", "velocity_in": "u", "acceleration": "g",
     "velocity_out": "v", "span": "h", "duration": "t"}
  ]
}
```

Values, roles, and units are filled in by the shared builder at generation time
from `values` / `given` / `find`; the JSON declares **structure only**. The
five-stage declarative validation gate (`templates/declarative/gate.py`) gains a
check that every symbol named in `"diagram"` exists in the topic's variables.

## Decision 5 — `graph` is superseded by `diagram`

`sympy_data["graph"]` exists solely for `motion-graphs` and was never rendered
(the specs say "rendering with the TikZ track"). Rather than ship two parallel
figure contracts, `motion-graphs` moves to `diagram_spec` with `kind:
"plot-2d"`, carrying the same axes/points information plus role tagging (which
for this kind governs annotation only — see the `plot-2d` exception above).

The `graph_spec` field and the `"graph"` key are **removed** — the `Template`
dataclass ends up with `diagram_spec` in place of `graph_spec`, not alongside
it. Nothing consumes `"graph"` today, so this is a clean deletion rather than a
deprecation. `templates/motion_graphs.py:66`'s exact-arithmetic point derivation
is preserved verbatim; only its wrapper changes.

## Decision 6 — the web app becomes a dumb serializer, with no fallback

In `physics-jotelab`:

* `lib/engine/sympy-data.ts` — add an **optional** `diagramSchema` mirroring the
  payload above, parsed at the existing trust boundary.
* `lib/tikz/diagram/spec-to-tikz.ts` — **new.** Pure `spec → tikzpicture` string,
  one renderer per `kind`. Contains no physics, derives no values, and makes no
  decision about what to show beyond obeying `role`.
* `lib/tikz/templates/` — **deleted** (`suvat.ts`, `index.ts`, `suvat.test.ts`).
* `lib/tikz/attach-diagram.ts` — calls `specToTikz(sympy_data.diagram)` when the
  key is present; when absent, attaches **no diagram at all**.

`compile.ts`, `wrap-document.ts`, `embed-fonts.ts`, `sanitize-svg.ts`, the SVG
cache, the concurrency gate, and `compilation-log.ts` are all untouched. The
compile-rate benchmark keeps working; its `source` becomes `engine` rather than
`template`.

### Accepted consequence: old rows lose their diagrams

Questions persisted before this change have a `sympy_data` with no `diagram`
key. With no web-side fallback, **saved worksheets render without diagrams until
regenerated.** This is accepted deliberately: keeping the TypeScript template
alive as a legacy path would preserve exactly the split authorship this work
exists to remove. One author, or none.

## Engine transport

**Finding: the service exists as real, tested code — but only in unmerged git
history, with no evidence it is actually deployed anywhere.**

`git log --all --oneline -- 'service/*'` finds exactly one commit:
`5e3ea5c "Expose the engine as a FastAPI service (DEVELOPMENT_PLAN 1.1)"`
(2026-07-05), which adds `service/app.py` (`POST /generate`, `POST /verify`,
`GET /health`), `service/__init__.py`, a `Dockerfile`, `.env.example` entries,
and `tests/test_service.py` (9 `TestClient` tests). Its `/generate` handler
matches `client.ts` exactly: header `X-Engine-Api-Key`, env `ENGINE_API_KEY` —
this is the real counterpart to the doc comment in `client.ts`, not the
differently-shaped `api/` package described in this repo's own
`docs/superpowers/plans/2026-07-05-fastapi-service.md` /
`.../specs/2026-07-05-fastapi-service-design.md` (that plan uses `X-API-Key` /
`JOTELAB_API_KEY` and a batch `/topics` + `/generate` envelope, was never
implemented here, and should be treated as superseded/stale documentation —
not a task to pick up).

That commit lives only on `remotes/origin/epic/proposal-alignment`, whose tip
*is* `5e3ea5c` — it has not advanced since 2026-07-05.
`git merge-base --is-ancestor 5e3ea5c HEAD` returns false: it is **not an
ancestor of `main`** (currently `e3bc2e1`, from 2026-07-24) or of this
worktree's branch. No merge or revert of it appears anywhere in `main`'s
history. Spot-checking the functions it calls —
`engine.loop.generate(topic, given=, find=, conditions=, difficulty=, seed=)`,
`harness.verify.verify(data, difficulty=)`, `engine.registry.load_template` /
`topics()` — their signatures on current `main` still match what
`service/app.py` expects, so re-merging is a low-friction cherry-pick, not a
rewrite.

No evidence of an actual running deployment was found: no `render.yaml` or
other deploy manifest in either repo, no non-localhost `ENGINE_BASE_URL`
anywhere. The web repo's `.env.example` has `ENGINE_BASE_URL=http://localhost:8000`
— a local-dev default, not proof of a live instance. The Dockerfile names
Render as the intended host (per the commit message) but that is intent, not
deployment.

**Prerequisite, out of this plan's scope:** merge/cherry-pick `5e3ea5c`'s
`service/` package onto current `main` and actually deploy it, then point a
real `ENGINE_BASE_URL` at it. This is bounded, already-implemented work (merge
+ redeploy), not a from-scratch FastAPI build — smaller than it would be had
Step 1 turned up nothing, but still a precondition for Tasks 12–17 to exercise
a live transport.

### Does a new `build_sympy_data` key reach the web app automatically?

**At the HTTP layer, yes, with zero transport code change.** `service/app.py`'s
`/generate` handler calls `engine_generate(...)`, runs it through
`verify(...)`, and does `return data` — the dict is returned as-is and FastAPI
JSON-serializes it verbatim; only the *request* model is a typed Pydantic
schema, `sympy_data` itself is never re-modeled. So `data["diagram"]`
(`engine/contract.py`) would appear on the wire the moment
`build_sympy_data` sets it — no service code to touch.

**At the web's parse boundary, no — the schema must be updated, or the key is
silently dropped.** `lib/engine/sympy-data.ts`'s `sympyDataSchema` is a plain
Zod v4 `z.object({...})` (no `.passthrough()` / `.strict()` anywhere in the
file) enumerating exactly `topic, seed, given, find, steps, final_answer,
policy_applied, plausible`. Zod's default object mode strips any key not in
the schema from the parsed result. This isn't hypothetical: `build_sympy_data`
already conditionally adds a `"graph"` key today
(`engine/contract.py:136-139`, when `template.graph_spec` is set), and
`sympyDataSchema` has no `graph` field — a repo-wide grep of `lib/` and `app/`
in the web repo turns up zero references to `.graph` or `sympy_data.graph`,
confirming that key is already invisible past this boundary in the live app.

`diagram` would meet the identical fate unless `lib/engine/sympy-data.ts`
declares it — which is exactly what Decision 6 above already plans (add an
optional `diagramSchema` at this trust boundary). No transport work beyond
that schema change is required; Decision 6's plan is both necessary and
sufficient.

## Testing

### Engine (`jotelab-ai`)

```bash
pytest tests/test_diagrams.py                    # spec shape, per kind
pytest tests/test_diagrams_invariants.py         # find-value omission, all topics × all splits
pytest                                           # full suite (no regressions in contract tests)
python -m engine --topic suvat --verify
python -m engine --topic upward-throw --verify   # reversal case
python -m engine --topic motion-graphs --verify  # plot-2d, replaces "graph" key
python -m templates.declarative                  # declarative gate incl. new diagram check
```

The invariant test is the important one: it enumerates every topic's
`valid_splits()` and asserts that for each, the emitted diagram contains no
`value`/`exact` on any element bound to the find symbol.

### Web (`physics-jotelab`)

```bash
pnpm vitest run lib/tikz/diagram/spec-to-tikz.test.ts   # golden TikZ per kind
pnpm vitest run lib/engine/sympy-data.test.ts           # optional diagram parses
pnpm vitest run lib/tikz                                # pipeline unaffected
pnpm vitest run                                         # full suite
```

Plus one **real compile** check per kind: feed a representative spec through
`specToTikz` into the actual node-tikzjax compiler and assert it produces an SVG,
so a malformed template can't ship green on string assertions alone.

## Docs to correct

| File | Change |
| --- | --- |
| `README.md:9,30,47` (engine) | LLM owns Thai phrasing only; drop "+ TikZ" |
| `DEVELOPMENT_PLAN.md:21` | Invariant loses "and emits TikZ" |
| `DEVELOPMENT_PLAN.md:205` | Risk row "LLM-generated TikZ" — resolved, not deferred |
| `docs/adr/007-diagram-generation.md` (web) | Superseding note: templates move engine-side |
| New ADR (web) | `008-engine-owned-diagrams.md` recording this contract |
| `2026-07-17-template-authoring-finetune-design.md:25,233` | Phase 3.1 task becomes `sympy_data → Thai prose` |

## Out of scope

* Non-linear-motion topics (Phase 4 circuits, dynamics free-body diagrams). The
  `kind` vocabulary is extensible; adding one is registering a builder.
* Backfilling `diagram` into already-persisted questions.
* Any LLM involvement in diagrams whatsoever — that is the point of this work.
* Rate-limiting `/api/tikz/compile` (still an open ADR-006 follow-up).
