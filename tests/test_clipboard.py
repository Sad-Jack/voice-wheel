"""Clipboard stack test. Touches the real pasteboard, so it saves and restores
the user's clipboard around the test. Skipped if PyObjC/AppKit isn't installed.
"""

import pytest

pytest.importorskip("AppKit")

from voice_wheel.hostos.macos.clipboard import Clipboard  # noqa: E402


def test_push_and_restore_round_trip():
    clip = Clipboard()
    original = clip.read_text()
    try:
        clip.write_text("first")
        clip.push_current()  # saves "first"
        clip.write_text("second (result)")
        assert clip.read_text() == "second (result)"
        assert clip.has_previous() is True

        assert clip.restore_previous() is True
        assert clip.read_text() == "first"
        assert clip.has_previous() is False
        assert clip.restore_previous() is False
    finally:
        if original is not None:
            clip.write_text(original)
