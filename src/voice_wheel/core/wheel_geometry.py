"""Pure radial-wheel geometry — no PyObjC, so it's unit-testable and reusable
across platforms (the macOS overlay and a future Windows one share this).

Zones by radius (logical px from the wheel center; ``rel`` = cursor offset from it):
    r < DEAD_ZONE     -> dictate  (center hub)
    DEAD_ZONE..MID    -> transform (inner ring: process speech)
    MID..OUTER        -> context   (outer ring: clipboard + speech)
    r > CANCEL        -> cancel    (cursor left the wheel — discard on release)

Sectors come from ``modes.sectors()``; sector 0 sits at the top, going clockwise.
"""

from __future__ import annotations

import math

from .modes import sectors

DEAD_ZONE = 46
MID = 96
OUTER = 138
CANCEL = OUTER + 22  # 160 — beyond the rim


def n() -> int:
    return max(1, len(sectors()))


def step() -> float:
    return 360.0 / n()


def center_angle(i: int) -> float:
    """Center of sector i in degrees (math convention). Sector 0 = top, clockwise."""
    return 90.0 - i * step()


def sector_index(dx: float, dy: float) -> int:
    a = math.degrees(math.atan2(dy, dx)) % 360.0
    return int(round((90.0 - a) / step())) % n()


def selection_for(rel: tuple[float, float]) -> tuple[str, str | None]:
    """('dictate'|'transform'|'context'|'cancel', sector_key_or_None) for a cursor offset."""
    dx, dy = rel
    r = math.hypot(dx, dy)
    secs = sectors()
    if r < DEAD_ZONE or not secs:
        return "dictate", None
    if r > CANCEL:
        return "cancel", None
    ring = "transform" if r < MID else "context"
    return ring, secs[sector_index(dx, dy)].key
