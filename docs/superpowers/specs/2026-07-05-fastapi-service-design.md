# FastAPI Service for the Jotelab Symbolic Engine — Design

**Date:** 2026-07-05 · **Status:** Approved design, pre-implementation
**Branch context:** `jotelab-ai` @ `template-expansion` (`1b5539a`)
**Plain-language companion:** `claude-test/docs/guides/fastapi-service-design-explained-simply.html`

## Purpose

An HTTP integration bridge wrapping the SymPy symbolic engine so `physics-jotelab`
(Next.js) can request problem generation from it — replacing the current
Gemini-generated numbers that violate the ADR-001 invariant ("every number a student
sees comes from the symbolic engine").

Chosen over: an internal dev-only API (doesn't fix the violation) and a full backend
(validation gate / template CRUD deferred). Batch-aware wrapper (Approach A) chosen
over single-problem RPC (N round-trips per worksheet) and an async job API (needless
state for millisecond-to-second generation).

## Architecture

New top-level package beside `engine/`; the engine is not modified.

```
api/
  __init__.py
  app.py        # FastAPI app factory: routes, auth wiring, exception handlers
  schemas.py    # Pydantic request/response envelope models
  auth.py       # X-API-Key dependency (shared secret from JOTELAB_API_KEY env)
  service.py    # generate_batch(): loops engine.generate(), verifies each instance
```

- `service.py` is the **only** module importing `engine`/`harness`.
- **Sacred rule 1 — pass-through:** the `sympy_data` dict is returned byte-identical.
  The API layer never reformats numbers (ADR-005: exact values authoritative).
- **Sacred rule 2 — verify before serving:** every generated instance runs through
  `harness.verify` in-process; a failing payload is never served.
- `schemas.py` validates the envelope only (topic, count, difficulty, seed, given/find).
  It does **not** re-model `sympy_data` — `engine/contract.py` owns that shape;
  a Pydantic copy would drift.
- Batch seeding: with a base `seed`, problem *i* (0-based) uses `seed + i`
  (echoed in `meta.seeds`); without one, fresh randomness (seeds still echoed
  so any batch can be reproduced afterwards).
- New dependencies: `fastapi`, `uvicorn` (runtime); `httpx` (dev/tests).

## API contract

| Endpoint | Auth | Request | Response |
|---|---|---|---|
| `POST /generate` | key | `{topic, count (1–20), difficulty?, seed?, given?, find?}` | `200 {problems: [sympy_data…], meta: {topic, difficulty, count, seeds}}` |
| `GET /topics` | key | — | `200 {topics: [{name, difficulties, splits}]}` |
| `GET /health` | none | — | `200 {status, engine_version, sympy_version}` |

## Error handling

- Engine exceptions propagate from `service.py` and are mapped to HTTP codes by
  exception handlers in `app.py` — no try/except in route functions. Real names:
  `NoCleanInstanceError` (convergence), `UnsolvableError` / `OverDeterminedError`
  (bad split), plus two new API-side exceptions in `service.py`:
  `UnknownTopicError` (wrapping the registry's `KeyError`) and
  `VerificationFailedError`.
- Codes: `401` bad/missing key · `422` invalid envelope (Pydantic native format)
  or unsolvable/over-determined split · `404` unknown topic · `409` convergence
  failure (`NoCleanInstanceError`) · `500` verification failure
  (payload logged in full; never served).
- Error body: `{"error": {"code": "<machine_readable>", "message": "...", "detail": {...}}}`.
- **Batch atomicity: all-or-nothing.** Any failed problem fails the whole request;
  no partial worksheets. Retrying a whole batch is cheaper than app-side merge logic.
- No per-request timeout machinery in v1: `count ≤ 20` × bounded `MAX_ATTEMPTS`
  keeps worst-case latency in single-digit seconds.

## Auth

Single shared secret: `X-API-Key` header checked against `JOTELAB_API_KEY`.
The service **refuses to start** if the variable is unset. Sufficient for
server-to-server calls from the Next.js backend; no user-level auth in v1.

## Testing

`tests/test_api.py` joins the existing pytest suite, using FastAPI's in-process
`TestClient` (no port binding; key injected via monkeypatch):

1. **Transparency parity (the invariant test):** `POST /generate` with a pinned seed
   returns `sympy_data` byte-identical to a direct `engine.generate()` call with the
   same seed.
2. Auth: missing/wrong key → 401; correct key → 200; `/health` open.
3. Envelope: unknown topic → 404; `count` 0 or 21 → 422; bad difficulty → 422.
4. Verification gate: monkeypatched `harness.verify` raising ⇒ 500, no payload served.
5. Batch determinism: `count=5, seed=42` twice ⇒ identical problems; `meta.seeds`
   echoes the five derived seeds.

Manual: `uvicorn api.app:app --reload`, curl, and the built-in `/docs` Swagger UI.
End-to-end from `physics-jotelab` (Inngest → staging container) is out of scope here.

## Deployment

- `Dockerfile`: `python:3.12-slim`, install from `requirements.txt` (the repo's
  install workflow; it carries the `sympy==1.13.*` pin — exact round-trip depends
  on it), copy
  `engine/ templates/ harness/ api/`, run
  `uvicorn api.app:app --host 0.0.0.0 --port 8000`. Single worker; stateless, scale
  horizontally. Target: any container host (Railway/Fly/Render).
- Config is env-only: `JOTELAB_API_KEY` (required), `PORT` (default 8000).
- `GET /health` reports `sympy_version` so a mis-pinned deploy is externally visible.
- No CORS middleware: calls are server-side only, by design.
- Serverless rejected: SymPy import cost makes cold starts unacceptable.

## Out of scope (v1)

`POST /verify` endpoint · template-validation endpoints (ADR-007 gate over HTTP) ·
`physics-jotelab` integration changes · rate limiting · user-level auth ·
async job API.
