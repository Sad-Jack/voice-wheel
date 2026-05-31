"""Clipboard round-trip test. Touches the real pasteboard, so it saves and
restores the user's clipboard around the test. Skipped if PyObjC isn't installed.
"""

import pytest

pytest.importorskip("AppKit")

from voice_wheel.hostos.macos.clipboard import Clipboard  # noqa: E402


def test_write_read_round_trip():
    clip = Clipboard()
    original = clip.read_text()
    try:
        clip.write_text("hello result")
        assert clip.read_text() == "hello result"
        clip.write_text("замена")
        assert clip.read_text() == "замена"
    finally:
        if original is not None:
            clip.write_text(original)
