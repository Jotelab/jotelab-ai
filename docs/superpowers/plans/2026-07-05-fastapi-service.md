# FastAPI Integration Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An authenticated HTTP service (`api/` package) wrapping `engine.generate()` so `physics-jotelab` can request batches of verified `sympy_data` problems.

**Architecture:** A thin FastAPI layer over the untouched engine: `service.py` is the only module importing `engine`/`harness`; it generates `count` problems (seeds `seed + i`), verifies each with `verify_generic` before it can be served, and passes `sympy_data` through byte-identical. `app.py` maps typed exceptions to HTTP codes via handlers. Spec: `docs/superpowers/specs/2026-07-05-fastapi-service-design.md`.

**Tech Stack:** Python ≥3.11, FastAPI, uvicorn, Pydantic v2, pytest + fastapi TestClient (httpx), SymPy `1.13.*` (pinned — do not change).

## Global Constraints

- The engine (`engine/`, `templates/`, `harness/`) is **not modified** by any task.
- `sympy_data` passes through the API byte-identical — never reformat, round, or re-model it in Pydantic (`engine/contract.py` is the single source of truth).
- Every generated problem must pass `harness.verify.verify_generic` in-process before being served; a failing payload is never returned.
- `sympy==1.13.*` pin stays exactly as-is in `requirements.txt`.
- Batch limits: `1 ≤ count ≤ 20`; difficulty ∈ {`easy`, `medium`, `hard`}; batch is all-or-nothing.
- Auth: header `X-API-Key` checked against env `JOTELAB_API_KEY`; the app **refuses to start** if the env var is unset.
- Error body shape (all non-422-Pydantic errors): `{"error": {"code": "<snake_case>", "message": "<human>", "detail": {}}}`.
- All commands below run from the repo root `/home/thanakorn/Projects/jotelab-ai` with `.venv/bin/` tools.

---

### Task 1: Repair the dev environment and add API dependencies

The existing `.venv` is broken: it was created with Python 3.14 (`.venv/lib/python3.14/`) but `/usr/bin/python3` now resolves to 3.13.13, so `import sympy` fails. Recreate it, prove the existing suite is green, then add the API dependencies.

**Files:**
- Modify: `requirements.txt`

**Interfaces:**
- Produces: a working `.venv` (Python 3.13) with `fastapi`, `uvicorn`, `httpx` installed; later tasks run `.venv/bin/pytest`.

- [ ] **Step 1: Recreate the venv and install current deps**

```bash
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Expected: installs `sympy 1.13.x` and `pytest`.

- [ ] **Step 2: Prove the existing suite is green before touching anything**

Run: `.venv/bin/pytest -q`
Expected: `58 passed`

- [ ] **Step 3: Add API dependencies to requirements.txt**

Replace the full contents of `requirements.txt` with:

```
# Symbolic engine (Python) — pinned per build guide §4. Independent of the web track.
sympy==1.13.*
pytest>=8

# HTTP API (FastAPI bridge — design doc 2026-07-05)
fastapi>=0.115
uvicorn>=0.30
httpx>=0.27  # TestClient transport; also handy for manual calls
```

- [ ] **Step 4: Install and sanity-check imports**

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python -c "import fastapi, uvicorn, httpx, sympy; print('ok', sympy.__version__)"
```

Expected: `ok 1.13.<x>` (any 1.13 patch).

- [ ] **Step 5: Re-run the suite (deps must not disturb the engine)**

Run: `.venv/bin/pytest -q`
Expected: `58 passed`

- [ ] **Step 6: Commit**

```bash
git add requirements.txt
git commit -m "chore: add fastapi/uvicorn/httpx for the API bridge"
```

---

### Task 2: `api/auth.py` — fail-closed shared-secret auth

**Files:**
- Create: `api/__init__.py`
- Create: `api/auth.py`
- Test: `tests/test_api_auth.py`

**Interfaces:**
- Produces:
  - `api.__version__: str` = `"0.1.0"` (mirrors `pyproject.toml`)
  - `api.auth.expected_key() -> str` — returns the configured key; raises `RuntimeError` if `JOTELAB_API_KEY` is unset/empty.
  - `api.auth.require_api_key` — FastAPI dependency; raises `fastapi.HTTPException(401)` on missing/wrong `X-API-Key` header. Task 5 wires it with `Depends(require_api_key)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_auth.py`:

```python
"""Auth unit tests: the shared-secret dependency, isolated on a stub app."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.auth import expected_key, require_api_key


def _stub_app():
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    def protected():
        return {"ok": True}

    return app


def test_expected_key_raises_when_unset(monkeypatch):
    monkeypatch.delenv("JOTELAB_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="JOTELAB_API_KEY"):
        expected_key()


def test_expected_key_raises_when_empty(monkeypatch):
    monkeypatch.setenv("JOTELAB_API_KEY", "")
    with pytest.raises(RuntimeError, match="JOTELAB_API_KEY"):
        expected_key()


def test_missing_key_is_401(monkeypatch):
    monkeypatch.setenv("JOTELAB_API_KEY", "sekrit")
    client = TestClient(_stub_app())
    assert client.get("/protected").status_code == 401


def test_wrong_key_is_401(monkeypatch):
    monkeypatch.setenv("JOTELAB_API_KEY", "sekrit")
    client = TestClient(_stub_app())
    r = client.get("/protected", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_correct_key_passes(monkeypatch):
    monkeypatch.setenv("JOTELAB_API_KEY", "sekrit")
    client = TestClient(_stub_app())
    r = client.get("/protected", headers={"X-API-Key": "sekrit"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_auth.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 3: Implement**

Create `api/__init__.py`:

```python
"""Jotelab symbolic-engine HTTP bridge (FastAPI).

Thin authenticated wrapper around :func:`engine.generate` so the web app
(physics-jotelab) consumes verified ``sympy_data`` instead of LLM-invented
numbers (design doc 2026-07-05). The API layer never touches a number:
``sympy_data`` passes through byte-identical (ADR-005), and nothing is served
that has not passed ``harness.verify.verify_generic`` in-process.
"""

__version__ = "0.1.0"  # mirrors pyproject.toml
```

Create `api/auth.py`:

```python
"""Shared-secret auth: X-API-Key header vs the JOTELAB_API_KEY env var.

Server-to-server only (the Next.js backend holds the key). Fail-closed: the
app factory calls :func:`expected_key` at startup and refuses to boot without
a key, rather than silently running open.
"""

import os
import secrets

from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

API_KEY_ENV = "JOTELAB_API_KEY"

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def expected_key() -> str:
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{API_KEY_ENV} is not set; refusing to start")
    return key


def require_api_key(provided: str | None = Security(_header)) -> None:
    if provided is None or not secrets.compare_digest(provided, expected_key()):
        raise HTTPException(status_code=401, detail="invalid or missing API key")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_auth.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add api/__init__.py api/auth.py tests/test_api_auth.py
git commit -m "feat(api): fail-closed X-API-Key auth dependency"
```

---

### Task 3: `api/service.py` — verified batch generation

**Files:**
- Create: `api/service.py`
- Test: `tests/test_api_service.py`

**Interfaces:**
- Consumes: `engine.generate(topic, given=None, find=None, difficulty="easy", seed=0)` → `sympy_data` dict; `engine.registry.load_template(topic)` (raises `KeyError` on unknown topic); `harness.verify.verify_generic(sympy_data, template, difficulty)` (raises `FidelityError`, an `AssertionError` subclass).
- Produces:
  - `api.service.UnknownTopicError(Exception)` — attr `.topic`
  - `api.service.VerificationFailedError(Exception)` — attrs `.sympy_data`, `.cause`
  - `api.service.generate_batch(topic, count, difficulty="easy", seed=None, given=None, find=None) -> tuple[list[dict], list[int]]` — returns `(problems, seeds)`; with base `seed`, problem *i* uses `seed + i`; without, fresh random seeds (still returned). Engine exceptions (`UnsolvableError`, `OverDeterminedError`, `NoCleanInstanceError`) propagate untouched.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_service.py`:

```python
"""generate_batch: seed derivation, pass-through parity, verify-before-serve."""

import json

import pytest

import engine
from api import service
from harness.verify import FidelityError


def _dumps(d):
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def test_batch_seeds_derive_from_base_seed():
    problems, seeds = service.generate_batch("suvat", 3, seed=100)
    assert seeds == [100, 101, 102]
    assert len(problems) == 3


def test_pass_through_is_byte_identical_to_direct_engine_call():
    problems, _ = service.generate_batch("suvat", 2, difficulty="medium", seed=42)
    for i, problem in enumerate(problems):
        direct = engine.generate("suvat", difficulty="medium", seed=42 + i)
        assert _dumps(problem) == _dumps(direct)


def test_fresh_seeds_when_no_base_seed_and_reproducible_afterwards():
    problems, seeds = service.generate_batch("suvat", 2)
    assert len(set(seeds)) == 2  # astronomically certain for 32-bit seeds
    replay, _ = service.generate_batch("suvat", 2, seed=seeds[0])
    assert _dumps(replay[0]) == _dumps(problems[0])


def test_unknown_topic_raises_typed_error():
    with pytest.raises(service.UnknownTopicError) as exc:
        service.generate_batch("optics", 1)
    assert exc.value.topic == "optics"


def test_failing_verification_is_never_served(monkeypatch):
    def boom(sympy_data, template, difficulty="easy"):
        raise FidelityError("forced failure")

    monkeypatch.setattr(service, "verify_generic", boom)
    with pytest.raises(service.VerificationFailedError) as exc:
        service.generate_batch("suvat", 1, seed=7)
    assert exc.value.sympy_data["topic"] == "suvat"


def test_engine_errors_propagate_untouched():
    from engine.errors import UnsolvableError

    with pytest.raises(UnsolvableError):
        # v1 SUVAT is single-equation: 2 given / 1 find is not solvable.
        service.generate_batch("suvat", 1, seed=1, given=["u", "a"], find="v")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_service.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'api.service'`

- [ ] **Step 3: Implement**

Create `api/service.py`:

```python
"""The only API module that talks to the engine (design doc: sacred rules).

Rule 1 — pass-through: the ``sympy_data`` dicts returned here are exactly what
``engine.generate`` produced; nothing is reformatted. Rule 2 — verify before
serving: every instance runs through ``verify_generic`` and a failure aborts
the whole batch (all-or-nothing) via :class:`VerificationFailedError`.
"""

import secrets

import engine
from engine.registry import load_template
from harness.verify import verify_generic


class UnknownTopicError(Exception):
    """Requested topic is not in the registry (maps to HTTP 404)."""

    def __init__(self, topic):
        self.topic = topic
        super().__init__(f"unknown topic {topic!r}")


class VerificationFailedError(Exception):
    """A generated instance failed Data Fidelity (maps to HTTP 500).

    Carries the offending payload so the app layer can log it in full — it is
    never served.
    """

    def __init__(self, sympy_data, cause):
        self.sympy_data = sympy_data
        self.cause = cause
        super().__init__(f"generated instance failed Data Fidelity: {cause}")


def generate_batch(topic, count, difficulty="easy", seed=None, given=None,
                   find=None):
    """Generate ``count`` verified problems; returns ``(problems, seeds)``.

    With a base ``seed``, problem *i* uses ``seed + i`` (spec: reproducible
    batches); without one, fresh random 32-bit seeds — echoed either way so any
    batch can be re-made.
    """
    try:
        template = load_template(topic)
    except KeyError:
        raise UnknownTopicError(topic) from None

    if seed is not None:
        seeds = [seed + i for i in range(count)]
    else:
        seeds = [secrets.randbelow(2**32) for _ in range(count)]

    problems = []
    for batch_seed in seeds:
        data = engine.generate(topic, given=given, find=find,
                               difficulty=difficulty, seed=batch_seed)
        try:
            verify_generic(data, template, difficulty)
        except AssertionError as exc:  # FidelityError subclasses AssertionError
            raise VerificationFailedError(data, exc) from exc
        problems.append(data)
    return problems, seeds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_service.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add api/service.py tests/test_api_service.py
git commit -m "feat(api): generate_batch with seed derivation and verify-before-serve"
```

---

### Task 4: `api/schemas.py` — envelope models

**Files:**
- Create: `api/schemas.py`
- Test: `tests/test_api_schemas.py`

**Interfaces:**
- Produces (all Pydantic v2 `BaseModel`s, consumed by Task 5):
  - `GenerateRequest`: `topic: str`, `count: int` (1–20), `difficulty: Literal["easy","medium","hard"] = "easy"`, `seed: int | None = None`, `given: list[str] | None = None`, `find: str | None = None`; validation error unless `given`/`find` are provided together.
  - `BatchMeta`: `topic: str`, `difficulty: str`, `count: int`, `seeds: list[int]`
  - `GenerateResponse`: `problems: list[dict]`, `meta: BatchMeta`
  - `SplitOut`: `given: list[str]`, `find: str` · `TopicOut`: `name: str`, `difficulties: list[str]`, `splits: list[SplitOut]` · `TopicsResponse`: `topics: list[TopicOut]`
  - `HealthResponse`: `status: str`, `engine_version: str`, `sympy_version: str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_schemas.py`:

```python
"""Envelope validation only — sympy_data itself is deliberately untyped."""

import pytest
from pydantic import ValidationError

from api.schemas import GenerateRequest


def test_minimal_request_defaults():
    req = GenerateRequest(topic="suvat", count=1)
    assert req.difficulty == "easy"
    assert req.seed is None and req.given is None and req.find is None


def test_count_bounds():
    with pytest.raises(ValidationError):
        GenerateRequest(topic="suvat", count=0)
    with pytest.raises(ValidationError):
        GenerateRequest(topic="suvat", count=21)
    assert GenerateRequest(topic="suvat", count=20).count == 20


def test_difficulty_is_closed_set():
    with pytest.raises(ValidationError):
        GenerateRequest(topic="suvat", count=1, difficulty="brutal")


def test_given_and_find_must_travel_together():
    with pytest.raises(ValidationError):
        GenerateRequest(topic="suvat", count=1, given=["u", "a", "t"])
    with pytest.raises(ValidationError):
        GenerateRequest(topic="suvat", count=1, find="v")
    req = GenerateRequest(topic="suvat", count=1, given=["u", "a", "t"], find="v")
    assert req.given == ["u", "a", "t"] and req.find == "v"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_schemas.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'api.schemas'`

- [ ] **Step 3: Implement**

Create `api/schemas.py`:

```python
"""Pydantic envelope models. The envelope only: ``problems`` items stay plain
dicts because ``engine/contract.py`` owns the ``sympy_data`` shape — a second
Pydantic copy would drift (design doc §Architecture)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class GenerateRequest(BaseModel):
    topic: str
    count: int = Field(ge=1, le=20)
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    seed: Optional[int] = None
    given: Optional[list[str]] = None
    find: Optional[str] = None

    @model_validator(mode="after")
    def _given_and_find_together(self):
        if (self.given is None) != (self.find is None):
            raise ValueError("given and find must be provided together")
        return self


class BatchMeta(BaseModel):
    topic: str
    difficulty: str
    count: int
    seeds: list[int]


class GenerateResponse(BaseModel):
    problems: list[dict]
    meta: BatchMeta


class SplitOut(BaseModel):
    given: list[str]
    find: str


class TopicOut(BaseModel):
    name: str
    difficulties: list[str]
    splits: list[SplitOut]


class TopicsResponse(BaseModel):
    topics: list[TopicOut]


class HealthResponse(BaseModel):
    status: str
    engine_version: str
    sympy_version: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_schemas.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/schemas.py tests/test_api_schemas.py
git commit -m "feat(api): request/response envelope schemas"
```

---

### Task 5: `api/app.py` — app factory, routes, exception mapping

**Files:**
- Create: `api/app.py`
- Test: `tests/test_api_endpoints.py`

**Interfaces:**
- Consumes: everything produced by Tasks 2–4; `engine.registry.topics()` / `load_template()`; `Template.valid_splits() -> list[tuple[tuple[Symbol, ...], Symbol]]` (symbols have `.name`); `engine.errors.{UnsolvableError, OverDeterminedError, NoCleanInstanceError}`.
- Produces: `api.app.create_app() -> FastAPI` (factory — served with `uvicorn --factory api.app:create_app`). Calls `expected_key()` first, so construction fails without `JOTELAB_API_KEY`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_endpoints.py`:

```python
"""End-to-end endpoint tests over TestClient (in-process, no port)."""

import json

import pytest
from fastapi.testclient import TestClient

import engine
from api import service
from api.app import create_app
from engine.errors import NoCleanInstanceError

KEY = "test-key"
AUTH = {"X-API-Key": KEY}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("JOTELAB_API_KEY", KEY)
    return TestClient(create_app())


def _dumps(d):
    return json.dumps(d, ensure_ascii=False, sort_keys=True)


def test_factory_refuses_to_start_without_key(monkeypatch):
    monkeypatch.delenv("JOTELAB_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="JOTELAB_API_KEY"):
        create_app()


def test_health_is_open_and_reports_versions(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["sympy_version"].startswith("1.13")


def test_protected_endpoints_reject_missing_or_wrong_key(client):
    assert client.get("/topics").status_code == 401
    r = client.post("/generate", json={"topic": "suvat", "count": 1},
                    headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_topics_lists_suvat_with_splits(client):
    r = client.get("/topics", headers=AUTH)
    assert r.status_code == 200
    (suvat,) = [t for t in r.json()["topics"] if t["name"] == "suvat"]
    assert suvat["difficulties"] == ["easy", "medium", "hard"]
    assert {"given": ["u", "a", "t"], "find": "v"} in suvat["splits"]


def test_generate_transparency_parity(client):
    """The invariant test: the wire payload IS the engine payload."""
    r = client.post("/generate", headers=AUTH,
                    json={"topic": "suvat", "count": 2, "difficulty": "medium",
                          "seed": 42})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["seeds"] == [42, 43]
    for i, problem in enumerate(body["problems"]):
        direct = engine.generate("suvat", difficulty="medium", seed=42 + i)
        assert _dumps(problem) == _dumps(direct)


def test_generate_is_deterministic_over_http(client):
    req = {"topic": "suvat", "count": 5, "seed": 42}
    a = client.post("/generate", json=req, headers=AUTH).json()
    b = client.post("/generate", json=req, headers=AUTH).json()
    assert _dumps(a) == _dumps(b)
    assert a["meta"]["seeds"] == [42, 43, 44, 45, 46]


def test_unknown_topic_is_404(client):
    r = client.post("/generate", json={"topic": "optics", "count": 1},
                    headers=AUTH)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "unknown_topic"


def test_bad_envelope_is_422(client):
    assert client.post("/generate", json={"topic": "suvat", "count": 0},
                       headers=AUTH).status_code == 422
    assert client.post("/generate",
                       json={"topic": "suvat", "count": 1, "difficulty": "x"},
                       headers=AUTH).status_code == 422


def test_unsolvable_split_is_422(client):
    r = client.post("/generate", headers=AUTH,
                    json={"topic": "suvat", "count": 1,
                          "given": ["u", "a"], "find": "v"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unsolvable_split"


def test_convergence_failure_is_409(client, monkeypatch):
    def exhausted(*args, **kwargs):
        raise NoCleanInstanceError("suvat", "v", attempts=200)

    monkeypatch.setattr(service.engine, "generate", exhausted)
    r = client.post("/generate", json={"topic": "suvat", "count": 1},
                    headers=AUTH)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "convergence_failed"


def test_verification_failure_is_500_and_serves_nothing(client, monkeypatch):
    from harness.verify import FidelityError

    def boom(sympy_data, template, difficulty="easy"):
        raise FidelityError("forced")

    monkeypatch.setattr(service, "verify_generic", boom)
    r = client.post("/generate", json={"topic": "suvat", "count": 1},
                    headers=AUTH)
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "verification_failed"
    assert "problems" not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api_endpoints.py -v`
Expected: FAIL (collection error) with `ModuleNotFoundError: No module named 'api.app'`

- [ ] **Step 3: Implement**

Create `api/app.py`:

```python
"""FastAPI switchboard: routes, auth wiring, exception→HTTP mapping.

Serve with:  uvicorn --factory api.app:create_app
(A factory, not a module-level ``app``: construction reads JOTELAB_API_KEY and
must be able to fail loudly — and tests build isolated apps per fixture.)
"""

import logging

import sympy
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from api import __version__, service
from api.auth import expected_key, require_api_key
from api.schemas import (BatchMeta, GenerateRequest, GenerateResponse,
                         HealthResponse, SplitOut, TopicOut, TopicsResponse)
from engine.errors import (NoCleanInstanceError, OverDeterminedError,
                           UnsolvableError)
from engine.registry import load_template, topics

log = logging.getLogger("jotelab.api")

DIFFICULTIES = ["easy", "medium", "hard"]


def _error(status, code, message, detail=None):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message,
                           "detail": detail or {}}},
    )


def create_app() -> FastAPI:
    expected_key()  # fail closed: no key, no app
    app = FastAPI(title="Jotelab Symbolic Engine API", version=__version__)

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        code = "unauthorized" if exc.status_code == 401 else "http_error"
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(service.UnknownTopicError)
    async def unknown_topic(request: Request, exc: service.UnknownTopicError):
        return _error(404, "unknown_topic", str(exc),
                      {"topic": exc.topic, "known": topics()})

    @app.exception_handler(UnsolvableError)
    async def unsolvable(request: Request, exc: UnsolvableError):
        return _error(422, "unsolvable_split", str(exc))

    @app.exception_handler(OverDeterminedError)
    async def over_determined(request: Request, exc: OverDeterminedError):
        return _error(422, "over_determined_split", str(exc))

    @app.exception_handler(NoCleanInstanceError)
    async def no_clean_instance(request: Request, exc: NoCleanInstanceError):
        return _error(409, "convergence_failed", str(exc),
                      {"attempts": exc.attempts})

    @app.exception_handler(service.VerificationFailedError)
    async def verification_failed(request: Request,
                                  exc: service.VerificationFailedError):
        # The payload never leaves the process; log it in full so a fidelity
        # bug is diagnosable from server logs alone (design doc §Errors).
        log.error("Data Fidelity failure — payload withheld: %s | %r",
                  exc.cause, exc.sympy_data)
        return _error(500, "verification_failed",
                      "a generated instance failed verification and was not served")

    @app.get("/health", response_model=HealthResponse)
    def health():
        return HealthResponse(status="ok", engine_version=__version__,
                              sympy_version=sympy.__version__)

    @app.get("/topics", response_model=TopicsResponse,
             dependencies=[Depends(require_api_key)])
    def list_topics():
        out = []
        for name in topics():
            template = load_template(name)
            splits = [SplitOut(given=[s.name for s in given], find=find.name)
                      for given, find in template.valid_splits()]
            out.append(TopicOut(name=name, difficulties=DIFFICULTIES,
                                splits=splits))
        return TopicsResponse(topics=out)

    @app.post("/generate", response_model=GenerateResponse,
              dependencies=[Depends(require_api_key)])
    def generate(req: GenerateRequest):
        problems, seeds = service.generate_batch(
            req.topic, req.count, difficulty=req.difficulty, seed=req.seed,
            given=req.given, find=req.find)
        return GenerateResponse(
            problems=problems,
            meta=BatchMeta(topic=req.topic, difficulty=req.difficulty,
                           count=req.count, seeds=seeds))

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api_endpoints.py -v`
Expected: 11 passed

Note: TestClient raises server exceptions by default only for unhandled ones; all five custom handlers return JSON, so no `raise_server_exceptions` tweak is needed.

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: `84 passed` (58 existing + 5 auth + 6 service + 4 schemas + 11 endpoints)

- [ ] **Step 6: Commit**

```bash
git add api/app.py tests/test_api_endpoints.py
git commit -m "feat(api): app factory with routes and exception mapping"
```

---

### Task 6: Dockerfile, manual smoke test, README section

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Modify: `README.md` (append a new `## HTTP API` section at the end)

**Interfaces:**
- Consumes: `create_app` factory (Task 5); `requirements.txt` (Task 1).
- Produces: a runnable container; documented run instructions.

- [ ] **Step 1: Write the Dockerfile**

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /srv/jotelab

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine/ engine/
COPY templates/ templates/
COPY harness/ harness/
COPY api/ api/

# JOTELAB_API_KEY must be provided at run time; the app refuses to start without it.
# PORT is honoured for container hosts that inject it (design doc: env-only config).
EXPOSE 8000
CMD ["sh", "-c", "uvicorn --factory api.app:create_app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Create `.dockerignore`:

```
.venv
.git
.claude
docs
tests
__pycache__
*.pyc
.pytest_cache
```

- [ ] **Step 2: Manual smoke test (local uvicorn — no Docker needed for the gate)**

```bash
JOTELAB_API_KEY=dev-key .venv/bin/uvicorn --factory api.app:create_app --port 8123 &
sleep 2
curl -s localhost:8123/health
curl -s -H "X-API-Key: dev-key" localhost:8123/topics | head -c 200; echo
curl -s -X POST -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"topic":"suvat","count":2,"difficulty":"medium","seed":42}' \
  localhost:8123/generate | .venv/bin/python -m json.tool | head -30
kill %1
```

Expected: health returns `{"status":"ok",...}`; topics lists `suvat`; generate returns two problems and `"seeds": [42, 43]`.

Also verify fail-closed startup:

```bash
.venv/bin/uvicorn --factory api.app:create_app --port 8124
```

Expected: crashes immediately with `RuntimeError: JOTELAB_API_KEY is not set; refusing to start` (Ctrl-C not needed).

If Docker is available, optionally:

```bash
docker build -t jotelab-api . && docker run --rm -e JOTELAB_API_KEY=dev-key -p 8000:8000 jotelab-api
```

- [ ] **Step 3: Append the README section**

Append to `README.md`:

````markdown
## HTTP API (integration bridge)

A thin authenticated FastAPI wrapper (`api/`) exposes the engine to
[physics-jotelab] so every number the app shows comes from SymPy, never an LLM
(ADR-001). The API passes `sympy_data` through byte-identical and re-verifies
every instance with the Data-Fidelity harness before serving it.

```bash
pip install -r requirements.txt
JOTELAB_API_KEY=dev-key uvicorn --factory api.app:create_app  # http://localhost:8000
```

| Endpoint | Auth (`X-API-Key`) | Purpose |
|---|---|---|
| `POST /generate` | yes | `{topic, count ≤ 20, difficulty?, seed?, given?, find?}` → verified problems + echoed seeds |
| `GET /topics` | yes | registered topics, difficulties, valid splits |
| `GET /health` | no | liveness + engine/SymPy versions |

Batches are all-or-nothing; with `seed`, problem *i* uses `seed + i`, so any
batch is reproducible. Errors use `{"error": {code, message, detail}}` with
`401/404/409/422/500`. Container: `docker build -t jotelab-api . && docker run
-e JOTELAB_API_KEY=... -p 8000:8000 jotelab-api`. Design:
`docs/superpowers/specs/2026-07-05-fastapi-service-design.md`.
````

- [ ] **Step 4: Full suite one last time**

Run: `.venv/bin/pytest -q`
Expected: `84 passed`

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore README.md
git commit -m "feat(api): Dockerfile + README section for the HTTP bridge"
```
