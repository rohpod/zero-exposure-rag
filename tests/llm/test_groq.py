import json

import httpx
import pytest

from app.llm import groq as groq_module
from app.llm.base import LLMConfigError, LLMRateLimited, LLMUnavailable
from app.llm.groq import GroqProvider

MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]


def ok_body(content="Hello", usage=True):
    body = {"choices": [{"message": {"content": content}}]}
    if usage:
        body["usage"] = {"prompt_tokens": 11, "completion_tokens": 3}
    return body


def provider(handler):
    return GroqProvider("key-123", "qwen/qwen3.8-27b", 5, transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(groq_module.time, "sleep", lambda s: None)


def test_request_shape_and_result():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body())

    result = provider(handler).generate(MESSAGES, max_tokens=200, temperature=0.0)
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer key-123"
    assert seen["body"] == {
        "model": "qwen/qwen3.8-27b",
        "messages": MESSAGES,
        "max_tokens": 200,
        "temperature": 0.0,
        "seed": 42,
        "reasoning_effort": "none",
    }
    assert (result.text, result.provider, result.model) == ("Hello", "groq", "qwen/qwen3.8-27b")
    assert (result.prompt_tokens, result.completion_tokens, result.cached) == (11, 3, False)


def test_think_block_is_stripped():
    p = provider(lambda r: httpx.Response(200, json=ok_body("<think>secret\nplan</think>Answer")))
    assert p.generate(MESSAGES, 10).text == "Answer"


def test_rate_limit_maps_to_error_with_retry_after_and_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "7"}, json={})

    with pytest.raises(LLMRateLimited) as exc:
        provider(handler).generate(MESSAGES, 10)
    assert exc.value.retry_after == 7.0
    assert len(calls) == 1


def test_rate_limit_without_header():
    with pytest.raises(LLMRateLimited) as exc:
        provider(lambda r: httpx.Response(429, json={})).generate(MESSAGES, 10)
    assert exc.value.retry_after is None


def test_server_error_retries_once_then_fails():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={})

    with pytest.raises(LLMUnavailable):
        provider(handler).generate(MESSAGES, 10)
    assert len(calls) == 2


def test_server_error_then_success():
    responses = iter([httpx.Response(503, json={}), httpx.Response(200, json=ok_body("Fine"))])
    assert provider(lambda r: next(responses)).generate(MESSAGES, 10).text == "Fine"


def test_timeout_retries_once_then_fails():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMUnavailable):
        provider(handler).generate(MESSAGES, 10)
    assert len(calls) == 2


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_map_to_config_error_without_retry(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json={})

    with pytest.raises(LLMConfigError):
        provider(handler).generate(MESSAGES, 10)
    assert len(calls) == 1


def test_missing_key_is_a_config_error():
    with pytest.raises(LLMConfigError):
        GroqProvider("", "m")
