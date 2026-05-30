"""Phase 0 — overlay focus spike (THE gating de-risk).

Proves the single make-or-break property of this product: a radial overlay can
appear at the cursor and be interacted with **without stealing keyboard focus**
from whatever app was focused before it appeared. If focus moved, the user's
Cmd+V after release would paste into the wrong place and the product is dead.

Approach: a pure-PyObjC **non-activating NSPanel** (the plan's preferred path,
independent of Qt). The panel is borderless, translucent, floats above
everything, joins all Spaces, and is shown with ``orderFrontRegardless`` so it
never activates the app. The app itself runs as an accessory (no Dock icon).

A ~60 Hz timer polls the cursor and redraws a placeholder 3-ring / 4-sector
wheel, highlighting the ring (by radius) and sector (by angle) the cursor points
at — exactly the interaction the real wheel will use.

---------------------------------------------------------------------------
PASS / FAIL CHECKLIST (run it and check by hand):
  1. Run:  python spikes/overlay_focus_spike.py
     (Grant Accessibility/Input Monitoring to your terminal if asked.)
  2. A translucent wheel appears, anchored where your mouse was at launch.
  3. Click into another app (e.g. a text field in Telegram, Notes, a browser)
     and TYPE. -> PASS if your keystrokes land in that app.
  4. Move the mouse over the wheel; the highlighted ring+sector should track the
     cursor's radius and angle. Clicking directly ON the wheel must STILL not
     move focus away from the app you were typing in. -> PASS if focus stays.
  5. No Dock icon appears for this process. -> PASS.
  Stop with Ctrl+C in the terminal.

If step 3 or 4 fails (focus jumps to Python), the non-activating mask isn't
taking — that's the signal to investigate before building Phase D.
---------------------------------------------------------------------------
"""

from __future__ import annotations

import math

from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSEvent,
    NSFloatingWindowLevel,
    NSPanel,
    NSScreen,
    NSTimer,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
import objc
from Foundation import NSMakePoint, NSMakeRect, NSObject, NSPoint
from PyObjCTools import AppHelper

PANEL = 500  # panel is square, PANEL x PANEL
CENTER = PANEL / 2
DEAD_ZONE = 40
RINGS = [(40, 90, "Dictate"), (90, 150, "Transform"), (150, 220, "Context")]
SECTORS = ["Clean", "Short", "Friendly", "Tech"]


class WheelView(NSView):
    def initWithFrame_(self, frame):  # noqa: N802
        self = objc.super(WheelView, self).initWithFrame_(frame)
        if self is not None:
            self.rel = (0.0, 0.0)  # cursor offset from center
        return self

    def isFlipped(self):  # noqa: N802 - keep bottom-left origin math simple
        return False

    def drawRect_(self, _rect):  # noqa: N802
        center = NSMakePoint(CENTER, CENTER)
        dx, dy = self.rel
        r = math.hypot(dx, dy)
        active_ring = _ring_index(r)
        active_sector = _sector_index(dx, dy) if active_ring is not None else None

        # Dim backdrop disk so the wheel reads against any app behind it.
        backdrop = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(CENTER - 230, CENTER - 230, 460, 460)
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0, 0, 0, 0.28).setFill()
        backdrop.fill()

        for i, (inner, outer, _label) in enumerate(RINGS):
            mid = (inner + outer) / 2.0
            band = NSBezierPath.bezierPath()
            band.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
                center, mid, 0, 360
            )
            band.setLineWidth_(outer - inner - 4)
            alpha = 0.85 if i == active_ring else 0.30
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.95, 1.0, alpha).setStroke()
            band.stroke()

        # Sector dividers.
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0, 0, 0, 0.45).setStroke()
        for k in range(len(SECTORS)):
            ang = math.radians(90 * k + 45)
            line = NSBezierPath.bezierPath()
            line.moveToPoint_(NSMakePoint(CENTER + DEAD_ZONE * math.cos(ang),
                                          CENTER + DEAD_ZONE * math.sin(ang)))
            line.lineToPoint_(NSMakePoint(CENTER + 220 * math.cos(ang),
                                          CENTER + 220 * math.sin(ang)))
            line.setLineWidth_(1.5)
            line.stroke()

        # Highlight the active ring+sector wedge.
        if active_ring is not None and active_sector is not None:
            inner, outer, _ = RINGS[active_ring]
            mid = (inner + outer) / 2.0
            start = 90 * active_sector - 45
            wedge = NSBezierPath.bezierPath()
            wedge.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
                center, mid, start, start + 90
            )
            wedge.setLineWidth_(outer - inner - 4)
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.30, 0.80, 1.0, 0.95).setStroke()
            wedge.stroke()

        # Dead zone.
        dz = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(CENTER - DEAD_ZONE, CENTER - DEAD_ZONE, 2 * DEAD_ZONE, 2 * DEAD_ZONE)
        )
        NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 1, 1, 0.10).setFill()
        dz.fill()


class WheelController(NSObject):
    def start(self):
        # Anchor at the center of the main screen so the whole wheel is visible.
        frame = NSScreen.mainScreen().frame()
        self.anchor = (
            frame.origin.x + frame.size.width / 2.0,
            frame.origin.y + frame.size.height / 2.0,
        )
        self.ticks = 0

        rect = NSMakeRect(
            self.anchor[0] - CENTER, self.anchor[1] - CENTER, PANEL, PANEL
        )
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setLevel_(NSFloatingWindowLevel)
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorIgnoresCycle
        )

        view = WheelView.alloc().initWithFrame_(NSMakeRect(0, 0, PANEL, PANEL))
        panel.setContentView_(view)
        panel.orderFrontRegardless()  # show WITHOUT activating

        self.panel = panel
        self.view = view

        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 60.0, self, "onTick:", None, True
        )
        print(
            f"Spike running. Anchor (screen center): {self.anchor}. "
            "Move the mouse to select; Ctrl+C to stop.",
            flush=True,
        )

    def onTick_(self, _timer):  # noqa: N802
        m = NSEvent.mouseLocation()
        rel = (m.x - self.anchor[0], m.y - self.anchor[1])
        self.view.rel = rel
        self.view.setNeedsDisplay_(True)
        self.ticks += 1
        if self.ticks % 60 == 0:  # ~once per second: proves the loop is live
            r = math.hypot(rel[0], rel[1])
            ring = _ring_index(r)
            name = RINGS[ring][2] if ring is not None else "—"
            print(f"tick {self.ticks}: r={r:.0f}px ring={name}", flush=True)


def _ring_index(r: float):
    for i, (inner, outer, _label) in enumerate(RINGS):
        if inner <= r < outer:
            return i
    return None


def _sector_index(dx: float, dy: float) -> int:
    # Sectors centered on the diagonal dividers at 45°, 135°, ...
    ang = math.degrees(math.atan2(dy, dx)) % 360
    return int(((ang + 45) % 360) // 90)


def main() -> None:
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    controller = WheelController.alloc().init()
    controller.start()
    AppHelper.runEventLoop()  # Ctrl+C exits cleanly


if __name__ == "__main__":
    main()
