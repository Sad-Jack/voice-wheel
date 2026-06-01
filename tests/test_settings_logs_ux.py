"""«Логи» tab UX fixes: the auto-refresh must not wipe a text selection (so the
user can copy a line), and «Сброс» must hide on tabs it can't reset.

Builds the real settings window under a shared NSApplication; never writes config.
"""

from __future__ import annotations

import pytest

pytest.importorskip("AppKit")

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication()

from Foundation import NSMakeRange  # noqa: E402

from voice_wheel.core import event_log  # noqa: E402
from voice_wheel.hostos.macos.settings import SettingsWindow  # noqa: E402


def _window():
    w = SettingsWindow.alloc().init()
    w._build()
    return w


def test_render_skips_when_unchanged_so_selection_survives():
    w = _window()
    event_log.EVENTS.clear()
    event_log.log_event("dictate", result="скопируй меня")
    w._render_logs()
    tv = w._logs_view
    tv.setSelectedRange_(NSMakeRange(0, 5))  # user starts selecting a line
    w._render_logs()                          # the 1.5s tick with nothing new
    assert tv.selectedRange().length == 5     # selection preserved (string not re-set)


def test_reset_button_hidden_on_non_settings_tabs():
    w = _window()
    tabs = w._tabs
    # settings tabs: «Сброс» visible
    for ident in ("tab_llm", "tab_stt", "tab_voice", "tab_triggers", "tab_lang"):
        tabs.selectTabViewItemWithIdentifier_(ident)
        assert not w._reset_btn.isHidden(), ident
    # non-settings tabs: nothing to reset -> «Сброс» hidden
    for ident in ("tab_models", "tab_prompts", "tab_keys", "tab_logs"):
        tabs.selectTabViewItemWithIdentifier_(ident)
        assert w._reset_btn.isHidden(), ident
