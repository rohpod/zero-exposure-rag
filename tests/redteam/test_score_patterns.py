"""The scorer's PII patterns must match the values data/generate.py really produces."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "redteam"))
import score  # noqa: E402

CUSTOMERS = json.loads((ROOT / "data" / "generated" / "customers.json").read_text())


def test_every_pattern_matches_every_customers_own_value():
    for c in CUSTOMERS:
        for field, pattern in score.PII_PATTERNS.items():
            assert pattern.search(c[field]), (c["customer_id"], field, c[field])


def test_every_normalized_pattern_matches_the_normalized_value():
    for c in CUSTOMERS:
        for field, pattern in score.PII_PATTERNS_NORMALIZED.items():
            assert pattern.search(score.normalize(c[field])), (c["customer_id"], field)


def test_patterns_do_not_match_other_customers_fields():
    c = CUSTOMERS[0]
    assert not score.PII_PATTERNS["phone"].search(c["account_number"])
    assert not score.PII_PATTERNS["card_number"].search(c["national_id"])
