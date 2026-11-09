"""Optional SQLite response cache that wraps any provider."""
import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from app.llm.base import LLMProvider, LLMResult

DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "llm_cache.sqlite3"


class CachedProvider:
    def __init__(self, inner: LLMProvider, path: Path | str = DEFAULT_CACHE_PATH):
        self.inner = inner
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, result TEXT NOT NULL)"
            )

    @property
    def model(self) -> str:
        return self.inner.model

    def _key(self, messages, max_tokens, temperature) -> str:
        provider = type(self.inner).__name__
        payload = json.dumps(
            [provider, self.inner.model, messages, max_tokens, temperature], sort_keys=True
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResult:
        key = self._key(messages, max_tokens, temperature)
        conn = sqlite3.connect(self.path)
        try:
            row = conn.execute("SELECT result FROM llm_cache WHERE key = ?", (key,)).fetchone()
            if row:
                data = json.loads(row[0])
                data["cached"] = True
                return LLMResult(**data)
            # Errors propagate from here and are therefore never stored.
            result = self.inner.generate(messages, max_tokens, temperature)
            stored = asdict(result)
            stored["cached"] = False
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, result) VALUES (?, ?)",
                (key, json.dumps(stored)),
            )
            conn.commit()
            return result
        finally:
            conn.close()
