"""OpenAI backend (#37): availability + request routing. A fake client is
injected, so these never touch the network or need the `openai` package."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from voice_wheel.core.config import LLMConfig
from voice_wheel.core.llm import LLMClient, LLMUnavailableError


def _fake_openai(captured):
    """A stand-in for openai.OpenAI: client.chat.completions.create(...)."""
    class _Completions:
        def create(self, **kwargs):
            captured.append(kwargs)
            msg = SimpleNamespace(content="  привет  ")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))


def _client(model="gpt-4o-mini", **kw):
    return LLMClient(LLMConfig(backend="openai", model=model, **kw))


def test_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert _client().available is False


def test_available_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert _client().available is True


def test_complete_routes_to_openai_and_strips(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: list = []
    c = _client(max_tokens=256)
    c._openai = _fake_openai(captured)  # inject — skip the real client build
    out = c.complete("СИСТЕМА", "привет мир")
    assert out == "привет"  # stripped
    assert captured and captured[0]["model"] == "gpt-4o-mini"
    assert captured[0]["max_tokens"] == 256
    msgs = captured[0]["messages"]
    assert msgs[0] == {"role": "system", "content": "СИСТЕМА"}
    assert msgs[1] == {"role": "user", "content": "привет мир"}


def test_per_sector_model_override(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: list = []
    c = LLMClient(
        LLMConfig(backend="openai", model="gpt-4o-mini"),
        sector_models={"деловой": {"backend": "openai", "model": "gpt-4o"}},
    )
    c._openai = _fake_openai(captured)
    c.complete("s", "u", sector_key="деловой")
    assert captured[0]["model"] == "gpt-4o"  # the override wins


def test_complete_raises_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMUnavailableError):
        _client().complete("s", "u")
