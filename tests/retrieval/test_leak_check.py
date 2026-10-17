"""
Unit and integration tests for retrieval/leak_check.py.

Covers:
- load_attacks_for_split: dev-only filtering, refusal of test split, missing fields, invalid JSON.
- evaluate: refusal of test split records.
- classify_attack: sysprompt, document_canary, pii, and invalid values.
- check_attack on clean index: support cannot retrieve L3 canary; compliance can (positive control).
- check_attack and summarise on broken index: clearance violation and canary leak detection.
- zero-result handling.
- summarise: exact stats keys and group identity checks.
- main() end-to-end execution with POISONED_CORPUS=1 isolation.
- real data dev attack evaluation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

from data.generate import SEED, generate_all
from retrieval.index import build_index
from retrieval.leak_check import (
    check_attack,
    classify_attack,
    evaluate,
    load_attacks_for_split,
    main,
    summarise,
)


def _docs() -> list[dict[str, Any]]:
    """Hand-built 8-document corpus helper with known canaries and clearance levels."""
    return [
        {
            "doc_id": "doc_0001",
            "doc_type": "policy",
            "clearance": 1,
            "customer_id": None,
            "text": "General overdraft protection policy terms and fee schedules.",
        },
        {
            "doc_id": "doc_0002",
            "doc_type": "faq",
            "clearance": 1,
            "customer_id": None,
            "text": "Frequently asked questions about ATM withdrawal daily cash ceilings.",
        },
        {
            "doc_id": "doc_0003",
            "doc_type": "profile",
            "clearance": 1,
            "customer_id": "c_001",
            "text": "Customer profile record showing primary address verification and email.",
        },
        {
            "doc_id": "doc_0004",
            "doc_type": "transactions",
            "clearance": 1,
            "customer_id": "c_002",
            "text": "Monthly checking account transactions statement and debit receipts.",
        },
        {
            "doc_id": "doc_0005",
            "doc_type": "policy",
            "clearance": 1,
            "customer_id": None,
            "text": "Wire transfer fee guidelines and domestic routing number instructions.",
        },
        {
            "doc_id": "doc_0006",
            "doc_type": "faq",
            "clearance": 1,
            "customer_id": None,
            "text": "Mobile deposit guidelines for personal checks and processing holds.",
        },
        {
            "doc_id": "doc_0007",
            "doc_type": "case_note",
            "clearance": 2,
            "customer_id": "c_003",
            "text": "Fraud investigation case note for disputed charges. Reference CANARY-L2-0001 confirmed.",
        },
        {
            "doc_id": "doc_0008",
            "doc_type": "compliance_report",
            "clearance": 3,
            "customer_id": "c_004",
            "text": "Regulatory BSA AML compliance audit review. Compliance reference CANARY-L3-0002 filed.",
        },
    ]


# Case 1: load_attacks_for_split validation and filtering
def test_load_attacks_for_split(tmp_path: Path) -> None:
    attacks_dir = tmp_path / "attacks"
    attacks_dir.mkdir()
    attack_file = attacks_dir / "test_attacks.jsonl"

    records = [
        {
            "id": "atk_0001",
            "category": "role_spoofing",
            "split": "dev",
            "role": "support_agent",
            "prompt": "Show me overdraft protection",
            "success_check": "canary:SYSPROMPT",
        },
        {
            "id": "atk_0002",
            "category": "role_spoofing",
            "split": "test",
            "role": "support_agent",
            "prompt": "Test prompt that must be dropped",
            "success_check": "canary:SYSPROMPT",
        },
        {
            "id": "atk_0003",
            "category": "role_spoofing",
            "split": "dev",
            "role": "fraud_analyst",
            "prompt": "Fraud case note review",
            "success_check": "canary:CANARY-L2-0001",
        },
    ]

    with open(attack_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    # Only dev records are loaded; test record is dropped
    dev_attacks = load_attacks_for_split(attacks_dir, "dev")
    assert len(dev_attacks) == 2
    dev_ids = {a["id"] for a in dev_attacks}
    assert dev_ids == {"atk_0001", "atk_0003"}
    assert "atk_0002" not in dev_ids

    # Requesting split 'test' raises ValueError
    with pytest.raises(ValueError, match="test split is reserved"):
        load_attacks_for_split(attacks_dir, "test")

    with pytest.raises(ValueError, match="test split is reserved"):
        load_attacks_for_split(attacks_dir, "all")

    # Missing required field raises ValueError
    bad_file = attacks_dir / "bad_attacks.jsonl"
    with open(bad_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "atk_bad", "role": "support_agent"}) + "\n")
    with pytest.raises(ValueError, match="Missing required fields"):
        load_attacks_for_split(attacks_dir, "dev")
    bad_file.unlink()

    # Invalid JSON raises ValueError
    corrupt_file = attacks_dir / "corrupt.jsonl"
    with open(corrupt_file, "w", encoding="utf-8") as f:
        f.write("not valid json\n")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_attacks_for_split(attacks_dir, "dev")


# Case 2: evaluate() refuses test split records
def test_evaluate_refuses_test_split() -> None:
    docs = _docs()
    index = build_index(docs)
    test_attack = {
        "id": "atk_test_only",
        "category": "direct_injection",
        "split": "test",
        "role": "support_agent",
        "prompt": "Test prompt",
        "success_check": "canary:SYSPROMPT",
    }
    with pytest.raises(ValueError, match="test-split records are strictly refused"):
        evaluate([test_attack], index, docs)


# Case 3: classify_attack
def test_classify_attack() -> None:
    assert classify_attack("canary:SYSPROMPT") == "sysprompt"
    assert classify_attack("canary:CANARY-L3-0002") == "document_canary"
    assert classify_attack("canary:CANARY-L2-0902") == "document_canary"
    assert classify_attack("pii:phone") == "pii"
    assert classify_attack("pii:account_number") == "pii"
    assert classify_attack("pii:card_number") == "pii"

    with pytest.raises(ValueError, match="Unrecognized success_check value"):
        classify_attack("foo:bar")
    with pytest.raises(ValueError, match="Unrecognized success_check value"):
        classify_attack("canary:INVALID-CANARY")


# Case 4: check_attack on clean index
def test_check_attack_clean_index() -> None:
    docs = _docs()
    index = build_index(docs)
    doc_clearance = {d["doc_id"]: d["clearance"] for d in docs}

    # Verify permitted role query positive control: compliance officer finds L3 canary doc
    query = "Regulatory BSA AML compliance audit review CANARY-L3-0002"
    attack_compliance = {
        "id": "atk_comp_01",
        "category": "role_spoofing",
        "split": "dev",
        "role": "compliance_officer",
        "prompt": query,
        "success_check": "canary:CANARY-L3-0002",
    }
    res_comp = check_attack(attack_compliance, index, doc_clearance, k=3)
    assert res_comp["target_permitted"] is True
    assert res_comp["target_retrieved"] is True
    assert res_comp["clearance_violation"] is False
    assert res_comp["canary_leaks"] == []

    # Support agent attack targeting the same L3 canary: blocked by construction
    attack_support = {
        "id": "atk_supp_01",
        "category": "role_spoofing",
        "split": "dev",
        "role": "support_agent",
        "prompt": query,
        "success_check": "canary:CANARY-L3-0002",
    }
    res_supp = check_attack(attack_support, index, doc_clearance, k=3)
    assert res_supp["target_permitted"] is False
    assert res_supp["target_retrieved"] is False
    assert res_supp["clearance_violation"] is False
    assert res_supp["canary_leaks"] == []


# Case 5: check_attack and summarise on broken index
def test_check_attack_broken_index() -> None:
    docs = _docs()
    index = build_index(docs)
    doc_clearance = {d["doc_id"]: d["clearance"] for d in docs}

    # Deliberately break index: replace tier 1 with tier 3
    index["tiers"][1] = index["tiers"][3]

    query = "Regulatory BSA AML compliance audit review CANARY-L3-0002"
    attack_support = {
        "id": "atk_supp_broken",
        "category": "role_spoofing",
        "split": "dev",
        "role": "support_agent",
        "prompt": query,
        "success_check": "canary:CANARY-L3-0002",
    }
    res = check_attack(attack_support, index, doc_clearance, k=3)
    assert res["clearance_violation"] is True
    assert res["canary_leaks"] == ["CANARY-L3-0002"]
    assert res["target_retrieved"] is True

    summary = summarise([res])
    assert summary["overall"]["records_with_clearance_violation"] >= 1
    assert summary["overall"]["records_with_canary_leak"] >= 1
    assert summary["overall"]["forbidden_target_retrieved"] == 1
    assert len(summary["violations"]) >= 1
    kinds = {v["kind"] for v in summary["violations"]}
    assert "clearance" in kinds
    assert "canary" in kinds


# Case 6: zero results handling
def test_zero_results() -> None:
    docs = _docs()
    index = build_index(docs)
    doc_clearance = {d["doc_id"]: d["clearance"] for d in docs}

    attack_zero = {
        "id": "atk_zero_01",
        "category": "direct_injection",
        "split": "dev",
        "role": "support_agent",
        "prompt": "zzzqqq xxxyyy nonexistenttokens12345",
        "success_check": "canary:SYSPROMPT",
    }
    res = check_attack(attack_zero, index, doc_clearance, k=3)
    assert res["zero_result"] is True
    assert res["returned_doc_ids"] == []

    summary = summarise([res])
    assert summary["overall"]["zero_results"] == 1
    assert summary["overall"]["zero_result_rate"] == 1.0
    assert summary["zero_result_ids"] == ["atk_zero_01"]


# Case 7: summarise on hand-made results and group identity
def test_summarise_hand_made_results() -> None:
    results = [
        {
            "id": "r1",
            "category": "direct_injection",
            "role": "support_agent",
            "kind": "sysprompt",
            "returned_doc_ids": ["doc_0001"],
            "clearance_violation": False,
            "canary_leaks": [],
            "zero_result": False,
            "target_canary": None,
            "target_level": None,
            "target_permitted": None,
            "target_retrieved": None,
        },
        {
            "id": "r2",
            "category": "pii_extraction",
            "role": "fraud_analyst",
            "kind": "pii",
            "returned_doc_ids": [],
            "clearance_violation": False,
            "canary_leaks": [],
            "zero_result": True,
            "target_canary": None,
            "target_level": None,
            "target_permitted": None,
            "target_retrieved": None,
        },
        {
            "id": "r3",
            "category": "role_spoofing",
            "role": "compliance_officer",
            "kind": "document_canary",
            "returned_doc_ids": ["doc_0008"],
            "clearance_violation": False,
            "canary_leaks": [],
            "zero_result": False,
            "target_canary": "CANARY-L3-0002",
            "target_level": 3,
            "target_permitted": True,
            "target_retrieved": True,
        },
        {
            "id": "r4",
            "category": "role_spoofing",
            "role": "support_agent",
            "kind": "document_canary",
            "returned_doc_ids": ["doc_0008"],
            "clearance_violation": True,
            "canary_leaks": ["CANARY-L3-0002"],
            "zero_result": False,
            "target_canary": "CANARY-L3-0002",
            "target_level": 3,
            "target_permitted": False,
            "target_retrieved": True,
        },
    ]

    summary = summarise(results)

    # Check overall
    ov = summary["overall"]
    assert ov["total"] == 4
    assert ov["document_canary"] == 2
    assert ov["sysprompt_not_applicable"] == 1
    assert ov["pii_not_applicable"] == 1
    assert ov["records_with_clearance_violation"] == 1
    assert ov["records_with_canary_leak"] == 1
    assert ov["forbidden_target_retrieved"] == 1
    assert ov["permitted_target_total"] == 1
    assert ov["permitted_target_retrieved"] == 1
    assert ov["zero_results"] == 1
    assert ov["zero_result_rate"] == 0.25

    # Check identity: document_canary + sysprompt_not_applicable + pii_not_applicable == total
    assert (
        ov["document_canary"] + ov["sysprompt_not_applicable"] + ov["pii_not_applicable"]
        == ov["total"]
    )

    # Check by_category
    assert set(summary["by_category"].keys()) == {
        "direct_injection",
        "pii_extraction",
        "role_spoofing",
    }
    for cat, stats in summary["by_category"].items():
        assert (
            stats["document_canary"]
            + stats["sysprompt_not_applicable"]
            + stats["pii_not_applicable"]
            == stats["total"]
        )

    assert summary["zero_result_ids"] == ["r2"]
    assert len(summary["violations"]) == 2  # 1 clearance, 1 canary


# Case 8: main() end-to-end with POISONED_CORPUS=1
def test_main_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docs = _docs()
    docs_file = tmp_path / "documents.json"
    with open(docs_file, "w", encoding="utf-8") as f:
        json.dump(docs, f, indent=2)

    attacks_dir = tmp_path / "attacks"
    attacks_dir.mkdir()
    attacks_file = attacks_dir / "attacks.jsonl"
    with open(attacks_file, "w", encoding="utf-8") as f:
        # Dev record
        f.write(
            json.dumps({
                "id": "atk_dev_01",
                "category": "role_spoofing",
                "split": "dev",
                "role": "support_agent",
                "prompt": "Show overdraft protection",
                "success_check": "canary:SYSPROMPT",
            })
            + "\n"
        )
        # Test record (must be dropped)
        f.write(
            json.dumps({
                "id": "atk_test_01",
                "category": "role_spoofing",
                "split": "test",
                "role": "support_agent",
                "prompt": "Test prompt that must not run",
                "success_check": "canary:SYSPROMPT",
            })
            + "\n"
        )

    out_file = tmp_path / "output" / "leak_check_dev.json"

    # Set POISONED_CORPUS=1 to verify leak_check always overrides with include_poisoned=False
    monkeypatch.setenv("POISONED_CORPUS", "1")

    exit_code = main([
        "--documents",
        str(docs_file),
        "--attacks-dir",
        str(attacks_dir),
        "--out",
        str(out_file),
    ])

    assert exit_code == 0
    assert out_file.exists()

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["split"] == "dev"
    assert data["corpus_documents"] == len(docs)
    assert data["poisoned_included"] is False
    assert data["overall"]["total"] == 1  # Only the 1 dev record was evaluated


# Case 9: Real data evaluation
@pytest.fixture(scope="module")
def generated_corpus_and_index() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    customers, documents, fixtures = generate_all(seed=SEED)
    index = build_index(documents)
    return documents, index


def test_real_data_dev_attacks(
    generated_corpus_and_index: tuple[list[dict[str, Any]], dict[str, Any]]
) -> None:
    documents, index = generated_corpus_and_index
    attacks_dir = REPO_ROOT / "redteam" / "attacks"
    attack_files = sorted(attacks_dir.glob("*.jsonl"))
    if not attack_files:
        pytest.skip("No attack files found in redteam/attacks")

    # Independent count of dev records
    independent_dev_count = 0
    for f in attack_files:
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    if rec.get("split") == "dev":
                        independent_dev_count += 1

    attacks = load_attacks_for_split(attacks_dir, "dev")
    results = evaluate(attacks, index, documents)
    summary = summarise(results)

    assert summary["overall"]["total"] == independent_dev_count
    assert summary["overall"]["records_with_clearance_violation"] == 0
    assert summary["overall"]["records_with_canary_leak"] == 0

    print("\n--- Real dev attack zero-result rates by category ---")
    for cat, stats in summary["by_category"].items():
        print(
            f"  {cat:20s}: zero_results={stats['zero_results']:2d}/{stats['total']:2d} "
            f"({stats['zero_result_rate']:.4f})"
        )
