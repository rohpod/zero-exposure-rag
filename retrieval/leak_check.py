"""Diagnostic tool for measuring leaks and zero-result rates at the retrieval layer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

# Ensure repository root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from retrieval.index import DOCUMENTS_PATH, build_index, load_documents
from retrieval.retriever import ROLE_MAX_CLEARANCE, retrieve

ATTACKS_DIR = BASE_DIR / "redteam" / "attacks"
OUTPUT_PATH = BASE_DIR / "data" / "generated" / "leak_check_dev.json"
DEFAULT_K = 3
REQUIRED_FIELDS = {"id", "category", "split", "role", "prompt", "success_check"}
CANARY_RE = re.compile(r"CANARY-L(\d)-(\d{4})")
_DOC_CANARY_RE = re.compile(r"^canary:CANARY-L\d-\d{4}$")


def load_attacks_for_split(attacks_dir: Path | str, split: str) -> list[dict[str, Any]]:
    """Load attack records for a specific split from all .jsonl files in attacks_dir."""
    if split != "dev":
        raise ValueError(
            f"Invalid split {split!r}: the test split is reserved for the final run "
            "and must not be used here."
        )

    p = Path(attacks_dir)
    if not p.exists():
        raise FileNotFoundError(f"Attacks path not found: {p}")

    files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    records: list[dict[str, Any]] = []

    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON in {filepath.name}:{line_num}: {exc}") from exc

                missing = REQUIRED_FIELDS - set(rec.keys())
                if missing:
                    raise ValueError(f"Missing required fields {sorted(missing)} in {filepath.name}:{line_num}")

                if rec["split"] == "dev":
                    records.append(rec)
    return records


def classify_attack(success_check: str) -> str:
    """Classify an attack's success_check type into 'sysprompt', 'document_canary', or 'pii'."""
    if success_check == "canary:SYSPROMPT":
        return "sysprompt"
    if _DOC_CANARY_RE.match(success_check):
        return "document_canary"
    if success_check.startswith("pii:"):
        return "pii"
    raise ValueError(f"Unrecognized success_check value: {success_check!r}")


def check_attack(
    attack: dict[str, Any],
    index: dict[str, Any],
    doc_clearance: dict[str, int],
    k: int,
) -> dict[str, Any]:
    """Run a single attack prompt through retrieve() and check for leaks."""
    prompt = attack["prompt"]
    role = attack["role"]
    success_check = attack["success_check"]
    kind = classify_attack(success_check)
    max_clearance = ROLE_MAX_CLEARANCE[role]

    results = retrieve(prompt, role=role, k=k, index=index)
    returned_doc_ids = [r["doc_id"] for r in results]
    zero_result = len(results) == 0

    clearance_violation = False
    for r in results:
        chunk_clr = r["clearance"]
        doc_id = r["doc_id"]
        if chunk_clr > max_clearance or doc_id not in doc_clearance:
            clearance_violation = True
        else:
            true_clr = doc_clearance[doc_id]
            if true_clr > max_clearance or chunk_clr != true_clr:
                clearance_violation = True

    leaked_canaries: set[str] = set()
    for r in results:
        for match in CANARY_RE.finditer(r.get("text", "")):
            if int(match.group(1)) > max_clearance:
                leaked_canaries.add(match.group(0))

    if kind == "document_canary":
        target_canary: str | None = success_check.split("canary:", 1)[1]
        m = CANARY_RE.search(target_canary)
        target_level: int | None = int(m.group(1)) if m else None
        target_permitted: bool | None = (target_level <= max_clearance) if target_level is not None else None
        target_retrieved: bool | None = any(target_canary in r.get("text", "") for r in results)
    else:
        target_canary, target_level, target_permitted, target_retrieved = None, None, None, None

    return {
        "id": attack["id"],
        "category": attack["category"],
        "role": role,
        "kind": kind,
        "returned_doc_ids": returned_doc_ids,
        "clearance_violation": clearance_violation,
        "canary_leaks": sorted(leaked_canaries),
        "zero_result": zero_result,
        "target_canary": target_canary,
        "target_level": target_level,
        "target_permitted": target_permitted,
        "target_retrieved": target_retrieved,
    }


def evaluate(
    attacks: list[dict[str, Any]],
    index: dict[str, Any],
    documents: list[dict[str, Any]],
    k: int = DEFAULT_K,
) -> list[dict[str, Any]]:
    """Evaluate dev-split attack records against the index. Refuses any test-split record."""
    for attack in attacks:
        if attack.get("split") != "dev":
            raise ValueError(f"Refusing record {attack.get('id')}: test-split records are strictly refused.")

    doc_clearance = {d["doc_id"]: d["clearance"] for d in documents}
    return [check_attack(attack, index, doc_clearance, k=k) for attack in attacks]


def _compute_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(items)
    zero_results = sum(1 for r in items if r["zero_result"])
    return {
        "total": total,
        "document_canary": sum(1 for r in items if r["kind"] == "document_canary"),
        "sysprompt_not_applicable": sum(1 for r in items if r["kind"] == "sysprompt"),
        "pii_not_applicable": sum(1 for r in items if r["kind"] == "pii"),
        "records_with_clearance_violation": sum(1 for r in items if r["clearance_violation"]),
        "records_with_canary_leak": sum(1 for r in items if len(r["canary_leaks"]) > 0),
        "forbidden_target_retrieved": sum(1 for r in items if r["target_permitted"] is False and r["target_retrieved"]),
        "permitted_target_total": sum(1 for r in items if r["target_permitted"] is True),
        "permitted_target_retrieved": sum(1 for r in items if r["target_permitted"] is True and r["target_retrieved"]),
        "zero_results": zero_results,
        "zero_result_rate": round(zero_results / total, 4) if total > 0 else 0.0,
    }


def summarise(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise retrieval check results into overall and per-category statistics."""
    overall = _compute_stats(results)
    by_category = {cat: _compute_stats([r for r in results if r["category"] == cat])
                   for cat in sorted({r["category"] for r in results})}

    violations: list[dict[str, Any]] = []
    for r in results:
        if r["clearance_violation"]:
            violations.append({
                "id": r["id"], "category": r["category"], "role": r["role"], "kind": "clearance",
                "detail": f"Clearance violation: returned {r['returned_doc_ids']} exceeded max clearance for {r['role']}",
            })
        if r["canary_leaks"]:
            violations.append({
                "id": r["id"], "category": r["category"], "role": r["role"], "kind": "canary",
                "detail": f"Canary leak: leaked restricted canaries {r['canary_leaks']}",
            })

    return {
        "overall": overall,
        "by_category": by_category,
        "violations": violations,
        "zero_result_ids": sorted(r["id"] for r in results if r["zero_result"]),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for retrieval diagnostic leak check."""
    parser = argparse.ArgumentParser(description="Diagnostic tool for retrieval leaks on dev attacks.")
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--attacks-dir", type=Path, default=ATTACKS_DIR, help="Path to attacks directory")
    parser.add_argument("--documents", type=Path, default=DOCUMENTS_PATH, help="Path to clean documents JSON")
    parser.add_argument("--out", type=Path, default=OUTPUT_PATH, help="Output JSON path")
    args = parser.parse_args(argv)

    documents = load_documents(path=args.documents, include_poisoned=False)
    index = build_index(documents)
    attacks = load_attacks_for_split(args.attacks_dir, "dev")
    results = evaluate(attacks, index, documents, k=args.k)
    summary = summarise(results)

    ov = summary["overall"]
    print("=== Retrieval Leak Check (dev split) ===")
    print(
        f"Overall: total={ov['total']} | doc_canary={ov['document_canary']} | "
        f"sysprompt_n/a={ov['sysprompt_not_applicable']} | pii_n/a={ov['pii_not_applicable']} | "
        f"clearance_violations={ov['records_with_clearance_violation']} | "
        f"canary_leaks={ov['records_with_canary_leak']} | "
        f"zero_result_rate={ov['zero_result_rate']:.4f} ({ov['zero_results']}/{ov['total']})"
    )
    for cat, cs in summary["by_category"].items():
        print(
            f"  - {cat:20s}: total={cs['total']:2d} | "
            f"violations={cs['records_with_clearance_violation']} | "
            f"canary_leaks={cs['records_with_canary_leak']} | "
            f"zero_result_rate={cs['zero_result_rate']:.4f}"
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"split": "dev", "k": args.k, "corpus_documents": len(documents),
                   "poisoned_included": False, **summary}, f, indent=2)
        f.write("\n")

    print(f"Wrote diagnostic report to {out_path}")
    return 1 if (ov["records_with_clearance_violation"] > 0 or ov["records_with_canary_leak"] > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
