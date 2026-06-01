"""The «Ключи» tab marks a key «не работает» after an auth failure for its
backend, and clears the mark on a later success or when the user edits the key.

Builds the settings window (which only READS config.json) and drives the event
log + status directly — it never writes config, so it's safe in the suite.
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


def _status_visible(w, env):
    row = next(r for r in w._key_rows if r["env"] == env)
    return not row["status"].isHidden()


def test_auth_failure_marks_the_right_key():
    w = _window()
    event_log.EVENTS.clear()
    event_log.log_event("error", level="error", message="401 unauthorized",
                        cat="auth", backend="anthropic")
    w._refresh_key_status()
    assert _status_visible(w, "ANTHROPIC_API_KEY")
    assert not _status_visible(w, "OPENAI_API_KEY")  # unrelated key untouched


def test_later_success_clears_the_mark():
    w = _window()
    event_log.EVENTS.clear()
    event_log.log_event("error", level="error", message="401", cat="auth",
                        backend="anthropic")
    event_log.log_event("transform", sector="clean", result="ok", backend="anthropic")
    w._refresh_key_status()
    assert not _status_visible(w, "ANTHROPIC_API_KEY")


def test_non_auth_error_does_not_mark():
    w = _window()
    event_log.EVENTS.clear()
    event_log.log_event("error", level="error", message="connection refused",
                        cat="unreachable", backend="anthropic")
    w._refresh_key_status()
    assert not _status_visible(w, "ANTHROPIC_API_KEY")


def test_editing_the_key_clears_a_stale_mark():
    w = _window()
    event_log.EVENTS.clear()
    event_log.log_event("error", level="error", message="401", cat="auth",
                        backend="openai")
    w._refresh_key_status()
    assert _status_visible(w, "OPENAI_API_KEY")
    # the user starts fixing the key -> the stale mark must drop immediately
    row = next(r for r in w._key_rows if r["env"] == "OPENAI_API_KEY")
    row["secure"].setStringValue_("sk-newkey")
    w.controlTextDidChange_(_Notif(row["secure"]))
    assert not _status_visible(w, "OPENAI_API_KEY")


class _Notif:
    """Minimal stand-in for the NSNotification passed to controlTextDidChange_."""

    def __init__(self, obj):
        self._obj = obj

    def object(self):
        return self._obj
