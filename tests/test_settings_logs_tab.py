"""The «Логи» tab builds, renders the event feed, and formats each event kind.

Builds the settings window (which only READS config.json) and drives the log
view directly — it never writes config, so it's safe to run in the suite.
"""

from __future__ import annotations

import pytest

pytest.importorskip("AppKit")

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication()

from voice_wheel.core import event_log  # noqa: E402
from voice_wheel.hostos.macos.settings import SettingsWindow  # noqa: E402


def _window():
    w = SettingsWindow.alloc().init()
    w._build()
    return w


def test_logs_tab_exists_and_builds():
    w = _window()
    idents = [
        w._tabs.tabViewItemAtIndex_(i).identifier()
        for i in range(w._tabs.numberOfTabViewItems())
    ]
    assert "tab_logs" in idents
    assert w._logs_view is not None


def test_empty_feed_shows_placeholder():
    w = _window()
    event_log.EVENTS.clear()
    w._render_logs()
    assert "Пока пусто" in str(w._logs_view.string())


def test_each_event_kind_renders_a_line():
    w = _window()
    event_log.EVENTS.clear()
    event_log.log_event("dictate", transcript="привет", result="привет")
    event_log.log_event("transform", sector="clean", result="готовый текст")
    event_log.log_event("context", sector="reply", context="ctx", result="ответ")
    event_log.log_event("tts", text="озвучено")
    event_log.log_event("error", level="error", message="401 unauthorized", cat="auth")
    event_log.log_event("crash", level="error", message="ValueError: x")
    w._render_logs()
    text = str(w._logs_view.string())
    lines = text.splitlines()
    assert len(lines) == 6  # one line per event
    assert "🎤" in text and "Диктовка" in text
    assert "🧠 clean" in text
    assert "Буфер был" in text and "🧠 reply" in text
    assert "🔊" in text and "озвучено" in text
    assert "ключ не работает" in text  # auth error -> human category
    assert "💥" in text and "Сбой" in text


def test_clear_button_empties_the_feed():
    w = _window()
    event_log.log_event("dictate", result="x")
    w.clearLogs_(None)
    assert "Пока пусто" in str(w._logs_view.string())
    assert event_log.EVENTS.recent() == []
