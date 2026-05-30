"""Menu-bar status item (NSStatusItem).

Mic icon + live status, a History submenu (last results — click to re-copy),
"restore previous clipboard", and Quit. The controller wires handlers via
``set_handlers`` and refreshes the list via ``update_history``.
"""

from __future__ import annotations

import objc
from AppKit import (
    NSApplication,
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
        self._restore = None
        self._settings = None

        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        button = self._status_item.button()
        img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "mic.circle.fill", "Voice Wheel"
        )
        if img is not None:
            img.setTemplate_(True)
            button.setImage_(img)
        else:
            button.setTitle_("VW")

        menu = NSMenu.alloc().init()
        self._status_mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Voice Wheel", None, ""
        )
        self._status_mi.setEnabled_(False)
        menu.addItem_(self._status_mi)
        menu.addItem_(NSMenuItem.separatorItem())

        self._history_mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "История", None, ""
        )
        self._history_menu = NSMenu.alloc().init()
        self._history_mi.setSubmenu_(self._history_menu)
        menu.addItem_(self._history_mi)
        self._refresh_history_menu([])

        self._restore_mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Вернуть прошлый буфер", "restoreClicked:", ""
        )
        self._restore_mi.setTarget_(self)
        self._restore_mi.setEnabled_(False)
        menu.addItem_(self._restore_mi)

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
    def set_handlers(self, reuse, restore, settings=None):
        self._reuse = reuse
        self._restore = restore
        self._settings = settings

    def setStatus_(self, text):  # noqa: N802
        self._status_mi.setTitle_(text)

    @objc.python_method
    def set_restore_enabled(self, enabled: bool):
        self._restore_mi.setEnabled_(bool(enabled))

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

    def restoreClicked_(self, _sender):  # noqa: N802
        if self._restore is not None:
            self._restore()

    def settingsClicked_(self, _sender):  # noqa: N802
        if self._settings is not None:
            self._settings()

    def quitApp_(self, _sender):  # noqa: N802
        NSApplication.sharedApplication().terminate_(None)
