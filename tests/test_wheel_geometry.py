from voice_wheel.core.wheel_geometry import (
    CANCEL,
    DEAD_ZONE,
    MID,
    OUTER,
    center_angle,
    n,
    sector_index,
    selection_for,
    step,
)


def test_zones_by_radius():
    assert selection_for((0, 0)) == ("dictate", None)
    assert selection_for((0, (DEAD_ZONE + MID) / 2))[0] == "transform"
    assert selection_for((0, (MID + OUTER) / 2))[0] == "context"
    assert selection_for((0, CANCEL + 30)) == ("cancel", None)


def test_sector_index_directions():
    if n() != 4:
        return  # directions below assume the 4 default sectors
    assert sector_index(0, 100) == 0    # up
    assert sector_index(100, 0) == 1    # right
    assert sector_index(0, -100) == 2   # down
    assert sector_index(-100, 0) == 3   # left


def test_step_and_center_angle():
    assert step() == 360.0 / n()
    assert center_angle(0) == 90.0      # sector 0 sits at the top


def test_selection_returns_sector_key():
    ring, key = selection_for((0, (DEAD_ZONE + MID) / 2))
    assert ring == "transform"
    assert isinstance(key, str) and key
