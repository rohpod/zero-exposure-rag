"""
FastAPI application entry point.

Endpoints:
- GET /health   : liveness/readiness check
- POST /ask     : main pipeline endpoint (added in a later commit)
- GET /audit    : latest audit rows, read only (added later)
- GET /dashboard: serves static dashboard files (added later)
"""
from fastapi import FastAPI

from app.config import STUB_MODE

app = FastAPI(title="Zero-Exposure RAG")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "stub_mode": STUB_MODE,
        "model_loaded": False,  # updated once real model integration lands
    }
