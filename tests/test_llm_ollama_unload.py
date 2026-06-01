"""Ollama unload() — releases the model on quit so nothing stays loaded after we
exit. `requests` is monkeypatched, so these never touch the network."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from voice_wheel.core.config import LLMConfig
from voice_wheel.core.llm import LLMClient


def _fake_requests(captured, *, boom=False):
    def post(url, json=None, timeout=None, headers=None):
        captured.append({"url": url, "json": json, "headers": headers})
        if boom:
            raise RuntimeError("ollama down")
        return SimpleNamespace(status_code=200)

    return SimpleNamespace(post=post)


def test_unload_posts_keep_alive_zero(monkeypatch):
    captured: list = []
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "requests", _fake_requests(captured))
    LLMClient(LLMConfig(backend="ollama", ollama_model="qwen2.5:7b",
                        ollama_url="http://localhost:11434")).unload()
    assert len(captured) == 1
    assert captured[0]["url"].endswith("/api/generate")
    assert captured[0]["json"] == {"model": "qwen2.5:7b", "keep_alive": 0}
    assert captured[0]["headers"] == {}  # no token -> plain (local Ollama)


def test_requests_carry_bearer_when_token_set(monkeypatch):
    captured: list = []
    monkeypatch.setenv("OLLAMA_API_KEY", "sk-remote-9")
    monkeypatch.setitem(sys.modules, "requests", _fake_requests(captured))
    LLMClient(LLMConfig(backend="ollama")).unload()
    assert captured and captured[0]["headers"] == {"Authorization": "Bearer sk-remote-9"}


def test_unload_noop_for_non_ollama(monkeypatch):
    captured: list = []
    monkeypatch.setitem(sys.modules, "requests", _fake_requests(captured))
    LLMClient(LLMConfig(backend="openai", model="gpt-4o-mini")).unload()
    assert captured == []  # cloud backend: nothing to unload, no request made


def test_unload_swallows_errors(monkeypatch):
    captured: list = []
    monkeypatch.setitem(sys.modules, "requests", _fake_requests(captured, boom=True))
    LLMClient(LLMConfig(backend="ollama")).unload()  # must not raise — never block shutdown
    assert len(captured) == 1
