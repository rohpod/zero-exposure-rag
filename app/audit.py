"""
SQLite audit log. Every request writes exactly one row here, including
blocked requests and errors. This is a security invariant (see
docs/security-model.md).

The database path comes from AUDIT_DB_PATH and is git-ignored
(see .gitignore: *.sqlite, *.sqlite3).
"""
import json
import sqlite3
from contextlib import contextmanager

from app.config import get_settings
from app.guards.pii import redact

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    request_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    user_id TEXT,
    role TEXT,
    query TEXT,
    decision TEXT NOT NULL,
    block_reason TEXT,
    retrieved_doc_ids TEXT,
    redaction_count INTEGER,
    latency_ms TEXT,
    guard_reasons TEXT
);
"""


@contextmanager
def _connect():
    path = get_settings().audit_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        yield conn
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(_SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_log)")}
    if "guard_reasons" not in columns:
        conn.execute("ALTER TABLE audit_log ADD COLUMN guard_reasons TEXT")


def init_db() -> None:
    with _connect() as conn:
        _ensure_schema(conn)
        conn.commit()


def write_row(
    request_id: str,
    timestamp: str,
    user_id: str | None,
    role: str | None,
    query: str | None,
    decision: str,
    block_reason: str | None = None,
    retrieved_doc_ids: list | None = None,
    redaction_count: int | None = None,
    latency_ms: dict | None = None,
    guard_reasons: list[str] | None = None,
) -> None:
    """
    Writes one audit row. decision must be one of:
    "answered" | "blocked_input" | "blocked_output" | "error".

    The query is stored redacted with the support-agent policy, so typed PII
    never lands in the log. guard_reasons may quote leaked values; that is why
    /audit is restricted to the compliance role.
    """
    stored_query = redact(query, "support_agent")["text"] if query is not None else None
    with _connect() as conn:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO audit_log
            (request_id, timestamp, user_id, role, query, decision,
             block_reason, retrieved_doc_ids, redaction_count, latency_ms,
             guard_reasons)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                timestamp,
                user_id,
                role,
                stored_query,
                decision,
                block_reason,
                json.dumps(retrieved_doc_ids or []),
                redaction_count,
                json.dumps(latency_ms or {}),
                json.dumps(guard_reasons or []),
            ),
        )
        conn.commit()


def read_latest(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        _ensure_schema(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["retrieved_doc_ids"] = json.loads(d["retrieved_doc_ids"] or "[]")
            d["latency_ms"] = json.loads(d["latency_ms"] or "{}")
            d["guard_reasons"] = json.loads(d["guard_reasons"] or "[]")
            result.append(d)
        return result
