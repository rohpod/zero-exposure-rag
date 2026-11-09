import hashlib
import re

from app.guards.normalize import normalize
from app.guards.pii import redact
from retrieval.index import tokenize

# Matched on normalised text, so "C A N A R Y - L 3 ..." is still caught.
_SYSPROMPT_CANARY = "CANARYSYSPROMPT"
_DOC_CANARY_RE = re.compile(r"CANARYL([123])(\d{4})")

# Matches long, repetitive single-digit sequences separated by hyphens or whitespace
# (e.g. hallucinated card-like digit loops of 20+ single digits).
_REPETITIVE_DIGIT_SEQUENCE_RE = re.compile(r"\b\d(?:[-\s]+\d){19,}\b")

SHINGLE_SIZE = 8

ROLE_CLEARANCE = {
    "support_agent": 1,
    "fraud_analyst": 2,
    "compliance_officer": 3,
}


def _hash_window(tokens: list[str]) -> int:
    return int.from_bytes(hashlib.sha256(" ".join(tokens).encode()).digest()[:8], "big")


def _windows(text: str) -> set[int]:
    tokens = tokenize(text)
    return {
        _hash_window(tokens[i : i + SHINGLE_SIZE])
        for i in range(len(tokens) - SHINGLE_SIZE + 1)
    }


def build_restricted_shingles(documents: list[dict]) -> dict[int, set[int]]:
    """
    For each clearance level, hashes of every 8-token window that appears in
    documents at that level and in no document at a lower level (shared
    boilerplate is not a leak of the higher level).
    """
    by_level: dict[int, set[int]] = {1: set(), 2: set(), 3: set()}
    for doc in documents:
        by_level[doc["clearance"]] |= _windows(doc["text"])
    restricted: dict[int, set[int]] = {}
    seen_lower: set[int] = set()
    for level in (1, 2, 3):
        restricted[level] = by_level[level] - seen_lower
        seen_lower |= by_level[level]
    return restricted


def _canaries_above_clearance(text: str, clearance: int) -> list[str]:
    norm = normalize(text)
    found = []
    if _SYSPROMPT_CANARY in norm:
        found.append("CANARY-SYSPROMPT")
    for level, digits in _DOC_CANARY_RE.findall(norm):
        if int(level) > clearance:
            found.append(f"CANARY-L{level}-{digits}")
    return found


def _contains_repetitive_digit_sequence(text: str) -> list[str]:
    return _REPETITIVE_DIGIT_SEQUENCE_RE.findall(text)


def _restricted_overlap(
    text: str, clearance: int, shingles: dict[int, set[int]] | None
) -> bool:
    if not shingles:
        return False
    above: set[int] = set()
    for level, hashes in shingles.items():
        if level > clearance:
            above |= hashes
    return bool(_windows(text) & above)


def scan_output(
    text: str,
    role: str,
    shingles: dict[int, set[int]] | None = None,
) -> dict:
    """
    Block canary leaks, hallucinated digit loops and verbatim text from
    documents above the role's clearance; otherwise redact PII for the role.
    `reasons` may quote the leaked value: it goes to the audit log only and
    must never be returned to the client.
    """
    reasons = []
    role_clearance = ROLE_CLEARANCE.get(role, 0)

    canaries_found = _canaries_above_clearance(text, role_clearance)
    if canaries_found:
        reasons.append(f"canary leaked: {', '.join(canaries_found)}")

    for seq in _contains_repetitive_digit_sequence(text):
        preview = f"{seq[:50]}..." if len(seq) > 50 else seq
        reasons.append(
            f"repetitive digit sequence detected (possible hallucinated number): {preview}"
        )

    if _restricted_overlap(text, role_clearance, shingles):
        reasons.append("verbatim text from a document above the role's clearance")

    if reasons:
        return {"text": "", "blocked": True, "reasons": reasons, "redaction_count": 0}

    redacted = redact(text, role)
    return {
        "text": redacted["text"],
        "blocked": False,
        "reasons": [],
        "redaction_count": len(redacted.get("found", [])),
    }
