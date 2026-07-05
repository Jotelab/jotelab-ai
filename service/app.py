"""FastAPI app exposing the symbolic engine over HTTP (DEVELOPMENT_PLAN §1.1).

Two endpoints, both behind a shared-secret header (``X-Engine-Api-Key``):

* ``POST /generate`` — sample one fully-solved problem via
  :func:`engine.loop.generate`, **enforce Data Fidelity at the source** by running
  it through :func:`harness.verify.verify` before returning, and emit the locked
  ``sympy_data`` contract verbatim (see :mod:`engine.contract`).
* ``POST /verify`` — run the Data Fidelity harness on a caller-supplied
  ``sympy_data`` payload and report whether it is faithful.

The web app trusts numbers only because they are verified here, not downstream:
a ``/generate`` response can never leave this process without passing the harness.
No engine logic lives in this module — it is a thin transport + auth layer.
"""

from __future__ import annotations

import os
import random
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from engine.errors import EngineError
from engine.loop import generate as engine_generate
from engine.registry import load_template, topics
from harness.verify import FidelityError, verify

app = FastAPI(
    title="Jotelab Symbolic Engine",
    version="0.1.0",
    description=(
        "Neuro-symbolic core: every number a student sees originates here and is "
        "verified by the Data Fidelity harness before it is returned."
    ),
)


# --------------------------------------------------------------------------- #
# Auth — shared secret header (DEVELOPMENT_PLAN §1.1: ENGINE_API_KEY).
# --------------------------------------------------------------------------- #
def require_api_key(x_engine_api_key: Optional[str] = Header(default=None)) -> None:
    """Reject any request whose ``X-Engine-Api-Key`` header != ``ENGINE_API_KEY``.

    The secret is read from the environment on every call (not cached) so the
    service picks up a rotated key without a restart. If ``ENGINE_API_KEY`` is not
    configured the service fails closed with 503 rather than silently running open.
    """
    expected = os.environ.get("ENGINE_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ENGINE_API_KEY is not configured on the engine service.",
        )
    if x_engine_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Engine-Api-Key header.",
        )


# --------------------------------------------------------------------------- #
# Request models.
# --------------------------------------------------------------------------- #
class GenerateRequest(BaseModel):
    """Mirror of :func:`engine.loop.generate`'s public parameters.

    Basic mode: send only ``topic`` (+ ``difficulty``). Advanced mode: pin
    ``given`` (3 variable names) and ``find`` (1). Omitting both ``given`` and
    ``find`` picks a random valid split; omitting ``seed`` picks a random seed —
    so a bare request yields a fresh problem, exactly like ``python -m engine``.
    """

    topic: str = "suvat"
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    given: Optional[list[str]] = Field(
        default=None, description="Advanced mode: the Given variable names, e.g. ['u','a','t']."
    )
    find: Optional[str] = Field(
        default=None, description="Advanced mode: the single Find/target variable, e.g. 'v'."
    )
    conditions: Optional[dict[str, int]] = Field(
        default=None, description="Pin variables to exact integer values, e.g. {'u': 0}."
    )
    seed: Optional[int] = Field(
        default=None, description="RNG seed for reproducibility; random each call if omitted."
    )


class VerifyRequest(BaseModel):
    """A ``sympy_data`` payload to re-check through the Data Fidelity harness."""

    sympy_data: dict
    difficulty: Literal["easy", "medium", "hard"] = "easy"


class VerifyResponse(BaseModel):
    verified: bool
    detail: Optional[str] = None


# --------------------------------------------------------------------------- #
# Endpoints.
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    """Unauthenticated liveness probe — also lists the topics the engine serves."""
    return {"status": "ok", "topics": topics()}


def _random_split(topic: str) -> tuple[list[str], str]:
    """Pick a random valid ``(given, find)`` split for ``topic`` (names).

    Reuses the template's own :meth:`~templates.base.Template.valid_splits`, the
    same source the CLI uses, so the service and ``python -m engine`` agree on what
    a fresh Basic-mode problem looks like.
    """
    template = load_template(topic)
    given, find = random.choice(template.valid_splits())
    return [s.name for s in given], find.name


@app.post("/generate", dependencies=[Depends(require_api_key)])
def generate(req: GenerateRequest) -> dict:
    """Generate one verified, fully-solved problem as ``sympy_data``.

    The response is guaranteed to have passed the Data Fidelity harness; fidelity
    is enforced here at the source, never trusted downstream (DEVELOPMENT_PLAN §1.1).
    """
    seed = req.seed if req.seed is not None else random.randrange(1_000_000)
    given, find = req.given, req.find
    try:
        if given is None and find is None:
            given, find = _random_split(req.topic)
        data = engine_generate(
            req.topic,
            given=given,
            find=find,
            conditions=req.conditions or None,
            difficulty=req.difficulty,
            seed=seed,
        )
    except KeyError as exc:  # unknown topic or variable name
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except EngineError as exc:  # unsolvable / over-determined / no clean instance
        raise HTTPException(status_code=422, detail=str(exc))  # Unprocessable

    # Fidelity gate: a response can never leave unverified (DEVELOPMENT_PLAN §1.1).
    try:
        verify(data, difficulty=req.difficulty)
    except NotImplementedError as exc:  # topic has no harness yet — refuse to ship it
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        )
    except FidelityError as exc:  # engine produced unfaithful data — must never happen
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data Fidelity check failed at source: {exc}",
        )
    return data


@app.post(
    "/verify",
    response_model=VerifyResponse,
    dependencies=[Depends(require_api_key)],
)
def verify_payload(req: VerifyRequest) -> VerifyResponse:
    """Run the Data Fidelity harness on a caller-supplied ``sympy_data`` payload."""
    try:
        verify(req.sympy_data, difficulty=req.difficulty)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
    except FidelityError as exc:
        return VerifyResponse(verified=False, detail=str(exc))
    except (KeyError, TypeError) as exc:  # malformed payload
        raise HTTPException(
            status_code=422, detail=f"Malformed sympy_data payload: {exc}"
        )
    return VerifyResponse(verified=True)
