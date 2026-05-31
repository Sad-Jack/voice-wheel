"""Clipboard access via NSPasteboard (PyObjC).

Chosen over ``pyperclip`` because we need reliable, synchronous read/write and a
``changeCount`` to detect external changes — and because Context mode (ring 3)
must save the user's previous clipboard and let them restore it on demand.

Restore is **on demand only**. Never auto-restore: if we restored right after
writing the result, the user's Cmd+V would grab the wrong thing.
"""

from __future__ import annotations

import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString

_KEYCODE_C = 0x08  # ANSI 'c'


def _post_cmd_c() -> None:
    """Synthesize a ⌘C keystroke to the focused app (copies its selection)."""
    down = Quartz.CGEventCreateKeyboardEvent(None, _KEYCODE_C, True)
    Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
    up = Quartz.CGEventCreateKeyboardEvent(None, _KEYCODE_C, False)
    Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


class Clipboard:
    def __init__(self) -> None:
        self._pb = NSPasteboard.generalPasteboard()

    def read_text(self) -> str | None:
        value = self._pb.stringForType_(NSPasteboardTypeString)
        return str(value) if value is not None else None

    def read_selection(self, timeout: float = 0.4) -> str | None:
        """Copy the focused app's current selection via ⌘C and return it, then
        restore the clipboard so this read doesn't clobber it. Returns None if
        nothing was selected (the pasteboard never changed).

        Call this OFF the main thread — it posts a keystroke and polls the
        pasteboard with short sleeps while the target app does the copy.
        """
        before = int(self._pb.changeCount())
        saved = self.read_text()
        _post_cmd_c()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if int(self._pb.changeCount()) != before:
                selection = self.read_text()
                if saved is not None:  # put the user's clipboard back as it was
                    self.write_text(saved)
                return selection
            time.sleep(0.02)
        return None  # ⌘C produced nothing -> no selection

    def write_text(self, text: str) -> None:
        self._pb.clearContents()
        self._pb.setString_forType_(text, NSPasteboardTypeString)
