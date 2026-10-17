"""
FastAPI application entry point.

Endpoints:
- GET /health   : liveness/readiness check
- POST /ask     : main pipeline endpoint (stub mode only so far)
- GET /audit    : latest audit rows, read only (added later)
- GET /dashboard: serves static dashboard files (added later)
"""
import uuid

from fastapi import FastAPI, Header, HTTPException

from app.auth import AuthError, resolve_token
from app.config import STUB_MODE
from app.schemas import AskRequest, AskResponse
from app.stub_data import STUB_ANSWER, STUB_GUARDS, STUB_LATENCY_MS, STUB_SOURCES

app = FastAPI(title="Zero-Exposure RAG")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "stub_mode": STUB_MODE,
        "model_loaded": False,  # updated once real model integration lands
    }


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, x_user_token: str = Header(...)):
    try:
        identity = resolve_token(x_user_token)
    except AuthError:
        raise HTTPException(status_code=401, detail="invalid or missing token")

    # Role comes only from the resolved token, never from the request body.
    _role = identity["role"]

    if not STUB_MODE:
        raise HTTPException(
            status_code=501,
            detail="Real pipeline not yet implemented. Set STUB_MODE=1.",
        )

    return AskResponse(
        request_id=f"r_{uuid.uuid4().hex[:8]}",
        answer=STUB_ANSWER,
        blocked=False,
        block_reason=None,
        sources=STUB_SOURCES,
        guards=STUB_GUARDS,
        latency_ms=STUB_LATENCY_MS,
    )
