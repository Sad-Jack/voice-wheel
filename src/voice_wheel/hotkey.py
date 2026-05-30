"""Global hold-to-record listener (pynput) bridged to Qt signals.

Runs pynput on its own daemon thread and emits only Qt signals with primitive
payloads — the cardinal cross-thread rule. The controller connects these to
main-thread slots (show overlay + start recording / stop + process).

Hold-to-record only: ``pressed`` fires once on the initial press and ``released``
once on release; auto-repeat presses while held are ignored.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal
from pynput import keyboard, mouse

from .config import HotkeyConfig

log = logging.getLogger(__name__)


class HotkeyListener(QObject):
    pressed = pyqtSignal(int, int)  # cursor (x, y) at press, screen coords
    released = pyqtSignal()

    def __init__(self, config: HotkeyConfig) -> None:
        super().__init__()
        self._cfg = config
        self._listener = None
        self._mouse_ctrl = mouse.Controller()
        self._held = False

    def start(self) -> None:
        if self._cfg.kind == "mouse":
            self._target = _parse_button(self._cfg.key)
            self._listener = mouse.Listener(on_click=self._on_click)
        else:
            self._target = _parse_key(self._cfg.key)
            self._listener = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release
            )
        self._listener.start()
        log.info("hotkey listener started (%s:%s)", self._cfg.kind, self._cfg.key)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def is_alive(self) -> bool:
        return self._listener is not None and self._listener.running

    # -- keyboard -------------------------------------------------------------

    def _on_press(self, key) -> None:  # noqa: ANN001
        if self._matches(key) and not self._held:
            self._held = True
            self._emit_pressed()

    def _on_release(self, key) -> None:  # noqa: ANN001
        if self._matches(key) and self._held:
            self._held = False
            self.released.emit()

    # -- mouse ----------------------------------------------------------------

    def _on_click(self, x, y, button, is_down) -> None:  # noqa: ANN001
        if button != self._target:
            return
        if is_down and not self._held:
            self._held = True
            self.pressed.emit(int(x), int(y))
        elif not is_down and self._held:
            self._held = False
            self.released.emit()

    # -- helpers --------------------------------------------------------------

    def _matches(self, key) -> bool:  # noqa: ANN001
        return key == self._target

    def _emit_pressed(self) -> None:
        try:
            x, y = self._mouse_ctrl.position
        except Exception:  # noqa: BLE001
            x, y = 0, 0
        self.pressed.emit(int(x), int(y))


def _parse_key(name: str):
    """'f8' -> Key.f8, 'alt_r' -> Key.alt_r, single char -> KeyCode."""
    name = name.strip().lower()
    if hasattr(keyboard.Key, name):
        return getattr(keyboard.Key, name)
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    raise ValueError(f"Unrecognized keyboard key: {name!r}")


def _parse_button(name: str):
    name = name.strip().lower()
    if hasattr(mouse.Button, name):
        return getattr(mouse.Button, name)
    raise ValueError(
        f"Unrecognized mouse button: {name!r} (try left/right/middle, "
        "or a numbered button your mouse exposes)"
    )
