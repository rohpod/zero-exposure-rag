"""
Orchestrates the /ask request through the seven pipeline steps, in order:
auth -> input guard -> retrieval -> LLM -> output guard -> audit -> response.

In STUB_MODE, retrieval, the LLM and the guards return canned values from
app.stub_data. Each step is called behind its interface so a stub can be
swapped for the real implementation with a one-line change here.

Every request writes exactly one audit row, including auth failures.
"""
import datetime
import uuid

from app.audit import write_row
from app.auth import AuthError, resolve_token
from app.config import STUB_MODE
from app.stub_data import STUB_ANSWER, STUB_GUARDS, STUB_LATENCY_MS, STUB_SOURCES


class PipelineAuthError(Exception):
    pass


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run_pipeline(query: str, token: str) -> dict:
    """
    Runs the full pipeline for one request and returns a dict matching
    the AskResponse schema.
    """
    request_id = f"r_{uuid.uuid4().hex[:8]}"

    try:
        identity = resolve_token(token)
    except AuthError as exc:
        # Auth failures still get an audit row, with no user_id/role known.
        write_row(
            request_id=request_id,
            timestamp=_now(),
            user_id=None,
            role=None,
            query=query,
            decision="blocked_input",
            block_reason="auth",
        )
        raise PipelineAuthError(str(exc)) from exc

    # Role comes only from the resolved token, never from the request body
    # or query text. This is enforced simply by never reading role from
    # anywhere else in this function.
    role = identity["role"]
    user_id = identity["user_id"]

    if STUB_MODE:
        # Step order below mirrors the real pipeline even in stub mode,
        # so later swapping in real components does not change this shape.
        # 1. input guard -> STUB_GUARDS["input"]
        # 2. retrieval   -> STUB_SOURCES
        # 3. LLM         -> STUB_ANSWER
        # 4. output guard -> STUB_GUARDS["output"]
        write_row(
            request_id=request_id,
            timestamp=_now(),
            user_id=user_id,
            role=role,
            query=query,
            decision="answered",
            retrieved_doc_ids=STUB_SOURCES,
            redaction_count=STUB_GUARDS["output"]["redactions"],
            latency_ms=STUB_LATENCY_MS,
        )
        return {
            "request_id": request_id,
            "answer": STUB_ANSWER,
            "blocked": False,
            "block_reason": None,
            "sources": STUB_SOURCES,
            "guards": STUB_GUARDS,
            "latency_ms": STUB_LATENCY_MS,
        }

    raise NotImplementedError("Real pipeline not yet implemented. Set STUB_MODE=1.")
