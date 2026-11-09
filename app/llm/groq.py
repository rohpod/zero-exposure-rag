"""Groq (OpenAI-compatible) chat completions client."""
import re
import time

import httpx

from app.llm.base import (
    LLMConfigError,
    LLMRateLimited,
    LLMResult,
    LLMUnavailable,
)

BASE_URL = "https://api.groq.com/openai/v1"
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
RETRY_DELAY_S = 1.0


class GroqProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise LLMConfigError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        self.model = model
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_s,
            transport=transport,
        )

    def _post(self, body: dict) -> httpx.Response:
        try:
            return self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise LLMUnavailable("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailable("LLM connection error") from exc

    def generate(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> LLMResult:
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "seed": 42,
            "reasoning_effort": "none",
        }
        try:
            resp = self._post(body)
            if resp.status_code >= 500:
                raise LLMUnavailable(f"LLM server error {resp.status_code}")
        except LLMUnavailable:
            # Exactly one retry, for 5xx or timeout/connection errors only.
            time.sleep(RETRY_DELAY_S)
            resp = self._post(body)
            if resp.status_code >= 500:
                raise LLMUnavailable(f"LLM server error {resp.status_code}")

        if resp.status_code == 429:
            header = resp.headers.get("retry-after")
            try:
                retry_after = float(header) if header is not None else None
            except ValueError:
                retry_after = None
            raise LLMRateLimited(retry_after=retry_after)
        if resp.status_code in (401, 403):
            raise LLMConfigError(f"LLM auth failed ({resp.status_code})")
        if resp.status_code >= 400:
            raise LLMUnavailable(f"LLM request failed ({resp.status_code})")

        data = resp.json()
        text = data["choices"][0]["message"]["content"] or ""
        text = _THINK_RE.sub("", text).strip()
        usage = data.get("usage") or {}
        return LLMResult(
            text=text,
            provider="groq",
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
