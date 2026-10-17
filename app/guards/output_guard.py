import re
from app.guards.pii import redact

# Matches any canary string following the project's convention, e.g.
# CANARY-L2-0501, CANARY-L3-0601, or CANARY-SYSPROMPT.
_canary_re = re.compile(r"CANARY-[A-Z0-9\-]+", re.IGNORECASE)

# How many consecutive characters of overlap with a restricted document
# counts as "quoting a large verbatim chunk".
VERBATIM_CHUNK_THRESHOLD = 60


def _contains_canary(text: str) -> list[str]:
    return _canary_re.findall(text)


def _contains_verbatim_chunk(text: str, context_docs: list[dict], role_clearance: int) -> list[str]:
    """Check if `text` contains a long substring lifted from a document
    above the role's clearance level."""
    found = []
    for doc in context_docs or []:
        doc_clearance = doc.get("clearance", 0)
        if doc_clearance <= role_clearance:
            continue  # role is allowed to see this document, not a concern
        doc_text = doc.get("text", "")
        for i in range(0, max(len(doc_text) - VERBATIM_CHUNK_THRESHOLD, 0) + 1, 20):
            chunk = doc_text[i : i + VERBATIM_CHUNK_THRESHOLD]
            if chunk and chunk in text:
                found.append(doc.get("doc_id", "unknown"))
                break
    return found


ROLE_CLEARANCE = {
    "support_agent": 1,
    "fraud_analyst": 2,
    "compliance_officer": 3,
}


def scan_output(text: str, role: str, context_docs: list[dict] = None) -> dict:
    reasons = []

    canaries_found = _contains_canary(text)
    if canaries_found:
        reasons.append(f"canary leaked: {', '.join(canaries_found)}")

    role_clearance = ROLE_CLEARANCE.get(role, 0)
    verbatim_docs = _contains_verbatim_chunk(text, context_docs or [], role_clearance)
    if verbatim_docs:
        reasons.append(f"verbatim restricted text from: {', '.join(verbatim_docs)}")

    if reasons:
        return {"text": "", "blocked": True, "reasons": reasons}

    redacted = redact(text, role)
    return {"text": redacted["text"], "blocked": False, "reasons": []}
