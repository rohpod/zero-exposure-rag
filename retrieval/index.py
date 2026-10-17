"""
Document chunking, loading, and per-tier BM25 index construction for Zero-Exposure RAG.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from rank_bm25 import BM25Okapi


BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_PATH = BASE_DIR / "data" / "generated" / "documents.json"
CHUNK_WORDS: int = 200
OVERLAP_WORDS: int = 40
TIERS: tuple[int, ...] = (1, 2, 3)


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


def load_documents(path: Path | str = DOCUMENTS_PATH) -> list[dict[str, Any]]:
    """
    Load documents from documents.json.

    Raises FileNotFoundError with helpful instructions if the file is missing.
    """
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError("documents.json not found; run python3 data/generate.py first")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list in {p}, got {type(data).__name__}")
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
