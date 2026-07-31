"""Tests for Gemini template authoring (service/authoring.py + POST /author).

No test here calls a real model: the model is a plain ``prompt -> text``
callable, so fakes stand in for Gemini and the tests exercise the real gate,
registry, and persistence paths around it.
"""

import json
from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from engine import registry  # noqa: E402
from engine.registry import load_template, topics  # noqa: E402
from service import authoring  # noqa: E402
from service.app import app  # noqa: E402
from service.authoring import (  # noqa: E402
    AuthoringError,
    TopicCollisionError,
    author_template,
)

API_KEY = "test-secret"
AUTH = {"X-Engine-Api-Key": API_KEY}

DATA_DIR = Path(__file__).resolve().parents[1] / "templates" / "data"
TOPIC = "authored-test-topic"


def good_doc(topic=TOPIC):
    """A known gate-passing doc: the vetted free_fall seed under a fresh name."""
    doc = json.loads((DATA_DIR / "free_fall.json").read_text())
    doc["topic"] = topic
    return doc


@pytest.fixture(autouse=True)
def isolate(monkeypatch, tmp_path):
    """Persist to a temp dir and drop any topic a test registers."""
    monkeypatch.setattr(registry, "AUTHORED_DIR", tmp_path / "authored")
    before = set(topics())
    yield
    for name in set(topics()) - before:
        registry._REGISTRY.pop(name, None)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ENGINE_API_KEY", API_KEY)
    return TestClient(app)


# --------------------------------------------------------------------------- #
# author_template — the loop itself.
# --------------------------------------------------------------------------- #
def test_happy_path_registers_and_persists():
    result = author_template("free fall from a height",
                             model_call=lambda p: json.dumps(good_doc()))

    assert result.attempts == 1
    assert result.report.passed
    assert TOPIC in topics()
    assert load_template(TOPIC).topic == TOPIC
    persisted = json.loads(result.path.read_text())
    assert persisted["topic"] == TOPIC
    assert persisted["trust_state"] == "unverified"


def test_repair_loop_feeds_gate_reason_back():
    prompts = []

    def flaky(prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            return "sorry, no JSON here"
        return json.dumps(good_doc())

    result = author_template("free fall", model_call=flaky)

    assert result.attempts == 2
    assert "REJECTED" in prompts[1]
    assert "valid JSON" in prompts[1]


def test_gate_failure_reason_reaches_repair_prompt():
    bad = good_doc()
    bad["equations"] = ["Eq(v, u + g*t)"]  # too few equations: split underivable
    prompts = []

    def flaky(prompt):
        prompts.append(prompt)
        return json.dumps(good_doc() if len(prompts) > 1 else bad)

    result = author_template("free fall", model_call=flaky)

    assert result.attempts == 2
    assert "gate stage" in prompts[1]


def test_exhaustion_raises_with_last_report():
    bad = good_doc()
    bad["golden_cases"] = []  # stage 4 requires >= 1

    with pytest.raises(AuthoringError) as excinfo:
        author_template("free fall", max_attempts=2,
                        model_call=lambda p: json.dumps(bad))

    err = excinfo.value
    assert err.attempts == 2
    assert err.last_draft["topic"] == TOPIC
    assert any(not s.passed for s in err.last_report.stages)
    assert TOPIC not in topics()


def test_pinned_topic_collision_raises_before_model_call():
    def explode(prompt):
        raise AssertionError("model must not be called")

    with pytest.raises(TopicCollisionError):
        author_template("anything", topic="suvat", model_call=explode)


def test_model_chosen_collision_triggers_rename_retry():
    prompts = []

    def flaky(prompt):
        prompts.append(prompt)
        name = "suvat" if len(prompts) == 1 else TOPIC
        return json.dumps(good_doc(topic=name))

    result = author_template("kinematics", model_call=flaky)

    assert result.attempts == 2
    assert "already exists" in prompts[1]


# --------------------------------------------------------------------------- #
# Registry — authored templates reload after a restart.
# --------------------------------------------------------------------------- #
def test_registry_reloads_authored_dir(monkeypatch):
    registry.AUTHORED_DIR.mkdir(parents=True)
    (registry.AUTHORED_DIR / f"{TOPIC}.json").write_text(json.dumps(good_doc()))

    monkeypatch.setattr(registry, "_declarative_loaded", False)
    assert TOPIC in topics()


def test_registry_skips_broken_authored_file(monkeypatch):
    registry.AUTHORED_DIR.mkdir(parents=True)
    (registry.AUTHORED_DIR / "broken.json").write_text('{"topic": "broken"}')

    monkeypatch.setattr(registry, "_declarative_loaded", False)
    assert "broken" not in topics()
    assert "suvat" in topics()  # the rest of the registry survives


# --------------------------------------------------------------------------- #
# POST /author — transport layer.
# --------------------------------------------------------------------------- #
def test_author_requires_api_key(client):
    resp = client.post("/author", json={"description": "free fall"})
    assert resp.status_code == 401


def test_author_503_without_gemini_key(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENERATIVE_AI_API_KEY", raising=False)
    resp = client.post("/author", json={"description": "free fall"}, headers=AUTH)
    assert resp.status_code == 503
    assert "GOOGLE_API_KEY" in resp.json()["detail"]


def test_author_endpoint_happy_path(client, monkeypatch):
    monkeypatch.setattr(authoring, "get_model_call",
                        lambda: lambda p: json.dumps(good_doc()))

    resp = client.post("/author", json={"description": "free fall"}, headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == TOPIC
    assert body["attempts"] == 1
    assert [s["passed"] for s in body["gate_report"]] == [True] * 5
    assert body["template"]["trust_state"] == "unverified"
    assert body["samples"], "expected at least one verified sample instance"
    assert all(s["topic"] == TOPIC for s in body["samples"])

    # The authored topic is immediately servable by /generate — the demo flow.
    gen = client.post("/generate", json={"topic": TOPIC}, headers=AUTH)
    assert gen.status_code == 200


def test_author_endpoint_409_on_pinned_collision(client, monkeypatch):
    monkeypatch.setattr(authoring, "get_model_call",
                        lambda: lambda p: json.dumps(good_doc()))
    resp = client.post("/author", json={"description": "x", "topic": "suvat"},
                       headers=AUTH)
    assert resp.status_code == 409


def test_author_endpoint_422_reports_last_draft(client, monkeypatch):
    bad = good_doc()
    bad["golden_cases"] = []
    monkeypatch.setattr(authoring, "get_model_call",
                        lambda: lambda p: json.dumps(bad))

    resp = client.post("/author",
                       json={"description": "x", "max_attempts": 2}, headers=AUTH)

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["attempts"] == 2
    assert detail["last_draft"]["topic"] == TOPIC
    assert any(not s["passed"] for s in detail["gate_report"])
