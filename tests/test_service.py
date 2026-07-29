"""Tests for the engine HTTP service (service/app.py, DEVELOPMENT_PLAN §1.1)."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from service.app import app  # noqa: E402

API_KEY = "test-secret"
AUTH = {"X-Engine-Api-Key": API_KEY}


@pytest.fixture()
def client(monkeypatch):
    """A TestClient with ENGINE_API_KEY configured (auth enabled)."""
    monkeypatch.setenv("ENGINE_API_KEY", API_KEY)
    return TestClient(app)


def test_health_needs_no_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "suvat" in body["topics"]


def test_generate_requires_api_key(client):
    resp = client.post("/generate", json={"topic": "suvat"})
    assert resp.status_code == 401


def test_generate_fails_closed_without_configured_key(monkeypatch):
    """If ENGINE_API_KEY is unset the service refuses to serve (503)."""
    monkeypatch.delenv("ENGINE_API_KEY", raising=False)
    resp = TestClient(app).post("/generate", json={"topic": "suvat"}, headers=AUTH)
    assert resp.status_code == 503


def test_generate_pinned_is_verified_and_reproducible(client):
    """The worked SUVAT example returns the locked contract and passes fidelity."""
    payload = {
        "topic": "suvat",
        "given": ["u", "a", "t"],
        "find": "v",
        "conditions": {"u": 0, "a": 2, "t": 5},
        "difficulty": "easy",
    }
    resp = client.post("/generate", json=payload, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["topic"] == "suvat"
    assert data["find"] == {"symbol": "v", "value": 10, "exact": "10", "unit": "m/s"}
    assert data["plausible"] is True

    # The generated payload must itself verify through /verify.
    v = client.post("/verify", json={"sympy_data": data}, headers=AUTH)
    assert v.status_code == 200
    assert v.json() == {"verified": True, "detail": None}


def test_generate_bare_request_is_fresh_and_valid(client):
    """A bare request picks a random split+seed and still returns a verified problem."""
    resp = client.post("/generate", json={}, headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["topic"] == "suvat"
    assert isinstance(data["seed"], int)
    assert len(data["given"]) == 3


def test_generate_unsolvable_returns_422(client):
    resp = client.post(
        "/generate",
        json={"topic": "suvat", "given": ["u", "a"], "find": "v"},
        headers=AUTH,
    )
    assert resp.status_code == 422
    assert "cannot solve" in resp.json()["detail"]


def test_generate_unknown_topic_returns_400(client):
    resp = client.post("/generate", json={"topic": "nope"}, headers=AUTH)
    assert resp.status_code == 400


def test_verify_rejects_tampered_payload(client):
    """Corrupting a number is caught by the Data Fidelity harness (verified=false)."""
    data = client.post(
        "/generate",
        json={"topic": "suvat", "given": ["u", "a", "t"], "find": "v",
              "conditions": {"u": 0, "a": 2, "t": 5}},
        headers=AUTH,
    ).json()
    data["find"]["exact"] = "999"  # tamper: no longer the true answer
    data["find"]["value"] = 999
    resp = client.post("/verify", json={"sympy_data": data}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["verified"] is False


def test_generate_serves_every_registered_topic(client):
    """The verify_generic gate serves all topics, not just suvat.

    Regression for the sandbox finding: the original service called the
    SUVAT-only ``harness.verify.verify`` and answered 501 for every other
    registered topic.
    """
    from engine.registry import topics

    for topic in topics():
        resp = client.post(
            "/generate", json={"topic": topic, "seed": 1}, headers=AUTH
        )
        assert resp.status_code == 200, f"{topic}: {resp.json()}"
        assert resp.json()["topic"] == topic


def test_chain_sanctioned_link_is_verified_and_reproducible(client):
    """A free-fall → suvat chain (sanctioned link) serves end to end."""
    payload = {
        "difficulty": "easy",
        "seed": 7,
        "parts": [
            {"topic": "free-fall"},
            {"topic": "suvat", "given": ["u", "a", "t"], "find": "s",
             "receive": "u"},
        ],
    }
    resp = client.post("/chain", json=payload, headers=AUTH)
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    parts = data["parts"]
    assert len(parts) == 2
    # The link carries part 1's exact answer into part 2's received given.
    linked = next(g for g in parts[1]["given"] if g["symbol"] == "u")
    assert linked["exact"] == parts[0]["find"]["exact"]
    # Determinism: same request, same chain.
    again = client.post("/chain", json=payload, headers=AUTH)
    assert again.json() == data


def test_chain_missing_receive_returns_400(client):
    resp = client.post(
        "/chain",
        json={"parts": [{"topic": "free-fall"}, {"topic": "suvat"}]},
        headers=AUTH,
    )
    assert resp.status_code == 400
    assert "receive" in resp.json()["detail"]


def test_chain_unsanctioned_link_returns_400(client):
    """A physically unvetted composition is refused loudly, not served."""
    resp = client.post(
        "/chain",
        json={
            "parts": [
                {"topic": "free-fall"},
                {"topic": "upward-throw", "receive": "u"},
            ]
        },
        headers=AUTH,
    )
    assert resp.status_code == 400
    assert "sanctioned" in resp.json()["detail"]
