"""
Orchestrates the /ask request through the seven pipeline steps, in order:
auth -> input guard -> retrieval -> LLM -> output guard -> audit -> response.

In STUB_MODE, retrieval, the LLM and the guards all return canned values
from app.stub_data. When STUB_MODE is off, the LLM step calls the real
Granite model via app.llm; retrieval and guards are still stubbed until
those tracks land (see docs/decisions.md). Each step is called behind its
interface so a stub can be swapped for the real implementation with a
one-line change here.

Every request writes exactly one audit row, including auth failures.

EVAL_MODE / X-Guards: the X-Guards header only has an effect when the
EVAL_MODE environment variable is "1". Otherwise guards_disabled is always
False regardless of what the header says. This is a security invariant
(see PLAN.docx and docs/decisions.md).
"""
import datetime
import time
import uuid

from app.audit import write_row
from app.auth import AuthError, resolve_token
from app.config import EVAL_MODE, STUB_MODE
from app.llm import generate
from app.stub_data import STUB_GUARDS, STUB_SOURCES
from retrieval.index import build_index, load_documents
from retrieval.retriever import retrieve

_index: dict | None = None


def _get_index() -> dict:
    """Lazy module-level index loading, mirroring app.llm._get_llm() pattern."""
    global _index
    if _index is None:
        docs = load_documents()
        _index = build_index(docs)
    return _index


class PipelineAuthError(Exception):
    pass


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def resolve_guards_disabled(x_guards_header: str | None) -> bool:
    """
    Returns whether guards should be treated as disabled for this request.
    Only ever True when EVAL_MODE=1 AND the header value is "off".
    """
    if not EVAL_MODE:
        return False
    return (x_guards_header or "").strip().lower() == "off"


def _answer_with_stub(request_id, user_id, role, query, guards_disabled) -> dict:
    from app.stub_data import STUB_ANSWER, STUB_LATENCY_MS

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
        "guards_disabled": guards_disabled,
    }


def _answer_with_real_llm(request_id, user_id, role, query, guards_disabled) -> dict:
    # Guards are still stubbed; retrieval and LLM are real.
    # 1. input guard -> STUB_GUARDS["input"] (stub)
    # 2. retrieval   -> real retrieve() call with clearance filtering
    t_retrieval_0 = time.monotonic()
    results = retrieve(query, role, k=3, index=_get_index())
    retrieval_latency_ms = int((time.monotonic() - t_retrieval_0) * 1000)
    retrieved_doc_ids = [doc["doc_id"] for doc in results]

    # Build prompt including retrieved context alongside query
    if results:
        context_text = "\n\n".join(doc["text"] for doc in results)
        prompt = f"Context:\n{context_text}\n\nQuestion: {query}"
    else:
        prompt = query

    # 3. LLM         -> real generate() call with context
    t_llm_0 = time.monotonic()
    answer = generate(prompt, max_tokens=200, temperature=0.0)
    llm_latency_ms = int((time.monotonic() - t_llm_0) * 1000)

    # 4. output guard -> STUB_GUARDS["output"] (stub)
    latency_ms = {
        "input_guard": 1,
        "retrieval": retrieval_latency_ms,
        "llm": llm_latency_ms,
        "output_guard": 1,
    }

    write_row(
        request_id=request_id,
        timestamp=_now(),
        user_id=user_id,
        role=role,
        query=query,
        decision="answered",
        retrieved_doc_ids=retrieved_doc_ids,
        redaction_count=STUB_GUARDS["output"]["redactions"],
        latency_ms=latency_ms,
    )
    return {
        "request_id": request_id,
        "answer": answer,
        "blocked": False,
        "block_reason": None,
        "sources": retrieved_doc_ids,
        "guards": STUB_GUARDS,
        "latency_ms": latency_ms,
        "guards_disabled": guards_disabled,
    }


def run_pipeline(query: str, token: str, x_guards_header: str | None = None) -> dict:
    """
    Runs the full pipeline for one request and returns a dict matching
    the AskResponse schema.
    """
    request_id = f"r_{uuid.uuid4().hex[:8]}"
    guards_disabled = resolve_guards_disabled(x_guards_header)

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
        return _answer_with_stub(request_id, user_id, role, query, guards_disabled)

    return _answer_with_real_llm(request_id, user_id, role, query, guards_disabled)
