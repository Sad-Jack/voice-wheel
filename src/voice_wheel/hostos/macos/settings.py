"""Settings window (NSWindow) — edit config.json from a GUI instead of by hand.

Opened from the menu-bar. The app is an accessory (no Dock icon); while the
settings window is open we switch to a regular activation policy so it can take
focus, and switch back when it closes. Save writes config.json (other keys are
preserved); cheap settings apply live, the rest on the next restart.

The window is split into tabs (LLM / Речь / Голос / Триггеры) so it stays short
and the Save button is always visible below the tabs.
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
    NSEvent,
    NSEventMaskKeyDown,
    NSEventMaskOtherMouseDown,
    NSEventMaskRightMouseDown,
    NSEventModifierFlagCommand,
    NSEventModifierFlagControl,
    NSEventModifierFlagOption,
    NSEventModifierFlagShift,
    NSEventTypeKeyDown,
    NSFont,
    NSPopUpButton,
    NSTabView,
    NSTabViewItem,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRect, NSObject

from ...core.config import _project_root
from ...core.modes import sectors

log = logging.getLogger(__name__)


class _FlippedView(NSView):
    """Top-left origin so tab content lays out top-to-bottom regardless of height."""

    def isFlipped(self):  # noqa: N802
        return True


BASE_MODEL_LABEL = "(как базовая)"  # per-prompt override = "no override, use the default LLM"

# macOS keyCodes -> pynput-compatible names for keys that aren't plain characters.
_KEYCODE_NAMES = {
    122: "f1", 120: "f2", 99: "f3", 118: "f4", 96: "f5", 97: "f6",
    98: "f7", 100: "f8", 101: "f9", 109: "f10", 103: "f11", 111: "f12",
    49: "space", 36: "enter", 53: "esc", 48: "tab", 51: "backspace",
    123: "left", 124: "right", 125: "down", 126: "up",
}


def _format_combo(event) -> str | None:
    """An NSKeyDown event -> a config key string like 'cmd+f', 'shift+f8', 'space'."""
    flags = event.modifierFlags()
    mods = []
    if flags & NSEventModifierFlagCommand:
        mods.append("cmd")
    if flags & NSEventModifierFlagControl:
        mods.append("ctrl")
    if flags & NSEventModifierFlagOption:
        mods.append("alt")
    if flags & NSEventModifierFlagShift:
        mods.append("shift")
    main = _KEYCODE_NAMES.get(int(event.keyCode()))
    if main is None:
        chars = str(event.charactersIgnoringModifiers() or "").lower().strip()
        if len(chars) == 1 and chars.isprintable():
            main = chars
    if not main:
        return None
    return "+".join([*mods, main])


def _mouse_kind_key(button_number: int):
    """A pressed mouse button -> (kind, key) for the config. 1=right, 2=middle, 3+=side."""
    if button_number == 1:
        return "mouse", "right"
    if button_number == 2:
        return "mouse", "middle"
    if button_number >= 3:
        return "mouse_side", str(button_number)
    return None, None


def _capture_kind_key(event):
    """Decode a captured NSEvent into (kind, key). 'cancel' on Escape; (None, None)
    if unrecognized (keep waiting)."""
    if event.type() == NSEventTypeKeyDown:
        if int(event.keyCode()) == 53:   # Escape -> cancel capture
            return "cancel", None
        combo = _format_combo(event)
        return ("keyboard", combo) if combo else (None, None)
    return _mouse_kind_key(int(event.buttonNumber()))


# (human label, config value) — the LLM backend picker shows the label, stores the value.
LLM_BACKENDS = [
    ("Локально — Ollama (бесплатно, без ключа)", "ollama"),
    ("Claude Max (подписка)", "claude_warm"),
    ("Claude API (нужен ключ)", "anthropic"),
    ("Claude CLI", "claude_cli"),
]
STT_BACKENDS = ["auto", "mlx", "faster-whisper"]
STT_MODELS = ["tiny", "base", "small", "medium", "large"]
LANGS = ["auto", "ru", "en"]
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
W = 520
H = 440


class SettingsWindow(NSObject):
    def init(self):
        self = objc.super(SettingsWindow, self).init()
        if self is not None:
            self._window = None
            self._preview_speaker = None  # plays a sample when the voice changes
            self._sector_overrides = {}   # sector_key -> {backend, model}; per-prompt model
            self._editing_sector = None   # which prompt's override is currently in the fields
            self._apply_cb = None         # controller hook to apply cheap settings live
            self._capture_monitor = None  # active NSEvent monitor while catching a key
        return self

    @objc.python_method
    def set_apply_callback(self, cb):
        self._apply_cb = cb

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
        root = win.contentView()

        tabs = NSTabView.alloc().initWithFrame_(NSMakeRect(10, 48, W - 20, H - 58))
        root.addSubview_(tabs)

        view = [None]   # the current tab's content view
        cur = [14]      # y cursor inside that view (flipped: grows downward)

        def add_tab(label):
            v = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, W - 28, H - 96))
            item = NSTabViewItem.alloc().initWithIdentifier_(label)
            item.setLabel_(label)
            item.setView_(v)
            tabs.addTabViewItem_(item)
            view[0] = v
            cur[0] = 14

        def text(s, x, w, size, bold=False, color=None):
            f = NSTextField.labelWithString_(s)
            f.setFrame_(NSMakeRect(x, cur[0], w, 20))
            f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
            if color is not None:
                f.setTextColor_(color)
            view[0].addSubview_(f)
            return f

        def header(s):
            text(s, 12, W - 52, 13, bold=True)
            cur[0] += 28

        def hint(s):
            cur[0] += 20
            text(s, 34, W - 72, 10, color=NSColor.secondaryLabelColor())
            cur[0] += 4

        def rowlabel(s, x=34, w=150):
            return text(s, x, w, 12)

        def popup(items, x=190, w=290):
            p = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(x, cur[0] - 3, w, 26), False)
            p.addItemsWithTitles_(items)
            view[0].addSubview_(p)
            return p

        def field(x=190, w=290):
            t = NSTextField.alloc().initWithFrame_(NSMakeRect(x, cur[0] - 2, w, 24))
            view[0].addSubview_(t)
            return t

        def checkbox(s, x=34):
            b = NSButton.checkboxWithTitle_target_action_(s, None, None)
            b.setFrame_(NSMakeRect(x, cur[0] - 2, W - 96, 22))
            view[0].addSubview_(b)
            return b

        def btn(title, action, x, w):
            b = NSButton.buttonWithTitle_target_action_(title, self, action)
            b.setFrame_(NSMakeRect(x, cur[0] - 2, w, 24))
            view[0].addSubview_(b)
            return b

        def gap(px=34):
            cur[0] += px

        # ---- LLM tab ----
        add_tab("LLM")
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
        header("🎛 Модель на промпт (опц.)")
        self._sectors = list(sectors())
        rowlabel("Промпт")
        self._prompt = popup([s.label for s in self._sectors])
        self._prompt.setTarget_(self)
        self._prompt.setAction_("promptChanged:")
        gap()
        rowlabel("Модель")
        self._sec_backend = popup([BASE_MODEL_LABEL] + [lbl for lbl, _ in LLM_BACKENDS], x=190, w=160)
        self._sec_model = field(x=358, w=124)
        hint("«(как базовая)» = движок/модель из «Обработка речи». Иначе — свои для промпта.")

        # ---- Speech (STT) tab ----
        add_tab("Речь")
        header("🎙 Распознавание (речь → текст)")
        rowlabel("Движок")
        self._stt_backend = popup(STT_BACKENDS)
        hint("Чем распознаём речь. auto: mlx на Apple Silicon, иначе faster-whisper (можно не трогать).")
        gap()
        rowlabel("Модель")
        self._stt_model = popup(STT_MODELS)
        hint("tiny → быстро/грубо · medium/large → точно/медленно. small — оптимум для русского.")
        gap()
        rowlabel("Язык")
        self._lang = popup(LANGS)
        hint("auto — определять язык по речи. Или зафиксируй ru/en для точности.")

        # ---- Voice (TTS) tab ----
        add_tab("Голос")
        header("🔊 Голос (озвучка)")
        self._tts_enabled = checkbox("Озвучка включена")
        self._tts_enabled.setTarget_(self)
        self._tts_enabled.setAction_("ttsEnabledChanged:")
        gap(30)
        rowlabel("Голос")
        self._tts_voice = popup([v[0] for v in TTS_VOICES])
        self._tts_voice.setTarget_(self)
        self._tts_voice.setAction_("ttsVoiceChanged:")  # play a sample on change
        gap()
        self._prem = btn("macOS: скачать премиум-голоса…", "downloadPremium:", 190, 290)
        gap()
        rowlabel("Кнопка озвучки")
        self._tts_kind = popup(KINDS, x=190, w=105)
        self._tts_key = field(x=300, w=82)
        btn("Поймать", "captureTts:", 388, 100)
        hint("вид + кнопка/клавиша, или «Поймать» → нажми нужную.")

        # ---- Triggers tab ----
        add_tab("Триггеры")
        header("⌨️ Триггер записи (колесо)")
        rowlabel("Кнопка")
        self._wheel_kind = popup(KINDS, x=190, w=105)
        self._wheel_key = field(x=300, w=82)
        btn("Поймать", "captureWheel:", 388, 100)
        hint("вид + кнопка/клавиша, или «Поймать» → нажми нужную (комбо вроде ⌘F тоже).")
        gap()
        header("⚙️ Прочее")
        self._concurrent = checkbox("Запись во время обработки (concurrent)")

        # ---- Save + note (always visible, below the tabs) ----
        self._note = NSTextField.labelWithString_("")
        self._note.setFrame_(NSMakeRect(16, 15, W - 160, 18))
        self._note.setFont_(NSFont.systemFontOfSize_(11))
        self._note.setTextColor_(NSColor.secondaryLabelColor())
        root.addSubview_(self._note)

        save = NSButton.buttonWithTitle_target_action_("Сохранить", self, "save:")
        save.setFrame_(NSMakeRect(W - 130, 12, 116, 30))
        root.addSubview_(save)

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
        self._stt_model.selectItemWithTitle_(str(stt.get("model", "small")))
        self._lang.selectItemWithTitle_(data.get("language", "ru"))
        self._wheel_kind.selectItemWithTitle_(hk.get("kind", "mouse_side"))
        self._wheel_key.setStringValue_(str(hk.get("key", "3")))
        self._tts_kind.selectItemWithTitle_(tts_hk.get("kind", "mouse_side"))
        self._tts_key.setStringValue_(str(tts_hk.get("key", "4")))
        self._tts_voice.selectItemWithTitle_(self._voice_label(tts))
        self._tts_enabled.setState_(1 if tts.get("enabled", True) else 0)
        self._apply_tts_enabled()
        self._concurrent.setState_(1 if data.get("concurrent", False) else 0)
        self._sector_overrides = {
            k: v for k, v in (data.get("sector_models") or {}).items()
            if isinstance(v, dict)  # skip the "_comment" string
        }
        self._editing_sector = None
        if self._sectors:
            self._prompt.selectItemAtIndex_(0)
        self._load_selected_override()
        self._note.setStringValue_("")

    def save_(self, _sender):  # noqa: N802
        data = self._read()
        data.setdefault("llm", {})
        data["llm"]["backend"] = self._llm_value(str(self._backend.titleOfSelectedItem()))
        data["llm"]["ollama_model"] = str(self._ollama.stringValue())
        data["llm"]["model"] = str(self._claude.stringValue())
        data.setdefault("stt", {})
        data["stt"]["backend"] = str(self._stt_backend.titleOfSelectedItem())
        data["stt"]["model"] = str(self._stt_model.titleOfSelectedItem())
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
        # per-prompt model overrides (capture the prompt currently shown first)
        self._save_current_override()
        existing = data.get("sector_models")
        sm = dict(self._sector_overrides)
        if isinstance(existing, dict) and "_comment" in existing:
            sm["_comment"] = existing["_comment"]
        data["sector_models"] = sm
        try:
            self._path().write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:  # disk/permissions — tell the user, don't throw into ObjC
            log.warning("could not write %s: %s", self._path(), exc)
            self._note.setStringValue_(f"⚠️ Не удалось сохранить: {exc}")
            return
        applied = False
        if self._apply_cb is not None:
            try:
                self._apply_cb()
                applied = True
            except Exception as exc:  # noqa: BLE001 - never let live-apply break Save
                log.warning("live-apply failed: %s", exc)
        if applied:
            self._note.setStringValue_(
                "Сохранено и применено: голос, LLM/модели, concurrent. "
                "Триггеры и STT-модель — после перезапуска."
            )
        else:
            self._note.setStringValue_("Сохранено. Перезапусти приложение (меню-бар → Выход).")
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

    # -- per-prompt model override -------------------------------------------

    @objc.python_method
    def _sector_key_for_label(self, label: str):
        return next((s.key for s in self._sectors if s.label == label), None)

    @objc.python_method
    def _save_current_override(self):
        """Persist the fields into the in-memory map for the prompt being edited."""
        key = self._editing_sector
        if not key:
            return
        backend_label = str(self._sec_backend.titleOfSelectedItem())
        if backend_label == BASE_MODEL_LABEL:
            self._sector_overrides.pop(key, None)  # no override -> use the default LLM
        else:
            self._sector_overrides[key] = {
                "backend": self._llm_value(backend_label),
                "model": str(self._sec_model.stringValue()).strip(),
            }

    @objc.python_method
    def _load_selected_override(self):
        """Load the selected prompt's override (or 'base') into the fields."""
        key = self._sector_key_for_label(str(self._prompt.titleOfSelectedItem()))
        self._editing_sector = key
        override = self._sector_overrides.get(key) if key else None
        if override:
            self._sec_backend.selectItemWithTitle_(self._llm_label(override.get("backend", "ollama")))
            self._sec_model.setStringValue_(str(override.get("model", "")))
        else:
            self._sec_backend.selectItemWithTitle_(BASE_MODEL_LABEL)
            self._sec_model.setStringValue_("")

    def promptChanged_(self, _sender):  # noqa: N802
        self._save_current_override()    # keep edits for the prompt we're leaving
        self._load_selected_override()   # show the newly-selected prompt's override

    @objc.python_method
    def _apply_tts_enabled(self):
        """Disable the voice + read-aloud-button controls when TTS is off."""
        on = bool(self._tts_enabled.state())
        for ctl in (self._tts_voice, self._prem, self._tts_kind, self._tts_key):
            ctl.setEnabled_(on)

    def ttsEnabledChanged_(self, _sender):  # noqa: N802
        self._apply_tts_enabled()

    # -- key capture ("Поймать") ---------------------------------------------

    def captureWheel_(self, _sender):  # noqa: N802
        self._begin_capture(self._wheel_kind, self._wheel_key, _sender)

    def captureTts_(self, _sender):  # noqa: N802
        self._begin_capture(self._tts_kind, self._tts_key, _sender)

    @objc.python_method
    def _begin_capture(self, kind_popup, key_field, button):
        """Catch the next key/combo OR mouse button and write it into the trigger
        fields. (A side button already bound to a trigger is swallowed by our event
        tap and can't be caught here — press Esc to cancel and type it instead.)"""
        if self._capture_monitor is not None:
            return  # already catching
        old_title = str(button.title())
        button.setTitle_("нажми…")
        self._note.setStringValue_("Нажми клавишу/комбо или кнопку мыши (Esc — отмена)…")
        mask = NSEventMaskKeyDown | NSEventMaskOtherMouseDown | NSEventMaskRightMouseDown

        def handler(event):
            kind, key = _capture_kind_key(event)
            if kind is None:
                return None  # unrecognized — keep waiting
            if kind != "cancel":
                kind_popup.selectItemWithTitle_(kind)
                key_field.setStringValue_(key)
                self._note.setStringValue_(f"Поймал: {kind} / {key}. Нажми «Сохранить».")
            if self._capture_monitor is not None:
                NSEvent.removeMonitor_(self._capture_monitor)
                self._capture_monitor = None
            button.setTitle_(old_title)
            return None  # swallow so the press doesn't hit a control

        self._capture_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask, handler
        )

    def ttsVoiceChanged_(self, _sender):  # noqa: N802
        self._preview_voice()

    @objc.python_method
    def _preview_voice(self):
        """Speak a short sample with the just-selected voice so you can hear it."""
        backend, piper_voice = self._selected_voice()
        try:
            if self._preview_speaker is not None:
                self._preview_speaker.stop()  # cut off the previous sample
            if backend == "piper":
                from ...core.config import app_support_dir
                from ...core.piper_tts import PiperSpeaker

                cache = app_support_dir() / "piper"
                if not (cache / f"{piper_voice}.onnx").exists():
                    self._note.setStringValue_("Скачиваю голос для прослушивания…")
                self._preview_speaker = PiperSpeaker(piper_voice, cache)
            else:
                from .tts import Speaker

                self._preview_speaker = Speaker("")  # macOS, best for the language
            self._preview_speaker.toggle("Привет! Это пример выбранного голоса.")
        except Exception as exc:  # noqa: BLE001 - preview must never break the window
            log.warning("voice preview failed: %s", exc)

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
        if self._capture_monitor is not None:
            NSEvent.removeMonitor_(self._capture_monitor)
            self._capture_monitor = None
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
