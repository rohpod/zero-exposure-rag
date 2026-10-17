"""
Unit and integration tests for synthetic data generation in data/generate.py.

Covers:
- Determinism across repeated seeded runs
- Document schema validation against docs/schema.json
- Target counts across document types and security clearance tiers
- Payment card Luhn checksum validity and error-rejection unit tests
- Canary string format, placement, and global uniqueness
- Relevance sanity fixtures format and reference validity
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data.generate import (
    SCHEMA_PATH,
    SEED,
    calculate_luhn_check_digit,
    generate_all,
    generate_customers,
    luhn_checksum,
    validate_all_documents,
    validate_document_against_schema,
)


def test_determinism_generate_all():
    """Generating data twice with the same seed must produce identical outputs."""
    cust1, docs1, fix1 = generate_all(seed=SEED)
    cust2, docs2, fix2 = generate_all(seed=SEED)

    assert cust1 == cust2, "Customer outputs differed across identical seeds"
    assert docs1 == docs2, "Document outputs differed across identical seeds"
    assert fix1 == fix2, "Relevance fixture outputs differed across identical seeds"


def test_document_schema_validation():
    """Every generated document must conform strictly to docs/schema.json."""
    _, docs, _ = generate_all(seed=SEED)
    assert len(docs) > 0

    # Validate all generated documents
    validate_all_documents(docs, SCHEMA_PATH)

    # Unit-level checks of the schema validator rejecting invalid structures
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # 1. Missing required field
    bad_doc1 = {"doc_id": "doc_0001", "doc_type": "policy", "clearance": 1, "text": "Hello"}
    try:
        validate_document_against_schema(bad_doc1, schema)
        assert False, "Validator should have rejected missing customer_id"
    except ValueError:
        pass

    # 2. Invalid clearance level (e.g. 4)
    bad_doc2 = {"doc_id": "doc_0001", "doc_type": "policy", "clearance": 4, "customer_id": None, "text": "Hello"}
    try:
        validate_document_against_schema(bad_doc2, schema)
        assert False, "Validator should have rejected invalid clearance"
    except ValueError:
        pass

    # 3. Invalid doc_type enum
    bad_doc3 = {"doc_id": "doc_0001", "doc_type": "unknown_type", "clearance": 1, "customer_id": None, "text": "Hello"}
    try:
        validate_document_against_schema(bad_doc3, schema)
        assert False, "Validator should have rejected unknown doc_type"
    except ValueError:
        pass

    # 4. Invalid doc_id format
    bad_doc4 = {"doc_id": "invalid_id", "doc_type": "policy", "clearance": 1, "customer_id": None, "text": "Hello"}
    try:
        validate_document_against_schema(bad_doc4, schema)
        assert False, "Validator should have rejected invalid doc_id format"
    except ValueError:
        pass


def test_document_counts_and_types():
    """Verify target counts for customers and document types."""
    customers, docs, _ = generate_all(seed=SEED)

    # 200 customers
    assert len(customers) == 200

    # Total documents = 750
    assert len(docs) == 750

    counts: dict[str, int] = {}
    for d in docs:
        t = d["doc_type"]
        counts[t] = counts.get(t, 0) + 1

    assert counts.get("transactions", 0) == 200, "Expected ~200 transaction documents"
    assert counts.get("profile", 0) == 400, "Expected ~400 profile/support documents"
    assert counts.get("policy", 0) == 15, "Expected 15 policy documents"
    assert counts.get("faq", 0) == 15, "Expected 15 FAQ documents"
    assert counts.get("policy", 0) + counts.get("faq", 0) == 30, "Expected ~30 policy/FAQ documents total"
    assert counts.get("case_note", 0) == 100, "Expected ~100 case notes"
    assert counts.get("compliance_report", 0) == 20, "Expected ~20 compliance reports"


def test_clearance_tiers():
    """Verify clearance tier distributions."""
    _, docs, _ = generate_all(seed=SEED)

    clearance_counts: dict[int, int] = {}
    for d in docs:
        c = d["clearance"]
        clearance_counts[c] = clearance_counts.get(c, 0) + 1

    # Clearance 1: transactions (200) + profile (400) + policy/faq (30) = 630
    assert clearance_counts[1] == 630
    # Clearance 2: case notes (100)
    assert clearance_counts[2] == 100
    # Clearance 3: compliance reports (20)
    assert clearance_counts[3] == 20


def test_customer_pii_uniqueness_and_luhn():
    """Verify all generated customers have distinct PII and Luhn-valid cards."""
    customers = generate_customers(count=200)

    accs = set()
    cards = set()
    phones = set()
    emails = set()
    nat_ids = set()

    for c in customers:
        accs.add(c["account_number"])
        cards.add(c["card_number"])
        phones.add(c["phone"])
        emails.add(c["email"])
        nat_ids.add(c["national_id"])

        # Card number must be Luhn-valid
        raw_card = c["card_number"].replace("-", "")
        assert luhn_checksum(raw_card) is True, f"Card {c['card_number']} failed Luhn check"

    assert len(accs) == 200, "Duplicate account numbers found"
    assert len(cards) == 200, "Duplicate card numbers found"
    assert len(phones) == 200, "Duplicate phone numbers found"
    assert len(emails) == 200, "Duplicate emails found"
    assert len(nat_ids) == 200, "Duplicate national IDs found"


def test_luhn_algorithm_unit_checks():
    """Unit-level verification of the luhn_checksum and check-digit calculations."""
    # Standard synthetic valid cards
    assert luhn_checksum("4532015112830366") is True
    assert luhn_checksum("4111111111111111") is True
    assert luhn_checksum("378282246310005") is True

    # Known invalid cards (altered check digits)
    assert luhn_checksum("4532015112830367") is False
    assert luhn_checksum("4111111111111112") is False

    # Edge cases: zeros, non-digits, length boundaries
    assert luhn_checksum("0000000000000000") is False
    assert luhn_checksum("12345") is False
    assert luhn_checksum("123456789012345678901") is False
    assert luhn_checksum("411111111111111A") is False

    # Check digit computation round-trip
    partial = "453201511283036"
    expected_check = 6
    assert calculate_luhn_check_digit(partial) == expected_check
    assert luhn_checksum(partial + str(expected_check)) is True


def test_canary_format_and_uniqueness():
    """Verify canary string presence, format, and corpus-wide uniqueness."""
    _, docs, _ = generate_all(seed=SEED)

    canaries: list[str] = []

    for d in docs:
        clearance = d["clearance"]
        doc_id = d["doc_id"]
        doc_digits = doc_id.split("_")[1]

        if clearance == 1:
            # Clearance 1 must never contain a canary token
            assert "CANARY" not in d["text"], f"Doc {doc_id} has clearance 1 but contains CANARY!"
        elif clearance == 2:
            expected_canary = f"CANARY-L2-{doc_digits}"
            matches = re.findall(r"CANARY-L\d-\d{4}", d["text"])
            assert len(matches) == 1, f"Doc {doc_id} (clearance 2) must contain exactly one canary, found: {matches}"
            assert matches[0] == expected_canary, f"Doc {doc_id} expected {expected_canary}, got {matches[0]}"
            assert f"Internal reference: {expected_canary}." in d["text"]
            canaries.append(matches[0])
        elif clearance == 3:
            expected_canary = f"CANARY-L3-{doc_digits}"
            matches = re.findall(r"CANARY-L\d-\d{4}", d["text"])
            assert len(matches) == 1, f"Doc {doc_id} (clearance 3) must contain exactly one canary, found: {matches}"
            assert matches[0] == expected_canary, f"Doc {doc_id} expected {expected_canary}, got {matches[0]}"
            assert f"Compliance reference: {expected_canary}." in d["text"]
            canaries.append(matches[0])

    # Exactly 120 canaries: 100 for clearance 2, 20 for clearance 3
    assert len(canaries) == 120
    # All canaries must be globally unique
    assert len(set(canaries)) == 120, "Duplicate canary strings detected across corpus"


def test_relevance_fixtures():
    """Verify ground-truth relevance fixtures."""
    _, docs, fixtures = generate_all(seed=SEED)
    doc_ids = {d["doc_id"] for d in docs}

    assert len(fixtures) == 20, f"Expected exactly 20 relevance fixtures, got {len(fixtures)}"

    for fix in fixtures:
        assert "query" in fix and isinstance(fix["query"], str) and len(fix["query"]) > 5
        assert "best_doc_id" in fix and fix["best_doc_id"] in doc_ids


if __name__ == "__main__":
    # Direct runner so test suite can execute in environments without pytest
    print("Running tests in tests/data/test_generate.py...")
    test_determinism_generate_all()
    print("  [PASS] test_determinism_generate_all")
    test_document_schema_validation()
    print("  [PASS] test_document_schema_validation")
    test_document_counts_and_types()
    print("  [PASS] test_document_counts_and_types")
    test_clearance_tiers()
    print("  [PASS] test_clearance_tiers")
    test_customer_pii_uniqueness_and_luhn()
    print("  [PASS] test_customer_pii_uniqueness_and_luhn")
    test_luhn_algorithm_unit_checks()
    print("  [PASS] test_luhn_algorithm_unit_checks")
    test_canary_format_and_uniqueness()
    print("  [PASS] test_canary_format_and_uniqueness")
    test_relevance_fixtures()
    print("  [PASS] test_relevance_fixtures")
    print("All tests passed successfully!")
