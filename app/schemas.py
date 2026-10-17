"""
Shared request/response models for the /ask endpoint.
See PLAN.docx 'Shared interfaces' for the authoritative contract.
"""
from pydantic import BaseModel


class AskRequest(BaseModel):
    query: str


class GuardResult(BaseModel):
    label: str | None = None
    score: float | None = None
    redactions: int | None = None


class AskResponse(BaseModel):
    request_id: str
    answer: str
    blocked: bool
    block_reason: str | None = None
    sources: list[str]
    guards: dict
    latency_ms: dict
    guards_disabled: bool = False
