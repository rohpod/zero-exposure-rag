"""
FastAPI application entry point.

Endpoints:
- GET /health      : liveness/readiness check
- POST /ask        : main pipeline endpoint
- GET /audit       : latest audit rows, read only
- GET /dashboard/* : serves static dashboard files from dashboard/
"""
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles

from app.audit import read_latest
from app.config import STUB_MODE
from app.pipeline import PipelineAuthError, run_pipeline
from app.schemas import AskRequest, AskResponse

app = FastAPI(title="Zero-Exposure RAG")

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "stub_mode": STUB_MODE,
        "model_loaded": False,  # updated once real model integration lands
    }


@app.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    x_user_token: str | None = Header(default=None),
    x_guards: str | None = Header(default=None),
):
    try:
        result = run_pipeline(
            query=body.query, token=x_user_token, x_guards_header=x_guards
        )
    except PipelineAuthError:
        raise HTTPException(status_code=401, detail="invalid or missing token")
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))

    return AskResponse(**result)


@app.get("/audit")
def audit(limit: int = 50):
    return {"rows": read_latest(limit=limit)}


app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
