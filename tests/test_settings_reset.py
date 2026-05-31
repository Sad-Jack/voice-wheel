"""«Сброс» must only arm Save when it actually changes a value (#54 follow-up):
resetting a tab that's already at defaults should leave Save disabled.

Builds the settings window (which only READS config.json) and sets controls
directly — it never writes config, so it's safe to run in the suite.
"""

from __future__ import annotations

import pytest

pytest.importorskip("AppKit")

from AppKit import NSApplication  # noqa: E402

NSApplication.sharedApplication()

from voice_wheel.hostos.macos.settings import SettingsWindow  # noqa: E402


def _window():
    w = SettingsWindow.alloc().init()
    w._build()
    return w


def test_reset_on_default_tab_keeps_save_disabled():
    w = _window()
    # Speech tab already at its dataclass defaults (auto / small / ru).
    w._stt_backend.selectItemWithTitle_("auto")
    w._stt_model.selectItemWithTitle_("small")
    w._lang.selectItemWithTitle_("ru")
    w._set_dirty(False)
    w._tabs.selectTabViewItemAtIndex_(1)  # Речь
    w.resetCurrentTab_(None)
    assert w._dirty is False
    assert not w._save_btn.isEnabled()


def test_reset_that_changes_a_value_arms_save():
    w = _window()
    w._stt_model.selectItemWithTitle_("large")  # not the default
    w._set_dirty(False)
    w._tabs.selectTabViewItemAtIndex_(1)
    w.resetCurrentTab_(None)
    assert w._dirty is True
    assert w._save_btn.isEnabled()
    assert str(w._stt_model.titleOfSelectedItem()) == "small"
