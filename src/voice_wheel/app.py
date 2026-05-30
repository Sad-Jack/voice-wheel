"""Application bootstrap and controller.

Wires the pieces together on a single PyQt6 event loop:

    hotkey (daemon thread) --signals--> Controller (main thread)
        press   -> start recording, status "Listening…"
        release -> stop recording, hand audio to the Worker
    Worker (QThread)       --signals--> Controller (main thread)
        resultReady -> success cue, refresh history
        error       -> tray balloon

Runs as a macOS accessory (no Dock icon). The radial wheel (Phase D) will hook
into the same press/release pair; until then the mode comes from
``config.default_mode``.
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication

from .clipboard import Clipboard
from .config import Config, app_support_dir
from .feedback import Feedback
from .history import History
from .hotkey import HotkeyListener
from .llm import LLMClient
from .pipeline import Pipeline, PipelineResult
from .recorder import Recorder, trim_silence
from .stt import STTEngine
from .tray import Tray
from .worker import Worker

log = logging.getLogger(__name__)


class Controller(QObject):
    jobRequested = pyqtSignal(object, str, str)  # audio, ring, sector
    warmUpRequested = pyqtSignal()

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._busy = False

        # Core services
        self._clipboard = Clipboard()
        self._history = History(
            app_support_dir() / "history.sqlite", limit=config.history_limit
        )
        self._recorder = Recorder()
        stt = STTEngine(config.stt)
        llm = LLMClient(config.llm)
        pipeline = Pipeline(stt, llm, self._clipboard, config)

        # UI
        self._tray = Tray(language=config.language)
        self._feedback = Feedback(tray=self._tray._icon)

        # Worker thread
        self._thread = QThread()
        self._worker = Worker(pipeline, self._clipboard, self._history)
        self._worker.moveToThread(self._thread)
        self.jobRequested.connect(self._worker.process)
        self.warmUpRequested.connect(self._worker.warm_up)
        self._worker.resultReady.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.warmedUp.connect(lambda: self._tray.set_status("Voice Wheel — ready"))

        # Hotkey
        self._hotkey = HotkeyListener(config.hotkey)
        self._hotkey.pressed.connect(self._on_press)
        self._hotkey.released.connect(self._on_release)

        # Tray wiring
        self._tray.languageChanged.connect(self._on_language_changed)
        self._tray.restoreRequested.connect(self._on_restore)
        self._tray.reuseRequested.connect(self._clipboard.write_text)
        self._tray.quitRequested.connect(self.shutdown)

        # Watchdog: restart the listener if its event tap dies.
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(5000)
        self._watchdog.timeout.connect(self._check_listener)

    def start(self) -> None:
        self._thread.start()
        self._hotkey.start()
        self._watchdog.start()
        self._tray.set_status("Voice Wheel — warming up…")
        self.warmUpRequested.emit()
        self._tray.update_history(self._history.recent())

    # -- hotkey -> recording --------------------------------------------------

    def _on_press(self, _x: int, _y: int) -> None:
        if self._busy:
            return
        self._busy = True
        self._recorder.start()
        self._tray.set_status("Listening… (release to process)")

    def _on_release(self) -> None:
        if not self._recorder.is_recording:
            self._busy = False
            return
        audio = trim_silence(self._recorder.stop())
        ring = self._config.default_mode.ring
        sector = self._config.default_mode.sector
        self._tray.set_status("Processing…")
        self.jobRequested.emit(audio, ring, sector)

    # -- worker results -------------------------------------------------------

    def _on_result(self, result: PipelineResult) -> None:
        self._busy = False
        note = "Copied"
        if result.llm_skipped:
            note = "Copied (raw — no API key)"
        elif result.context_truncated:
            note = "Copied (context truncated)"
        self._feedback.success(note)
        self._tray.set_status(f"Voice Wheel — {note}")
        self._tray.update_history(self._history.recent())
        self._tray.set_restore_enabled(self._clipboard.has_previous())

    def _on_error(self, message: str) -> None:
        self._busy = False
        self._feedback.error(message)
        self._tray.set_status("Voice Wheel — ready")

    # -- tray actions ---------------------------------------------------------

    def _on_language_changed(self, language: str) -> None:
        self._config.language = language
        log.info("language -> %s", language)

    def _on_restore(self) -> None:
        if self._clipboard.restore_previous():
            self._tray.set_restore_enabled(self._clipboard.has_previous())
            self._tray.set_status("Voice Wheel — clipboard restored")

    def _check_listener(self) -> None:
        if not self._hotkey.is_alive():
            log.warning("hotkey listener died; restarting")
            self._hotkey.start()

    # -- lifecycle ------------------------------------------------------------

    def shutdown(self) -> None:
        self._watchdog.stop()
        self._hotkey.stop()
        self._thread.quit()
        self._thread.wait(2000)
        self._history.close()
        QApplication.instance().quit()


def _set_accessory_policy() -> None:
    """No Dock icon + focus-weak agent (also set LSUIElement=1 when bundled)."""
    try:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
        )

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("could not set accessory activation policy: %s", exc)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray-only app, no windows
    _set_accessory_policy()

    config = Config.load()
    controller = Controller(config)
    controller.start()

    log.info(
        "Voice Wheel running. Hold %s:%s to record. Default mode: %s/%s.",
        config.hotkey.kind,
        config.hotkey.key,
        config.default_mode.ring,
        config.default_mode.sector,
    )
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
