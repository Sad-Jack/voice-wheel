"""Global side-mouse-button trigger via a Quartz CGEventTap on a DEDICATED THREAD.

pynput on macOS only reports left/middle/right — side buttons (back/forward) are
invisible to it. A CGEventTap sees ``otherMouseDown``/``otherMouseUp`` with the
button number, so we use it for the hold-to-record trigger.

CRITICAL: the tap runs its own CFRunLoop on a dedicated daemon thread — NOT the
main run loop. An active (suppress) tap whose run loop also drives the UI (60 fps
wheel redraw, audio device open/close) can stall: when the main thread is busy
the windowserver waits for the tap callback → input freezes / beachball. On its
own thread the tap is always responsive; the callback only hops the actual work
to the main thread (handlers use performSelectorOnMainThread, which is
cross-thread safe). Needs Accessibility.
"""

from __future__ import annotations

import logging
import threading

import Quartz

log = logging.getLogger(__name__)

# Convenience names -> CGEvent button numbers. 3 = first side (back), 4 = second.
SIDE_BUTTONS = {"side1": 3, "side2": 4, "back": 3, "forward": 4}


class SideButtonTap:
    def __init__(self, handlers: dict, suppress: bool = True):
        # handlers: {button_number(int): {"press": cb|None, "release": cb|None}}
        self._handlers = {int(k): v for k, v in handlers.items()}
        self._suppress = suppress
        self._tap = None
        self._thread = None
        self._ready = threading.Event()
        self._error = None

    def start(self) -> None:
        """Start the tap on its own thread. Raises if it can't be created (e.g. no
        Accessibility) — the caller decides what to do."""
        self._thread = threading.Thread(target=self._run, name="eventtap", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("event-tap thread did not start in time")
        if self._error is not None:
            raise self._error
        log.info("side-button tap started on its own thread (buttons %s)", sorted(self._handlers))

    def _run(self) -> None:
        try:
            mask = Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown) | Quartz.CGEventMaskBit(
                Quartz.kCGEventOtherMouseUp
            )
            option = (
                Quartz.kCGEventTapOptionDefault
                if self._suppress
                else Quartz.kCGEventTapOptionListenOnly
            )
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                option,
                mask,
                self._callback,
                None,
            )
            if not tap:
                self._error = RuntimeError(
                    "CGEventTapCreate failed — Accessibility permission missing?"
                )
                self._ready.set()
                return
            self._tap = tap
            src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetCurrent(), src, Quartz.kCFRunLoopCommonModes
            )
            Quartz.CGEventTapEnable(tap, True)
        except Exception as exc:  # noqa: BLE001
            self._error = exc
            self._ready.set()
            return
        self._ready.set()
        Quartz.CFRunLoopRun()  # blocks this daemon thread, pumping the tap forever

    def _callback(self, proxy, type_, event, refcon):  # noqa: ANN001 - runs on the tap thread
        # Re-arm if the system disabled the tap (timeout / heavy load).
        if type_ in (
            Quartz.kCGEventTapDisabledByTimeout,
            Quartz.kCGEventTapDisabledByUserInput,
        ):
            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, True)
            return event

        bn = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGMouseEventButtonNumber)
        handler = self._handlers.get(bn)
        if handler is None:
            return event  # not one of ours -> pass through

        # No internal held-state: the controller dedupes and self-heals. Handlers
        # only hop to the main thread (performSelectorOnMainThread) — fast & safe.
        if type_ == Quartz.kCGEventOtherMouseDown and handler.get("press"):
            handler["press"]()
        elif type_ == Quartz.kCGEventOtherMouseUp and handler.get("release"):
            handler["release"]()

        return None if self._suppress else event
