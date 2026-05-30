"""Clipboard access via NSPasteboard (PyObjC).

Chosen over ``pyperclip`` because we need reliable, synchronous read/write and a
``changeCount`` to detect external changes — and because Context mode (ring 3)
must save the user's previous clipboard and let them restore it on demand.

Restore is **on demand only**. Never auto-restore: if we restored right after
writing the result, the user's Cmd+V would grab the wrong thing.
"""

from __future__ import annotations

from AppKit import NSPasteboard, NSPasteboardTypeString


class Clipboard:
    def __init__(self) -> None:
        self._pb = NSPasteboard.generalPasteboard()
        self._previous: list[str] = []

    def read_text(self) -> str | None:
        value = self._pb.stringForType_(NSPasteboardTypeString)
        return str(value) if value is not None else None

    def write_text(self, text: str) -> None:
        self._pb.clearContents()
        self._pb.setString_forType_(text, NSPasteboardTypeString)

    def change_count(self) -> int:
        return int(self._pb.changeCount())

    def push_current(self) -> None:
        """Save the current clipboard so it can be restored later (Context mode)."""
        current = self.read_text()
        if current is not None:
            self._previous.append(current)

    def has_previous(self) -> bool:
        return bool(self._previous)

    def restore_previous(self) -> bool:
        """Pop the most recently saved clipboard back onto the pasteboard."""
        if not self._previous:
            return False
        self.write_text(self._previous.pop())
        return True
