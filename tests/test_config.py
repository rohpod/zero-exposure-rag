import json

import pytest

from app.auth import ROLES, load_tokens
from app.config import ConfigError, Settings, reload_settings


def test_defaults():
    s = Settings.from_env({})
    assert (s.llm_provider, s.llm_model, s.llm_max_tokens, s.retrieval_k) == (
        "mock", "qwen/qwen3.8-27b", 200, 3,
    )
    assert s.eval_mode is False and s.poisoned_corpus is False and s.llm_cache is False


@pytest.mark.parametrize(
    "env, message",
    [
        ({"LLM_PROVIDER": "openai"}, "LLM_PROVIDER"),
        ({"LLM_PROVIDER": "groq"}, "GROQ_API_KEY"),
        ({"LLM_MOCK_MODE": "x"}, "LLM_MOCK_MODE"),
        ({"EVAL_MODE": "yes"}, "EVAL_MODE"),
        ({"LLM_MAX_TOKENS": "abc"}, "LLM_MAX_TOKENS"),
        ({"RETRIEVAL_K": "0"}, "RETRIEVAL_K"),
    ],
)
def test_invalid_values_fail_clearly(env, message):
    with pytest.raises(ConfigError, match=message):
        Settings.from_env(env)


def test_tokens_json_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"from_file": {"user_id": "u", "role": "support_agent"}}))
    monkeypatch.setenv("AUTH_TOKENS_FILE", str(path))
    monkeypatch.setenv("AUTH_TOKENS_JSON", json.dumps({"from_env": {"user_id": "u", "role": "fraud_analyst"}}))
    reload_settings()
    assert list(load_tokens()) == ["from_env"]
    monkeypatch.delenv("AUTH_TOKENS_JSON")
    reload_settings()
    assert list(load_tokens()) == ["from_file"]


def test_unknown_role_in_tokens_is_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_TOKENS_JSON", json.dumps({"t": {"user_id": "u", "role": "root"}}))
    reload_settings()
    with pytest.raises(ValueError, match="unknown role"):
        load_tokens()
    assert "root" not in ROLES


def test_no_tokens_logs_a_warning(monkeypatch, caplog, tmp_path):
    monkeypatch.delenv("AUTH_TOKENS_JSON", raising=False)
    monkeypatch.setenv("AUTH_TOKENS_FILE", str(tmp_path / "missing.json"))
    reload_settings()
    with caplog.at_level("WARNING"):
        assert load_tokens() == {}
    assert "No auth tokens" in caplog.text
