from types import SimpleNamespace

from voice_wheel.core.pipeline import Pipeline


class FakeSTT:
    def __init__(self, text):
        self.text = text

    def transcribe(self, audio, language):
        return self.text


class FakeLLM:
    def __init__(self, available=True):
        self._available = available
        self.calls = []

    @property
    def available(self):
        return self._available

    def available_for(self, sector_key):
        return self._available

    def complete(self, system, user, sector_key=None):
        self.calls.append((system, user))
        return f"LLM<<{user}>>"


class FakeClipboard:
    def __init__(self, text=None):
        self._text = text

    def read_text(self):
        return self._text


def make_config(language="ru", max_context_chars=6000):
    return SimpleNamespace(language=language, max_context_chars=max_context_chars)


# audio is only inspected via `.size`; a stub avoids needing numpy.
AUDIO = SimpleNamespace(size=1600)


def test_dictate_skips_llm():
    llm = FakeLLM(available=True)
    pipe = Pipeline(FakeSTT("привет мир"), llm, FakeClipboard(), make_config())
    result = pipe.run(AUDIO, "dictate", "normalize")
    assert result.result == "привет мир"
    assert llm.calls == []  # never touched the LLM
    assert result.llm_skipped is False


def test_transform_calls_llm():
    llm = FakeLLM(available=True)
    pipe = Pipeline(FakeSTT("сырая мысль"), llm, FakeClipboard(), make_config())
    result = pipe.run(AUDIO, "transform", "normalize")
    # the user message is labelled ГОЛОС: with no БУФЕР on the no-context ring
    assert result.result == "LLM<<ГОЛОС:\nсырая мысль>>"
    _system, user = llm.calls[0]
    assert user == "ГОЛОС:\nсырая мысль"
    assert len(llm.calls) == 1


def test_transform_degrades_without_api_key():
    llm = FakeLLM(available=False)
    pipe = Pipeline(FakeSTT("сырая мысль"), llm, FakeClipboard(), make_config())
    result = pipe.run(AUDIO, "transform", "normalize")
    assert result.result == "сырая мысль"
    assert result.llm_skipped is True
    assert llm.calls == []


def test_context_includes_clipboard_and_truncates():
    llm = FakeLLM(available=True)
    clip = FakeClipboard(text="X" * 100)
    pipe = Pipeline(FakeSTT("ответь дружелюбно"), llm, clip, make_config(max_context_chars=10))
    result = pipe.run(AUDIO, "context", "friendly")
    assert result.used_context is True
    assert result.context_truncated is True
    _system, user = llm.calls[0]
    assert "XXXXXXXXXX" in user  # 10 chars of context
    assert "X" * 11 not in user  # not more than the limit
    assert "ответь дружелюбно" in user
    # speech and clipboard are labelled and separated, so the model can't mistake
    # the buffer (possibly someone else's text) for the user's own words
    assert "ГОЛОС:\nответь дружелюбно" in user
    assert "БУФЕР:\n" in user
    assert user.index("ГОЛОС:") < user.index("БУФЕР:")


def test_transform_empty_transcript_skips_llm():
    # a silent press (STT heard nothing) must NOT hit the LLM (B3) — there is
    # nothing to transform, and a weak model could hallucinate a reply
    llm = FakeLLM(available=True)
    pipe = Pipeline(FakeSTT("   "), llm, FakeClipboard(), make_config())
    result = pipe.run(AUDIO, "transform", "normalize")
    assert result.result == ""
    assert llm.calls == []


def test_context_empty_speech_and_clipboard_skips_llm():
    llm = FakeLLM(available=True)
    pipe = Pipeline(FakeSTT(""), llm, FakeClipboard(text=""), make_config())
    result = pipe.run(AUDIO, "context", "friendly")
    assert result.result == ""
    assert llm.calls == []  # nothing to send at all


def test_context_buffer_only_still_calls_llm():
    # empty speech but a non-empty clipboard is the valid "buffer-only" mode —
    # the short-circuit must NOT swallow it
    llm = FakeLLM(available=True)
    pipe = Pipeline(FakeSTT(""), llm, FakeClipboard(text="чужой пост"), make_config())
    result = pipe.run(AUDIO, "context", "friendly")
    assert len(llm.calls) == 1
    _system, user = llm.calls[0]
    assert user == "БУФЕР:\nчужой пост"  # no ГОЛОС section, buffer present
    assert result.result == "LLM<<БУФЕР:\nчужой пост>>"
