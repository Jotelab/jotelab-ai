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
engine/        # Python: constrained SymPy engine + topic templates (SUVAT first)
harness/       # Data Fidelity verification harness (independent re-derivation)
app/           # Next.js App Router (Generate + Library)
components/    # shadcn/ui components, the A4 Canvas
lib/           # Zod schemas (the LLM output contract), AI SDK / Supabase clients
```

Engineering documentation (design docs, specs, ADRs, the build guide, daily reports) is maintained
in the separate **Jotelab documentation workspace** (`claude-test/docs/`). Start with
**ADR-001 (Neuro-Symbolic Split)** and the **Symbolic Engine Spec** + **Build Guide**.

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
pytest                 # unit + property tests
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

Early build, June 2026, for NSC 2026 (ครั้งที่ 28). **In scope:** high-school physics
(kinematics/SUVAT first, then circuits, waves, thermodynamics), structural 2D TikZ diagrams,
Thai-language output, PC/tablet. **Out of scope:** chemistry / advanced math, photorealistic or 3D
graphics, English-language output, smartphone-first UI.
