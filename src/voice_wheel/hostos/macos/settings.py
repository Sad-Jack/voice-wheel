"""Settings window (NSWindow) — edit config.json from a GUI instead of by hand.

Opened from the menu-bar. The app is an accessory (no Dock icon); while the
settings window is open we switch to a regular activation policy so it can take
focus, and switch back when it closes. Save writes config.json (other keys, like
sector_models, are preserved); changes apply on the next app restart.
"""

from __future__ import annotations

import json
import logging
import threading

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSButton,
    NSColor,
    NSFont,
    NSPopUpButton,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRect, NSObject

from ...core.config import _project_root

log = logging.getLogger(__name__)

BACKENDS = ["ollama", "claude_warm", "anthropic", "claude_cli"]
STT_BACKENDS = ["auto", "mlx", "faster-whisper"]
LANGS = ["ru", "en", "auto"]
KINDS = ["mouse_side", "keyboard", "mouse"]
# TTS voice picker: (label, backend, piper_voice). "system" = macOS voices (auto-picks
# the best installed quality); "piper" = local neural, auto-downloaded on save/first use.
TTS_VOICES = [
    ("macOS (системный голос)", "system", ""),
    ("Piper: Irina — нейро (RU, жен.)", "piper", "ru_RU-irina-medium"),
    ("Piper: Денис — нейро (RU, муж.)", "piper", "ru_RU-denis-medium"),
    ("Piper: Руслан — нейро (RU, муж.)", "piper", "ru_RU-ruslan-medium"),
    ("Piper: Дмитрий — нейро (RU, муж.)", "piper", "ru_RU-dmitri-medium"),
]
W = 480
H = 700


class SettingsWindow(NSObject):
    def init(self):
        self = objc.super(SettingsWindow, self).init()
        if self is not None:
            self._window = None
        return self

    # -- public ---------------------------------------------------------------

    @objc.python_method
    def show(self):
        self._build()
        self._load()
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
        self._window.center()
        self._window.makeKeyAndOrderFront_(None)

    # -- build ----------------------------------------------------------------

    @objc.python_method
    def _build(self):
        if self._window is not None:
            return
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("Voice Wheel — Настройки")
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self)
        content = win.contentView()

        def label(text, yy, x=24, w=150, size=12, bold=False):
            f = NSTextField.labelWithString_(text)
            f.setFrame_(NSMakeRect(x, yy, w, 20))
            f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
            content.addSubview_(f)
            return f

        def popup(items, yy, x=180, w=270):
            p = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(x, yy - 3, w, 26), False)
            p.addItemsWithTitles_(items)
            content.addSubview_(p)
            return p

        def field(yy, x=180, w=270):
            t = NSTextField.alloc().initWithFrame_(NSMakeRect(x, yy - 2, w, 24))
            content.addSubview_(t)
            return t

        def checkbox(text, yy, x=180):
            b = NSButton.checkboxWithTitle_target_action_(text, None, None)
            b.setFrame_(NSMakeRect(x, yy - 2, 270, 22))
            content.addSubview_(b)
            return b

        y = H - 42
        label("Настройки", y, x=24, w=300, size=17, bold=True)
        y -= 42
        label("LLM backend", y); self._backend = popup(BACKENDS, y); y -= 38
        label("Ollama модель", y); self._ollama = field(y); y -= 38
        label("Claude модель", y); self._claude = field(y); y -= 38
        label("STT движок", y); self._stt_backend = popup(STT_BACKENDS, y); y -= 38
        label("STT модель", y); self._stt_model = field(y); y -= 38
        label("Язык", y); self._lang = popup(LANGS, y); y -= 42
        label("Триггер колеса", y)
        self._wheel_kind = popup(KINDS, y, x=180, w=140)
        self._wheel_key = field(y, x=330, w=120)
        y -= 38
        label("Триггер озвучки", y)
        self._tts_kind = popup(KINDS, y, x=180, w=140)
        self._tts_key = field(y, x=330, w=120)
        y -= 38
        label("Голос (TTS)", y)
        self._tts_voice = popup([v[0] for v in TTS_VOICES], y)
        y -= 34
        prem = NSButton.buttonWithTitle_target_action_(
            "macOS: скачать премиум-голоса…", self, "downloadPremium:"
        )
        prem.setFrame_(NSMakeRect(180, y - 2, 270, 24))
        content.addSubview_(prem)
        y -= 38
        self._tts_enabled = checkbox("Озвучка включена", y); y -= 30
        self._concurrent = checkbox("Запись во время обработки", y); y -= 40

        self._note = label("", y, x=24, w=W - 48, size=11)
        self._note.setTextColor_(NSColor.secondaryLabelColor())

        save = NSButton.buttonWithTitle_target_action_("Сохранить", self, "save:")
        save.setFrame_(NSMakeRect(W - 140, 16, 120, 30))
        content.addSubview_(save)

        self._window = win

    # -- load / save ----------------------------------------------------------

    @objc.python_method
    def _path(self):
        return _project_root() / "config.json"

    @objc.python_method
    def _read(self):
        try:
            return json.loads(self._path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}  # no config yet — start from defaults, silently
        except (ValueError, OSError) as exc:  # malformed/unreadable: warn, don't crash the UI
            log.warning("could not read %s: %s", self._path(), exc)
            return {}

    @objc.python_method
    def _load(self):
        data = self._read()
        llm = data.get("llm", {})
        hk = data.get("hotkey", {})
        tts = data.get("tts", {})
        tts_hk = tts.get("hotkey", {})
        self._backend.selectItemWithTitle_(llm.get("backend", "ollama"))
        self._ollama.setStringValue_(str(llm.get("ollama_model", "qwen2.5:7b")))
        self._claude.setStringValue_(str(llm.get("model", "claude-haiku-4-5")))
        stt = data.get("stt", {})
        self._stt_backend.selectItemWithTitle_(stt.get("backend", "auto"))
        self._stt_model.setStringValue_(str(stt.get("model", "small")))
        self._lang.selectItemWithTitle_(data.get("language", "ru"))
        self._wheel_kind.selectItemWithTitle_(hk.get("kind", "mouse_side"))
        self._wheel_key.setStringValue_(str(hk.get("key", "3")))
        self._tts_kind.selectItemWithTitle_(tts_hk.get("kind", "mouse_side"))
        self._tts_key.setStringValue_(str(tts_hk.get("key", "4")))
        self._tts_voice.selectItemWithTitle_(self._voice_label(tts))
        self._tts_enabled.setState_(1 if tts.get("enabled", True) else 0)
        self._concurrent.setState_(1 if data.get("concurrent", False) else 0)
        self._note.setStringValue_("")

    def save_(self, _sender):  # noqa: N802
        data = self._read()
        data.setdefault("llm", {})
        data["llm"]["backend"] = str(self._backend.titleOfSelectedItem())
        data["llm"]["ollama_model"] = str(self._ollama.stringValue())
        data["llm"]["model"] = str(self._claude.stringValue())
        data.setdefault("stt", {})
        data["stt"]["backend"] = str(self._stt_backend.titleOfSelectedItem())
        data["stt"]["model"] = str(self._stt_model.stringValue())
        data["language"] = str(self._lang.titleOfSelectedItem())
        data["hotkey"] = {
            "kind": str(self._wheel_kind.titleOfSelectedItem()),
            "key": str(self._wheel_key.stringValue()),
        }
        data.setdefault("tts", {})
        data["tts"]["enabled"] = bool(self._tts_enabled.state())
        data["tts"]["hotkey"] = {
            "kind": str(self._tts_kind.titleOfSelectedItem()),
            "key": str(self._tts_key.stringValue()),
        }
        backend, piper_voice = self._selected_voice()
        data["tts"]["backend"] = backend
        if backend == "piper":
            data["tts"]["piper_voice"] = piper_voice
        data["concurrent"] = bool(self._concurrent.state())
        try:
            self._path().write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:  # disk/permissions — tell the user, don't throw into ObjC
            log.warning("could not write %s: %s", self._path(), exc)
            self._note.setStringValue_(f"⚠️ Не удалось сохранить: {exc}")
            return
        self._note.setStringValue_("Сохранено. Перезапусти приложение (меню-бар → Выход, затем ./run.sh).")
        if backend == "piper":
            self._maybe_download_piper(piper_voice)

    # -- TTS voice helpers ----------------------------------------------------

    @objc.python_method
    def _voice_label(self, tts: dict) -> str:
        """Map the saved config back to a dropdown label."""
        backend = tts.get("backend", "system")
        piper_voice = tts.get("piper_voice", "ru_RU-irina-medium")
        for label, b, pv in TTS_VOICES:
            if b == backend and (b != "piper" or pv == piper_voice):
                return label
        return TTS_VOICES[0][0]

    @objc.python_method
    def _selected_voice(self):
        """Map the dropdown selection to (backend, piper_voice)."""
        sel = str(self._tts_voice.titleOfSelectedItem())
        for label, backend, piper_voice in TTS_VOICES:
            if label == sel:
                return backend, piper_voice
        return "system", ""

    @objc.python_method
    def _maybe_download_piper(self, voice_name: str) -> None:
        """Fetch the Piper voice now (in the background) if it isn't cached yet."""
        if not voice_name:
            return
        from ...core.config import app_support_dir

        cache = app_support_dir() / "piper"
        if (cache / f"{voice_name}.onnx").exists():
            return
        self._note.setStringValue_(f"Скачиваю голос «{voice_name}»… применится после перезапуска.")

        def _dl():
            try:
                from piper.download_voices import download_voice

                cache.mkdir(parents=True, exist_ok=True)
                download_voice(voice_name, cache)
                log.info("piper voice %s downloaded", voice_name)
            except Exception as exc:  # noqa: BLE001
                log.warning("piper voice download failed: %s", exc)

        threading.Thread(target=_dl, daemon=True).start()

    def downloadPremium_(self, _sender):  # noqa: N802
        """Open the macOS Spoken Content pane so the user can download a premium voice."""
        from AppKit import NSWorkspace
        from Foundation import NSURL

        url = NSURL.URLWithString_(
            "x-apple.systempreferences:com.apple.preference.universalaccess?SpokenContent"
        )
        NSWorkspace.sharedWorkspace().openURL_(url)
        self._note.setStringValue_(
            "Открыл «Озвучивание»: скачай русский голос (Enhanced/Premium), затем выбери "
            "«macOS» в списке голосов. Применится после перезапуска."
        )

    def windowWillClose_(self, _notif):  # noqa: N802
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
