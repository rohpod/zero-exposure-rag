"""
Document chunking, loading, and per-tier BM25 index construction for Zero-Exposure RAG.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from rank_bm25 import BM25Okapi


BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_PATH = BASE_DIR / "data" / "generated" / "documents.json"
POISONED_DOCUMENTS_PATH = BASE_DIR / "data" / "poisoned_documents.json"
SCHEMA_PATH = BASE_DIR / "docs" / "schema.json"
CHUNK_WORDS: int = 200
OVERLAP_WORDS: int = 40
TIERS: tuple[int, ...] = (1, 2, 3)

ALLOWED_DOC_TYPES: set[str] = {
    "policy",
    "faq",
    "profile",
    "transactions",
    "case_note",
    "compliance_report",
}
DOC_ID_REGEX = re.compile(r"^doc_[0-9]{4}$")
CUSTOMER_ID_REGEX = re.compile(r"^c_[0-9]+$")
CANARY_REGEX = re.compile(r"CANARY-L[23]-\d{4}")



def tokenize(text: str) -> list[str]:
    """
    Extract lowercase alphanumeric tokens from text.
    """
    return re.findall(r"[a-z0-9]+", text.lower())


def chunk_text(
    text: str,
    size: int = CHUNK_WORDS,
    overlap: int = OVERLAP_WORDS,
) -> list[str]:
    """
    Split text into overlapping word windows, preserving original characters and newlines.

    - size: maximum number of words per chunk.
    - overlap: number of words shared between consecutive chunks.
    - step = size - overlap.

    Returns:
    - [] if text contains 0 words.
    - [text.strip()] if text contains <= size words.
    - list of overlapping chunk strings preserving inner whitespace/newlines.
    """
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError(
            f"Invalid chunk configuration: size={size}, overlap={overlap}. "
            "Must satisfy size > 0 and 0 <= overlap < size."
        )

    spans = list(re.finditer(r"\S+", text))
    n_words = len(spans)
    if n_words == 0:
        return []

    if n_words <= size:
        return [text.strip()]

    step = size - overlap
    chunks: list[str] = []
    start_idx = 0

    while start_idx < n_words:
        end_idx = min(start_idx + size, n_words)
        char_start = spans[start_idx].start()
        char_end = spans[end_idx - 1].end()
        chunk_str = text[char_start:char_end]
        chunks.append(chunk_str)

        if end_idx >= n_words:
            break
        start_idx += step

    return chunks


def build_chunks(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Convert a list of document dicts into a flat list of chunk dicts.

    Each chunk dict has keys:
    - chunk_id: f"{doc_id}#{chunk_index}" (0-indexed)
    - doc_id: str
    - doc_type: str
    - clearance: int
    - customer_id: str | None
    - text: str
    """
    chunks: list[dict[str, Any]] = []
    for doc in documents:
        clearance = doc.get("clearance")
        if clearance not in TIERS:
            raise ValueError(
                f"Invalid clearance {clearance!r} in doc {doc.get('doc_id')}. "
                f"Must be one of {TIERS}"
            )
        doc_id = doc["doc_id"]
        doc_type = doc["doc_type"]
        customer_id = doc.get("customer_id")
        text = doc.get("text", "")

        doc_chunks = chunk_text(text)
        for idx, chunk_text_str in enumerate(doc_chunks):
            chunks.append({
                "chunk_id": f"{doc_id}#{idx}",
                "doc_id": doc_id,
                "doc_type": doc_type,
                "clearance": int(clearance),
                "customer_id": customer_id,
                "text": chunk_text_str,
            })
    return chunks


def validate_poisoned_documents(
    documents: list[dict[str, Any]],
    clean_documents: list[dict[str, Any]] | None = None,
) -> None:
    """
    Validate that poisoned documents conform to docs/schema.json and canary invariants.

    - Every document has the required fields with matching types and values.
    - doc_id matches ^doc_[0-9]{4}$.
    - doc_type is one of the allowed schema types.
    - clearance is 1, 2, or 3.
    - customer_id is None or matches ^c_[0-9]+$.
    - text is a non-empty string.
    - Clearance-1 documents contain no canary strings and no 'CANARY' token.
    - Clearance-2 and 3 documents contain exactly one unique canary matching CANARY-L{clearance}-xxxx.
    - No duplicate doc_ids or duplicate canaries.
    - If clean_documents is provided, verifies no doc_id or canary collisions with the clean corpus.
    """
    if not isinstance(documents, list):
        raise ValueError(f"Expected a list of documents, got {type(documents).__name__}")

    seen_doc_ids: set[str] = set()
    seen_canaries: set[str] = set()
    required_keys = {"doc_id", "doc_type", "clearance", "customer_id", "text"}

    clean_ids: set[str] = {d["doc_id"] for d in clean_documents} if clean_documents else set()
    clean_canaries: set[str] = set()
    if clean_documents:
        for d in clean_documents:
            clean_canaries.update(CANARY_REGEX.findall(d.get("text", "")))

    for doc in documents:
        if not isinstance(doc, dict):
            raise ValueError(f"Expected document dict, got {type(doc).__name__}")

        if set(doc.keys()) != required_keys:
            missing = required_keys - set(doc.keys())
            extra = set(doc.keys()) - required_keys
            raise ValueError(
                f"Document schema mismatch. Missing: {missing}, Extra: {extra}"
            )

        doc_id = doc["doc_id"]
        if not isinstance(doc_id, str) or not DOC_ID_REGEX.match(doc_id):
            raise ValueError(f"Invalid doc_id format: {doc_id!r}")
        if doc_id in seen_doc_ids:
            raise ValueError(f"Duplicate doc_id in poisoned documents: {doc_id}")
        if doc_id in clean_ids:
            raise ValueError(f"Poisoned doc_id collides with clean corpus: {doc_id}")
        seen_doc_ids.add(doc_id)

        doc_type = doc["doc_type"]
        if doc_type not in ALLOWED_DOC_TYPES:
            raise ValueError(f"Invalid doc_type {doc_type!r} in doc {doc_id}")

        clearance = doc["clearance"]
        if clearance not in TIERS:
            raise ValueError(f"Invalid clearance {clearance!r} in doc {doc_id}")

        customer_id = doc["customer_id"]
        if customer_id is not None:
            if not isinstance(customer_id, str) or not CUSTOMER_ID_REGEX.match(customer_id):
                raise ValueError(f"Invalid customer_id {customer_id!r} in doc {doc_id}")

        text = doc["text"]
        if not isinstance(text, str) or len(text.strip()) == 0:
            raise ValueError(f"Document text must be a non-empty string in doc {doc_id}")

        # Canary checks
        if clearance == 1:
            matches = CANARY_REGEX.findall(text)
            if matches or "CANARY" in text:
                raise ValueError(
                    f"Clearance 1 poisoned doc {doc_id} contains canary token: {matches or 'CANARY'}"
                )
        elif clearance in (2, 3):
            matches = CANARY_REGEX.findall(text)
            if len(matches) == 0:
                raise ValueError(
                    f"Clearance {clearance} poisoned doc {doc_id} is missing a canary string"
                )
            if len(matches) > 1:
                raise ValueError(
                    f"Clearance {clearance} poisoned doc {doc_id} has multiple canary strings: {matches}"
                )

            canary = matches[0]
            expected_prefix = f"CANARY-L{clearance}-"
            if not canary.startswith(expected_prefix):
                raise ValueError(
                    f"Doc {doc_id} clearance is {clearance} but canary is {canary}"
                )
            if canary in seen_canaries:
                raise ValueError(f"Duplicate canary in poisoned documents: {canary}")
            if canary in clean_canaries:
                raise ValueError(f"Poisoned canary collides with clean corpus: {canary}")
            seen_canaries.add(canary)


def load_poisoned_documents(
    path: Path | str = POISONED_DOCUMENTS_PATH,
) -> list[dict[str, Any]]:
    """
    Load poisoned documents from data/poisoned_documents.json.

    Raises FileNotFoundError if the file is missing, and ValueError if the contents
    fail schema or canary invariant validation.
    """
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Poisoned documents file not found: {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {p}, got {type(data).__name__}")
    validate_poisoned_documents(data)
    return data


def load_documents(
    path: Path | str = DOCUMENTS_PATH,
    include_poisoned: bool | None = None,
    poisoned_path: Path | str = POISONED_DOCUMENTS_PATH,
) -> list[dict[str, Any]]:
    """
    Load documents from documents.json.

    If include_poisoned is None, falls back to the POISONED_CORPUS environment variable
    (defaults to False; set POISONED_CORPUS=1 to include).
    If include_poisoned is True, returns clean + poisoned documents combined.
    If include_poisoned is False, returns clean documents only.

    Raises FileNotFoundError with helpful instructions if documents.json is missing.
    """
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError("documents.json not found; run python3 data/generate.py first")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {p}, got {type(data).__name__}")

    if include_poisoned is None:
        include_poisoned = os.getenv("POISONED_CORPUS", "0") == "1"

    if include_poisoned:
        poisoned = load_poisoned_documents(poisoned_path)
        validate_poisoned_documents(poisoned, clean_documents=data)
        return data + poisoned

    return data


def build_index(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build per-tier BM25 indexes from a list of document dicts.

    Tier N contains only chunks with clearance <= N.
    BM25 corpus statistics (IDF, avg doc length) are computed strictly from that subset.

    Returns:
    {
        "chunks": list[dict[str, Any]],
        "tiers": {
            1: (chunk_positions_tier1, bm25_tier1),
            2: (chunk_positions_tier2, bm25_tier2),
            3: (chunk_positions_tier3, bm25_tier3),
        }
    }
    """
    chunks = build_chunks(documents)

    tiers: dict[int, tuple[list[int], BM25Okapi]] = {}

    for tier in TIERS:
        chunk_positions = [i for i, c in enumerate(chunks) if c["clearance"] <= tier]
        tokenized_corpus = [tokenize(chunks[pos]["text"]) for pos in chunk_positions]
        bm25 = BM25Okapi(tokenized_corpus)
        tiers[tier] = (chunk_positions, bm25)

    return {
        "chunks": chunks,
        "tiers": tiers,
    }

