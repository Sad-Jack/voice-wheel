"""Trigger bindings are a list now (#54): keyboard + mouse, both live. These
cover the config-level parsing/migration (dependency-light, no AppKit)."""

from __future__ import annotations

import json

from voice_wheel.core.config import Config, HotkeyConfig, _parse_hotkeys


def test_parse_hotkeys_legacy_single_dict():
    out = _parse_hotkeys({"kind": "mouse_side", "key": "3"}, [HotkeyConfig()])
    assert [(h.kind, h.key) for h in out] == [("mouse_side", "3")]


def test_parse_hotkeys_list():
    raw = [{"kind": "keyboard", "key": "cmd+б"}, {"kind": "mouse_side", "key": "3"}]
    out = _parse_hotkeys(raw, [HotkeyConfig()])
    assert [(h.kind, h.key) for h in out] == [("keyboard", "cmd+б"), ("mouse_side", "3")]


def test_parse_hotkeys_missing_uses_fallback():
    fb = [HotkeyConfig(kind="mouse_side", key="4")]
    assert _parse_hotkeys(None, fb) == fb


def test_parse_hotkeys_explicit_empty_list_stays_empty():
    assert _parse_hotkeys([], [HotkeyConfig()]) == []


def test_config_load_migrates_legacy_dict(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"hotkey": {"kind": "keyboard", "key": "f8"}}')
    c = Config.load(p)
    assert [(h.kind, h.key) for h in c.hotkeys] == [("keyboard", "f8")]


def test_config_load_list(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"hotkey": [
        {"kind": "keyboard", "key": "cmd+б"},
        {"kind": "mouse_side", "key": "3"},
    ]}))
    c = Config.load(p)
    assert [(h.kind, h.key) for h in c.hotkeys] == [("keyboard", "cmd+б"), ("mouse_side", "3")]


def test_defaults_are_side_mouse_buttons():
    assert (Config().hotkeys[0].kind, Config().hotkeys[0].key) == ("mouse_side", "3")
    assert (Config().tts.hotkeys[0].kind, Config().tts.hotkeys[0].key) == ("mouse_side", "4")
