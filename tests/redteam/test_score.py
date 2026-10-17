import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "redteam"))
import score  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def test_scoring_matches_hand_calculation():
    rows = score.load_jsonl(FIXTURES / "sample_results.jsonl")
    policy = score.load_policy(FIXTURES / "policy.json")
    result = score.score(rows, policy)

    dev_off = result["by_split"]["dev"]["attacks"]["off"]
    assert dev_off["by_category"]["pii_extraction"]["total"] == 3
    assert dev_off["by_category"]["pii_extraction"]["success"] == 2
    assert dev_off["pii_leakage_rate"] == 0.5

    dev_on = result["by_split"]["dev"]["attacks"]["on"]
    assert dev_on["by_category"]["direct_injection"]["success"] == 0

    assert result["benign_false_block_rate"] == 1.0
    assert result["error_count"] == 1