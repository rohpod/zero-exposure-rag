"""
Orchestrates the /ask request through the pipeline steps, in order:
auth -> input guard -> retrieval -> redact context -> LLM -> output guard
-> audit -> response.

Every request writes exactly one audit row, including auth failures and
errors (see docs/security-model.md).

EVAL_MODE / X-Guards: the X-Guards header only has an effect when EVAL_MODE=1.
Otherwise guards_disabled is always False regardless of what the header says.
This is a security invariant (see docs/security-model.md).
"""
import datetime
import logging
import time
import uuid

from app import audit
from app.auth import AuthError, resolve_token
from app.config import get_settings
from app.guards.injection import scan_input
from app.guards.output_guard import build_restricted_shingles, scan_output
from app.guards.pii import redact
from app.llm import LLMConfigError, LLMRateLimited, LLMUnavailable, get_llm
from app.prompts import build_messages
from retrieval.index import build_index, load_documents
from retrieval.retriever import retrieve

logger = logging.getLogger(__name__)

_index: dict | None = None
_shingles: dict[int, set[int]] | None = None


def init_pipeline() -> None:
    """Build the retrieval index and the restricted-text shingles (called at startup)."""
    global _index, _shingles
    settings = get_settings()
    docs = load_documents(include_poisoned=settings.poisoned_corpus)
    _index = build_index(docs)
    _shingles = build_restricted_shingles(docs)


class PipelineAuthError(Exception):
    pass


class PipelineError(Exception):
    """A request failed after authentication; carries the HTTP mapping."""

    def __init__(self, status_code: int, detail: str, retry_after: float | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def resolve_guards_disabled(x_guards_header: str | None) -> bool:
    """
    Returns whether guards should be treated as disabled for this request.
    Only ever True when EVAL_MODE=1 AND the header value is "off".
    """
    requested = (x_guards_header or "").strip().lower() == "off"
    if not get_settings().eval_mode:
        if requested:
            logger.warning("Ignoring X-Guards: off because EVAL_MODE is not enabled")
        return False
    return requested


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _run(request_id, user_id, role, query, guards_disabled) -> dict:
    settings = get_settings()
    latency = {"input_guard": 0, "retrieval": 0, "llm": 0, "output_guard": 0}

    t0 = time.monotonic()
    input_result = scan_input(query)
    latency["input_guard"] = _ms(t0)
    input_info = {"label": input_result["label"], "score": input_result["score"]}

    if not guards_disabled and input_result["label"] in ("injection", "exfil"):
        audit.write_row(
            request_id=request_id,
            timestamp=_now(),
            user_id=user_id,
            role=role,
            query=query,
            decision="blocked_input",
            block_reason="input_guard",
            retrieved_doc_ids=[],
            redaction_count=0,
            latency_ms=latency,
            guard_reasons=[f"input guard label: {input_result['label']}"],
        )
        return {
            "request_id": request_id,
            "answer": "",
            "blocked": True,
            "block_reason": "input_guard",
            "sources": [],
            "guards": {"input": input_info, "output": None},
            "latency_ms": latency,
            "guards_disabled": guards_disabled,
            "llm_cached": False,
        }

    t0 = time.monotonic()
    chunks = retrieve(query, role, k=settings.retrieval_k, index=_index)
    latency["retrieval"] = _ms(t0)
    retrieved_doc_ids = [c["doc_id"] for c in chunks]

    # Redact before generation: the model never sees PII the role may not see.
    # Guards-off sends raw chunks on purpose (that is the comparison).
    if guards_disabled:
        llm_chunks = chunks
    else:
        llm_chunks = [{**c, "text": redact(c["text"], role)["text"]} for c in chunks]

    t0 = time.monotonic()
    llm_result = get_llm().generate(
        build_messages(query, llm_chunks),
        max_tokens=settings.llm_max_tokens,
        temperature=0.0,
    )
    latency["llm"] = _ms(t0)
    answer = llm_result.text

    t0 = time.monotonic()
    output_result = scan_output(answer, role, _shingles)
    latency["output_guard"] = _ms(t0)

    if not guards_disabled and output_result["blocked"]:
        audit.write_row(
            request_id=request_id,
            timestamp=_now(),
            user_id=user_id,
            role=role,
            query=query,
            decision="blocked_output",
            block_reason="output_guard",
            retrieved_doc_ids=retrieved_doc_ids,
            redaction_count=output_result["redaction_count"],
            latency_ms=latency,
            guard_reasons=output_result["reasons"],
        )
        return {
            "request_id": request_id,
            "answer": "",
            "blocked": True,
            "block_reason": "output_guard",
            "sources": [],
            "guards": {
                "input": input_info,
                "output": {"blocked": True, "redaction_count": 0},
            },
            "latency_ms": latency,
            "guards_disabled": guards_disabled,
            "llm_cached": llm_result.cached,
        }

    final_answer = answer if guards_disabled else output_result["text"]
    redaction_count = 0 if guards_disabled else output_result["redaction_count"]
    audit.write_row(
        request_id=request_id,
        timestamp=_now(),
        user_id=user_id,
        role=role,
        query=query,
        decision="answered",
        retrieved_doc_ids=retrieved_doc_ids,
        redaction_count=redaction_count,
        latency_ms=latency,
    )
    return {
        "request_id": request_id,
        "answer": final_answer,
        "blocked": False,
        "block_reason": None,
        "sources": retrieved_doc_ids,
        "guards": {
            "input": input_info,
            "output": {"blocked": False, "redaction_count": redaction_count},
        },
        "latency_ms": latency,
        "guards_disabled": guards_disabled,
        "llm_cached": llm_result.cached,
    }


def _audit_error(request_id, user_id, role, query, reason) -> None:
    audit.write_row(
        request_id=request_id,
        timestamp=_now(),
        user_id=user_id,
        role=role,
        query=query,
        decision="error",
        block_reason=reason,
    )


def run_pipeline(query: str, token: str | None, x_guards_header: str | None = None) -> dict:
    """
    Runs the full pipeline for one request and returns a dict matching
    the AskResponse schema. Raises PipelineAuthError (401) or PipelineError.
    """
    request_id = f"r_{uuid.uuid4().hex[:8]}"
    guards_disabled = resolve_guards_disabled(x_guards_header)

    try:
        identity = resolve_token(token)
    except AuthError as exc:
        # Auth failures still get an audit row, with no user_id/role known.
        audit.write_row(
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

    try:
        return _run(request_id, user_id, role, query, guards_disabled)
    except LLMRateLimited as exc:
        _audit_error(request_id, user_id, role, query, "llm_rate_limited")
        raise PipelineError(
            429, "The language model is rate limited; retry later.", exc.retry_after
        ) from exc
    except (LLMUnavailable, LLMConfigError) as exc:
        logger.error("LLM unavailable: %s", exc)
        _audit_error(request_id, user_id, role, query, "llm_unavailable")
        raise PipelineError(503, "The language model is unavailable.") from exc
    except Exception as exc:
        logger.exception("Unhandled error in pipeline")
        _audit_error(request_id, user_id, role, query, "internal")
        raise PipelineError(500, "Internal server error.") from exc
