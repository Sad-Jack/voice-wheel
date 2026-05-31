"""Settings window (NSWindow) — edit config.json from a GUI instead of by hand.

Opened from the menu-bar. The app is an accessory (no Dock icon); while the
settings window is open we switch to a regular activation policy so it can take
focus, and switch back when it closes. Save writes config.json (other keys, like
sector_models, are preserved); changes apply on the next app restart.

Layout is grouped into labelled sections (LLM / STT / Voice / Triggers / Other),
backends are shown with human-readable labels (not raw config values), and the
model field that doesn't apply to the chosen LLM backend is hidden.
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

# (human label, config value) — the LLM backend picker shows the label, stores the value.
LLM_BACKENDS = [
    ("Локально — Ollama (бесплатно, без ключа)", "ollama"),
    ("Claude Max (подписка)", "claude_warm"),
    ("Claude API (нужен ключ)", "anthropic"),
    ("Claude CLI", "claude_cli"),
]
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
W = 500
H = 720


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
    def _build(self):  # noqa: C901 - flat UI construction, easier read top-to-bottom
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
        cur = [H - 36]  # y cursor, top-down

        def text(s, x, w, size, bold=False, color=None):
            f = NSTextField.labelWithString_(s)
            f.setFrame_(NSMakeRect(x, cur[0], w, 20))
            f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
            if color is not None:
                f.setTextColor_(color)
            content.addSubview_(f)
            return f

        def header(s):
            cur[0] -= 30
            text(s, 20, W - 40, 13, bold=True)
            cur[0] -= 4

        def hint(s):
            cur[0] -= 17
            text(s, 40, W - 60, 10, color=NSColor.secondaryLabelColor())

        def rowlabel(s, x=40, w=150):
            return text(s, x, w, 12)

        def popup(items, x=200, w=270):
            p = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(x, cur[0] - 3, w, 26), False)
            p.addItemsWithTitles_(items)
            content.addSubview_(p)
            return p

        def field(x=200, w=270):
            t = NSTextField.alloc().initWithFrame_(NSMakeRect(x, cur[0] - 2, w, 24))
            content.addSubview_(t)
            return t

        def checkbox(s, x=40):
            b = NSButton.checkboxWithTitle_target_action_(s, None, None)
            b.setFrame_(NSMakeRect(x, cur[0] - 2, W - 80, 22))
            content.addSubview_(b)
            return b

        def gap(px=34):
            cur[0] -= px

        text("Настройки", 20, 300, 17, bold=True)

        header("🧠 Обработка речи (LLM)")
        rowlabel("Движок")
        self._backend = popup([lbl for lbl, _ in LLM_BACKENDS])
        self._backend.setTarget_(self)
        self._backend.setAction_("llmBackendChanged:")
        hint("Что превращает распознанную речь в результат под промпт сектора.")
        gap()
        # The two model fields share one slot — only the relevant one is shown.
        self._ollama_label = rowlabel("Модель Ollama")
        self._ollama = field()
        self._claude_label = rowlabel("Модель Claude")
        self._claude = field()
        gap()

        header("🎙 Распознавание (речь → текст)")
        rowlabel("Движок")
        self._stt_backend = popup(STT_BACKENDS)
        gap()
        rowlabel("Модель")
        self._stt_model = field()
        hint("tiny / base / small / medium — точность ↔ скорость. small — оптимум для русского.")
        gap()
        rowlabel("Язык")
        self._lang = popup(LANGS)
        gap()

        header("🔊 Голос (озвучка)")
        rowlabel("Голос")
        self._tts_voice = popup([v[0] for v in TTS_VOICES])
        gap()
        prem = NSButton.buttonWithTitle_target_action_(
            "macOS: скачать премиум-голоса…", self, "downloadPremium:"
        )
        prem.setFrame_(NSMakeRect(200, cur[0] - 2, 270, 24))
        content.addSubview_(prem)
        gap(32)
        self._tts_enabled = checkbox("Озвучка включена")
        gap(30)

        header("⌨️ Триггеры")
        rowlabel("Колесо записи")
        self._wheel_kind = popup(KINDS, x=200, w=140)
        self._wheel_key = field(x=350, w=120)
        gap()
        rowlabel("Озвучка")
        self._tts_kind = popup(KINDS, x=200, w=140)
        self._tts_key = field(x=350, w=120)
        hint("вид + кнопка/клавиша: mouse_side + 3 или 4, либо keyboard + f8, либо mouse + left.")
        gap()

        header("⚙️ Прочее")
        self._concurrent = checkbox("Запись во время обработки (concurrent)")
        gap(30)

        self._note = text("", 20, W - 40, 11, color=NSColor.secondaryLabelColor())

        save = NSButton.buttonWithTitle_target_action_("Сохранить", self, "save:")
        save.setFrame_(NSMakeRect(W - 140, 16, 120, 30))
        content.addSubview_(save)

        self._window = win
        self._apply_llm_visibility("ollama")  # _load re-applies with the saved value

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
        backend = llm.get("backend", "ollama")
        self._backend.selectItemWithTitle_(self._llm_label(backend))
        self._apply_llm_visibility(backend)
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
        data["llm"]["backend"] = self._llm_value(str(self._backend.titleOfSelectedItem()))
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

    # -- LLM backend helpers --------------------------------------------------

    @objc.python_method
    def _llm_label(self, value: str) -> str:
        for lbl, v in LLM_BACKENDS:
            if v == value:
                return lbl
        return LLM_BACKENDS[0][0]

    @objc.python_method
    def _llm_value(self, label: str) -> str:
        for lbl, v in LLM_BACKENDS:
            if lbl == label:
                return v
        return "ollama"

    @objc.python_method
    def _apply_llm_visibility(self, backend: str):
        """Show only the model field that applies to the chosen backend."""
        is_ollama = backend == "ollama"
        self._ollama_label.setHidden_(not is_ollama)
        self._ollama.setHidden_(not is_ollama)
        self._claude_label.setHidden_(is_ollama)
        self._claude.setHidden_(is_ollama)

    def llmBackendChanged_(self, _sender):  # noqa: N802
        self._apply_llm_visibility(self._llm_value(str(self._backend.titleOfSelectedItem())))

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
