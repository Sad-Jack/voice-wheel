"""Global trigger registration (Quartz event tap + pynput), decoupled from the app.

One place owns every trigger: side mouse buttons via a Quartz CGEventTap, and
keyboard / standard mouse via pynput. All of them funnel to the target NSObject's
selectors via ``performSelectorOnMainThread``.

CRITICAL: the Quartz tap callback runs in the windowserver input path — it MUST
stay fast and only dispatch ASYNC (waitUntilDone=False). Doing heavy work inline
there freezes the whole input system (beachball). That's why every handler just
``_fire``s a selector and returns.
"""

from __future__ import annotations

import logging

from pynput import keyboard, mouse

from .mouse_tap import SIDE_BUTTONS, SideButtonTap

log = logging.getLogger(__name__)


class TriggerManager:
    """Registers triggers for a target NSObject (which holds the action selectors)."""

    def __init__(self, target) -> None:  # noqa: ANN001
        self._target = target
        self._tap = None
        self._kb_listener = None
        self._ms_listener = None

    def start(self, triggers) -> bool:
        """``triggers``: list of (HotkeyConfig, press_selector|None, release_selector|None).

        Returns False if a side-button tap was required but could not start
        (e.g. Accessibility not granted yet) — the app stays alive regardless.
        """
        side: dict = {}
        kb: list = []   # (mod_names, main_key, press_sel, release_sel) — supports combos
        ms: dict = {}
        for hk, p_sel, r_sel in triggers:
            if hk.kind == "mouse_side":
                key = hk.key.strip().lower()
                bn = int(key) if key.isdigit() else SIDE_BUTTONS.get(key, 3)
                side[bn] = {
                    "press": (lambda s=p_sel: self._fire(s)) if p_sel else None,
                    "release": (lambda s=r_sel: self._fire(s)) if r_sel else None,
                }
            elif hk.kind == "keyboard":
                mods, main = _parse_combo(hk.key)
                if main is not None:
                    kb.append((mods, main, p_sel, r_sel))
            elif hk.kind == "mouse":
                ms[_parse_button(hk.key)] = {"press": p_sel, "release": r_sel}

        ok = True
        if side:
            try:
                self._tap = SideButtonTap(side, suppress=True)
                self._tap.start()
            except Exception as exc:  # noqa: BLE001 - no Accessibility yet: stay alive
                log.warning("trigger tap not started (grant Accessibility & restart): %s", exc)
                ok = False
        if kb or ms:
            try:
                self._start_pynput(kb, ms)
            except Exception as exc:  # noqa: BLE001
                log.warning("keyboard/mouse trigger not started: %s", exc)
        return ok

    def _fire(self, selector):  # noqa: ANN001
        self._target.performSelectorOnMainThread_withObject_waitUntilDone_(selector, None, False)

    def _start_pynput(self, kb, ms):  # noqa: ANN001
        if kb:
            held_mods: set = set()  # modifier names currently down
            active: set = set()     # indices of triggers currently firing (held)

            def on_press(key):
                m = _mod_name(key)
                if m:
                    held_mods.add(m)
                    return
                for i, (mods, main, p_sel, _r) in enumerate(kb):
                    if key == main and mods <= held_mods and i not in active:
                        active.add(i)
                        if p_sel:
                            self._fire(p_sel)

            def on_release(key):
                m = _mod_name(key)
                if m:
                    held_mods.discard(m)
                    for i in list(active):  # releasing a required modifier ends the hold
                        mods, _main, _p, r_sel = kb[i]
                        if m in mods:
                            active.discard(i)
                            if r_sel:
                                self._fire(r_sel)
                    return
                for i in list(active):
                    _mods, main, _p, r_sel = kb[i]
                    if key == main:
                        active.discard(i)
                        if r_sel:
                            self._fire(r_sel)

            self._kb_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._kb_listener.start()

        if ms:
            def on_click(x, y, button, pressed):  # noqa: ANN001
                h = ms.get(button)
                if not h:
                    return
                if pressed and h["press"]:
                    self._fire(h["press"])
                elif not pressed and h["release"]:
                    self._fire(h["release"])

            self._ms_listener = mouse.Listener(on_click=on_click)
            self._ms_listener.start()


MODS = ("cmd", "ctrl", "alt", "shift")


def _mod_name(key):  # noqa: ANN001
    """A pynput modifier key -> canonical name ('cmd'/'ctrl'/'alt'/'shift'), else None."""
    name = getattr(key, "name", "") or ""  # KeyCode (char keys) has no .name
    for m in MODS:
        if name.startswith(m):
            return m
    if name.startswith("alt"):  # alt_gr
        return "alt"
    return None


def _parse_combo(spec: str):
    """'cmd+f' -> ({'cmd'}, KeyCode 'f'); 'f8' -> (set(), Key.f8). main is None if unknown."""
    parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    mods = {p for p in parts if p in MODS}
    mains = [p for p in parts if p not in MODS]
    if not mains:
        return mods, None
    try:
        return mods, _parse_key(mains[-1])
    except ValueError:
        log.warning("unrecognized keyboard trigger: %r", spec)
        return mods, None


def _parse_key(name: str):
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
    raise ValueError(f"Unrecognized mouse button: {name!r}")
