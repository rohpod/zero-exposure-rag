import json

import pytest
from fastapi.testclient import TestClient

TOKENS = {
    "tok_support": {"user_id": "u_support", "role": "support_agent"},
    "tok_fraud": {"user_id": "u_fraud", "role": "fraud_analyst"},
    "tok_compliance": {"user_id": "u_compliance", "role": "compliance_officer"},
}


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    """Build a TestClient against the real pipeline with the mock LLM and a temp audit DB."""
    from app.main import app

    clients = []

    def _make(**env):
        defaults = {
            "LLM_PROVIDER": "mock",
            "LLM_MOCK_MODE": "fixed",
            "EVAL_MODE": "0",
            "POISONED_CORPUS": "0",
            "LLM_CACHE": "0",
            "AUDIT_DB_PATH": str(tmp_path / "audit.sqlite3"),
            "AUTH_TOKENS_JSON": json.dumps(TOKENS),
        }
        for key, value in {**defaults, **env}.items():
            monkeypatch.setenv(key, value)
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def headers(token: str, **extra) -> dict:
    return {"X-User-Token": token, **extra}


@pytest.fixture
def audit_rows():
    from app import audit

    return audit.read_latest
