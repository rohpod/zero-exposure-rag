"""Provider-neutral types for LLM calls."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    cached: bool = False


class LLMProvider(Protocol):
    def generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResult: ...


class LLMError(Exception):
    pass


class LLMRateLimited(LLMError):
    def __init__(self, message: str = "rate limited", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMUnavailable(LLMError):
    pass


class LLMConfigError(LLMError):
    pass
