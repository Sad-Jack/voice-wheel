"""Completion pulse: a brief expanding ring at the cursor when the result is ready."""

from __future__ import annotations

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSPanel,
    NSTimer,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakePoint, NSMakeRect

PSIZE = 150
PC = PSIZE / 2.0


class PulseView(NSView):
    def initWithFrame_(self, frame):  # noqa: N802
        self = objc.super(PulseView, self).initWithFrame_(frame)
        if self is not None:
            self.progress = 1.0
            self.panel = None
        return self

    def isFlipped(self):  # noqa: N802
        return False

    def drawRect_(self, _rect):  # noqa: N802
        if self.progress >= 1.0:
            return
        p = self.progress
        r = 12 + p * (PC - 16)
        alpha = max(0.0, 1.0 - p)
        path = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(PC - r, PC - r, 2 * r, 2 * r)
        )
        path.setLineWidth_(5 * (1 - p) + 2)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.30, 0.85, 0.45, alpha).setStroke()
        path.stroke()

    def onStep_(self, timer):  # noqa: N802
        self.progress += 0.06
        if self.progress >= 1.0:
            self.progress = 1.0
            timer.invalidate()
            if self.panel is not None:
                self.panel.orderOut_(None)
            return
        self.setNeedsDisplay_(True)


class PulseOverlay:
    def __init__(self) -> None:
        self._panel = None
        self._view = None

    def _ensure(self) -> None:
        if self._panel is not None:
            return
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PSIZE, PSIZE),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setLevel_(3)
        panel.setIgnoresMouseEvents_(True)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
        )
        view = PulseView.alloc().initWithFrame_(NSMakeRect(0, 0, PSIZE, PSIZE))
        view.panel = panel
        panel.setContentView_(view)
        self._panel = panel
        self._view = view

    def pulse_at(self, x: float, y: float) -> None:
        """Main-thread only."""
        self._ensure()
        self._panel.setFrameOrigin_(NSMakePoint(x - PC, y - PC))
        self._view.progress = 0.0
        self._panel.orderFrontRegardless()
        self._view.setNeedsDisplay_(True)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 60.0, self._view, "onStep:", None, True
        )
