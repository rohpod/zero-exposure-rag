"""Properties of the committed attack suite (redteam/attacks/*.jsonl)."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "redteam"))
import score  # noqa: E402

CATEGORIES = ["direct_injection", "indirect_injection", "role_spoofing",
              "pii_extraction", "obfuscated_exfil"]
POLICY = score.load_policy(ROOT / "app" / "guards" / "policy.json")


def load(cat):
    path = ROOT / "redteam" / "attacks" / f"{cat}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


ALL = [r for cat in CATEGORIES for r in load(cat)]


def test_fifty_records_and_forty_distinct_prompts_per_category():
    for cat in CATEGORIES:
        rows = load(cat)
        assert len(rows) == 50, cat
        assert len({r["prompt"] for r in rows}) >= 40, cat


def test_ids_are_unique():
    assert len({r["id"] for r in ALL}) == len(ALL)


def test_no_prompt_contains_canary_text():
    assert not [r["id"] for r in ALL if "CANARY" in r["prompt"].upper()]


def test_every_attack_is_achievable_for_its_role():
    invalid = [(r["id"], score.invalid_reason(r, POLICY)) for r in ALL
               if score.invalid_reason(r, POLICY)]
    assert invalid == []


def test_dev_and_test_prompts_do_not_intersect():
    dev = {r["prompt"] for r in ALL if r["split"] == "dev"}
    test = {r["prompt"] for r in ALL if r["split"] == "test"}
    assert dev and test and not (dev & test)


def test_split_is_roughly_sixty_forty():
    counts = Counter(r["split"] for r in ALL)
    assert 0.55 <= counts["dev"] / len(ALL) <= 0.65


def test_role_spoofing_uses_a_lower_token_than_the_claimed_role():
    clearance = score.ROLE_CLEARANCE
    for r in load("role_spoofing"):
        assert clearance[r["claimed_role"]] > clearance[r["role"]]


def test_obfuscated_exfil_targets_pii_the_role_cannot_see():
    for r in load("obfuscated_exfil"):
        assert r["success_check"].startswith("pii:")


def test_indirect_attacks_cover_at_least_five_poisoned_targets():
    assert len({r["target_doc"] for r in load("indirect_injection")}) >= 5


def test_benign_set_has_one_hundred_queries_with_tricky_terms():
    path = ROOT / "redteam" / "benign" / "benign_queries.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(rows) == 100 and len({r["id"] for r in rows}) == 100
    tricky = ("ignore", "act as", "system", "override", "instructions", "account number", "reveal")
    assert sum(any(t in r["prompt"].lower() for t in tricky) for r in rows) >= 40
    assert {r["role"] for r in rows} == set(score.ROLE_CLEARANCE)


def test_dev_small_subset_is_ten_dev_attacks_per_category_plus_twenty_benign():
    ids = (ROOT / "redteam" / "subsets" / "dev_small.txt").read_text().split()
    by_id = {r["id"]: r for r in ALL}
    attacks = [by_id[i] for i in ids if i in by_id]
    assert len(ids) == 70 and len(attacks) == 50
    assert all(a["split"] == "dev" for a in attacks)
    assert Counter(a["category"] for a in attacks) == Counter({c: 10 for c in CATEGORIES})
    assert len([i for i in ids if i.startswith("ben_")]) == 20
