"""Global side-mouse-button trigger via a Quartz CGEventTap.

pynput on macOS only reports left/middle/right — side buttons (back/forward) are
invisible to it. A CGEventTap sees ``otherMouseDown``/``otherMouseUp`` with the
button number, so we use it for the hold-to-record trigger.

The tap is added to the main run loop, so its callback fires on the main thread —
no thread hop needed. With ``suppress=True`` the trigger button is consumed
(it won't also navigate back/forward in a browser). Needs Accessibility, which
the app already requires for the global hotkey.
"""

from __future__ import annotations

import logging

import Quartz

log = logging.getLogger(__name__)

# Convenience names -> CGEvent button numbers. 3 = first side (back), 4 = second.
SIDE_BUTTONS = {"side1": 3, "side2": 4, "back": 3, "forward": 4}


class SideButtonTap:
    def __init__(self, button_number: int, on_press, on_release, suppress: bool = True):
        self._bn = int(button_number)
        self._on_press = on_press
        self._on_release = on_release
        self._suppress = suppress
        self._tap = None
        self._src = None
        self._held = False

    def start(self) -> None:
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown) | Quartz.CGEventMaskBit(
            Quartz.kCGEventOtherMouseUp
        )
        option = (
            Quartz.kCGEventTapOptionDefault
            if self._suppress
            else Quartz.kCGEventTapOptionListenOnly
        )
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            option,
            mask,
            self._callback,
            None,
        )
        if not self._tap:
            raise RuntimeError(
                "CGEventTapCreate failed — Accessibility permission missing?"
            )
        self._src = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), self._src, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(self._tap, True)
        log.info("side-button tap started (button #%d)", self._bn)

    def _callback(self, proxy, type_, event, refcon):  # noqa: ANN001
        # Re-arm if the system disabled the tap (timeout / heavy load).
        if type_ in (
            Quartz.kCGEventTapDisabledByTimeout,
            Quartz.kCGEventTapDisabledByUserInput,
        ):
            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, True)
            return event

        bn = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGMouseEventButtonNumber)
        if bn != self._bn:
            return event

        if type_ == Quartz.kCGEventOtherMouseDown and not self._held:
            self._held = True
            self._on_press()
        elif type_ == Quartz.kCGEventOtherMouseUp and self._held:
            self._held = False
            self._on_release()

        return None if self._suppress else event
