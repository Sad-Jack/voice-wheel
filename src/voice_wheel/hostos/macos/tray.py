"""Menu-bar status item (NSStatusItem).

A mic icon tinted green (ready) / red (not ready), a History submenu (last
results — click to re-copy), Settings, and Quit. The controller wires the
re-copy + settings handlers via ``set_handlers``, refreshes the list via
``update_history``, and reflects readiness via ``set_ready``.

Readiness is shown by icon color instead of a text line: if the app is running
it's "ready" by definition, so a "ready" label carried no information — a green
(ok) / red (warming up or no Accessibility) tint says it at a glance, always
visible without opening the menu.
"""

from __future__ import annotations

import objc
from AppKit import (
    NSApplication,
    NSColor,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSStatusBar,
    NSVariableStatusItemLength,
)
from Foundation import NSObject


def _elide(text: str, length: int = 52) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= length else flat[: length - 1] + "…"


class MenuBar(NSObject):
    def init(self):
        self = objc.super(MenuBar, self).init()
        if self is None:
            return None
        self._reuse = None
        self._settings = None

        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self._button = self._status_item.button()
        img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "mic.circle.fill", "Voice Wheel"
        )
        if img is not None:
            img.setTemplate_(True)
            self._button.setImage_(img)
        else:
            self._button.setTitle_("VW")
        self._button.setContentTintColor_(NSColor.systemRedColor())  # red until ready

        menu = NSMenu.alloc().init()
        self._history_mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "История", None, ""
        )
        self._history_menu = NSMenu.alloc().init()
        self._history_mi.setSubmenu_(self._history_menu)
        menu.addItem_(self._history_mi)
        self._refresh_history_menu([])

        settings_mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Настройки…", "settingsClicked:", ","
        )
        settings_mi.setTarget_(self)
        menu.addItem_(settings_mi)

        menu.addItem_(NSMenuItem.separatorItem())
        quit_mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Выход", "quitApp:", "q"
        )
        quit_mi.setTarget_(self)
        menu.addItem_(quit_mi)

        self._status_item.setMenu_(menu)
        self._menu = menu
        return self

    # -- wiring ---------------------------------------------------------------

    @objc.python_method
    def set_handlers(self, reuse, settings=None):
        self._reuse = reuse
        self._settings = settings

    @objc.python_method
    def set_ready(self, ready: bool):
        """Tint the menu-bar icon: green = ready, red = not ready."""
        color = NSColor.systemGreenColor() if ready else NSColor.systemRedColor()
        self._button.setContentTintColor_(color)

    @objc.python_method
    def update_history(self, entries):
        self._refresh_history_menu(entries)

    @objc.python_method
    def _refresh_history_menu(self, entries):
        self._history_menu.removeAllItems()
        if not entries:
            empty = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("(пусто)", None, "")
            empty.setEnabled_(False)
            self._history_menu.addItem_(empty)
            return
        for e in entries:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                _elide(e.result), "historyClicked:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(e.result)
            self._history_menu.addItem_(item)

    # -- actions --------------------------------------------------------------

    def historyClicked_(self, sender):  # noqa: N802
        text = sender.representedObject()
        if self._reuse is not None and text is not None:
            self._reuse(str(text))

    def settingsClicked_(self, _sender):  # noqa: N802
        if self._settings is not None:
            self._settings()

    def quitApp_(self, _sender):  # noqa: N802
        NSApplication.sharedApplication().terminate_(None)
