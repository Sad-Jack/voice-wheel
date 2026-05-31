"""Interface-language (#43/#53) invariants: complete translations and the
index-mapped dropdown constants that keep Save safe across a language switch.

Imports AppKit (via settings) like test_settings_capture, so it only runs where
PyObjC is available; skipped otherwise.
"""

from __future__ import annotations

import pytest

pytest.importorskip("AppKit")

from voice_wheel.hostos.macos.i18n import STR, detect_ui_lang, resolve_lang, t  # noqa: E402
from voice_wheel.hostos.macos.settings import LLM_BACKENDS, TTS_VOICES  # noqa: E402


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
    assert detect_ui_lang() in ("ru", "en")


def test_resolve_lang_passthrough_and_detect():
    assert resolve_lang("ru") == "ru"
    assert resolve_lang("en") == "en"
    assert resolve_lang("") in ("ru", "en")   # empty -> follow system
    assert resolve_lang(None) in ("ru", "en")


def test_menu_and_runtime_keys_present():
    for key in ("menu_history", "menu_settings", "menu_quit", "menu_empty",
                "ready_msg", "lang_restart_warn", "reset_tab", "save"):
        assert key in STR
    assert t("menu_quit", "ru") == "Выход"
    assert t("menu_quit", "en") == "Quit"
