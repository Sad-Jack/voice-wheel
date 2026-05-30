"""The radial wheel overlay — neon "hacker HUD" style (pure PyObjC, non-activating).

Three depth zones by radius:
- center (r < DEAD_ZONE)      → dictate (STT only).
- inner ring (DEAD_ZONE..MID) → transform: process my speech with the sector's prompt.
- outer ring (MID..OUTER)     → context: clipboard as context + my speech → prompt → clipboard.

Monochrome neon cyan. Radar ticks around the rim for the HUD feel. The active
sector glows; inactive sectors are thin outlines (no fill). Center shows a mic for
dictate, or the aimed sector's name (one clean label) + "+ БУФЕР" in the outer ring.
Wedges are annular segments — they never poke into the center hub.
"""

from __future__ import annotations

import math

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSCompositingOperationSourceAtop,
    NSCompositingOperationSourceOver,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
    NSPanel,
    NSRectFillUsingOperation,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakePoint, NSMakeRect, NSString

from ...core.modes import sectors
from ...core.wheel_geometry import (
    DEAD_ZONE,
    MID,
    OUTER,
    center_angle,
    n,
    sector_index,
    selection_for,
    step,
)

# Panel size & colors are rendering concerns (the geometry lives in core).
PANEL = 330
CENTER = PANEL / 2.0
CYAN = (0.16, 0.82, 1.00)
RED = (1.00, 0.32, 0.38)


def _col(rgb, a):  # noqa: ANN001
    r, g, b = rgb
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)


def _annular(center, r_in, r_out, start, end):  # noqa: ANN001
    p = NSBezierPath.bezierPath()
    p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(center, r_out, start, end)
    p.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
        center, r_in, end, start, True
    )
    p.closePath()
    return p


def _glow(path, rgb, base_w):  # noqa: ANN001
    for w, a in ((base_w + 6, 0.10), (base_w + 3, 0.22), (base_w, 0.95)):
        path.setLineWidth_(w)
        _col(rgb, a).setStroke()
        path.stroke()


def _mono(size, weight=0.3):  # noqa: ANN001
    try:
        return NSFont.monospacedSystemFontOfSize_weight_(size, weight)
    except Exception:  # noqa: BLE001
        return NSFont.boldSystemFontOfSize_(size)


def _draw_ticks(center):  # noqa: ANN001
    for k in range(24):
        ang = math.radians(k * 15)
        cardinal = (k % 6 == 0)
        r0 = OUTER + 5
        r1 = OUTER + (12 if cardinal else 8)
        c, s = math.cos(ang), math.sin(ang)
        line = NSBezierPath.bezierPath()
        line.moveToPoint_(NSMakePoint(CENTER + r0 * c, CENTER + r0 * s))
        line.lineToPoint_(NSMakePoint(CENTER + r1 * c, CENTER + r1 * s))
        line.setLineWidth_(1.6 if cardinal else 1.0)
        _col(CYAN, 0.55 if cardinal else 0.25).setStroke()
        line.stroke()


def _draw_symbol(name, cx, cy, size, rgb):  # noqa: ANN001
    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if img is None:
        return False
    img.setTemplate_(True)
    s = img.size()
    w, h = s.width, s.height
    scale = size / max(w, h)
    dw, dh = w * scale, h * scale
    tinted = img.copy()
    tinted.lockFocus()
    _col(rgb, 1.0).set()
    NSRectFillUsingOperation(NSMakeRect(0, 0, w, h), NSCompositingOperationSourceAtop)
    tinted.unlockFocus()
    tinted.setTemplate_(False)
    tinted.drawInRect_fromRect_operation_fraction_(
        NSMakeRect(cx - dw / 2, cy - dh / 2, dw, dh),
        NSMakeRect(0, 0, w, h),
        NSCompositingOperationSourceOver,
        1.0,
    )
    return True


def _draw_label(text, dx, dy, size, rgb, bold=False):  # noqa: ANN001
    font = _mono(size, 0.5 if bold else 0.3)
    attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: _col(rgb, 1.0)}
    ns = NSString.stringWithString_(text)
    sz = ns.sizeWithAttributes_(attrs)
    cx, cy = CENTER + dx, CENTER + dy
    pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(cx - sz.width / 2.0 - 6, cy - sz.height / 2.0 - 1, sz.width + 12, sz.height + 2),
        5, 5,
    )
    _col((0.0, 0.0, 0.0), 0.7).setFill()
    pill.fill()
    ns.drawAtPoint_withAttributes_(NSMakePoint(cx - sz.width / 2.0, cy - sz.height / 2.0), attrs)


class WheelView(NSView):
    def initWithFrame_(self, frame):  # noqa: N802
        self = objc.super(WheelView, self).initWithFrame_(frame)
        if self is not None:
            self.rel = (0.0, 0.0)
        return self

    def isFlipped(self):  # noqa: N802
        return False

    def drawRect_(self, _rect):  # noqa: N802
        center = NSMakePoint(CENTER, CENTER)
        count = n()
        st = step()
        ring, _key = selection_for(self.rel)
        active = None if ring in ("dictate", "cancel") else sector_index(*self.rel)

        # Dark base + double frame + radar ticks.
        _col((0.03, 0.05, 0.08), 0.85).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(CENTER - OUTER - 3, CENTER - OUTER - 3, 2 * (OUTER + 3), 2 * (OUTER + 3))
        ).fill()
        for fr, a in ((OUTER + 3, 0.30), (OUTER + 14, 0.14)):
            ring_path = NSBezierPath.bezierPath()
            ring_path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(center, fr, 0, 360)
            ring_path.setLineWidth_(1.0)
            _col(CYAN, a).setStroke()
            ring_path.stroke()
        _draw_ticks(center)

        # Sectors — monochrome cyan. Inactive: thin outline. Active: glow fill.
        for i in range(count):
            start = center_angle(i) - st / 2.0 + 1.4
            end = start + st - 2.8
            inner = _annular(center, DEAD_ZONE + 3, MID - 2, start, end)
            outer = _annular(center, MID + 2, OUTER - 2, start, end)
            if ring == "transform" and i == active:
                _col(CYAN, 0.24).setFill(); inner.fill(); _glow(inner, CYAN, 1.6)
                outer.setLineWidth_(1.1); _col(CYAN, 0.18).setStroke(); outer.stroke()
            elif ring == "context" and i == active:
                _col(CYAN, 0.24).setFill(); outer.fill(); _glow(outer, CYAN, 1.6)
                inner.setLineWidth_(1.1); _col(CYAN, 0.18).setStroke(); inner.stroke()
            else:
                for seg in (inner, outer):
                    seg.setLineWidth_(1.2)
                    _col(CYAN, 0.30).setStroke(); seg.stroke()

        # Center hub.
        hub = NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(CENTER - DEAD_ZONE, CENTER - DEAD_ZONE, 2 * DEAD_ZONE, 2 * DEAD_ZONE)
        )
        _col((0.04, 0.06, 0.09), 0.95).setFill()
        hub.fill()
        if ring == "dictate":
            _col(CYAN, 0.13).setFill(); hub.fill(); _glow(hub, CYAN, 1.7)
        elif ring == "cancel":
            hub.setLineWidth_(1.4); _col(RED, 0.55).setStroke(); hub.stroke()
        else:
            hub.setLineWidth_(1.2); _col(CYAN, 0.35).setStroke(); hub.stroke()

        # Center content (on top).
        if ring == "cancel":
            _draw_label("✕ Отмена", 0, 0, 13, RED, bold=True)
        elif ring == "dictate":
            if not _draw_symbol("mic.fill", CENTER, CENTER, 28, CYAN):
                _draw_label("ГОЛОС", 0, 0, 12, CYAN, bold=True)
        else:
            sector = sectors()[active]
            if ring == "context":
                _draw_label(sector.label, 0, 7, 13, CYAN, bold=True)
                _draw_label("+ БУФЕР", 0, -11, 9, (0.75, 0.92, 1.0))
            else:
                _draw_label(sector.label, 0, 0, 13, CYAN, bold=True)


class WheelOverlay:
    """Owns the non-activating panel. All methods must run on the main thread."""

    def __init__(self) -> None:
        self._panel = None
        self._view = None
        self._anchor = (0.0, 0.0)

    def _ensure(self) -> None:
        if self._panel is not None:
            return
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PANEL, PANEL),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setLevel_(3)
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setIgnoresMouseEvents_(True)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorIgnoresCycle
        )
        view = WheelView.alloc().initWithFrame_(NSMakeRect(0, 0, PANEL, PANEL))
        panel.setContentView_(view)
        self._panel = panel
        self._view = view

    def show_at(self, x: float, y: float) -> None:
        self._ensure()
        self._anchor = (x, y)
        self._view.rel = (0.0, 0.0)
        self._panel.setFrameOrigin_(NSMakePoint(x - CENTER, y - CENTER))
        self._view.setNeedsDisplay_(True)
        self._panel.orderFrontRegardless()

    def update(self, mouse_x: float, mouse_y: float) -> None:
        if self._view is None:
            return
        self._view.rel = (mouse_x - self._anchor[0], mouse_y - self._anchor[1])
        self._view.setNeedsDisplay_(True)

    def selection(self) -> tuple[str, str | None]:
        if self._view is None:
            return "dictate", None
        return selection_for(self._view.rel)

    def hide(self) -> None:
        if self._panel is not None:
            self._panel.orderOut_(None)
