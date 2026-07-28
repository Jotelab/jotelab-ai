# Jotelab

**Jotelab** generates unlimited **isomorphic high-school physics problems** (โจทย์คู่ขนาน) — same
underlying structure, fresh numbers and context — each with an automatic step-by-step solution, for
Thai students and teachers. It replaces static drill sheets and removes the teacher bottleneck of
hand-building parallel problem sets.

It uses a **neuro-symbolic** design: a constrained **symbolic engine (SymPy)** owns all computation,
and a **fine-tuned LLM (Qwen 3.5)** owns only the natural-Thai phrasing and the TikZ diagram code —
so the math is provably correct and the language is fluent.

> **The invariant.** Every number a student sees comes from the symbolic engine. The LLM never
> computes, alters, or "corrects" a value — it only phrases problems in Thai and draws figures.
> This is Jotelab's entire claim over generic AI; the **Data Fidelity** benchmark exists to police it.

> **Invariant scope for user-authored templates (ADR-007).** For **built-in developer templates**
> (e.g. `suvat`) the guarantee above holds in full. For **user-authored declarative templates**
> ([`templates/declarative/`](templates/declarative/)) it narrows: every number is the
> *arithmetically-exact* solution of the template's declared equation set, machine-verified to be
> dimensionally consistent and to reproduce the author's golden worked example(s). The engine no
> longer guarantees the *equations themselves* are the correct physical laws — that is asserted by
> the author and evidenced by the golden cases plus the `unverified`/`verified` provenance signal.

## Architecture

```
Frontend (Next.js / React)
  → API routes (Auth & Credits / Generation Engine orchestrator)
     1. SymPy engine        → samples numbers, reverse-engineers a clean answer, emits sympy_data
     2. Qwen 3.5 + Zod      → phrases the problem in Thai + emits TikZ (never computes)
     3. Supabase (Postgres) → persists worksheets/questions, manages credits
  → A4 Canvas (KaTeX + TikZ) → live preview + vector PDF export
```

Numbers always originate in the symbolic layer and flow **into** the LLM, never the reverse. The
LLM's output is forced through a **Zod schema** and validated before it is trusted, persisted, or
rendered.

## Tech stack

| Layer | Tools |
| --- | --- |
| Web | Next.js (App Router) + React, Tailwind CSS v4, shadcn/ui (Radix), Lucide icons |
| Backend / data | Supabase (PostgreSQL, Auth, Google OAuth) |
| AI integration | Vercel AI SDK & Gateway, `generateObject()` + Zod structured output |
| Symbolic engine | **SymPy** (Python) — constrained engine with a constraint-based re-roll loop |
| Language model | **Qwen 3.5**, LoRA fine-tuned — Thai phrasing + TikZ, no computation |
| Rendering | KaTeX (math), TikZjax (diagrams), CSS print media queries (A4 / PDF) |

Languages: **TypeScript** for the app, **Python** for the symbolic engine and model fine-tuning.

## The four subsystems

1. **Batch Generation Engine** — Basic mode (random by topic/grade) and Advanced mode (user pins
   Given variables, the Find target, and numeric conditions), plus auto-generated TikZ figures.
2. **Interactive A4 Canvas** — live A4 preview, KaTeX/TikZ rendering, per-question micro-editing
   (regenerate / re-roll numbers / toggle the step-by-step solution).
3. **Personal Library & Export** — Google OAuth sign-in, cloud-saved worksheet history, vector PDF export.
4. **Credit Economy** — per-usage credit accounting so cloud inference cost stays sustainable.

## Repo layout

> The product is in early build. Current focus is the **critical path** — the symbolic engine
> (Python/SymPy). The layout below is the target; sections fill in as each track lands.

```
engine/                  # constrained SymPy engine: bounded re-roll loop, registry, contract, CLI
templates/               # topic templates
  base.py                #   the Template dataclass (topic-agnostic)
  suvat.py               #   SUVAT as code — the built-in reference template
  declarative/           #   ADR-007: declarative-template parser + 5-stage validation gate + CLI
  data/suvat.json        #   SUVAT re-expressed as declarative data (byte-parity with suvat.py)
  scenes/                #   scene compiler: a physical setup (bodies/phases) -> template doc
    data/two_phase_ascent.json  #   registered topic "two-phase-ascent"
harness/                 # Data Fidelity verification harness (independent re-derivation)
app/                     # Next.js App Router (Generate + Library)
components/              # shadcn/ui components, the A4 Canvas
lib/                     # Zod schemas (the LLM output contract), AI SDK / Supabase clients
```

Engineering documentation (design docs, specs, ADRs, the build guide, daily reports) is maintained
in the separate **Jotelab documentation workspace** (`claude-test/docs/`). Start with
**ADR-001 (Neuro-Symbolic Split)** and the **Symbolic Engine Spec** + **Build Guide**.

## Declarative topic templates (ADR-007)

A topic template can be **declarative JSON data** instead of Python code, so the topic library can
grow without a developer in the authoring path. A template document declares its variables (with
mandatory units and per-difficulty ranges), its equations as strings, a named root policy, a small
constraint DSL, a default split, and at least one golden worked example — see
[`templates/data/suvat.json`](templates/data/suvat.json). The engine parses it into the same
`Template` object the code path uses; **no user Python ever executes** (equations are checked against
an AST allow-list before `sympy.sympify`, which itself can run arbitrary code).

A submitted template is admitted to the registry only after passing a fixed **five-stage automated
gate** ([`templates/declarative/gate.py`](templates/declarative/gate.py)):

1. **Parse & sandbox** — equations parse against declared symbols only; anything else is rejected.
2. **Dimensional homogeneity** — every equation is dimensionally consistent (`sympy.physics.units`).
3. **Solvability derivation** — the default split is auto-derived and must be generatable.
4. **Golden-case replay** — the engine reproduces the author's worked example(s) *exactly* (ADR-005).
5. **Convergence + fidelity** — instances generate through the real loop and pass the Data Fidelity
   oracle at 100%.

Registration happens only on all-pass; otherwise a typed `TemplateValidationError` names the failing
stage. The gate proves *arithmetic* correctness, not *physical* truth — a self-consistent wrong
equation (e.g. a dropped `½`) passes dimensional analysis and is caught only if a correct golden case
disagrees. That residue is why the invariant is narrowed for user templates (see the invariant-scope
note above) and why each template carries an `unverified`/`verified` provenance signal. Full detail:
**Template Validation Spec** (`claude-test/docs/specs/template-validation-spec.html`).

Validate a template document from the command line:

```bash
python -m templates.declarative templates/data/suvat.json   # per-stage PASS/FAIL report; exit 0 on all-pass
```

## Scene topics (Andes-lite milestone 1)

A **scene** ([`templates/scenes/`](templates/scenes/)) is a higher-level authoring format for
declarative topics: instead of writing equations by hand, an author describes the *physical setup* —
one or more bodies, each moving through an ordered list of phases (e.g. constant-acceleration up,
then constant-acceleration down to `v=0`), plus which quantities are `given` and what is `sought`. A
small **compiler** (`templates/scenes/compile.py`, `compile_scene(scene_dict) -> template_doc`) walks
the phases, calls a per-phase **kinematics KB** (`templates/scenes/kb.py`) to emit the SUVAT
equations and auxiliary variables each phase needs, threads state across phase boundaries (a phase's
end state feeds the next phase's start state), and checks the result is well-posed before handing
back an ordinary template document — the same shape `templates/declarative/parse.py` already
consumes. `templates/scenes/ontology.py` owns naming/units/rendering and the typed `SceneError`.

Registration is **compile-at-registry-load**: `engine/registry.py` lists scene JSON files in an
`_SCENE_TOPICS` tuple (currently `two_phase_ascent.json`, registered under the topic
`two-phase-ascent`), and on the first lazy registry lookup it runs each one through
`compile_scene` before parsing the result with `parse_template` — a scene is never a special case
downstream; by the time a topic is in the registry it is indistinguishable from a hand-authored
declarative template. `templates/scenes/data/pursuit_scene.json` is a test fixture only (the
hand-written `pursuit` declarative topic already owns that topic name); it is not in `_SCENE_TOPICS`
and is not registered.

One documented v1 limitation: an `end_condition` of `{"v": k}` only supports `k=0` — the compiler
derives the phase duration (`Eq(t_i, (k-u)/a)`) instead of equating a bare numeral to a
unit-carrying auxiliary, because the latter fails the frozen dimensional-homogeneity gate stage;
nonzero `k` raises `SceneError` today.

Out of scope for this milestone (not built): scene *sampling*/grammar (random scene generation),
multi-phase multi-body scenes, meets deeper than phase 1, graph payloads for scenes, non-kinematics
principle families, and any user-authored scene upload/validation UI.

How to test:

```bash
# the scene-compiler unit tests (43 tests: ontology, KB, compile, well-posedness, registry wiring)
pytest tests/test_scene_compiler.py -q

# generate + verify an instance of the registered scene topic through the real engine loop
# (pin the given/find split — the topic's default sought variable H is the only reliably
# solvable find in this v1 scene; other splits can occasionally miss within the re-roll budget)
python -m engine --topic two-phase-ascent --given a,t1,g --find H --verify

# compile a scene straight through the five-stage gate, bypassing the registry
python -c "import json; from templates.scenes import compile_scene; from templates.declarative.gate import validate_template; print(validate_template(compile_scene(json.load(open('templates/scenes/data/two_phase_ascent.json'))), n_smoke=2).passed)"
```

## Prerequisites

- Node.js (Next.js 16.x / React 19.x) and a package manager
- Python 3.11+ with SymPy (engine and fine-tuning)
- A Supabase project (Postgres + Auth)
- Vercel AI Gateway access to a Qwen 3.5 (OpenAI-compatible) endpoint
- Google OAuth credentials (via Supabase Auth)

## Setup

```bash
# install web dependencies
<package-manager> install

# environment (.env.local) — to be finalized:
#   NEXT_PUBLIC_SUPABASE_URL, SUPABASE keys, AI Gateway endpoint/key, Google OAuth client
```

> Exact env var names, the package manager, and hosting region are **not yet finalized** — they will
> be pinned as the web track stands up.

## Running

```bash
# web app (once scaffolded)
<package-manager> run dev

# symbolic engine + tests (Python)
pytest                 # unit + property tests (156 green: engine, harness, declarative gate, parity, topics, chains)

# generate one fully-solved problem — a random topic each run (pin with --topic)
python -m engine --difficulty easy --verify
python -m engine --topic free-fall --verify      # pin the topic
python -m engine --given u,a,t --find v --seed 42  # pin the split+seed (defaults to suvat)

# validate a declarative topic template through the five-stage gate
python -m templates.declarative templates/data/suvat.json

# mixed (chained) problem: part 1's answer feeds a given of part 2
# --part TOPIC[:given,csv:find[:receive]] (2+ parts; receive auto-picked when unambiguous)
python -m engine --part free-fall --part suvat:u,a,t:s:u --verify
pytest tests/test_chain.py     # chain layer: links, typed errors, CLI, fidelity sweep

# Data Fidelity: run a SUVAT seed batch through the verification harness → expect 100%
```

## Correctness gates (the benchmark)

- **Data Fidelity** — numbers/units in the problem text match the SymPy computation 100%.
- **TikZ Compilation Rate** — generated TikZ renders without syntax errors.
- **Schema Adherence** — JSON output validates against the Zod schema on the first pass.
- **LLM-as-a-Judge** — a frontier model scores Thai fluency and physical plausibility.

The engine's milestone is **Data Fidelity = 100%** on a SUVAT seed batch — which unblocks the AI
(synthetic-data + fine-tune) and web tracks. Launch scope is **SUVAT-first, single strand**.

## Status & scope

Early build, June–July 2026, for NSC 2026 (ครั้งที่ 28). The symbolic engine hits **Data Fidelity =
100%** on the SUVAT batch, and **ADR-007 v1** (declarative topic templates + the five-stage validation
gate) is implemented — with `suvat` proven byte-for-byte identical whether loaded from code or from
JSON data. **In scope:** high-school physics (kinematics/SUVAT first, then circuits, waves,
thermodynamics), structural 2D TikZ diagrams, Thai-language output, PC/tablet. **Out of scope:**
chemistry / advanced math, photorealistic or 3D graphics, English-language output, smartphone-first
UI; and — deferred to the web app — the `TEMPLATES` table, the `unverified`→`verified` promotion
policy, and any authoring UI.
