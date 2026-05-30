"""Menu-bar (tray) UI via QSystemTrayIcon.

The app runs as a macOS accessory (no Dock icon), so the tray menu is the only
chrome: a status line, a language toggle, a history submenu (click to re-copy a
past result), restore-previous-clipboard, and quit. The icon is drawn in code as
a template image, so no asset file is needed.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .history import HistoryEntry

_LANGUAGES = ("ru", "en", "auto")


class Tray(QObject):
    languageChanged = pyqtSignal(str)
    restoreRequested = pyqtSignal()
    reuseRequested = pyqtSignal(str)  # re-copy a past result
    quitRequested = pyqtSignal()

    def __init__(self, language: str = "ru") -> None:
        super().__init__()
        self._icon = QSystemTrayIcon(_make_icon())
        self._icon.setToolTip("Voice Wheel")
        self._menu = QMenu()

        self._status = QAction("Voice Wheel — ready")
        self._status.setEnabled(False)
        self._menu.addAction(self._status)
        self._menu.addSeparator()

        self._build_language_menu(language)
        self._history_menu = self._menu.addMenu("History")
        self._refresh_history_menu([])

        self._restore = QAction("Restore previous clipboard")
        self._restore.triggered.connect(lambda: self.restoreRequested.emit())
        self._restore.setEnabled(False)
        self._menu.addAction(self._restore)

        self._menu.addSeparator()
        quit_action = QAction("Quit Voice Wheel")
        quit_action.triggered.connect(lambda: self.quitRequested.emit())
        self._menu.addAction(quit_action)

        self._icon.setContextMenu(self._menu)
        self._icon.show()

    # -- public API -----------------------------------------------------------

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def set_restore_enabled(self, enabled: bool) -> None:
        self._restore.setEnabled(enabled)

    def show_message(self, title: str, body: str) -> None:
        self._icon.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 2500)

    def update_history(self, entries: list[HistoryEntry]) -> None:
        self._refresh_history_menu(entries)

    # -- menu construction ----------------------------------------------------

    def _build_language_menu(self, current: str) -> None:
        lang_menu = self._menu.addMenu("Language")
        group = QActionGroup(self)
        group.setExclusive(True)
        for lang in _LANGUAGES:
            action = QAction(lang.upper(), self)
            action.setCheckable(True)
            action.setChecked(lang == current)
            action.triggered.connect(lambda _checked, l=lang: self.languageChanged.emit(l))
            group.addAction(action)
            lang_menu.addAction(action)

    def _refresh_history_menu(self, entries: list[HistoryEntry]) -> None:
        self._history_menu.clear()
        if not entries:
            empty = QAction("(empty)", self)
            empty.setEnabled(False)
            self._history_menu.addAction(empty)
            return
        for entry in entries:
            label = _elide(entry.result)
            action = QAction(label, self)
            action.triggered.connect(lambda _c, t=entry.result: self.reuseRequested.emit(t))
            self._history_menu.addAction(action)


def _elide(text: str, length: int = 48) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= length else flat[: length - 1] + "…"


def _make_icon() -> QIcon:
    pixmap = QPixmap(22, 22)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(0, 0, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(5, 5, 12, 12)
    painter.end()
    icon = QIcon(pixmap)
    icon.setIsMask(True)  # template image: macOS tints it for light/dark menu bar
    return icon
