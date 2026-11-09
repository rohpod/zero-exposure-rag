import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_showcase  # noqa: E402

META = {"commit": "abc", "llm_provider": "groq", "llm_model": "m", "eval_mode": True,
        "poisoned_corpus": True, "mode": "both", "timestamp": "2026-11-20T10:00:00+00:00"}


def row(attack_id, mode, answer, blocked=False, category="pii_extraction", n=0):
    return {"kind": "attack", "id": attack_id, "guards_mode": mode, "category": category,
            "split": "dev", "role": "support_agent", "success_check": "pii:phone",
            "prompt": f"call {attack_id} on +1-555-1001", "error": None,
            "timestamp": f"2026-11-20T10:00:{n:02d}+0000", "elapsed_s": 1.0,
            "response": {"request_id": f"r_{attack_id}{mode}", "answer": answer,
                         "blocked": blocked, "block_reason": "output_guard" if blocked else None,
                         "sources": ["doc_0001"], "latency_ms": {"llm": 5},
                         "guards": {"output": {"blocked": blocked, "redaction_count": 1}}}}


@pytest.fixture
def files(tmp_path):
    rows = []
    for i in range(1, 6):  # five attacks that leak with guards off and are blocked with guards on
        rows.append(row(f"a{i}", "off", "phone is +1-555-1001", n=i))
        rows.append(row(f"a{i}", "on", "", blocked=True, n=i))
    rows.append(row("b1", "off", "nothing", n=9))
    rows.append(row("b1", "on", "nothing", n=9))
    raw = tmp_path / "run.jsonl"
    raw.write_text("".join(json.dumps(r) + "\n" for r in rows))
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"quotable": True, "quotable_reasons": [], "meta": META}))
    return raw, results


def test_build_showcase_writes_all_four_files(files, tmp_path):
    raw, results = files
    out = tmp_path / "data"
    build_showcase.main(["--results", str(results), "--raw", str(raw), "--out", str(out)])
    assert sorted(p.name for p in out.iterdir()) == [
        "audit_sample.json", "examples.json", "meta.json", "results.json"]

    examples = json.loads((out / "examples.json").read_text())
    assert len(examples) == 2  # up to 2 per category
    assert examples[0]["guards_on_outcome"] == "Blocked (output_guard)"
    assert "+1-555-1001" in examples[0]["guards_off_answer"]

    audit = json.loads((out / "audit_sample.json").read_text())
    assert 0 < len(audit) <= 15
    assert "+1-555-1001" not in json.dumps(audit)  # queries redacted
    assert {"request_id", "timestamp", "role", "query", "decision", "block_reason",
            "retrieved_doc_ids", "redaction_count", "latency_ms"} <= set(audit[0])

    assert json.loads((out / "meta.json").read_text()) == {
        "model": "m", "provider": "groq", "date": "2026-11-20", "commit": "abc"}


def test_refuses_results_that_are_not_quotable(files, tmp_path):
    raw, results = files
    results.write_text(json.dumps({"quotable": False, "quotable_reasons": ["provider is mock"]}))
    with pytest.raises(SystemExit, match="not quotable"):
        build_showcase.main(["--results", str(results), "--raw", str(raw), "--out", str(tmp_path / "o")])
