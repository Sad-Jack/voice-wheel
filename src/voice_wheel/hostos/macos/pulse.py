"""Cursor feedback: a spinning "processing" indicator and a colored completion ping.

- ProcessingIndicator: a ring spinner that follows the cursor while STT/LLM run,
  so the user knows it's working (not dead).
- PulseOverlay: a one-shot ping at the cursor when done — green (ok), orange
  (raw text saved, LLM didn't answer), red (failed).
"""

from __future__ import annotations

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSEvent,
    NSPanel,
    NSTimer,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakePoint, NSMakeRect

PULSE_COLORS = {
    "green": (0.20, 1.00, 0.65),   # neon teal-green
    "orange": (1.00, 0.70, 0.15),  # neon amber
    "red": (1.00, 0.25, 0.35),     # neon red-pink
}
NEON_CYAN = (0.15, 0.80, 1.00)


def _make_panel(size: float) -> NSPanel:
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, size, size),
        NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered,
        False,
    )
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setLevel_(3)
    panel.setIgnoresMouseEvents_(True)
    panel.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
    )
    return panel


# ---------------------------------------------------------------- completion ping

PSIZE = 150
PC = PSIZE / 2.0


class PulseView(NSView):
    def initWithFrame_(self, frame):  # noqa: N802
        self = objc.super(PulseView, self).initWithFrame_(frame)
        if self is not None:
            self.progress = 1.0
            self.panel = None
            self.color = PULSE_COLORS["green"]
        return self

    def isFlipped(self):  # noqa: N802
        return False

    def drawRect_(self, _rect):  # noqa: N802
        if self.progress >= 1.0:
            return
        p = self.progress
        r = 12 + p * (PC - 16)
        alpha = max(0.0, 1.0 - p)
        base_w = 5 * (1 - p) + 2
        for extra, a_mul in ((7, 0.28), (0, 1.0)):  # glow + core
            path = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(PC - r, PC - r, 2 * r, 2 * r)
            )
            path.setLineWidth_(base_w + extra)
            r0, g0, b0 = self.color
            NSColor.colorWithCalibratedRed_green_blue_alpha_(r0, g0, b0, alpha * a_mul).setStroke()
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
        panel = _make_panel(PSIZE)
        view = PulseView.alloc().initWithFrame_(NSMakeRect(0, 0, PSIZE, PSIZE))
        view.panel = panel
        panel.setContentView_(view)
        self._panel = panel
        self._view = view

    def pulse_at(self, x: float, y: float, color: str = "green") -> None:
        """Main-thread only."""
        self._ensure()
        self._view.color = PULSE_COLORS.get(color, PULSE_COLORS["green"])
        self._panel.setFrameOrigin_(NSMakePoint(x - PC, y - PC))
        self._view.progress = 0.0
        self._panel.orderFrontRegardless()
        self._view.setNeedsDisplay_(True)
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 60.0, self._view, "onStep:", None, True
        )


# ---------------------------------------------------------------- processing spinner

SSIZE = 50
SC = SSIZE / 2.0
SPIN_R = 15.0


def _c(rgb, a):  # noqa: ANN001
    r, g, b = rgb
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)


class SpinnerView(NSView):
    def initWithFrame_(self, frame):  # noqa: N802
        self = objc.super(SpinnerView, self).initWithFrame_(frame)
        if self is not None:
            self.angle = 0.0
            self.panel = None
        return self

    def isFlipped(self):  # noqa: N802
        return False

    def drawRect_(self, _rect):  # noqa: N802
        center = NSMakePoint(SC, SC)
        a = self.angle
        # Faint hub for contrast over busy backgrounds.
        _c((0.03, 0.05, 0.09), 0.45).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(SC - SPIN_R - 4, SC - SPIN_R - 4, 2 * (SPIN_R + 4), 2 * (SPIN_R + 4))
        ).fill()
        # Three concentric arcs spinning at different speeds & directions.
        self._arc(center, SPIN_R, a, 135, 0.95)
        self._arc(center, SPIN_R * 0.64, -a * 1.7, 100, 0.85)
        self._arc(center, SPIN_R * 0.34, a * 2.6, 90, 1.0)

    @objc.python_method
    def _arc(self, center, r, start, sweep, alpha):  # noqa: ANN001
        for w, am in ((4.0, 0.12), (2.6, 0.26), (1.5, 1.0)):
            p = NSBezierPath.bezierPath()
            p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(center, r, start, start + sweep)
            p.setLineWidth_(w)
            _c(NEON_CYAN, alpha * am).setStroke()
            p.stroke()

    def onSpin_(self, _timer):  # noqa: N802
        m = NSEvent.mouseLocation()
        if self.panel is not None:
            self.panel.setFrameOrigin_(NSMakePoint(m.x - SC, m.y - SC))  # follow cursor
        self.angle = (self.angle + 5.0) % 360.0
        self.setNeedsDisplay_(True)


class ProcessingIndicator:
    def __init__(self) -> None:
        self._panel = None
        self._view = None
        self._timer = None

    def _ensure(self) -> None:
        if self._panel is not None:
            return
        panel = _make_panel(SSIZE)
        view = SpinnerView.alloc().initWithFrame_(NSMakeRect(0, 0, SSIZE, SSIZE))
        view.panel = panel
        panel.setContentView_(view)
        self._panel = panel
        self._view = view

    def start(self) -> None:
        """Main-thread only. Show the spinner and animate it following the cursor."""
        self._ensure()
        m = NSEvent.mouseLocation()
        self._panel.setFrameOrigin_(NSMakePoint(m.x - SC, m.y - SC))
        self._panel.orderFrontRegardless()
        self._view.setNeedsDisplay_(True)
        if self._timer is None:
            self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0 / 60.0, self._view, "onSpin:", None, True
            )

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        if self._panel is not None:
            self._panel.orderOut_(None)
