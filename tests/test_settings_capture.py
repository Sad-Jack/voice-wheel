import pytest

pytest.importorskip("AppKit")

from AppKit import (  # noqa: E402
    NSEvent,
    NSEventModifierFlagCommand,
    NSEventModifierFlagShift,
    NSEventTypeKeyDown,
)
from Foundation import NSMakePoint  # noqa: E402

from voice_wheel.hostos.macos.settings import _format_combo, _mouse_kind_key  # noqa: E402


def _key_event(flags, chars, keycode):
    return NSEvent.keyEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(  # noqa: E501
        NSEventTypeKeyDown, NSMakePoint(0, 0), flags, 0.0, 0, None, chars, chars, False, keycode
    )


def test_format_combo_modifier_char():
    assert _format_combo(_key_event(NSEventModifierFlagCommand, "f", 3)) == "cmd+f"


def test_format_combo_function_key():
    assert _format_combo(_key_event(0, "", 100)) == "f8"   # keyCode 100 = F8


def test_format_combo_multi_modifier():
    flags = NSEventModifierFlagCommand | NSEventModifierFlagShift
    assert _format_combo(_key_event(flags, "a", 0)) == "cmd+shift+a"


def test_mouse_buttons_map():
    assert _mouse_kind_key(1) == ("mouse", "right")
    assert _mouse_kind_key(2) == ("mouse", "middle")
    assert _mouse_kind_key(3) == ("mouse_side", "3")
    assert _mouse_kind_key(4) == ("mouse_side", "4")
    assert _mouse_kind_key(0) == (None, None)   # left -> ignored
