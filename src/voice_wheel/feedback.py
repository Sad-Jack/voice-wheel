"""User feedback: a subtle success cue and error surfacing.

Phase A keeps this minimal — a short system sound on success and a tray balloon
on error. The visual "cursor pulse" overlay arrives in Phase D, reusing the
non-activating-panel infrastructure proven by the overlay spike.
"""

from __future__ import annotations

import logging
from typing import Optional

from AppKit import NSSound

log = logging.getLogger(__name__)


class Feedback:
    def __init__(self, tray=None) -> None:  # noqa: ANN001 - tray is a QSystemTrayIcon
        self._tray = tray
        # Hold a reference so the async sound isn't GC'd mid-play.
        self._sound = NSSound.soundNamed_("Tink")

    def success(self, message: str = "Copied") -> None:
        if self._sound is not None:
            self._sound.stop()
            self._sound.play()
        log.info("done: %s", message)

    def error(self, message: str) -> None:
        log.warning("error: %s", message)
        if self._tray is not None:
            from PyQt6.QtWidgets import QSystemTrayIcon

            self._tray.showMessage(
                "Voice Wheel",
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
