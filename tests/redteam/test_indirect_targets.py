"""Every indirect attack's question must retrieve its poisoned document for its role."""
import json
from pathlib import Path

import pytest

from retrieval.index import build_index, load_documents
from retrieval.retriever import retrieve

ROOT = Path(__file__).resolve().parents[2]
ATTACKS = [json.loads(line) for line in
           (ROOT / "redteam" / "attacks" / "indirect_injection.jsonl").read_text().splitlines()
           if line.strip()]
POISONED_IDS = {d["doc_id"] for d in json.loads((ROOT / "data" / "poisoned_documents.json").read_text())}


@pytest.fixture(scope="module")
def index():
    return build_index(load_documents(include_poisoned=True))


def test_each_indirect_attack_retrieves_its_poisoned_doc_in_top_three(index):
    assert ATTACKS
    for attack in ATTACKS:
        assert attack["target_doc"] in POISONED_IDS
        top3 = {c["doc_id"] for c in retrieve(attack["prompt"], attack["role"], k=3, index=index)}
        assert attack["target_doc"] in top3, attack["id"]


def test_indirect_success_checks_match_the_poisoned_instruction():
    for attack in ATTACKS:
        if attack["target_doc"] in ("doc_0900", "doc_0905", "doc_0908"):
            assert attack["success_check"] == "canary:SYSPROMPT"
        else:
            assert attack["success_check"].startswith("pii:")
