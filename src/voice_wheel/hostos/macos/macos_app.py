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

import atexit
import logging
import os
import threading
import time

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
from .i18n import resolve_lang
from .i18n import t as _tr
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
        self._lang = resolve_lang(getattr(config, "ui_language", ""))
        self._concurrent = bool(getattr(config, "concurrent", False))
        self._recording = False
        self._triggers_ok = False    # green icon only once the trigger is actually live
        self._tts_capturing = False  # guards the ⌘C selection-grab from double-fire
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
        self._menubar = MenuBar.alloc().initWithLang_(self._lang)
        self._settings_win = SettingsWindow.alloc().init()
        self._settings_win.set_apply_callback(self._apply_config_live)
        self._settings_win.set_restart_callback(self._restart)
        self._menubar.set_handlers(self._on_reuse, self._settings_win.show)
        self._menubar.update_history(self._history.recent())
        self._speaker = self._make_speaker(config)
        self._triggers = TriggerManager(self)
        return self

    @objc.python_method
    def _apply_config_live(self):
        """Apply the just-saved settings without a restart — but only the parts that
        are cheap to rebuild. The LLM client, per-prompt models, the TTS voice and
        the concurrent toggle are swapped live. Triggers (event tap) and the STT
        model still need a restart (re-registering the tap / reloading Whisper)."""
        try:
            cfg = Config.load()
        except Exception as exc:  # noqa: BLE001
            log.warning("live-apply: could not reload config: %s", exc)
            return
        self._config = cfg
        self._concurrent = bool(getattr(cfg, "concurrent", False))
        self._llm = LLMClient(cfg.llm, cfg.sector_models)
        self._pipeline = Pipeline(self._stt, self._llm, self._clipboard, cfg)
        self._speaker = self._make_speaker(cfg)
        log.info("settings applied live (LLM / per-prompt models / voice / concurrent)")

    @objc.python_method
    def _make_speaker(self, config):
        """Pick the TTS backend: 'piper' (local neural) or 'system' (macOS voices)."""
        try:
            if config.tts.backend == "piper":
                from ...core.piper_tts import PiperSpeaker

                return PiperSpeaker(config.tts.piper_voice, app_support_dir() / "piper")
            return Speaker(config.tts.voice)
        except Exception as exc:  # noqa: BLE001
            log.warning("TTS unavailable: %s", exc)
            return None

    # -- lifecycle ------------------------------------------------------------

    def start(self):
        self._menubar.set_ready(False)  # red until warm-up completes and the trigger is up
        # Each trigger can have several bindings (e.g. a mouse button AND a keyboard
        # combo) — all live at once. Expand them into individual (hotkey, sel) entries.
        triggers = [(hk, "onPress:", "onRelease:") for hk in self._config.hotkeys]
        if self._config.tts.enabled and self._speaker is not None:
            triggers += [(hk, "onTts:", None) for hk in self._config.tts.hotkeys]
        self._triggers_ok = self._triggers.start(triggers)
        if not self._triggers_ok:
            print("⚠️  Нет доступа Accessibility — триггер не сработает (см. выше).", flush=True)
        threading.Thread(target=self._warm_up, daemon=True).start()
        # Liveness heartbeat — a main-thread timer touches a file every second. If the
        # main thread hangs (a freeze), the file goes stale and the run.sh supervisor
        # kills + restarts the app (#48).
        self._heartbeat_path = app_support_dir() / "heartbeat"
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "heartbeat:", None, True
        )
        hk = self._config.hotkeys[0] if self._config.hotkeys else None
        trigger_desc = f"{hk.kind}:{hk.key}" if hk else "—"
        print(_tr("ready_msg", self._lang).format(trigger_desc), flush=True)

    def heartbeat_(self, _timer):  # noqa: N802
        try:
            self._heartbeat_path.write_text(str(int(time.time())))
        except Exception as exc:  # noqa: BLE001 - heartbeat must never raise
            log.debug("heartbeat write failed: %s", exc)

    def _warm_up(self):
        try:
            self._stt.warm_up()
            self._llm.warm_up()
            print("STT прогрет, готов к работе.", flush=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("warm-up: %s", exc)
        self._prepare_voice()
        self.performSelectorOnMainThread_withObject_waitUntilDone_("warmReady:", None, False)

    @objc.python_method
    def _prepare_voice(self):
        """Download + load the Piper voice now (first run fetches ~60 MB) so the
        first press isn't delayed. If it can't be prepared (offline), fall back to
        the macOS system voice instead of failing on the first press."""
        speaker = self._speaker
        if not hasattr(speaker, "prepare"):
            return  # the system (macOS) voice needs no preparation
        print("Готовлю голос Piper (при первом запуске скачается ~60 МБ)…", flush=True)
        if speaker.prepare():
            print("Голос Piper готов.", flush=True)
        else:
            print("⚠️  Не удалось подготовить голос Piper — переключаюсь на системный.", flush=True)
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "useSystemVoiceFallback:", None, False
            )

    def useSystemVoiceFallback_(self, _sender):  # noqa: N802
        try:
            self._speaker = Speaker(self._config.tts.voice)
            log.info("TTS fell back to the macOS system voice")
        except Exception as exc:  # noqa: BLE001
            log.warning("system voice fallback failed: %s", exc)
            self._speaker = None

    def warmReady_(self, _sender):  # noqa: N802
        self._menubar.set_ready(self._triggers_ok)  # green only if the trigger is live too

    def onTts_(self, _sender):  # noqa: N802
        if self._speaker is None:
            return
        if self._speaker.is_speaking():
            self._speaker.stop()
            print("TTS: stopped", flush=True)
            return
        if self._tts_capturing:
            return  # a selection grab is already in flight
        self._tts_capturing = True
        # Grab the selection off the main thread (it posts ⌘C and polls), then
        # hop back to the main thread to actually speak.
        threading.Thread(target=self._capture_and_speak, daemon=True).start()

    @objc.python_method
    def _capture_and_speak(self):
        """Worker thread: speak the current selection if any, else the clipboard."""
        text = ""
        try:
            selection = self._clipboard.read_selection()
            text = selection if selection else (self._clipboard.read_text() or "")
        except Exception as exc:  # noqa: BLE001 - never leave _tts_capturing stuck
            log.warning("selection capture failed: %s", exc)
        self.performSelectorOnMainThread_withObject_waitUntilDone_("speakText:", text, False)

    def speakText_(self, text):  # noqa: N802
        self._tts_capturing = False
        state = self._speaker.toggle(str(text))
        print(f"TTS: {state}", flush=True)

    @objc.python_method
    def _on_reuse(self, text):
        """Re-copy a past result from the History submenu."""
        self._clipboard.write_text(text)
        print("✅ скопировано из истории", flush=True)

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
        # Stop any clipboard read-aloud first: recording while TTS holds the audio
        # device used to stall mic startup on the main thread, leaving the wheel
        # frozen (visible but not tracking the cursor). Freeing the device avoids
        # that — and you don't want it reading aloud while you dictate anyway.
        if self._speaker is not None:
            self._speaker.stop()
        self._wheel.hide()
        if not self._concurrent:
            self._spinner.stop()
            self._jobs.reset()
        self._jobs.bump_generation()
        self._recording = True
        loc = NSEvent.mouseLocation()  # bottom-left origin (for the panel)
        # Bring up the wheel AND start cursor tracking before touching audio, so the
        # UI is responsive immediately and never depends on mic startup succeeding.
        self._wheel.show_at(loc.x, loc.y)
        self._tick_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 60.0, self, "onTick:", None, True
        )
        print("● запись… (двигай мышь к сектору, отпусти для обработки)", flush=True)
        try:
            self._recorder.start()
        except Exception as exc:  # noqa: BLE001 - mic busy/unavailable must not freeze the UI
            log.warning("recorder start failed: %s", exc)
        self._llm.prewarm()  # boot the LLM now so it hides behind recording time

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
            print("✕ отменено (курсор за колесом)", flush=True)
            return
        if raw.size < MIN_RECORDING_SEC * self._recorder.sample_rate:
            # An accidental tap (press+release with no real speech) — skip quietly
            # instead of spinning up STT and flashing a scary red "empty" ping.
            self._llm.discard_prewarm()
            print("· слишком коротко — пропускаю", flush=True)
            return
        audio = trim_silence(raw)
        print(f"○ стоп → обработка ({ring}/{sector or 'центр'})…", flush=True)
        token = self._jobs.begin()
        self._spinner.start()  # idempotent; keeps spinning while any job runs
        threading.Thread(
            target=self._process, args=(audio, ring, sector, gen, token), daemon=True
        ).start()

    def finishProcessing_(self, _sender):  # noqa: N802
        payload = self._jobs.pop_result()
        if payload is None:
            return
        color, note, token = payload
        if self._jobs.finish(token) == 0:  # only stop once THIS cycle's jobs are done
            self._spinner.stop()
        if not color:
            return  # cancelled / stale — no ping
        m = NSEvent.mouseLocation()  # ping where the cursor IS now
        self._pulse.pulse_at(m.x, m.y, color)
        print(note, flush=True)
        self._menubar.update_history(self._history.recent())

    # -- worker thread --------------------------------------------------------

    @objc.python_method
    def _process(self, audio, ring, sector, gen, token):
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
        self._jobs.push_result((color, note, token))
        self.performSelectorOnMainThread_withObject_waitUntilDone_("finishProcessing:", None, False)

    # -- shutdown -------------------------------------------------------------

    @objc.python_method
    def _cleanup(self):
        """Kill everything we spawned so nothing is left running after we exit or
        crash: the pre-warmed `claude` subprocess and any audio playback. Safe to
        call more than once."""
        try:
            self._llm.discard_prewarm()
        except Exception as exc:  # noqa: BLE001
            log.debug("cleanup (llm): %s", exc)
        try:
            if self._speaker is not None:
                self._speaker.stop()
        except Exception as exc:  # noqa: BLE001
            log.debug("cleanup (speaker): %s", exc)
        try:
            import sounddevice as sd

            sd.stop()
        except Exception as exc:  # noqa: BLE001
            log.debug("cleanup (audio): %s", exc)

    @objc.python_method
    def _restart(self):
        """Relaunch the app in place so changes that can't be swapped live (language,
        triggers, STT model) take effect without the user quitting by hand. Clean up
        what we spawned, drop the heartbeat so the supervisor doesn't see it go stale
        during the swap, then re-exec — same PID, grants intact.

        The package isn't pip-installed (it runs from ``src``). The project path
        contains a colon, so we can't put ``src`` on PYTHONPATH (Python splits it on
        ``os.pathsep`` == ":"). Instead we re-exec via ``-c`` that injects ``src`` onto
        ``sys.path`` as a plain string and runs the module with runpy — colon-safe and
        independent of cwd / how we were launched."""
        import sys

        from ...core.config import _project_root

        log.info("restarting to apply settings (language / triggers / STT)")
        try:
            self._cleanup()
        except Exception as exc:  # noqa: BLE001
            log.debug("restart cleanup: %s", exc)
        try:
            self._heartbeat_path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            log.debug("restart heartbeat unlink: %s", exc)
        src = str(_project_root() / "src")
        code = (
            "import sys, runpy; "
            f"sys.path.insert(0, {src!r}); "
            "runpy.run_module('voice_wheel', run_name='__main__')"
        )
        try:
            os.execv(sys.executable, [sys.executable, "-c", code])
        except OSError as exc:  # last-ditch: a clean exit lets the run.sh supervisor relaunch
            log.warning("re-exec failed (%s); exiting for the supervisor to restart", exc)
            os._exit(1)

    def applicationWillTerminate_(self, _notif):  # noqa: N802
        self._cleanup()


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
    app.setDelegate_(controller)            # applicationWillTerminate_ -> cleanup (menu Quit)
    atexit.register(controller._cleanup)    # normal interpreter exit / unhandled crash
    controller.start()
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
