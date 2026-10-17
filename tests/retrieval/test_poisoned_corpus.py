"""
Tests for poisoned document corpus loading, validation, and isolation.

Covers:
- Default clean-only loading when include_poisoned=False or POISONED_CORPUS unset.
- Combined loading when include_poisoned=True or POISONED_CORPUS=1.
- Schema compliance of data/poisoned_documents.json against docs/schema.json.
- Canary invariants: clearance 1 has 0 canaries, clearance 2/3 has exactly 1.
- Uniqueness and non-collision of doc_ids and canaries against main corpus.
- Fail-closed validation for corrupt or non-compliant poisoned documents.
- Tiered BM25 index construction with combined corpus.
- Strict isolation of retriever.py's lazy _default_index cache against POISONED_CORPUS=1.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from retrieval.index import (
    ALLOWED_DOC_TYPES,
    CANARY_REGEX,
    DOCUMENTS_PATH,
    POISONED_DOCUMENTS_PATH,
    TIERS,
    build_chunks,
    build_index,
    load_documents,
    load_poisoned_documents,
    validate_poisoned_documents,
)
import retrieval.retriever as ret_mod

try:
    import pytest
except ImportError:
    pytest = None

try:
    import jsonschema
except ImportError:
    jsonschema = None


def test_load_documents_default_clean() -> None:
    """Default load_documents() and explicit include_poisoned=False return clean corpus only."""
    # Ensure env var is unset
    old_env = os.environ.pop("POISONED_CORPUS", None)
    try:
        clean_docs_default = load_documents()
        clean_docs_explicit = load_documents(include_poisoned=False)
        assert len(clean_docs_default) == len(clean_docs_explicit)
        assert len(clean_docs_default) > 0

        # Zero poisoned doc_09xx documents returned
        for doc in clean_docs_default:
            assert not doc["doc_id"].startswith("doc_09"), f"Unexpected poisoned doc {doc['doc_id']}"
    finally:
        if old_env is not None:
            os.environ["POISONED_CORPUS"] = old_env


def test_load_documents_include_poisoned_true() -> None:
    """load_documents(include_poisoned=True) returns clean plus poisoned documents combined."""
    clean_docs = load_documents(include_poisoned=False)
    poisoned_docs = load_poisoned_documents()
    combined_docs = load_documents(include_poisoned=True)

    assert len(combined_docs) == len(clean_docs) + len(poisoned_docs)
    assert len(poisoned_docs) >= 6

    combined_ids = {d["doc_id"] for d in combined_docs}
    for p_doc in poisoned_docs:
        assert p_doc["doc_id"] in combined_ids


def test_load_documents_env_var_opt_in() -> None:
    """POISONED_CORPUS=1 enables poisoned corpus when include_poisoned is None."""
    old_env = os.environ.get("POISONED_CORPUS")
    try:
        os.environ["POISONED_CORPUS"] = "1"
        docs_with_env = load_documents()
        assert len(docs_with_env) == len(load_documents(include_poisoned=True))

        # Explicit False overrides env var
        docs_explicit_clean = load_documents(include_poisoned=False)
        assert len(docs_explicit_clean) == len(load_documents(include_poisoned=False))
        assert not any(d["doc_id"].startswith("doc_09") for d in docs_explicit_clean)

        # POISONED_CORPUS=0 returns clean corpus only
        os.environ["POISONED_CORPUS"] = "0"
        docs_env_zero = load_documents()
        assert len(docs_env_zero) == len(docs_explicit_clean)
    finally:
        if old_env is not None:
            os.environ["POISONED_CORPUS"] = old_env
        else:
            os.environ.pop("POISONED_CORPUS", None)


def test_load_poisoned_documents_direct() -> None:
    """load_poisoned_documents() loads, validates, and returns data/poisoned_documents.json."""
    poisoned_docs = load_poisoned_documents()
    assert 6 <= len(poisoned_docs) <= 10

    # Test FileNotFoundError on non-existent file
    try:
        load_poisoned_documents(Path("non_existent_poisoned_docs.json"))
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_poisoned_documents_schema_compliance() -> None:
    """Verify that all documents in data/poisoned_documents.json strictly match docs/schema.json."""
    schema_path = REPO_ROOT / "docs" / "schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    poisoned_docs = load_poisoned_documents()
    required_keys = set(schema["required"])
    allowed_doc_types = set(schema["properties"]["doc_type"]["enum"])
    allowed_clearances = set(schema["properties"]["clearance"]["enum"])
    doc_id_pat = re.compile(schema["properties"]["doc_id"]["pattern"])
    cust_id_pat = re.compile(schema["properties"]["customer_id"]["oneOf"][0]["pattern"])

    found_clearances: set[int] = set()
    found_doc_types: set[str] = set()

    for doc in poisoned_docs:
        # Schema field checks
        assert isinstance(doc, dict)
        assert set(doc.keys()) == required_keys, f"Key mismatch in doc: {doc}"
        assert doc_id_pat.match(doc["doc_id"]), f"Invalid doc_id: {doc['doc_id']}"
        assert doc["doc_id"].startswith("doc_09"), f"doc_id outside 09xx range: {doc['doc_id']}"
        assert doc["doc_type"] in allowed_doc_types
        assert doc["clearance"] in allowed_clearances
        if doc["customer_id"] is not None:
            assert cust_id_pat.match(doc["customer_id"])
        assert isinstance(doc["text"], str) and len(doc["text"]) >= 1

        found_clearances.add(doc["clearance"])
        found_doc_types.add(doc["doc_type"])

        # If jsonschema is installed, run formal validator
        if jsonschema is not None:
            jsonschema.validate(instance=doc, schema=schema)

    # All three clearance tiers and at least 3 doc types represented
    assert found_clearances == {1, 2, 3}, f"Clearances missing: {found_clearances}"
    assert len(found_doc_types) >= 3, f"Expected >= 3 doc types, found: {found_doc_types}"


def test_poisoned_documents_canary_invariants() -> None:
    """
    Canary invariants:
    - Clearance 1 docs contain zero canaries and no 'CANARY' string.
    - Clearance 2 and 3 docs contain exactly one canary matching CANARY-L{clearance}-09xx.
    - All canaries within poisoned corpus are unique.
    """
    poisoned_docs = load_poisoned_documents()
    seen_canaries: set[str] = set()

    for doc in poisoned_docs:
        clearance = doc["clearance"]
        doc_id = doc["doc_id"]
        text = doc["text"]

        if clearance == 1:
            matches = CANARY_REGEX.findall(text)
            assert len(matches) == 0, f"Clearance 1 doc {doc_id} contains canary: {matches}"
            assert "CANARY" not in text, f"Clearance 1 doc {doc_id} contains 'CANARY' text token"
        elif clearance in (2, 3):
            matches = CANARY_REGEX.findall(text)
            assert len(matches) == 1, f"Clearance {clearance} doc {doc_id} must have 1 canary, got: {matches}"
            canary = matches[0]
            assert canary.startswith(f"CANARY-L{clearance}-"), f"Canary {canary} prefix mismatch in doc {doc_id}"
            assert canary not in seen_canaries, f"Duplicate canary {canary} in poisoned corpus"
            seen_canaries.add(canary)


def test_poisoned_canaries_and_ids_unique_against_main_corpus() -> None:
    """Verify poisoned documents do not collide with clean corpus IDs or canaries."""
    if not DOCUMENTS_PATH.exists():
        print(f"[SKIP] {DOCUMENTS_PATH} does not exist; skipping clean corpus collision check")
        return

    clean_docs = load_documents(include_poisoned=False)
    poisoned_docs = load_poisoned_documents()

    clean_ids = {d["doc_id"] for d in clean_docs}
    poisoned_ids = {d["doc_id"] for d in poisoned_docs}
    id_overlap = clean_ids & poisoned_ids
    assert len(id_overlap) == 0, f"doc_id collision between clean and poisoned: {id_overlap}"

    clean_canaries: set[str] = set()
    for d in clean_docs:
        clean_canaries.update(CANARY_REGEX.findall(d.get("text", "")))

    poisoned_canaries: set[str] = set()
    for d in poisoned_docs:
        poisoned_canaries.update(CANARY_REGEX.findall(d.get("text", "")))

    canary_overlap = clean_canaries & poisoned_canaries
    assert len(canary_overlap) == 0, f"Canary collision between clean and poisoned: {canary_overlap}"


def test_validate_poisoned_documents_rejects_invalids() -> None:
    """validate_poisoned_documents fails closed on corrupt docs, invalid canaries, or collisions."""
    valid_doc = {
        "doc_id": "doc_0999",
        "doc_type": "policy",
        "clearance": 1,
        "customer_id": None,
        "text": "Standard bank policy text with no canary token.",
    }

    # 1. Non-list
    try:
        validate_poisoned_documents({"not": "a list"})  # type: ignore[arg-type]
        assert False, "Expected ValueError for non-list"
    except ValueError:
        pass

    # 2. Missing required field
    bad_doc = copy.deepcopy(valid_doc)
    del bad_doc["clearance"]
    try:
        validate_poisoned_documents([bad_doc])
        assert False, "Expected ValueError for missing field"
    except ValueError:
        pass

    # 3. Clearance 1 containing canary
    bad_doc = copy.deepcopy(valid_doc)
    bad_doc["text"] = "Policy text CANARY-L2-0999"
    try:
        validate_poisoned_documents([bad_doc])
        assert False, "Expected ValueError for clearance 1 with canary"
    except ValueError:
        pass

    # 4. Clearance 2 missing canary
    bad_doc = copy.deepcopy(valid_doc)
    bad_doc["clearance"] = 2
    try:
        validate_poisoned_documents([bad_doc])
        assert False, "Expected ValueError for clearance 2 missing canary"
    except ValueError:
        pass

    # 5. Clearance 2 with wrong prefix
    bad_doc = copy.deepcopy(valid_doc)
    bad_doc["clearance"] = 2
    bad_doc["text"] = "Case note text CANARY-L3-0999"
    try:
        validate_poisoned_documents([bad_doc])
        assert False, "Expected ValueError for clearance 2 with L3 canary"
    except ValueError:
        pass

    # 6. Duplicate doc_ids within poisoned corpus
    bad_doc_c2 = {
        "doc_id": "doc_0999",
        "doc_type": "case_note",
        "clearance": 2,
        "customer_id": "c_001",
        "text": "Case note text CANARY-L2-0999",
    }
    try:
        validate_poisoned_documents([valid_doc, bad_doc_c2])
        assert False, "Expected ValueError for duplicate doc_id"
    except ValueError:
        pass

    # 7. Collision with clean corpus
    try:
        validate_poisoned_documents([valid_doc], clean_documents=[{"doc_id": "doc_0999"}])
        assert False, "Expected ValueError for doc_id collision with clean corpus"
    except ValueError:
        pass


def test_build_index_with_poisoned_corpus() -> None:
    """build_index() succeeds with combined clean+poisoned corpus with proper tier chunk counts."""
    docs = load_documents(include_poisoned=True)
    chunks = build_chunks(docs)
    assert len(chunks) >= len(docs)

    index = build_index(docs)
    assert "chunks" in index
    assert "tiers" in index
    assert len(index["tiers"]) == 3
    # Check monotonic tier sizing
    t1, t2, t3 = len(index["tiers"][1][0]), len(index["tiers"][2][0]), len(index["tiers"][3][0])
    assert t1 < t2 < t3


def test_retrieve_lazy_default_unaffected_by_env() -> None:
    """
    retriever.py's retrieve() with index=None (lazy default) uses clean-only corpus
    even when POISONED_CORPUS=1 is set in the environment.
    """
    ret_mod._default_index = None
    old_env = os.environ.get("POISONED_CORPUS")
    try:
        os.environ["POISONED_CORPUS"] = "1"
        ret_mod.retrieve("policy", role="support_agent")


        assert ret_mod._default_index is not None
        chunk_doc_ids = {c["doc_id"] for c in ret_mod._default_index["chunks"]}
        poisoned_docs = load_poisoned_documents()
        poisoned_ids = {d["doc_id"] for d in poisoned_docs}

        # Lazy default index must contain zero poisoned documents
        assert len(chunk_doc_ids & poisoned_ids) == 0, (
            f"Lazy default index contains poisoned documents! {chunk_doc_ids & poisoned_ids}"
        )
    finally:
        ret_mod._default_index = None
        if old_env is not None:
            os.environ["POISONED_CORPUS"] = old_env
        else:
            os.environ.pop("POISONED_CORPUS", None)


def test_injection_patterns_coverage() -> None:
    """Verify that all four required injection patterns are present in data/poisoned_documents.json."""
    poisoned_docs = load_poisoned_documents()
    texts = [d["text"].lower() for d in poisoned_docs]

    # 1. Instruction override
    override_count = sum(1 for t in texts if "override" in t or "disregard all preceding" in t or "ignore all previous" in t)
    assert override_count >= 2, f"Expected >= 2 instruction override docs, found {override_count}"

    # 2. Fake authority / role claim
    fake_auth_count = sum(1 for t in texts if "executive authorization" in t or "special security notice" in t or "administrator" in t)
    assert fake_auth_count >= 2, f"Expected >= 2 fake authority docs, found {fake_auth_count}"

    # 3. Canary bait
    canary_bait_count = sum(1 for t in texts if "reference verification" in t or "verify this internal reference" in t or "confirm and recite" in t)
    assert canary_bait_count >= 2, f"Expected >= 2 canary bait docs, found {canary_bait_count}"

    # 4. Exfiltration framing
    exfil_count = sum(1 for t in texts if "repeat the customer" in t or "extract and restate" in t or "unmasked json list" in t)
    assert exfil_count >= 2, f"Expected >= 2 exfiltration framing docs, found {exfil_count}"


if __name__ == "__main__":
    print("Running tests in tests/retrieval/test_poisoned_corpus.py...")
    test_load_documents_default_clean()
    print("  [PASS] test_load_documents_default_clean")
    test_load_documents_include_poisoned_true()
    print("  [PASS] test_load_documents_include_poisoned_true")
    test_load_documents_env_var_opt_in()
    print("  [PASS] test_load_documents_env_var_opt_in")
    test_load_poisoned_documents_direct()
    print("  [PASS] test_load_poisoned_documents_direct")
    test_poisoned_documents_schema_compliance()
    print("  [PASS] test_poisoned_documents_schema_compliance")
    test_poisoned_documents_canary_invariants()
    print("  [PASS] test_poisoned_documents_canary_invariants")
    test_poisoned_canaries_and_ids_unique_against_main_corpus()
    print("  [PASS] test_poisoned_canaries_and_ids_unique_against_main_corpus")
    test_validate_poisoned_documents_rejects_invalids()
    print("  [PASS] test_validate_poisoned_documents_rejects_invalids")
    test_build_index_with_poisoned_corpus()
    print("  [PASS] test_build_index_with_poisoned_corpus")
    test_retrieve_lazy_default_unaffected_by_env()
    print("  [PASS] test_retrieve_lazy_default_unaffected_by_env")
    test_injection_patterns_coverage()
    print("  [PASS] test_injection_patterns_coverage")
    print("All poisoned corpus tests passed successfully!")
