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
- Free-tier friendly: requests are spaced by --min-interval; on HTTP 429 the
  runner sleeps for Retry-After and retries, and stops cleanly when the daily
  limit is reached (re-run the same command to resume).
- Evaluation servers should run with LLM_CACHE=1 so reruns cost no tokens.
- Each run writes <out>.meta.json (server /health fields, commit, UTC time,
  shard, split, subset, mode); score.py refuses to merge incompatible runs.

Usage:
    python redteam/run_suite.py --attacks redteam/attacks --split dev --mode both
    python redteam/run_suite.py --subset redteam/subsets/dev_small.txt --mode both
    python redteam/run_suite.py --split all --mode both --shard 1/3
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROLE_ENV = {
    "support_agent": "TOKEN_SUPPORT_AGENT",
    "fraud_analyst": "TOKEN_FRAUD_ANALYST",
    "compliance_officer": "TOKEN_COMPLIANCE_OFFICER",
}
MAX_429_RETRIES = 3
DEFAULT_RETRY_AFTER_S = 60.0
# A Retry-After this long means the daily quota is gone, not a per-minute limit.
DAILY_LIMIT_RETRY_AFTER_S = 3600.0
DAILY_LIMIT_MESSAGE = "Daily limit reached; re-run the same command tomorrow to resume."
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


def parse_shard(value: str) -> tuple[int, int]:
    try:
        i, n = (int(x) for x in value.split("/"))
    except ValueError:
        sys.exit(f"--shard must look like i/N, got {value!r}")
    if not 1 <= i <= n:
        sys.exit(f"--shard i must be between 1 and N, got {value!r}")
    return i, n


def in_shard(job: dict, shard: tuple[int, int]) -> bool:
    i, n = shard
    digest = hashlib.sha256(f"{job['kind']}|{job['rec']['id']}|{job['mode']}".encode()).hexdigest()
    return int(digest, 16) % n == i - 1


def load_subset(path: str) -> set[str]:
    return {line.strip() for line in Path(path).read_text().splitlines() if line.strip()}


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


class DailyLimitReached(Exception):
    pass


def retry_after_seconds(resp) -> float:
    header = (getattr(resp, "headers", None) or {}).get("Retry-After")
    try:
        return float(header) if header is not None else DEFAULT_RETRY_AFTER_S
    except ValueError:
        return DEFAULT_RETRY_AFTER_S


def daily_limit_hit(resp) -> bool:
    text = (getattr(resp, "text", "") or "").lower()
    return (
        retry_after_seconds(resp) >= DAILY_LIMIT_RETRY_AFTER_S
        or "per day" in text
        or "daily" in text
    )


def send(session, base_url, token, query, mode, timeout, sleep=time.sleep):
    """POST one query. HTTP 429 is retried after Retry-After (up to
    MAX_429_RETRIES times); a daily limit or exhausted retries raise
    DailyLimitReached with the stored error row attached."""
    headers = {"X-User-Token": token}
    if mode == "off":
        headers["X-Guards"] = "off"
    t0 = time.time()
    attempts = 0
    while True:
        try:
            resp = session.post(f"{base_url}/ask", headers=headers,
                                json={"query": query}, timeout=timeout)
        except requests.RequestException as exc:
            return {"status_code": None, "error": f"request_failed: {exc}",
                    "response": None, "elapsed_s": round(time.time() - t0, 3)}
        elapsed = round(time.time() - t0, 3)
        if resp.status_code == 429:
            row = {"status_code": 429, "error": "http_429",
                   "response": resp.text[:2000], "elapsed_s": elapsed}
            if daily_limit_hit(resp) or attempts >= MAX_429_RETRIES:
                exc = DailyLimitReached()
                exc.row = row
                raise exc
            attempts += 1
            sleep(retry_after_seconds(resp))
            continue
        break
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


def fetch_health(session, base_url, timeout) -> dict | None:
    try:
        resp = session.get(f"{base_url}/health", timeout=timeout)
        if resp.status_code != 200:
            return None
        return resp.json()
    except (requests.RequestException, ValueError):
        return None


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def check_health(health: dict | None, attacks: list[dict], mode: str) -> None:
    """Refuse runs the server cannot support (exits with a message)."""
    if health is None:
        sys.exit("Cannot read /health from the server; is it running?")
    if mode == "both" and not health.get("eval_mode"):
        sys.exit("Refusing --mode both: the server has EVAL_MODE=0, so guards-off "
                 "requests would silently run with guards on. Start it with EVAL_MODE=1.")
    if (any(a["category"] == "indirect_injection" for a in attacks)
            and not health.get("poisoned_corpus")):
        sys.exit("Refusing to run indirect_injection attacks: the server has "
                 "POISONED_CORPUS=0. Start it with POISONED_CORPUS=1.")


def preflight(session, base_url, tokens, attack, timeout) -> None:
    """Send one attack in both modes; warn if the results are identical."""
    tok = tokens[attack["role"]]
    try:
        off = send(session, base_url, tok, attack["prompt"], "off", timeout)
        on = send(session, base_url, tok, attack["prompt"], "on", timeout)
    except DailyLimitReached:
        sys.exit(DAILY_LIMIT_MESSAGE)
    if off["error"] or on["error"]:
        print(f"PREFLIGHT: error (off={off['error']}, on={on['error']})")
        return
    same = all(off["response"].get(k) == on["response"].get(k)
               for k in ("answer", "blocked", "block_reason"))
    if same:
        print("PREFLIGHT WARNING: guards-off and guards-on responses are "
              "identical. Either the guards did nothing for this prompt, or EVAL_MODE "
              "is not 1 on the server. Do NOT quote guards-off numbers from this run.")
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
    ap.add_argument("--min-interval", type=float, default=6.0,
                    help="seconds between requests (free-tier rate limits)")
    ap.add_argument("--shard", default=None, metavar="i/N",
                    help="run only the i-th of N deterministic shards (1-based)")
    ap.add_argument("--subset", default=None,
                    help="file with one attack/benign ID per line; run only those")
    args = ap.parse_args(argv)

    tokens = {}
    for role, env in ROLE_ENV.items():
        val = os.getenv(env)
        if not val:
            sys.exit(f"Set environment variable {env} (do not hardcode tokens).")
        tokens[role] = val

    attacks = load_attacks(args.attacks, args.split)
    benign = [] if args.no_benign else load_jsonl(Path(args.benign))
    if args.subset:
        keep = load_subset(args.subset)
        attacks = [a for a in attacks if a["id"] in keep]
        benign = [b for b in benign if b["id"] in keep]
    jobs = build_jobs(attacks, benign, args.mode)
    if args.shard:
        shard = parse_shard(args.shard)
        jobs = [j for j in jobs if in_shard(j, shard)]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    health = fetch_health(session, args.base_url, args.timeout)
    if not args.no_preflight:
        check_health(health, attacks, args.mode)

    meta = {
        **(health or {}),
        "commit": git_commit(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "shard": args.shard,
        "split": args.split,
        "subset": args.subset,
        "mode": args.mode,
    }
    meta_path = Path(f"{out_path}.meta.json")
    if meta_path.exists():
        old = json.loads(meta_path.read_text())
        for key in ("commit", "llm_provider", "llm_model", "eval_mode", "poisoned_corpus"):
            if old.get(key) != meta.get(key):
                sys.exit(f"{meta_path} was written with a different {key} "
                         f"({old.get(key)!r} vs {meta.get(key)!r}); use a new --out file.")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    done = load_done(out_path, retry_errors=not args.no_retry_errors)
    todo = [j for j in jobs
            if job_key(j["kind"], j["rec"]["id"], j["mode"]) not in done]
    print(f"{len(jobs)} jobs, {len(jobs) - len(todo)} already done, "
          f"{len(todo)} to run.")

    if attacks and not args.no_preflight and args.mode == "both" and todo:
        preflight(session, args.base_url, tokens, attacks[0], args.timeout)

    errors = 0
    stopped = False
    with open(out_path, "a", encoding="utf-8") as f:
        for i, j in enumerate(todo, 1):
            rec = j["rec"]
            if i > 1 and args.min_interval > 0:
                time.sleep(args.min_interval)
            try:
                res = send(session, args.base_url, tokens[rec["role"]],
                           rec["prompt"], j["mode"], args.timeout)
            except DailyLimitReached as exc:
                res = exc.row
                stopped = True
            body = res["response"] if isinstance(res["response"], dict) else {}
            errors += bool(res["error"])
            row = {
                "kind": j["kind"], "id": rec["id"], "guards_mode": j["mode"],
                "category": rec.get("category"), "split": rec.get("split"),
                "role": rec["role"], "success_check": rec.get("success_check"),
                "prompt": rec["prompt"],
                "llm_cached": body.get("llm_cached"),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                **res,
            }
            f.write(json.dumps(row) + "\n")
            f.flush()
            os.fsync(f.fileno())  # survive a crash mid-run
            print(f"[{i}/{len(todo)}] {j['kind']} {rec['id']} "
                  f"mode={j['mode']} -> {res['error'] or 'ok'} "
                  f"({res['elapsed_s']}s)")
            if stopped:
                print(DAILY_LIMIT_MESSAGE)
                break

    print(f"Finished. errors={errors}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
