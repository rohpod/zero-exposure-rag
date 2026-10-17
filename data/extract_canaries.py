"""
Extract canary strings from data/generated/documents.json and produce a canary registry.

Creates data/generated/canary_registry.json for red-team leak-detection attacks.
Validates:
- Exactly one canary per clearance-2/3 document.
- Zero canaries in clearance-1 documents.
- No duplicate canaries across the corpus.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_PATH = BASE_DIR / "data" / "generated" / "documents.json"
OUTPUT_PATH = BASE_DIR / "data" / "generated" / "canary_registry.json"

CANARY_REGEX = re.compile(r"CANARY-L[23]-\d{4}")


def extract_canaries(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Extract and validate all canary strings from the provided document list.

    Returns a list of dicts with keys {"canary", "clearance", "doc_id"},
    sorted by clearance then by doc_id.
    """
    registry: list[dict[str, Any]] = []
    seen_canaries: set[str] = set()

    for doc in documents:
        doc_id = doc["doc_id"]
        clearance = doc["clearance"]
        text = doc.get("text", "")

        if clearance == 1:
            matches = CANARY_REGEX.findall(text)
            if matches or "CANARY" in text:
                raise ValueError(
                    f"Clearance 1 document {doc_id} contains canary token: {matches or 'CANARY'}"
                )
        elif clearance in (2, 3):
            matches = CANARY_REGEX.findall(text)
            if len(matches) == 0:
                raise ValueError(
                    f"Clearance {clearance} document {doc_id} is missing a canary string"
                )
            if len(matches) > 1:
                raise ValueError(
                    f"Clearance {clearance} document {doc_id} has multiple canary strings: {matches}"
                )

            canary = matches[0]
            expected_prefix = f"CANARY-L{clearance}-"
            if not canary.startswith(expected_prefix):
                raise ValueError(
                    f"Document {doc_id} has clearance {clearance} but canary is {canary}"
                )

            if canary in seen_canaries:
                raise ValueError(
                    f"Duplicate canary string detected across corpus: {canary} in document {doc_id}"
                )
            seen_canaries.add(canary)

            registry.append({
                "canary": canary,
                "clearance": clearance,
                "doc_id": doc_id,
            })
        else:
            raise ValueError(f"Document {doc_id} has unexpected clearance: {clearance}")

    # Sort by clearance then doc_id
    registry.sort(key=lambda entry: (entry["clearance"], entry["doc_id"]))
    return registry


def main(
    documents_path: Path = DOCUMENTS_PATH,
    output_path: Path = OUTPUT_PATH,
) -> None:
    """
    CLI entry point. Reads documents, extracts canaries, validates invariants,
    and writes canary_registry.json.
    """
    if not documents_path.exists():
        raise FileNotFoundError(
            f"Corpus file not found: {documents_path}. Please generate documents first."
        )

    with open(documents_path, "r", encoding="utf-8") as f:
        documents = json.load(f)

    if not isinstance(documents, list):
        raise ValueError(f"Expected a list of documents in {documents_path}, got {type(documents).__name__}")

    registry = extract_canaries(documents)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")

    c2_count = sum(1 for r in registry if r["clearance"] == 2)
    c3_count = sum(1 for r in registry if r["clearance"] == 3)

    print(f"Total canaries found: {len(registry)}")
    print(f"  Clearance 2: {c2_count}")
    print(f"  Clearance 3: {c3_count}")
    print(f"Wrote canary registry to {output_path}")


if __name__ == "__main__":
    main()
