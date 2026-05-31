import pytest

pytest.importorskip("Quartz")   # triggers -> mouse_tap -> Quartz (macOS only)
pytest.importorskip("pynput")

from pynput import keyboard  # noqa: E402

from voice_wheel.hostos.macos.triggers import _mod_name, _parse_combo  # noqa: E402


def test_parse_single_function_key():
    mods, main = _parse_combo("f8")
    assert mods == set()
    assert main == keyboard.Key.f8


def test_parse_single_char_key():
    mods, main = _parse_combo("a")
    assert mods == set()
    assert main == keyboard.KeyCode.from_char("a")


def test_parse_modifier_combo():
    mods, main = _parse_combo("cmd+f")
    assert mods == {"cmd"}
    assert main == keyboard.KeyCode.from_char("f")


def test_parse_multi_modifier_combo():
    mods, main = _parse_combo("cmd+shift+space")
    assert mods == {"cmd", "shift"}
    assert main == keyboard.Key.space


def test_parse_unknown_main_is_none():
    mods, main = _parse_combo("cmd+nope")
    assert mods == {"cmd"}
    assert main is None   # unrecognized main key -> None, no exception


def test_mod_name_maps_variants():
    assert _mod_name(keyboard.Key.cmd) == "cmd"
    assert _mod_name(keyboard.Key.cmd_l) == "cmd"
    assert _mod_name(keyboard.Key.shift_r) == "shift"
    assert _mod_name(keyboard.Key.ctrl) == "ctrl"
    assert _mod_name(keyboard.KeyCode.from_char("f")) is None
