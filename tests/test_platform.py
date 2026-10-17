import pytest
from fastapi.testclient import TestClient

import app.audit as audit
import app.pipeline as pipeline
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate each test from the real audit database.
    monkeypatch.setattr(audit, "DB_PATH", tmp_path / "test-audit.sqlite3")

    # Use a deterministic identity instead of depending on local token files.
    monkeypatch.setattr(
        pipeline,
        "resolve_token",
        lambda token: (
            {"user_id": "test-user", "role": "analyst"}
            if token == "valid-test-token"
            else (_ for _ in ()).throw(pipeline.AuthError("invalid token"))
        ),
    )
    monkeypatch.setattr(pipeline, "STUB_MODE", True)
    monkeypatch.setattr(pipeline, "EVAL_MODE", False)

    with TestClient(app) as test_client:
        yield test_client


def test_health_contract(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["stub_mode"] is True
    assert "model_loaded" in body


def test_ask_returns_expected_response_fields(client):
    response = client.post(
        "/ask",
        headers={"X-User-Token": "valid-test-token"},
        json={"query": "Summarize the quarterly report"},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["request_id"].startswith("r_")
    assert isinstance(body["answer"], str)
    assert isinstance(body["blocked"], bool)
    assert "block_reason" in body
    assert isinstance(body["sources"], list)
    assert isinstance(body["guards"], dict)
    assert isinstance(body["latency_ms"], dict)
    assert isinstance(body["guards_disabled"], bool)


def test_missing_token_is_rejected_and_audited(client):
    response = client.post("/ask", json={"query": "Hello"})

    assert response.status_code == 401

    rows = audit.read_latest()
    assert len(rows) == 1
    assert rows[0]["decision"] == "blocked_input"
    assert rows[0]["block_reason"] == "auth"

def test_invalid_token_is_rejected_and_audited(client):
    response = client.post(
        "/ask",
        headers={"X-User-Token": "invalid-test-token"},
        json={"query": "Hello"},
    )

    assert response.status_code == 401

    rows = audit.read_latest()
    assert len(rows) == 1
    assert rows[0]["decision"] == "blocked_input"
    assert rows[0]["block_reason"] == "auth"
    assert rows[0]["user_id"] is None
    assert rows[0]["role"] is None


def test_successful_request_is_audited(client):
    response = client.post(
        "/ask",
        headers={"X-User-Token": "valid-test-token"},
        json={"query": "Summarize the quarterly report"},
    )

    assert response.status_code == 200

    rows = audit.read_latest()
    assert len(rows) == 1
    assert rows[0]["decision"] == "answered"
    assert rows[0]["user_id"] == "test-user"
    assert rows[0]["role"] == "analyst"


def test_audit_endpoint_returns_persisted_rows(client):
    client.post(
        "/ask",
        headers={"X-User-Token": "valid-test-token"},
        json={"query": "Audit me"},
    )

    response = client.get("/audit")

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["query"] == "Audit me"


def test_guards_off_header_is_ignored_outside_eval_mode(client, monkeypatch):
    monkeypatch.setattr(pipeline, "EVAL_MODE", False)

    response = client.post(
        "/ask",
        headers={
            "X-User-Token": "valid-test-token",
            "X-Guards": "off",
        },
        json={"query": "Test evaluation header"},
    )

    assert response.status_code == 200
    assert response.json()["guards_disabled"] is False


def test_guards_can_be_disabled_in_eval_mode(client, monkeypatch):
    monkeypatch.setattr(pipeline, "EVAL_MODE", True)

    response = client.post(
        "/ask",
        headers={
            "X-User-Token": "valid-test-token",
            "X-Guards": "off",
        },
        json={"query": "Test evaluation header"},
    )

    assert response.status_code == 200
    assert response.json()["guards_disabled"] is True


def test_other_guards_header_values_do_not_disable_guards(client, monkeypatch):
    monkeypatch.setattr(pipeline, "EVAL_MODE", True)

    response = client.post(
        "/ask",
        headers={
            "X-User-Token": "valid-test-token",
            "X-Guards": "on",
        },
        json={"query": "Test evaluation header"},
    )

    assert response.status_code == 200
    assert response.json()["guards_disabled"] is False


@pytest.mark.parametrize(
    "decision",
    ["answered", "blocked_input", "blocked_output", "error"],
)
def test_audit_storage_supports_all_decision_types(client, decision):
    audit.write_row(
        request_id=f"test-{decision}",
        timestamp="2026-01-01T00:00:00+00:00",
        user_id="test-user",
        role="analyst",
        query="Synthetic test query",
        decision=decision,
        block_reason=None if decision == "answered" else "test",
    )

    rows = audit.read_latest()
    assert any(row["decision"] == decision for row in rows)
