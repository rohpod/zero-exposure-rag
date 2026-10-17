"""
Red-team harness: sends attack and benign prompts to POST /ask and stores the
raw responses, one JSON line per (record, mode). Resumable.

- Role comes from the token only. The body contains only {"query": ...}.
- Guards-off mode sends "X-Guards: off". The server honours it only if
  EVAL_MODE=1. Guards-on mode never sends the header.
- Any non-200 response is stored as an ERROR, never as "blocked".
- Tokens are read from environment variables, never hardcoded:
    TOKEN_SUPPORT_AGENT, TOKEN_FRAUD_ANALYST, TOKEN_COMPLIANCE_OFFICER
- Benign queries run in guards-on mode only (false-block rate).

Usage:
    python redteam/run_suite.py --attacks redteam/attacks --split dev --mode both
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROLE_ENV = {
    "support_agent": "TOKEN_SUPPORT_AGENT",
    "fraud_analyst": "TOKEN_FRAUD_ANALYST",
    "compliance_officer": "TOKEN_COMPLIANCE_OFFICER",
}
STUB_ANSWER = "This is a stubbed answer. Real generation is not yet connected."
REQUIRED_ATTACK_FIELDS = {"id", "category", "split", "role", "prompt", "success_check"}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    sys.exit(f"{path}:{n}: invalid JSON ({exc})")
    return rows


def load_attacks(path: str, split: str) -> list[dict]:
    p = Path(path)
    files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    rows = [r for f in files for r in load_jsonl(f)]
    for r in rows:
        missing = REQUIRED_ATTACK_FIELDS - r.keys()
        if missing:
            sys.exit(f"attack {r.get('id')}: missing fields {sorted(missing)}")
    if split != "all":
        rows = [r for r in rows if r["split"] == split]
    return rows


def build_jobs(attacks: list[dict], benign: list[dict], mode: str) -> list[dict]:
    jobs = []
    modes = ["off", "on"] if mode == "both" else [mode]
    for a in attacks:
        for m in modes:
            jobs.append({"kind": "attack", "mode": m, "rec": a})
    for b in benign:
        jobs.append({"kind": "benign", "mode": "on", "rec": b})
    return jobs


def job_key(kind: str, rec_id: str, mode: str) -> str:
    return f"{kind}|{rec_id}|{mode}"


def load_done(out_path: Path, retry_errors: bool) -> set[str]:
    done = set()
    if out_path.exists():
        for r in load_jsonl(out_path):
            if retry_errors and r.get("error"):
                continue
            done.add(job_key(r["kind"], r["id"], r["guards_mode"]))
    return done


def send(session, base_url, token, query, mode, timeout):
    headers = {"X-User-Token": token}
    if mode == "off":
        headers["X-Guards"] = "off"
    t0 = time.time()
    try:
        resp = session.post(f"{base_url}/ask", headers=headers,
                            json={"query": query}, timeout=timeout)
    except requests.RequestException as exc:
        return {"status_code": None, "error": f"request_failed: {exc}",
                "response": None, "elapsed_s": round(time.time() - t0, 3)}
    elapsed = round(time.time() - t0, 3)
    if resp.status_code != 200:
        return {"status_code": resp.status_code,
                "error": f"http_{resp.status_code}",
                "response": resp.text[:2000], "elapsed_s": elapsed}
    try:
        body = resp.json()
    except ValueError:
        return {"status_code": 200, "error": "bad_json",
                "response": resp.text[:2000], "elapsed_s": elapsed}
    return {"status_code": 200, "error": None, "response": body,
            "elapsed_s": elapsed}


def preflight(session, base_url, tokens, attack, timeout) -> None:
    """Send one attack in both modes; warn if the results are identical."""
    tok = tokens[attack["role"]]
    off = send(session, base_url, tok, attack["prompt"], "off", timeout)
    on = send(session, base_url, tok, attack["prompt"], "on", timeout)
    if off["error"] or on["error"]:
        print(f"PREFLIGHT: error (off={off['error']}, on={on['error']})")
        return
    same = all(off["response"].get(k) == on["response"].get(k)
               for k in ("answer", "blocked", "block_reason"))
    if same:
        print("PREFLIGHT WARNING: guards-off and guards-on responses are "
              "identical. Either guards are stubbed, or EVAL_MODE is not 1 on "
              "the server. Do NOT quote guards-off numbers from this run.")
    else:
        print("PREFLIGHT: modes differ (expected with real guards).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attacks", default="redteam/attacks")
    ap.add_argument("--benign", default="redteam/benign/benign_queries.jsonl")
    ap.add_argument("--no-benign", action="store_true")
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--mode", choices=["off", "on", "both"], default="both")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="redteam/raw/run_results.jsonl")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--no-retry-errors", action="store_true",
                    help="on resume, do not redo records that errored")
    ap.add_argument("--no-preflight", action="store_true")
    args = ap.parse_args(argv)

    tokens = {}
    for role, env in ROLE_ENV.items():
        val = os.getenv(env)
        if not val:
            sys.exit(f"Set environment variable {env} (do not hardcode tokens).")
        tokens[role] = val

    attacks = load_attacks(args.attacks, args.split)
    benign = [] if args.no_benign else load_jsonl(Path(args.benign))
    jobs = build_jobs(attacks, benign, args.mode)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(out_path, retry_errors=not args.no_retry_errors)
    todo = [j for j in jobs
            if job_key(j["kind"], j["rec"]["id"], j["mode"]) not in done]
    print(f"{len(jobs)} jobs, {len(jobs) - len(todo)} already done, "
          f"{len(todo)} to run.")

    session = requests.Session()
    if attacks and not args.no_preflight and args.mode == "both" and todo:
        preflight(session, args.base_url, tokens, attacks[0], args.timeout)

    stub_hits = errors = 0
    with open(out_path, "a", encoding="utf-8") as f:
        for i, j in enumerate(todo, 1):
            rec = j["rec"]
            res = send(session, args.base_url, tokens[rec["role"]],
                       rec["prompt"], j["mode"], args.timeout)
            body = res["response"] if isinstance(res["response"], dict) else {}
            stub = body.get("answer") == STUB_ANSWER
            stub_hits += stub
            errors += bool(res["error"])
            row = {
                "kind": j["kind"], "id": rec["id"], "guards_mode": j["mode"],
                "category": rec.get("category"), "split": rec.get("split"),
                "role": rec["role"], "success_check": rec.get("success_check"),
                "stub_detected": stub,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                **res,
            }
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())  # survive a crash mid-run
            print(f"[{i}/{len(todo)}] {j['kind']} {rec['id']} "
                  f"mode={j['mode']} -> {res['error'] or 'ok'} "
                  f"({res['elapsed_s']}s)")

    print(f"Finished. errors={errors}, stub_responses={stub_hits}.")
    if stub_hits:
        print("WARNING: stub responses detected. These results are NOT "
              "quotable. Quotable runs must use real components on the VM.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
