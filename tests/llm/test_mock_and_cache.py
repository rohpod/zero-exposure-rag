import pytest

from app.llm.base import LLMResult, LLMUnavailable
from app.llm.cache import CachedProvider
from app.llm.mock import MockProvider
from app.prompts import SYSTEM_PROMPT, build_messages

MESSAGES = build_messages("What is the ATM limit?\nsecond line", [{"doc_id": "doc_0001", "text": "Limit is $1,000."}])


def test_fixed_mode():
    result = MockProvider("fixed").generate(MESSAGES, 10)
    assert (result.text, result.provider, result.model) == ("Mock answer.", "mock", "mock-fixed")


def test_echo_mode_returns_question_line():
    assert MockProvider("echo").generate(MESSAGES, 10).text == "What is the ATM limit?"


def test_leaky_mode_returns_everything():
    text = MockProvider("leaky").generate(MESSAGES, 10).text
    assert SYSTEM_PROMPT in text
    assert "Limit is $1,000." in text and "What is the ATM limit?" in text


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        MockProvider("loud")


class CountingProvider:
    model = "counting"

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def generate(self, messages, max_tokens, temperature=0.0):
        self.calls += 1
        if self.fail:
            raise LLMUnavailable("down")
        return LLMResult(f"answer {self.calls}", "counting", "counting", 5, 2)


def test_cache_miss_then_hit(tmp_path):
    inner = CountingProvider()
    cache = CachedProvider(inner, tmp_path / "c.sqlite3")
    first = cache.generate(MESSAGES, 200)
    second = cache.generate(MESSAGES, 200)
    assert inner.calls == 1
    assert first.cached is False and second.cached is True
    assert second.text == first.text and second.prompt_tokens == 5


def test_cache_key_covers_all_inputs(tmp_path):
    inner = CountingProvider()
    cache = CachedProvider(inner, tmp_path / "c.sqlite3")
    cache.generate(MESSAGES, 200)
    cache.generate(MESSAGES, 100)
    cache.generate(MESSAGES, 200, temperature=0.5)
    cache.generate(build_messages("other", []), 200)
    assert inner.calls == 4


def test_cache_survives_restart(tmp_path):
    path = tmp_path / "c.sqlite3"
    CachedProvider(CountingProvider(), path).generate(MESSAGES, 200)
    inner = CountingProvider()
    assert CachedProvider(inner, path).generate(MESSAGES, 200).cached is True
    assert inner.calls == 0


def test_errors_are_not_cached(tmp_path):
    path = tmp_path / "c.sqlite3"
    failing = CountingProvider(fail=True)
    with pytest.raises(LLMUnavailable):
        CachedProvider(failing, path).generate(MESSAGES, 200)
    healthy = CountingProvider()
    result = CachedProvider(healthy, path).generate(MESSAGES, 200)
    assert result.cached is False and healthy.calls == 1


def test_build_messages_with_chunks():
    msgs = build_messages("Q?", [{"doc_id": "doc_1", "text": "A"}, {"doc_id": "doc_2", "text": "B"}])
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == SYSTEM_PROMPT
    assert msgs[1]["content"] == (
        '<document id="doc_1">\nA\n</document>\n<document id="doc_2">\nB\n</document>\n\nQuestion: Q?'
    )


def test_build_messages_without_chunks():
    msgs = build_messages("Q?", [])
    assert msgs[1]["content"] == "No reference documents were found.\n\nQuestion: Q?"
