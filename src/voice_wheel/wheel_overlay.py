"""The radial wheel overlay (pure PyObjC, non-activating NSPanel).

Center = dictate (STT only). Four directional sectors = LLM transform with a
preset style. The panel never steals focus (proven by the Phase 0 spike), so the
result can be pasted into whatever app was focused.

Layout (matches ``modes.SECTORS`` order): up=Чистовик, right=Деловой,
down=Кратко, left=Дружелюбно.
"""

from __future__ import annotations

import math

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSPanel,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakePoint, NSMakeRect, NSString

from .modes import SECTORS

PANEL = 460
CENTER = PANEL / 2.0
DEAD_ZONE = 58  # r < this -> center (dictate)
OUTER = 200
LABEL_R = (DEAD_ZONE + OUTER) / 2.0

# Direction (degrees, math convention) for each sector, aligned to SECTORS order.
_DIRS = [90, 0, 270, 180]  # up, right, down, left


def selection_for(rel: tuple[float, float]) -> tuple[str, str | None]:
    """('dictate', None) in the center, else ('transform', sector_key)."""
    dx, dy = rel
    if math.hypot(dx, dy) < DEAD_ZONE:
        return "dictate", None
    return "transform", SECTORS[_sector_index(dx, dy)].key


def _sector_index(dx: float, dy: float) -> int:
    ang = math.degrees(math.atan2(dy, dx)) % 360
    if ang < 45 or ang >= 315:
        return 1  # right
    if ang < 135:
        return 0  # up
    if ang < 225:
        return 3  # left
    return 2  # down


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
        ring, sector_key = selection_for(self.rel)
        active_idx = None if ring == "dictate" else _sector_index(*self.rel)

        # Backdrop disk.
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0, 0, 0, 0.30).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(CENTER - OUTER - 6, CENTER - OUTER - 6, 2 * (OUTER + 6), 2 * (OUTER + 6))
        ).fill()

        # Sector pie slices (carved into a donut later by the center disk).
        for i, _dir in enumerate(_DIRS):
            start = _wedge_start(i)
            pie = NSBezierPath.bezierPath()
            pie.moveToPoint_(center)
            pie.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_(
                center, OUTER, start, start + 90
            )
            pie.closePath()
            if i == active_idx:
                NSColor.colorWithCalibratedRed_green_blue_alpha_(0.25, 0.78, 1.0, 0.92).setFill()
            else:
                NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.96, 1.0, 0.14).setFill()
            pie.fill()

        # Dividers.
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0, 0, 0, 0.40).setStroke()
        for i in range(4):
            ang = math.radians(_wedge_start(i))
            line = NSBezierPath.bezierPath()
            line.moveToPoint_(center)
            line.lineToPoint_(NSMakePoint(CENTER + OUTER * math.cos(ang), CENTER + OUTER * math.sin(ang)))
            line.setLineWidth_(1.0)
            line.stroke()

        # Center disk (covers inner pie -> donut). Highlighted when in dead zone.
        if ring == "dictate":
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.35, 0.85, 0.45, 0.95).setFill()
        else:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.10, 0.10, 0.12, 0.85).setFill()
        NSBezierPath.bezierPathWithOvalInRect_(
            NSMakeRect(CENTER - DEAD_ZONE, CENTER - DEAD_ZONE, 2 * DEAD_ZONE, 2 * DEAD_ZONE)
        ).fill()

        # Labels.
        self._label("Текст", 0, 0, bold=True)
        for i, sector in enumerate(SECTORS):
            ang = math.radians(_DIRS[i])
            self._label(sector.label, LABEL_R * math.cos(ang), LABEL_R * math.sin(ang))

    @objc.python_method
    def _label(self, text, dx, dy, bold=False):  # noqa: ANN001
        font = NSFont.boldSystemFontOfSize_(15) if bold else NSFont.systemFontOfSize_(13)
        attrs = {
            NSFontAttributeName: font,
            NSForegroundColorAttributeName: NSColor.whiteColor(),
        }
        ns = NSString.stringWithString_(text)
        size = ns.sizeWithAttributes_(attrs)
        pt = NSMakePoint(CENTER + dx - size.width / 2.0, CENTER + dy - size.height / 2.0)
        ns.drawAtPoint_withAttributes_(pt, attrs)


def _wedge_start(i: int) -> float:
    # Sector i is centered on _DIRS[i]; the 90°-wide wedge starts 45° before it.
    return _DIRS[i] - 45


class WheelOverlay:
    """Owns the non-activating panel. All methods must be called on the main thread."""

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
        panel.setLevel_(3)  # NSFloatingWindowLevel
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setIgnoresMouseEvents_(True)  # pure overlay; we poll the cursor
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
