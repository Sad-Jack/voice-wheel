"""Interface-language (#43/#53) invariants: complete translations and the
index-mapped dropdown constants that keep Save safe across a language switch.

Imports AppKit (via settings) like test_settings_capture, so it only runs where
PyObjC is available; skipped otherwise.
"""

from __future__ import annotations

import pytest

pytest.importorskip("AppKit")

from voice_wheel.hostos.macos.settings import (  # noqa: E402
    LLM_BACKENDS,
    STR,
    TTS_VOICES,
    _detect_ui_lang,
)


def test_every_string_has_both_languages():
    for key, pair in STR.items():
        assert isinstance(pair, tuple) and len(pair) == 2, key
        assert all(isinstance(s, str) and s for s in pair), f"empty translation for {key}"


def test_llm_backends_shape():
    # (value, (ru, en)) — value is the stored config key, label is index-mapped.
    for value, label in LLM_BACKENDS:
        assert isinstance(value, str) and value
        assert isinstance(label, tuple) and len(label) == 2 and all(label)
    assert [v for v, _ in LLM_BACKENDS][0] == "ollama"  # default first


def test_tts_voices_shape():
    # (backend, piper_voice, (ru, en))
    for backend, piper_voice, label in TTS_VOICES:
        assert backend in ("system", "piper")
        assert isinstance(piper_voice, str)
        assert isinstance(label, tuple) and len(label) == 2 and all(label)


def test_detect_ui_lang_is_ru_or_en():
    assert _detect_ui_lang() in ("ru", "en")
