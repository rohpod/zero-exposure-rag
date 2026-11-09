"""
FastAPI application entry point.

Endpoints:
- GET /health      : liveness/readiness check (never calls the LLM)
- POST /ask        : main pipeline endpoint
- GET /audit       : latest audit rows, compliance officers only
- GET /dashboard/* : serves static dashboard files from dashboard/
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import audit
from app.auth import AuthError, init_tokens, resolve_token
from app.config import get_settings, reload_settings
from app.guards.injection import load_model
from app.llm import get_llm, reset_llm
from app.pipeline import PipelineAuthError, PipelineError, init_pipeline, run_pipeline
from app.schemas import AskRequest, AskResponse

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Everything is loaded here, never lazily on the first request.
    reload_settings()
    init_tokens()
    init_pipeline()
    load_model()
    audit.init_db()
    reset_llm()
    get_llm()
    yield


app = FastAPI(title="Zero-Exposure RAG", lifespan=lifespan)


@app.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.model_name,
        "eval_mode": settings.eval_mode,
        "poisoned_corpus": settings.poisoned_corpus,
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
    except PipelineError as exc:
        headers = {}
        if exc.retry_after is not None:
            headers["Retry-After"] = str(int(exc.retry_after))
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail}, headers=headers
        )

    return AskResponse(**result)


@app.get("/audit")
def read_audit(
    x_user_token: str | None = Header(default=None),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        identity = resolve_token(x_user_token)
    except AuthError:
        raise HTTPException(status_code=401, detail="invalid or missing token")
    if identity["role"] != "compliance_officer":
        raise HTTPException(status_code=403, detail="compliance officers only")
    return {"rows": audit.read_latest(limit=limit)}


app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
