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
from pynput import keyboard, mouse

from .clipboard import Clipboard
from .config import Config, HotkeyConfig, app_support_dir
from .history import History
from .llm import LLMClient
from .pulse import PulseOverlay
from .recorder import Recorder, trim_silence
from .stt import STTEngine
from .pipeline import Pipeline
from .wheel_overlay import WheelOverlay

log = logging.getLogger(__name__)


class VoiceWheel(NSObject):
    # -- construction ---------------------------------------------------------

    def initWithConfig_(self, config):  # noqa: N802
        self = objc.super(VoiceWheel, self).init()
        if self is None:
            return None
        self._config = config
        self._busy = False
        self._tick_timer = None
        self._pending = None

        self._clipboard = Clipboard()
        self._history = History(
            app_support_dir() / "history.sqlite", limit=config.history_limit
        )
        self._recorder = Recorder()
        stt = STTEngine(config.stt)
        llm = LLMClient(config.llm)
        self._pipeline = Pipeline(stt, llm, self._clipboard, config)
        self._stt = stt
        self._llm = llm

        self._wheel = WheelOverlay()
        self._pulse = PulseOverlay()
        self._mouse_ctrl = mouse.Controller()
        self._listener = None
        self._tap = None
        return self

    # -- lifecycle ------------------------------------------------------------

    def start(self):
        self._start_listener()
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

    def _start_listener(self):
        cfg: HotkeyConfig = self._config.hotkey

        # Side mouse buttons (back/forward) are invisible to pynput on macOS;
        # use a Quartz event tap. Its callback runs on the main thread already.
        if cfg.kind == "mouse_side":
            from .mouse_tap import SIDE_BUTTONS, SideButtonTap

            key = cfg.key.strip().lower()
            bn = int(key) if key.isdigit() else SIDE_BUTTONS.get(key, 3)
            self._tap = SideButtonTap(
                bn,
                on_press=lambda: self.onPress_(None),
                on_release=lambda: self.onRelease_(None),
                suppress=True,
            )
            self._tap.start()
            return

        held = {"down": False}

        def fire(selector):
            self.performSelectorOnMainThread_withObject_waitUntilDone_(selector, None, False)

        if cfg.kind == "mouse":
            target = _parse_button(cfg.key)

            def on_click(x, y, button, pressed):
                if button != target:
                    return
                if pressed and not held["down"]:
                    held["down"] = True
                    fire("onPress:")
                elif not pressed and held["down"]:
                    held["down"] = False
                    fire("onRelease:")

            self._listener = mouse.Listener(on_click=on_click)
        else:
            target = _parse_key(cfg.key)

            def on_press(key):
                if key == target and not held["down"]:
                    held["down"] = True
                    fire("onPress:")

            def on_release(key):
                if key == target and held["down"]:
                    held["down"] = False
                    fire("onRelease:")

            self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    # -- main-thread slots ----------------------------------------------------

    def onPress_(self, _sender):  # noqa: N802
        if self._busy:
            return
        self._busy = True
        x, y = self._mouse_ctrl.position  # top-left origin
        loc = NSEvent.mouseLocation()  # bottom-left origin (for the panel)
        self._wheel.show_at(loc.x, loc.y)
        self._recorder.start()
        self._llm.prewarm()  # boot the LLM now so it hides behind recording time
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
        if not self._recorder.is_recording:
            self._busy = False
            self._wheel.hide()
            return
        ring, sector = self._wheel.selection()
        self._wheel.hide()
        audio = trim_silence(self._recorder.stop())
        loc = NSEvent.mouseLocation()
        print(f"○ стоп → обработка ({ring}/{sector or 'центр'})…", flush=True)
        threading.Thread(
            target=self._process, args=(audio, ring, sector, (loc.x, loc.y)), daemon=True
        ).start()

    def pulseReady_(self, _sender):  # noqa: N802
        _loc, note = self._pending
        m = NSEvent.mouseLocation()  # pulse where the cursor IS now, not where it was
        self._pulse.pulse_at(m.x, m.y)
        self._busy = False
        print(note, flush=True)

    def errorReady_(self, _sender):  # noqa: N802
        _loc, note = self._pending
        self._busy = False
        print(note, flush=True)

    # -- worker thread --------------------------------------------------------

    @objc.python_method
    def _process(self, audio, ring, sector, loc):
        try:
            result = self._pipeline.run(audio, ring, sector)
            self._llm.discard_prewarm()  # no-op if consumed; kills it if dictate (unused)
            if not result.result.strip():
                self._pending = (loc, "⚠️  Пусто — речь не распознана.")
                self.performSelectorOnMainThread_withObject_waitUntilDone_("errorReady:", None, False)
                return
            self._clipboard.push_current()
            self._clipboard.write_text(result.result)
            self._history.add(result.ring, result.sector, result.transcript, result.result)
            tag = "ТЕКСТ" if result.ring == "dictate" else result.sector.upper()
            if result.llm_skipped:
                tag += " (без LLM: нет API-ключа)"
            preview = result.result.replace("\n", " ")
            note = f"✅ [{tag}] → буфер: {preview[:120]}"
            self._pending = (loc, note)
            self.performSelectorOnMainThread_withObject_waitUntilDone_("pulseReady:", None, False)
        except Exception as exc:  # noqa: BLE001
            log.exception("processing failed")
            self._pending = (loc, f"❌ Ошибка: {exc}")
            self.performSelectorOnMainThread_withObject_waitUntilDone_("errorReady:", None, False)


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
                "⚠️  Нет доступа Accessibility — F8 ловиться не будет.\n"
                "   1) В появившемся диалоге нажми «Открыть настройки».\n"
                "   2) System Settings → Privacy & Security → Accessibility → включи Python.\n"
                "   3) Перезапусти приложение.",
                flush=True,
            )
        return bool(trusted)
    except Exception as exc:  # noqa: BLE001
        log.warning("accessibility check failed: %s", exc)
        return True


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a project-root .env (gitignored) into the env."""
    from .config import _project_root

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
