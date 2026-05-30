"""Background worker that owns the warm STT model + LLM client.

Lives on a long-lived QThread. The controller emits ``jobRequested`` (a queued
signal); ``process`` runs on this thread, so STT/LLM never block the UI. After
producing the result it saves the previous clipboard (for restore) and writes the
result, then emits ``resultReady``.

NSPasteboard read/write is thread-safe, so doing it here (off the main thread) is
fine; only NSWindow/UI work is main-thread-only.
"""

from __future__ import annotations

import logging

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from .clipboard import Clipboard
from .history import History
from .pipeline import Pipeline, PipelineResult

log = logging.getLogger(__name__)


class Worker(QObject):
    resultReady = pyqtSignal(object)  # PipelineResult
    error = pyqtSignal(str)
    warmedUp = pyqtSignal()

    def __init__(
        self, pipeline: Pipeline, clipboard: Clipboard, history: History
    ) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._clipboard = clipboard
        self._history = history

    @pyqtSlot()
    def warm_up(self) -> None:
        try:
            self._pipeline._stt.warm_up()
            self._pipeline._llm.warm_up()
        except Exception as exc:  # noqa: BLE001
            log.warning("warm-up failed: %s", exc)
        self.warmedUp.emit()

    @pyqtSlot(object, str, str)
    def process(self, audio: np.ndarray, ring: str, sector: str) -> None:
        try:
            result = self._pipeline.run(audio, ring, sector)
            if not result.result.strip():
                self.error.emit("Empty result (no speech detected?)")
                return
            # Save the prior clipboard so the user can restore it, then write.
            self._clipboard.push_current()
            self._clipboard.write_text(result.result)
            self._history.add(
                result.ring, result.sector, result.transcript, result.result
            )
            self.resultReady.emit(result)
        except Exception as exc:  # noqa: BLE001
            log.exception("processing failed")
            self.error.emit(str(exc))
