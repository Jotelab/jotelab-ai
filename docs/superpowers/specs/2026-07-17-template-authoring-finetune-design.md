# Fine-Tuning an LLM to Author Declarative Template JSON — Design

**Date:** 2026-07-17 · **Status:** Approved design, pre-implementation
**Branch context:** `jotelab-ai` @ `main` (`1e17733`); depends on
`worktree-linear-motion-vectors` (`vectors_1d` / `free_fall` / `relative_velocity`) landing
**Scope note:** This is a **new capability, not in `DEVELOPMENT_PLAN.md`.** It sits beside the
planned Phase 3.1 fine-tune (`sympy_data` → Thai phrasing), which is a *different* model task.
Recommended framing: **post-NSC / stretch track** — see §9.

---

## 1. Purpose

Let a teacher describe a problem type in natural language (e.g. *"projectile motion, launch
angle and range, medium difficulty"*) and have a **fine-tuned Qwen 3.5** emit a valid
**declarative template JSON** (the `templates/data/*.json` format from ADR-007). The engine then
samples numbers from that template exactly as it does today for the built-in `suvat` template.

The invariant is unchanged: **the LLM authors the *rules* (variables, equations, ranges,
constraints); the engine still owns every number.** For user-authored templates the guarantee
narrows per ADR-007 — every number is the arithmetically-exact solution of the author's declared
equations, machine-verified, and the template carries `trust_state: "unverified"`.

**Direction of the model task:** `natural-language request → template JSON`.
This is the inverse of the Phase 3.1 task (`sympy_data → Thai prose + TikZ`). They do not share a
dataset and should not share an adapter (§8).

---

## 2. Why this is tractable: the gate is a machine oracle

`templates/declarative/gate.py` runs a five-stage validation gate and admits a template *only* if
every stage passes:

1. **Parse & sandbox** — AST allow-list, then `sympify`
2. **Dimensional homogeneity** — `sympy.physics.units`
3. **Solvability derivation** — `default_split` must be a derivable split
4. **Golden-case replay** — each worked example reproduces exactly (ADR-005)
5. **Convergence + fidelity** — generate N/band via the real loop; `verify_generic` 100%

**Measured cost: ~0.48 s end-to-end on `suvat.json`, all five stages** (local, `.venv`). Because
it is fast and deterministic, the gate runs **in the loop at inference** — every model output is
validated before a teacher sees it, with a repair retry on failure. This is the load-bearing
design decision:

> **The fine-tune does not have to be correct. It has to be *frequently valid* and *cheap to
> serve*.** Correctness is enforced by the gate regardless of model quality. Fine-tuning optimizes
> first-pass gate rate, repair success, and inference cost — not soundness.

This is also why RL (GRPO with the gate as a verifiable reward) is deferred, not chosen: SFT on
gate-verified frontier output caps out at "good enough" for a format-authoring task, and a pure
gate reward invites reward-hacking toward degenerate-but-valid templates (see §7). RL is future
work once the data pipeline exists.

## 2a. The gap the gate does NOT close: pedagogical plausibility

`engine/policy.py` is explicit: *"Plausibility (never loosened) — lives in the template's
constraints, not here."* And `templates/base.py` on `VarSpec.ranges`: *"For variables that are
normally derived the range still doubles as a plausibility band on the solved value."*

**Consequence: the sampling ranges and constraint caps *are* the pedagogical-quality mechanism,
and the gate cannot check them.** A template with `a: [1,15] m/s²` and `t: [1,20] s` for a *car*
is dimensionally perfect, passes all five stages, and hands a student a 300 m/s result. Authoring
sensible ranges is exactly what "great-ish quality" means here, and it is the one thing the gate
does not verify.

Therefore quality acceptance = **gate passes AND an LLM-as-a-Judge rates *sampled instances* of
the template as physically plausible.** The judge (planned in Phase 5 as a *reporting metric*) is
promoted here to an **acceptance filter** (§4).

---

## 3. The core problem: one format, (almost) no corpus

You cannot fine-tune a model to write a format from a handful of examples. The seed corpus is four
templates, and they are unmerged (`worktree-linear-motion-vectors`). **Dataset construction is the
project; training is the easy part.**

The four seeds are valuable not as "four topics" but as coverage of the **DSL idioms** the model
must compose:

| Seed template | Idiom demonstrated |
|---|---|
| `suvat` | 5-equation set; unsigned; `smallest_positive_physical` + `nonneg_fallback_vars`; difficulty-scoped constraints (`"difficulty": "easy"`, `"scope": "root"`) |
| `vectors-1d` | single equation; `signed_physical`; `signed_answer: true`; signed ranges |
| `free-fall` | **pinned constant** — `g` range `[10,10]` + `==` constraint; always given, never solved |
| `relative-velocity` | signed; equation written `Eq(va, vab + vb)` (not the natural `Eq(vab, va - vb)`) to satisfy single-equation solvability derivation |

**The dataset goal is coverage of the idiom × topic cross-product, not raw pair count.** ~6 idioms:
signedness, pinned constants, difficulty-scoped constraints, root-policy choice, plausibility caps,
solvability-shaped equation phrasing.

---

## 4. Pipeline: back-translation + double filter

The wanted direction (request → template) has no natural corpus. The reverse is cheap, and the
gate verifies the *template* side independently of any request. So build the template side first,
verify it, then synthesize the request.

```
                                    ┌── curriculum spine (§5): ~20–25 equation sets, 4 strands ──┐
                                    ▼                                                            │
  [ A: frontier draft ] ── model A drafts template JSON, model B critiques (multi-agent)        │
        │                                                                                        │
        ▼                                                                                        │
  [ GATE FILTER ]  0.48s, free ── reject → becomes a REPAIR record (§6), keep report            │
        │ pass                                                                                   │
        ▼                                                                                        │
  [ JUDGE FILTER ] ── sample K instances from the template, judge plausibility 1–5,             │
        │              reject templates whose instances score low (closes §2a gap)              │
        │ accept                                                                                 │
        ▼                                                                                        │
  [ BACK-TRANSLATE ] ── frontier model: "what would a teacher have asked to get this template?"  │
        │              vary register → multiple requests per template                            │
        ▼                                                                                        │
  ( request , template ) pairs ─────────────────────────────────────────────────────────────────┘
```

Every accepted pair has a **guaranteed-valid, plausibility-screened target**. This is the
proposal's "multi-agent synthetic data (frontier AI cross-checking)" applied to template authoring.

---

## 5. Curriculum spine

~20–25 equation sets across the proposal's four strands (mechanics, E&M, waves & light,
thermodynamics), each with realistic ranges and typical Thai scenarios. The linear-motion coverage
doc (`Documents/linear-motion-coverage.html`) already decomposes one strand into ~7 sub-topics —
reuse that granularity.

**Hard constraint — respect the v1 single-equation solvability model.** The coverage doc lists
*multi-stage motion* as "blocked by the v1 single-equation solvability model." Do **not** seed the
spine with problem types the engine cannot solve; that manufactures guaranteed gate rejections and
teaches the model to write unsatisfiable templates. Spine entries must each reduce to a
single-equation solvable split until the engine's solvability model grows.

---

## 6. Dataset record types

Two record types, both emitted by the §4 pipeline:

- **Author record** — `request → template JSON`. The primary task.
- **Repair record** — `request + broken template + gate Report → fixed template`. Sourced *free*
  from gate rejects. `gate.py` already returns a `Report` whose `stages[].reason` says exactly what
  failed. This mirrors the inference-time retry, where the model gets that same `Report` on
  failure — so training on repairs directly teaches the self-repair behavior serving depends on.

Serialize as JSONL chat pairs. Hold out per §7. Never emit `trust_state: "verified"` in a target —
targets keep `"unverified"` (the `parse.py` default), matching ADR-007 provenance.

**Volume (diversity-bound, not count-bound):** ~20 spine topics × ~15–30 accepted variants ×
~3 request registers (formal/casual · Thai/English · difficulty-stated/omitted). A flat "2,000
pairs over 4 topics" target teaches format mimicry and will not generalize — reject that framing.

---

## 7. Evaluation: hold out a whole strand

Templates within one topic are near-duplicates; a random example split will flatter the model
badly. **Hold out an entire strand** (e.g. train with no thermodynamics, then request a thermo
template) to measure real generalization to an unseen physics area.

Metrics:

| Metric | Definition | Target |
|---|---|---|
| First-pass gate rate | % of raw model outputs passing all 5 stages | as high as possible |
| Post-repair gate rate | % passing after one repair retry with the `Report` | ≈100% (this is the served path) |
| Judge plausibility | mean 1–5 over sampled instances of accepted templates | ≥ the frontier-model baseline |
| Held-out-strand gate rate | first-pass gate rate on the unseen strand | the headline generalization number |

Report first-pass and post-repair separately (mirrors the Phase 5 Data-Fidelity pre/post-retry
convention).

---

## 8. Serving & integration

- **Constrained decoding against a JSON Schema (prerequisite, §10).** Decode the template against
  the schema so stage 1 (parse) is essentially unfailable — removes a whole rejection class before
  training even starts.
- **Gate-in-the-loop:** model → gate → (on fail) one repair retry with the `Report` → (on
  fail) reject with a teacher-facing message. Never serve an ungated template.
- **Judge-in-the-loop (live):** for a teacher-authored template, sample K instances and run the
  plausibility judge before offering it, same filter as §4. Latency/cost budget TBD — this is the
  one place the live path is heavier than gate-only.
- **Provenance:** persisted LLM-authored templates carry `trust_state: "unverified"`. A fine-tune
  must never silently promote to `"verified"`.
- **Separate adapter from Phase 3.1.** The two tasks (author-template vs phrase-from-`sympy_data`)
  are inverse directions; co-training risks interference. Ship as two LoRA adapters over one base,
  or two models. Do not merge the datasets.
- **Fallback:** frontier model (approach A) stays wired as the fallback provider — it *is* the data
  pipeline, so it is never throwaway. If the fine-tune underperforms, ship A and present the Qwen
  fine-tune as a benchmarked comparison (same fallback posture as Phase 3.3).

---

## 9. Relationship to `DEVELOPMENT_PLAN.md`

This capability is **not in the plan.** Honest accounting for the NSC timeline:

- Phase 3.1 (the *planned* fine-tune: `sympy_data` → Thai phrasing) is **P1 and not started.**
- All of Phase 4 (topic expansion) is **not started.**
- This doc proposes a **second** fine-tune track on top of the first.

**Recommendation:** treat this as a **post-NSC / stretch track.** For the NSC deadline, the higher-
value uses of the same machinery are: (a) approach A as an *internal* tool to accelerate Phase 4
authoring (a human reviews each template), and (b) banking the gate-verified templates A produces
as the seed corpus for this fine-tune later. That way none of the work is wasted and the plan's
critical path is not displaced.

---

## 10. Prerequisites & dependencies

1. **JSON Schema for the declarative template format** — does not exist today; the shape lives
   implicitly in `parse.py`, and `signed_answer` is present in 2 of 4 seeds and absent in the other
   2. Write it first: it is the prompt contract *and* the constrained-decoding grammar.
2. **`worktree-linear-motion-vectors` must merge** — three of the four seed templates
   (`vectors_1d`, `free_fall`, `relative_velocity`) are on that locked, unmerged branch.
3. **Frontier-model access** for the draft/critique/back-translate/judge pipeline (approach A).
4. **GPU for LoRA** on Qwen 3.5 (already contemplated by Phase 3.2).

---

## 11. Out of scope (v1)

- Multi-equation / multi-stage templates (blocked by the v1 solvability model — §5).
- RL / GRPO against the gate reward (§2; future work after the SFT pipeline exists).
- Auto-promotion of any template to `trust_state: "verified"`.
- TikZ authoring by the template model (that is the Phase 3.1 model's job, from `sympy_data`).

---

## How to test / validate this design

Design-stage checks (no training run needed):

```bash
# 1. Confirm the gate is fast enough to sit in the live loop (measured ~0.48s):
cd jotelab-ai/jotelab-ai
.venv/bin/python -c "import json,time; from templates.declarative.gate import validate_template; \
d=json.load(open('templates/data/suvat.json')); t=time.perf_counter(); r=validate_template(d); \
print('passed=%s wall=%.2fs'%(r.passed, time.perf_counter()-t))"

# 2. Confirm all four seed templates pass the gate (the corpus this design rests on):
#    (run from the worktree-linear-motion-vectors branch, where 3 of the 4 live)
.venv/bin/python -c "import json; from templates.declarative.gate import validate_template; \
[print(f, validate_template(json.load(open('templates/data/'+f))).passed) \
 for f in ['suvat.json','vectors_1d.json','free_fall.json','relative_velocity.json']]"

# 3. Confirm a deliberately-broken template yields a Report with a stage reason
#    (this Report is the repair-record training signal in §6):
.venv/bin/python -c "from templates.declarative.gate import validate_template; \
r=validate_template({'topic':'x','variables':{},'equations':['Eq(v, u + a*t)'],'golden_cases':[]}); \
print('passed=',r.passed); [print(s.number,s.name,s.passed,s.reason) for s in r.stages]"
```

Pipeline validation, once built: run approach A end-to-end on 2–3 spine topics, confirm
gate-accept + judge-accept rates are non-trivial before committing to full corpus generation.
Dataset validation: hold out one strand, train, and read the held-out-strand gate rate (§7) — that
single number tells you whether the model learned the *format* or merely memorized topics.
