"""Voice Wheel — pure-PyObjC app (no PyQt).

Flow:
    hold hotkey  -> wheel appears at cursor + recording starts
    move mouse   -> highlight center (dictate) or a sector (LLM style)
    release      -> wheel hides; selection applied; STT (+ LLM) runs in the
                    background; result -> clipboard; a pulse fires at the cursor
    Cmd+V        -> paste anywhere

Threading: pynput runs on its own thread and hops to the main thread via
``performSelectorOnMainThread``. STT/LLM run on a worker thread so the UI never
blocks. Only NSPanel/NSView work touches the main thread.
"""

from __future__ import annotations

import logging
import os
import threading

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSEvent,
    NSTimer,
)
from Foundation import NSObject
from PyObjCTools import AppHelper

from ...core.config import Config, app_support_dir
from ...core.history import History
from ...core.job_tracker import JobTracker
from ...core.llm import LLMClient
from ...core.pipeline import Pipeline
from ...core.recorder import Recorder, trim_silence
from ...core.stt import STTEngine
from .clipboard import Clipboard
from .pulse import ProcessingIndicator, PulseOverlay
from .settings import SettingsWindow
from .tray import MenuBar
from .triggers import TriggerManager
from .tts import Speaker
from .wheel_overlay import WheelOverlay

log = logging.getLogger(__name__)

MIN_RECORDING_SEC = 0.35  # shorter than this = an accidental tap, not a real request


class VoiceWheel(NSObject):
    # -- construction ---------------------------------------------------------

    def initWithConfig_(self, config):  # noqa: N802
        self = objc.super(VoiceWheel, self).init()
        if self is None:
            return None
        self._config = config
        self._concurrent = bool(getattr(config, "concurrent", False))
        self._recording = False
        self._tick_timer = None
        # All cross-thread state (cycle id, inflight count, result queue) lives here.
        self._jobs = JobTracker()

        self._clipboard = Clipboard()
        self._history = History(
            app_support_dir() / "history.sqlite", limit=config.history_limit
        )
        self._recorder = Recorder()
        stt = STTEngine(config.stt)
        llm = LLMClient(config.llm, config.sector_models)
        self._pipeline = Pipeline(stt, llm, self._clipboard, config)
        self._stt = stt
        self._llm = llm

        self._wheel = WheelOverlay()
        self._pulse = PulseOverlay()
        self._spinner = ProcessingIndicator()
        self._menubar = MenuBar.alloc().init()
        self._settings_win = SettingsWindow.alloc().init()
        self._menubar.set_handlers(self._on_reuse, self._on_restore, self._settings_win.show)
        self._menubar.update_history(self._history.recent())
        try:
            self._speaker = Speaker(config.tts.voice)
        except Exception as exc:  # noqa: BLE001
            log.warning("TTS unavailable: %s", exc)
            self._speaker = None
        self._triggers = TriggerManager(self)
        return self

    # -- lifecycle ------------------------------------------------------------

    def start(self):
        self._menubar.setStatus_("Voice Wheel — прогрев…")
        triggers = [(self._config.hotkey, "onPress:", "onRelease:")]
        if self._config.tts.enabled and self._speaker is not None:
            triggers.append((self._config.tts.hotkey, "onTts:", None))
        if not self._triggers.start(triggers):
            self._menubar.setStatus_("⚠️ Нет доступа: Accessibility")
        threading.Thread(target=self._warm_up, daemon=True).start()
        print(
            f"Voice Wheel готов. Зажми {self._config.hotkey.kind}:{self._config.hotkey.key}, "
            "говори, отпусти. Центр = текст, сектор = стиль. Ctrl+C для выхода.",
            flush=True,
        )

    def _warm_up(self):
        try:
            self._stt.warm_up()
            self._llm.warm_up()
            print("STT прогрет, готов к работе.", flush=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("warm-up: %s", exc)
        self.performSelectorOnMainThread_withObject_waitUntilDone_("warmReady:", None, False)

    def warmReady_(self, _sender):  # noqa: N802
        self._menubar.setStatus_("Voice Wheel — готов")

    def onTts_(self, _sender):  # noqa: N802
        if self._speaker is None:
            return
        state = self._speaker.toggle(self._clipboard.read_text())
        if state == "speaking":
            self._menubar.setStatus_("🔊 озвучка буфера…")
        elif state == "stopped":
            self._menubar.setStatus_("Voice Wheel — готов")
        else:
            self._menubar.setStatus_("буфер пуст")
        print(f"TTS: {state}", flush=True)

    @objc.python_method
    def _on_reuse(self, text):
        """Re-copy a past result from the History submenu."""
        self._clipboard.push_current()
        self._clipboard.write_text(text)
        self._menubar.set_restore_enabled(self._clipboard.has_previous())
        self._menubar.setStatus_("Voice Wheel — скопировано из истории")

    @objc.python_method
    def _on_restore(self):
        if self._clipboard.restore_previous():
            self._menubar.set_restore_enabled(self._clipboard.has_previous())
            self._menubar.setStatus_("Voice Wheel — буфер восстановлен")

    # -- main-thread slots ----------------------------------------------------

    def onPress_(self, _sender):  # noqa: N802
        # End the recording phase of any prior cycle. Non-concurrent: also cancel
        # in-flight processing (self-healing). Concurrent: let prior jobs keep
        # processing while a new recording starts.
        if self._tick_timer is not None:
            self._tick_timer.invalidate()
            self._tick_timer = None
        if self._recorder.is_recording:
            self._recorder.stop()
        self._wheel.hide()
        if not self._concurrent:
            self._spinner.stop()
            self._jobs.reset()
        self._jobs.bump_generation()
        self._recording = True
        loc = NSEvent.mouseLocation()  # bottom-left origin (for the panel)
        self._wheel.show_at(loc.x, loc.y)
        self._recorder.start()
        self._llm.prewarm()  # boot the LLM now so it hides behind recording time
        self._menubar.setStatus_("● запись…")
        print("● запись… (двигай мышь к сектору, отпусти для обработки)", flush=True)
        self._tick_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 60.0, self, "onTick:", None, True
        )

    def onTick_(self, _timer):  # noqa: N802
        m = NSEvent.mouseLocation()
        self._wheel.update(m.x, m.y)

    def onRelease_(self, _sender):  # noqa: N802
        if self._tick_timer is not None:
            self._tick_timer.invalidate()
            self._tick_timer = None
        if not self._recording or not self._recorder.is_recording:
            self._recording = False
            self._wheel.hide()
            return
        self._recording = False
        gen = self._jobs.generation
        ring, sector = self._wheel.selection()
        self._wheel.hide()
        raw = self._recorder.stop()
        if ring == "cancel":
            # Cursor left the wheel — discard everything, process nothing.
            self._llm.discard_prewarm()
            self._menubar.setStatus_("Voice Wheel — отменено")
            print("✕ отменено (курсор за колесом)", flush=True)
            return
        if raw.size < MIN_RECORDING_SEC * self._recorder.sample_rate:
            # An accidental tap (press+release with no real speech) — skip quietly
            # instead of spinning up STT and flashing a scary red "empty" ping.
            self._llm.discard_prewarm()
            self._menubar.setStatus_("Voice Wheel — слишком коротко")
            print("· слишком коротко — пропускаю", flush=True)
            return
        audio = trim_silence(raw)
        print(f"○ стоп → обработка ({ring}/{sector or 'центр'})…", flush=True)
        self._menubar.setStatus_("обработка…")
        self._jobs.begin()
        self._spinner.start()  # idempotent; keeps spinning while any job runs
        threading.Thread(
            target=self._process, args=(audio, ring, sector, gen), daemon=True
        ).start()

    def finishProcessing_(self, _sender):  # noqa: N802
        if self._jobs.finish() == 0:
            self._spinner.stop()
            self._menubar.setStatus_("Voice Wheel — готов")
        payload = self._jobs.pop_result()
        if payload is None:
            return
        color, note = payload
        if not color:
            return  # cancelled / stale — no ping
        m = NSEvent.mouseLocation()  # ping where the cursor IS now
        self._pulse.pulse_at(m.x, m.y, color)
        print(note, flush=True)
        self._menubar.update_history(self._history.recent())
        self._menubar.set_restore_enabled(self._clipboard.has_previous())

    # -- worker thread --------------------------------------------------------

    @objc.python_method
    def _process(self, audio, ring, sector, gen):
        color, note = "", ""
        try:
            result = self._pipeline.run(audio, ring, sector)
            self._llm.discard_prewarm()  # no-op if consumed; kills it if dictate (unused)
            if (not self._concurrent) and self._jobs.is_stale(gen):
                pass  # superseded by a newer press — drop (no clipboard, no ping)
            else:
                text = result.result.strip()
                if not text:
                    color, note = "red", f"⚠️  Пусто — {result.error or 'речь не распознана'}"
                else:
                    self._clipboard.push_current()
                    self._clipboard.write_text(result.result)
                    self._history.add(result.ring, result.sector, result.transcript, result.result)
                    preview = text.replace("\n", " ")[:120]
                    if result.error:
                        color, note = "orange", f"⚠️  LLM не ответил — сохранил сырой текст: {preview}"
                    elif result.llm_skipped:
                        color, note = "orange", f"✅ Сырой текст (LLM недоступен): {preview}"
                    else:
                        if result.ring == "dictate":
                            tag = "ТЕКСТ"
                        elif result.ring == "context":
                            tag = "БУФЕР→" + result.sector.upper()
                        else:
                            tag = result.sector.upper()
                        color, note = "green", f"✅ [{tag}] → буфер: {preview}"
        except Exception as exc:  # noqa: BLE001
            log.exception("processing failed")
            color, note = "red", f"❌ Ошибка: {exc}"
        self._jobs.push_result((color, note))
        self.performSelectorOnMainThread_withObject_waitUntilDone_("finishProcessing:", None, False)


def _ensure_accessibility() -> bool:
    """Prompt to add this binary to Accessibility (needed for the global hotkey)."""
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        trusted = AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        if not trusted:
            print(
                "⚠️  Нет доступа Accessibility — триггер ловиться не будет.\n"
                "   1) В появившемся диалоге нажми «Открыть настройки».\n"
                "   2) Privacy & Security → Accessibility → включи «Voice Wheel» (или Python).\n"
                "   3) Перезапусти приложение.",
                flush=True,
            )
        return bool(trusted)
    except Exception as exc:  # noqa: BLE001
        log.warning("accessibility check failed: %s", exc)
        return True


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a project-root .env (gitignored) into the env."""
    from ...core.config import _project_root

    env_file = _project_root() / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _load_dotenv()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    _ensure_accessibility()
    config = Config.load()
    controller = VoiceWheel.alloc().initWithConfig_(config)
    controller.start()
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
