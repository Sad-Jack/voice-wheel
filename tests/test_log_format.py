"""Pure-formatting tests for the «Логи» feed line (no AppKit needed).

format_log_line was lifted out of the settings God class precisely so it could be
tested directly like this, without building an NSWindow.
"""

from __future__ import annotations

from voice_wheel.hostos.macos.log_format import format_log_line


def _line(ev, lang="ru"):
    return format_log_line({"t": 0, **ev}, lang)


def test_timestamp_prefix_format():
    out = format_log_line({"t": 0, "kind": "tts", "text": "x"}, "ru")
    assert out[2] == ":" and out[5] == ":" and out[8:10] == "  "  # HH:MM:SS + 2 spaces
    assert format_log_line({"kind": "tts", "text": "x"}, "ru").startswith("--:--:--")


def test_each_kind_renders_ru():
    assert "🎤 Диктовка → «привет»" in _line({"kind": "dictate", "result": "привет"})
    assert "🎤 Записано → 🧠 clean → «готово»" in _line(
        {"kind": "transform", "sector": "clean", "result": "готово"})
    ctx = _line({"kind": "context", "sector": "reply", "result": "ответ"})
    assert "📋 Буфер был" in ctx and "🧠 reply" in ctx and "«ответ»" in ctx
    assert "🔊 Озвучено: «озвучено»" in _line({"kind": "tts", "text": "озвучено"})
    assert "💥 Сбой: ValueError" in _line({"kind": "crash", "message": "ValueError: x"})


def test_error_category_human_text():
    assert "ключ не работает" in _line({"kind": "error", "cat": "auth", "message": "401"})
    assert "сервер недоступен" in _line({"kind": "error", "cat": "unreachable", "message": "x"})
    # unknown category falls back to err_other
    assert "⚠️ Ошибка:" in _line({"kind": "error", "cat": "bogus", "message": "x"})
    assert "⚠️ Ошибка:" in _line({"kind": "error", "message": "no cat key"})


def test_long_text_is_truncated():
    out = _line({"kind": "tts", "text": "a" * 500})
    assert "…" in out
    assert "a" * 500 not in out


def test_newlines_collapsed_to_spaces():
    out = _line({"kind": "dictate", "result": "строка1\nстрока2"})
    assert "строка1 строка2" in out
    assert "\n" not in out.split("  ", 1)[1]  # no newline in the body


def test_dictate_falls_back_to_transcript():
    assert "«сырьё»" in _line({"kind": "dictate", "transcript": "сырьё"})  # no result key


def test_english_labels():
    assert "Dictation" in format_log_line({"t": 0, "kind": "dictate", "result": "hi"}, "en")
    assert "Spoken" in format_log_line({"t": 0, "kind": "tts", "text": "hi"}, "en")
