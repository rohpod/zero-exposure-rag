"""Deterministic offline provider used by tests, CI and the default config."""
from app.llm.base import LLMResult

MODES = ("fixed", "echo", "leaky")


class MockProvider:
    def __init__(self, mode: str = "fixed"):
        if mode not in MODES:
            raise ValueError(f"LLM_MOCK_MODE must be one of {MODES}, got {mode!r}")
        self.mode = mode
        self.model = f"mock-{mode}"

    def generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResult:
        if self.mode == "fixed":
            text = "Mock answer."
        elif self.mode == "echo":
            user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            question = user.rsplit("Question:", 1)[-1].strip()
            text = question.splitlines()[0] if question else ""
        else:  # leaky: simulates a model that repeats everything it was given
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            text = f"{system}\n\n{user}"
        return LLMResult(
            text=text,
            provider="mock",
            model=self.model,
            prompt_tokens=None,
            completion_tokens=None,
        )
