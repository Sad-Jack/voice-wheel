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


def test_ollama_error_surfaces_model_not_found(monkeypatch):
    """A 404 must raise Ollama's own «model 'X' not found» (so the «Логи» line says
    WHICH model is missing), not a bare «404 ... /api/chat»."""
    import pytest

    from voice_wheel.core.event_log import classify_error

    def post(url, json=None, timeout=None, headers=None):
        return SimpleNamespace(
            ok=False, status_code=404, url=url, text="",
            json=lambda: {"error": "model 'qwen2.5:3b' not found, try pulling it first"},
        )

    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=post))
    c = LLMClient(LLMConfig(backend="ollama", ollama_model="qwen2.5:3b"))
    with pytest.raises(RuntimeError) as ei:
        c.complete("system", "user")
    assert "qwen2.5:3b" in str(ei.value) and "not found" in str(ei.value)
    assert classify_error(str(ei.value)) == "model"  # the «Логи» error bucket
