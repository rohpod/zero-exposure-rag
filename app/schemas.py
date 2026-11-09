"""
Shared request/response models for the /ask endpoint.
See docs/security-model.md for what each field may and may not contain.
"""
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class InputGuardInfo(BaseModel):
    label: str
    score: float


class OutputGuardInfo(BaseModel):
    blocked: bool
    redaction_count: int


class GuardsInfo(BaseModel):
    input: InputGuardInfo
    output: OutputGuardInfo | None = None


class LatencyInfo(BaseModel):
    input_guard: int
    retrieval: int
    llm: int
    output_guard: int


class AskResponse(BaseModel):
    request_id: str
    answer: str
    blocked: bool
    block_reason: str | None = None
    sources: list[str]
    guards: GuardsInfo
    latency_ms: LatencyInfo
    guards_disabled: bool = False
    llm_cached: bool = False
