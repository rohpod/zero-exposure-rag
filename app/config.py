"""
Central configuration, loaded once from the environment.

Invalid values fail at startup with a clear message. See docs/development.md
for the full variable list.
"""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROVIDERS = ("mock", "groq")
MOCK_MODES = ("fixed", "echo", "leaky")


class ConfigError(ValueError):
    pass


def _int(env: dict, name: str, default: int, minimum: int = 1) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {value}")
    return value


def _flag(env: dict, name: str) -> bool:
    raw = env.get(name, "0")
    if raw not in ("0", "1"):
        raise ConfigError(f"{name} must be 0 or 1, got {raw!r}")
    return raw == "1"


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_model: str
    groq_api_key: str | None
    llm_max_tokens: int
    llm_timeout_s: int
    llm_mock_mode: str
    llm_cache: bool
    retrieval_k: int
    eval_mode: bool
    poisoned_corpus: bool
    auth_tokens_json: str | None
    auth_tokens_file: Path
    audit_db_path: Path
    port: int

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Settings":
        env = os.environ if env is None else env
        provider = env.get("LLM_PROVIDER", "mock")
        if provider not in PROVIDERS:
            raise ConfigError(f"LLM_PROVIDER must be one of {PROVIDERS}, got {provider!r}")
        mock_mode = env.get("LLM_MOCK_MODE", "fixed")
        if mock_mode not in MOCK_MODES:
            raise ConfigError(f"LLM_MOCK_MODE must be one of {MOCK_MODES}, got {mock_mode!r}")
        api_key = env.get("GROQ_API_KEY") or None
        if provider == "groq" and not api_key:
            raise ConfigError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        return cls(
            llm_provider=provider,
            llm_model=env.get("LLM_MODEL", "qwen/qwen3.8-27b"),
            groq_api_key=api_key,
            llm_max_tokens=_int(env, "LLM_MAX_TOKENS", 200),
            llm_timeout_s=_int(env, "LLM_TIMEOUT_S", 30),
            llm_mock_mode=mock_mode,
            llm_cache=_flag(env, "LLM_CACHE"),
            retrieval_k=_int(env, "RETRIEVAL_K", 3),
            eval_mode=_flag(env, "EVAL_MODE"),
            poisoned_corpus=_flag(env, "POISONED_CORPUS"),
            auth_tokens_json=env.get("AUTH_TOKENS_JSON") or None,
            auth_tokens_file=Path(
                env.get("AUTH_TOKENS_FILE") or ROOT / "app" / "auth_tokens.local.json"
            ),
            audit_db_path=Path(env.get("AUDIT_DB_PATH") or ROOT / "audit.sqlite3"),
            port=_int(env, "PORT", 8000),
        )

    @property
    def model_name(self) -> str:
        return f"mock-{self.llm_mock_mode}" if self.llm_provider == "mock" else self.llm_model


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reload_settings() -> Settings:
    """Re-read the environment (startup and tests)."""
    global _settings
    _settings = Settings.from_env()
    return _settings
