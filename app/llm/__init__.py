"""LLM provider selection. `get_llm()` returns a process-wide singleton."""
from app.config import get_settings
from app.llm.base import (
    LLMConfigError,
    LLMError,
    LLMProvider,
    LLMRateLimited,
    LLMResult,
    LLMUnavailable,
)

__all__ = [
    "LLMConfigError",
    "LLMError",
    "LLMProvider",
    "LLMRateLimited",
    "LLMResult",
    "LLMUnavailable",
    "get_llm",
    "reset_llm",
]

_llm: LLMProvider | None = None


def get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        settings = get_settings()
        if settings.llm_provider == "groq":
            from app.llm.groq import GroqProvider

            provider = GroqProvider(
                api_key=settings.groq_api_key,
                model=settings.llm_model,
                timeout_s=settings.llm_timeout_s,
            )
        else:
            from app.llm.mock import MockProvider

            provider = MockProvider(settings.llm_mock_mode)
        if settings.llm_cache:
            from app.llm.cache import CachedProvider

            provider = CachedProvider(provider)
        _llm = provider
    return _llm


def reset_llm() -> None:
    """Drop the singleton (used by tests after changing settings)."""
    global _llm
    _llm = None
