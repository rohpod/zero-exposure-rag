"""
Clearance-enforced BM25 retriever for Zero-Exposure RAG.

Enforces clearance filtering before ranking by construction:
the BM25 index is selected solely from the user's authenticated role.
"""
from __future__ import annotations

from typing import Any

from retrieval.index import (
    build_index,
    load_documents,
    tokenize,
)


ROLE_MAX_CLEARANCE: dict[str, int] = {
    "support_agent": 1,
    "fraud_analyst": 2,
    "compliance_officer": 3,
}

_default_index: dict[str, Any] | None = None


def retrieve(
    query: str,
    role: str,
    k: int = 3,
    index: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve the top-k document chunks cleared for the specified role.

    Clearance enforcement is structural: the BM25 index is selected solely
    from the authenticated role, never from query text.

    Parameters:
    - query: User search query string.
    - role: Authenticated caller role ('support_agent', 'fraud_analyst', 'compliance_officer').
    - k: Maximum number of chunks to return (default 3).
    - index: Optional pre-built index dictionary. If None, lazily loads default index.

    Returns:
    List of up to k result dicts, each containing:
    - doc_id: str
    - text: str
    - clearance: int
    - score: float (strictly positive)
    """
    if not isinstance(role, str) or role not in ROLE_MAX_CLEARANCE:
        raise ValueError(
            f"Invalid role: {role!r}. Allowed roles: {list(ROLE_MAX_CLEARANCE.keys())}"
        )

    tokens = tokenize(query)
    if not tokens or k <= 0:
        return []

    if index is None:
        global _default_index
        if _default_index is None:
            _default_index = build_index(load_documents(include_poisoned=False))

        index = _default_index

    tier = ROLE_MAX_CLEARANCE[role]
    chunk_positions, bm25 = index["tiers"][tier]
    if not chunk_positions:
        return []

    scores = bm25.get_scores(tokens)
    candidate_indices = list(range(len(chunk_positions)))
    candidate_indices.sort(key=lambda i: (-float(scores[i]), chunk_positions[i]))

    results: list[dict[str, Any]] = []
    chunks = index["chunks"]

    for i in candidate_indices:
        score = float(scores[i])
        if score <= 0.0:
            break

        pos = chunk_positions[i]
        chunk = chunks[pos]

        # Defense in depth: structurally impossible with per-tier index
        if chunk["clearance"] > tier:
            continue

        results.append({
            "doc_id": chunk["doc_id"],
            "text": chunk["text"],
            "clearance": chunk["clearance"],
            "score": score,
        })

        if len(results) >= k:
            break

    return results
