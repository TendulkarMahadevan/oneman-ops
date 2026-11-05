import pytest
from pydantic import BaseModel

from app import llm


class Out(BaseModel):
    n: int


def test_valid_json_parses(monkeypatch):
    monkeypatch.setattr(llm, "_post_chat", lambda m, json_mode: '```json\n{"n": 3}\n```')
    assert llm.chat_json("s", "u", Out).n == 3


def test_retries_once_then_succeeds(monkeypatch):
    replies = iter(["not json", '{"n": 7}'])
    monkeypatch.setattr(llm, "_post_chat", lambda m, json_mode: next(replies))
    assert llm.chat_json("s", "u", Out).n == 7


def test_fails_after_second_invalid(monkeypatch):
    monkeypatch.setattr(llm, "_post_chat", lambda m, json_mode: '{"n": "abc"}')
    with pytest.raises(llm.LLMError):
        llm.chat_json("s", "u", Out)


def test_unconfigured_raises():
    with pytest.raises(llm.LLMError):
        llm.chat_json("s", "u", Out)


def test_ping_uses_authenticated_call_and_caches(monkeypatch):
    from app import config

    s = config.get_settings()
    monkeypatch.setattr(s, "vultr_inference_api_key", "k")
    monkeypatch.setattr(s, "vultr_inference_model", "m")
    calls = []

    class R:
        status_code = 401

    def fake_post(url, **kw):
        calls.append((url, kw["headers"]))
        return R()

    monkeypatch.setattr(llm, "_ping_cache", None)
    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.ping() == (False, "http_401")
    assert llm.ping() == (False, "http_401")  # cached
    assert len(calls) == 1 and calls[0][0].endswith("/chat/completions")
    assert calls[0][1]["Authorization"] == "Bearer k"
