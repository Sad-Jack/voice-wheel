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

from voice_wheel.hostos.macos.settings import SettingsWindow, _conn_type_of  # noqa: E402


def _window():
    w = SettingsWindow.alloc().init()
    w._build()
    return w


def test_reset_on_default_tab_keeps_save_disabled():
    w = _window()
    # The "saved" state already equals the dataclass defaults (auto / small / ru).
    w._stt_backend.selectItemWithTitle_("auto")
    w._stt_model.selectItemWithTitle_("small")
    w._lang.selectItemWithTitle_("ru")
    w._capture_baseline()  # this is what's saved
    w._tabs.selectTabViewItemAtIndex_(1)  # Речь
    w.resetCurrentTab_(None)  # reset lands back on the saved values
    assert w._dirty is False
    assert not w._save_btn.isEnabled()


def test_reset_that_changes_a_value_arms_save():
    w = _window()
    w._stt_model.selectItemWithTitle_("large")  # the saved value is non-default
    w._capture_baseline()
    w._tabs.selectTabViewItemAtIndex_(1)
    w.resetCurrentTab_(None)  # reset -> small, differs from the saved 'large'
    assert w._dirty is True
    assert w._save_btn.isEnabled()
    assert str(w._stt_model.titleOfSelectedItem()) == "small"


def test_revert_a_change_disarms_save():
    # Changing a value then changing it back to the saved value disarms Save.
    w = _window()
    w._stt_model.selectItemWithTitle_("small")
    w._capture_baseline()
    w._stt_model.selectItemWithTitle_("large")
    w.markDirty_(None)
    assert w._dirty is True
    w._stt_model.selectItemWithTitle_("small")  # back to saved
    w.markDirty_(None)
    assert w._dirty is False  # nothing actually differs now


def test_trigger_sig_legacy_dict_equals_one_item_list():
    # The restart-on-save decision (#50) must treat a legacy {kind,key} and the
    # equivalent one-item list as the same binding, and be order-independent.
    w = _window()
    assert w._trigger_sig({"kind": "mouse_side", "key": "3"}) == w._trigger_sig(
        [{"kind": "mouse_side", "key": "3"}]
    )
    assert w._trigger_sig(
        [{"kind": "keyboard", "key": "a"}, {"kind": "mouse_side", "key": "3"}]
    ) == w._trigger_sig(
        [{"kind": "mouse_side", "key": "3"}, {"kind": "keyboard", "key": "a"}]
    )
    assert w._trigger_sig({"kind": "mouse_side", "key": "3"}) != w._trigger_sig(
        {"kind": "mouse_side", "key": "4"}
    )
    assert w._trigger_sig(None) == frozenset()


def test_conn_type_maps_backends_to_radio_groups():
    # The three radio types (#36) group the underlying LLM backends.
    assert _conn_type_of("ollama") == "ollama"
    assert _conn_type_of("anthropic") == "api"
    assert _conn_type_of("openai") == "api"
    assert _conn_type_of("claude_warm") == "cc"
    assert _conn_type_of("claude_cli") == "cc"


def test_connection_visibility_shows_only_selected_group():
    w = _window()
    for rb, t in w._conn_radios:
        rb.setState_(1 if t == "api" else 0)
    w._apply_conn_visibility()
    assert not w._grp_api.isHidden()
    assert w._grp_ollama.isHidden() and w._grp_cc.isHidden()

    for rb, t in w._conn_radios:
        rb.setState_(1 if t == "cc" else 0)
    w._apply_conn_visibility()
    assert not w._grp_cc.isHidden()
    assert w._grp_api.isHidden() and w._grp_ollama.isHidden()
