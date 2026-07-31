# `POST /author` — natural language → gate-vetted template (Gemini)

Turns a teacher-style description (e.g. *"projectile motion, launch angle and
range, medium difficulty"*) into a declarative template JSON, admits it through
the five-stage validation gate, registers it live, and persists it. This is the
template-authoring capability from the 2026-07-17 fine-tune spec with **Gemini
2.5 Flash doing the authoring instead of the planned Qwen fine-tune** — same
gate, same invariants, no training required. The invariant is unchanged: the
LLM authors the *rules*; the engine owns every number.

## Flow

1. Prompt = DSL reference + the five seed templates (`templates/data/*.json`)
   as few-shot examples + the fenced teacher request.
2. Gemini returns a draft template JSON.
3. `validate_template()` runs the five-stage gate; on failure the failing
   stage's reason is fed back to Gemini for a repair attempt
   (`max_attempts`, default 3, includes the first draft).
4. On all-pass: the topic is registered (immediately servable by `/generate`)
   and written to `templates/data/authored/<topic>.json` with
   `trust_state: "unverified"`. The registry re-loads that folder on startup,
   so authored topics survive a restart.

## Configuration

| Env var | Purpose |
| --- | --- |
| `ENGINE_API_KEY` | Shared secret for all endpoints (existing). |
| `GOOGLE_API_KEY` or `GOOGLE_GENERATIVE_AI_API_KEY` | Gemini key; either name works (free key: https://aistudio.google.com/apikey). Missing → `/author` returns 503. |
| `AUTHORING_MODEL_ID` | Optional model override (default `gemini-2.5-flash`). |

## Responses

- **200** — `{topic, attempts, gate_report, template, persisted_to, samples}`;
  `gate_report` lists the five stages with pass/reason, `samples` holds one
  verified `sympy_data` instance per difficulty band.
- **409** — a pinned `topic` name is already registered.
- **422** — every attempt failed the gate; `detail` carries `attempts`,
  `last_draft`, and the final `gate_report` for inspection.
- **502 / 503** — Gemini call failed / no Gemini key configured.

## How to test

Unit + endpoint tests (no network, the model is faked):

```bash
.venv/bin/python -m pytest tests/test_authoring.py -q
```

Full suite:

```bash
.venv/bin/python -m pytest -q
```

Live smoke test (demo-day flow), from the repo root:

```bash
pip install -r requirements.txt          # brings in google-genai
export ENGINE_API_KEY=dev-secret
export GOOGLE_API_KEY=<your key>
uvicorn service.app:app --port 8000
```

Then author a topic and immediately generate from it — or drive both from the
Swagger UI at http://localhost:8000/docs:

```bash
curl -s -X POST localhost:8000/author \
  -H 'X-Engine-Api-Key: dev-secret' -H 'Content-Type: application/json' \
  -d '{"description": "projectile motion: launch angle and range, medium difficulty"}'

curl -s -X POST localhost:8000/generate \
  -H 'X-Engine-Api-Key: dev-secret' -H 'Content-Type: application/json' \
  -d '{"topic": "<topic from the /author response>", "difficulty": "medium"}'

curl -s localhost:8000/health   # the new topic appears in "topics"
```

## Deferred (post-demo)

- **LLM-as-judge plausibility filter** (spec §2a): the gate cannot check that
  sampled values are *pedagogically* sensible; prompt guidance covers this for
  now. Bolt the judge on as an acceptance filter after demo day.
- The Qwen fine-tune itself (cheap self-hosted serving) — unchanged as future
  work; this endpoint is provider-agnostic at the `ModelCall` seam.
