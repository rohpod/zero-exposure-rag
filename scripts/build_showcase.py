"""
build_showcase.py: turn real evaluation output into the static showcase data
served by GitHub Pages (dashboard/data/).

Writes, into --out:
  results.json       copy of the scored results
  examples.json      per category, up to 2 attacks that succeeded with guards
                     off but not with guards on
  audit_sample.json  15 guards-on rows in the audit row shape, queries redacted
                     with the support policy
  meta.json          model, provider, date and commit of the run

Only commit dashboard/data/ with real evaluation output. The script refuses
results that are not quotable unless --allow-not-quotable is passed.

Usage:
    python scripts/build_showcase.py --results redteam/scored/results.json \
        --raw redteam/raw/run_1.jsonl redteam/raw/run_2.jsonl --out dashboard/data
"""
import argparse
import json
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "redteam"))

import score  # noqa: E402
from app.guards.pii import redact  # noqa: E402

EXAMPLES_PER_CATEGORY = 2
AUDIT_SAMPLE_SIZE = 15
SEED = 42


def decision_of(response: dict) -> tuple[str, str | None]:
    if response.get("blocked"):
        reason = response.get("block_reason")
        return ("blocked_input" if reason == "input_guard" else "blocked_output"), reason
    return "answered", None


def outcome_text(response: dict) -> str:
    if response.get("blocked"):
        return f"Blocked ({response.get('block_reason')})"
    return response.get("answer") or ""


def build_examples(rows: list[dict], policy: dict) -> list[dict]:
    by_id: dict[str, dict] = defaultdict(dict)
    for r in rows:
        if r.get("kind") == "attack":
            by_id[r["id"]][r["guards_mode"]] = r
    per_category: dict[str, list[dict]] = defaultdict(list)
    for attack_id in sorted(by_id):
        pair = by_id[attack_id]
        if "off" not in pair or "on" not in pair:
            continue
        off, on = pair["off"], pair["on"]
        off_status, _, off_norm = score.classify(off, policy)
        on_status, _, on_norm = score.classify(on, policy)
        if off_status == "scored" and on_status == "scored" and off_norm and not on_norm:
            per_category[off["category"]].append({
                "category": off["category"],
                "role": off["role"],
                "prompt": off.get("prompt", ""),
                "guards_off_answer": outcome_text(off["response"]),
                "guards_on_outcome": outcome_text(on["response"]),
            })
    examples = []
    for category in sorted(per_category):
        examples += per_category[category][:EXAMPLES_PER_CATEGORY]
    return examples


def build_audit_sample(rows: list[dict]) -> list[dict]:
    candidates = [r for r in rows
                  if r.get("guards_mode") == "on" and not r.get("error")
                  and isinstance(r.get("response"), dict)]
    candidates.sort(key=lambda r: (r["kind"], r["id"]))
    sample = random.Random(SEED).sample(candidates, min(AUDIT_SAMPLE_SIZE, len(candidates)))
    sample.sort(key=lambda r: r.get("timestamp") or "")
    out = []
    for r in sample:
        resp = r["response"]
        decision, reason = decision_of(resp)
        out.append({
            "request_id": resp.get("request_id"),
            "timestamp": r.get("timestamp"),
            "user_id": None,
            "role": r.get("role"),
            "query": redact(r.get("prompt", ""), "support_agent")["text"],
            "decision": decision,
            "block_reason": reason,
            "retrieved_doc_ids": resp.get("sources", []),
            "redaction_count": (resp.get("guards", {}).get("output") or {}).get("redaction_count", 0),
            "latency_ms": resp.get("latency_ms", {}),
        })
    return out


def build_meta(results: dict, raw_paths: list[Path]) -> dict:
    meta = results.get("meta")
    if not meta:
        metas = [json.loads(Path(f"{p}.meta.json").read_text()) for p in raw_paths
                 if Path(f"{p}.meta.json").exists()]
        if not metas:
            sys.exit("No run metadata found in results.json or next to the raw files.")
        meta = score.merge_meta(metas)
    return {
        "model": meta.get("llm_model"),
        "provider": meta.get("llm_provider"),
        "date": (meta.get("timestamp") or "")[:10],
        "commit": meta.get("commit"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="redteam/scored/results.json")
    ap.add_argument("--raw", nargs="+", required=True)
    ap.add_argument("--out", default="dashboard/data")
    ap.add_argument("--policy", default=str(ROOT / "app" / "guards" / "policy.json"))
    ap.add_argument("--allow-not-quotable", action="store_true")
    args = ap.parse_args(argv)

    results_path = Path(args.results)
    results = json.loads(results_path.read_text(encoding="utf-8"))
    if not results.get("quotable") and not args.allow_not_quotable:
        sys.exit("Refusing to build a showcase from results that are not quotable: "
                 + "; ".join(results.get("quotable_reasons", [])))

    raw_paths = [Path(p) for p in args.raw]
    rows: list[dict] = []
    for p in raw_paths:
        rows += score.load_jsonl(p)
    rows = score.dedup_rows(rows)
    policy = score.load_policy(Path(args.policy))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(results_path, out / "results.json")
    for name, data in (
        ("examples.json", build_examples(rows, policy)),
        ("audit_sample.json", build_audit_sample(rows)),
        ("meta.json", build_meta(results, raw_paths)),
    ):
        (out / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote showcase data to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
