"""
SQLite audit log. Every request writes exactly one row here, including
blocked requests and errors. This is a security invariant (see PLAN.docx).

The database path is git-ignored (see .gitignore: *.sqlite, *.sqlite3).
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "audit.sqlite3"

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
    latency_ms TEXT
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(_SCHEMA)
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
) -> None:
    """
    Writes one audit row. decision must be one of:
    "answered" | "blocked_input" | "blocked_output" | "error".
    """
    with _connect() as conn:
        conn.execute(_SCHEMA)
        conn.execute(
            """
            INSERT OR REPLACE INTO audit_log
            (request_id, timestamp, user_id, role, query, decision,
             block_reason, retrieved_doc_ids, redaction_count, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                timestamp,
                user_id,
                role,
                query,
                decision,
                block_reason,
                json.dumps(retrieved_doc_ids or []),
                redaction_count,
                json.dumps(latency_ms or {}),
            ),
        )
        conn.commit()


def read_latest(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        conn.execute(_SCHEMA)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["retrieved_doc_ids"] = json.loads(d["retrieved_doc_ids"] or "[]")
            d["latency_ms"] = json.loads(d["latency_ms"] or "{}")
            result.append(d)
        return result
