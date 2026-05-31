"""Settings window (NSWindow) — edit config.json from a GUI instead of by hand.

Opened from the menu-bar. The app is an accessory (no Dock icon); while the
settings window is open we switch to a regular activation policy so it can take
focus, and switch back when it closes. Save writes config.json (other keys are
preserved); cheap settings apply live, the rest on the next restart.

The window is split into tabs (LLM / Речь / Голос / Триггеры / Язык) so it stays
short and the Save button is always visible below the tabs.

Interface language (#43/#53): every chrome string goes through ``T(key)`` which
picks the RU or EN variant from ``STR``. The default follows the system locale;
the «Язык» tab lets you switch, which persists ``ui_language`` and rebuilds the
window in place. Dropdowns whose labels are translated (LLM engines, TTS voices)
map selection by *index*, not title, so a language switch can't break Save.
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
    NSLayoutAttributeCenterY,
    NSLayoutAttributeLeading,
    NSLayoutConstraint,
    NSPopUpButton,
    NSStackView,
    NSTabView,
    NSTabViewItem,
    NSTextField,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSUserInterfaceLayoutOrientationVertical,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSLocale, NSMakeRect, NSObject

from ...core.config import _project_root
from ...core.modes import sectors

log = logging.getLogger(__name__)


class _FlippedView(NSView):
    """Top-left origin so tab content lays out top-to-bottom regardless of height."""

    def isFlipped(self):  # noqa: N802
        return True


# -- interface strings (ru, en) -------------------------------------------------
# Every visible chrome string lives here so the whole window can switch language.
STR = {
    "win_title": ("Voice Wheel — Настройки", "Voice Wheel — Settings"),
    "tab_llm": ("LLM", "LLM"),
    "tab_stt": ("Речь", "Speech"),
    "tab_voice": ("Голос", "Voice"),
    "tab_triggers": ("Триггеры", "Triggers"),
    "tab_lang": ("Язык", "Language"),
    # LLM tab
    "llm_header": ("🧠 Обработка речи (LLM)", "🧠 Speech processing (LLM)"),
    "engine": ("Движок", "Engine"),
    "llm_hint": (
        "Что превращает распознанную речь в результат под промпт сектора.",
        "What turns recognized speech into the result for the sector's prompt.",
    ),
    "ollama_model": ("Модель Ollama", "Ollama model"),
    "claude_model": ("Модель Claude", "Claude model"),
    "rules_header": ("🎛 Модель на промпт — правила (опц.)", "🎛 Per-prompt model — rules (opt.)"),
    "rules_hint": (
        "Базовая (выше) — для всех промптов. Правило задаёт свою модель отдельному.",
        "Base (above) applies to every prompt. A rule sets a separate model for one.",
    ),
    "add_rule": ("+ Добавить правило", "+ Add rule"),
    "reset_tab": ("↺ Сбросить вкладку", "↺ Reset tab"),
    # Speech tab
    "stt_header": ("🎙 Распознавание (речь → текст)", "🎙 Recognition (speech → text)"),
    "stt_engine_hint": (
        "Чем распознаём речь. auto: mlx на Apple Silicon, иначе faster-whisper (можно не трогать).",
        "Speech recognizer. auto: mlx on Apple Silicon, else faster-whisper (safe to leave).",
    ),
    "model": ("Модель", "Model"),
    "stt_model_hint": (
        "tiny → быстро/грубо · medium/large → точно/медленно. small — оптимум для русского.",
        "tiny → fast/rough · medium/large → accurate/slow. small is the Russian sweet spot.",
    ),
    "language": ("Язык", "Language"),
    "stt_lang_hint": (
        "auto — определять язык по речи. Или зафиксируй ru/en для точности.",
        "auto — detect the language from speech. Or pin ru/en for accuracy.",
    ),
    # Voice tab
    "voice_header": ("🔊 Голос (озвучка)", "🔊 Voice (text-to-speech)"),
    "tts_enabled": ("Озвучка включена", "Text-to-speech enabled"),
    "voice": ("Голос", "Voice"),
    "premium": ("macOS: скачать премиум-голоса…", "macOS: download premium voices…"),
    "tts_button": ("Кнопка озвучки", "Read-aloud button"),
    "tts_hint": (
        "вид + кнопка/клавиша, или «Поймать» → нажми нужную.",
        "type + button/key, or «Catch» → press the one you want.",
    ),
    # Triggers tab
    "trig_header": ("⌨️ Триггер записи (колесо)", "⌨️ Record trigger (wheel)"),
    "trig_button": ("Кнопка", "Button"),
    "trig_hint": (
        "вид + кнопка/клавиша, или «Поймать» → нажми нужную (комбо вроде ⌘F тоже).",
        "type + button/key, or «Catch» → press the one you want (combos like ⌘F too).",
    ),
    "misc_header": ("⚙️ Прочее", "⚙️ Other"),
    "concurrent": (
        "Запись во время обработки (concurrent)",
        "Record while a result is processing (concurrent)",
    ),
    # Language tab
    "lang_header": ("🌐 Язык интерфейса", "🌐 Interface language"),
    "lang_row": ("Язык интерфейса", "Interface language"),
    "lang_hint": (
        "Меняет язык этого окна. По умолчанию — как в системе.",
        "Changes this window's language. Defaults to your system language.",
    ),
    # buttons / runtime
    "catch": ("Поймать", "Catch"),
    "catching": ("нажми…", "press…"),
    "save": ("Сохранить", "Save"),
    "note_saved_applied": (
        "Сохранено и применено: голос, LLM/модели, concurrent. "
        "Триггеры и STT-модель — после перезапуска.",
        "Saved and applied: voice, LLM/models, concurrent. "
        "Triggers and STT model — after restart.",
    ),
    "note_saved_restart": (
        "Сохранено. Перезапусти приложение (меню-бар → Выход).",
        "Saved. Restart the app (menu bar → Quit).",
    ),
    "note_save_fail": ("⚠️ Не удалось сохранить: {}", "⚠️ Couldn't save: {}"),
    "note_reset": (
        "Вкладка «{}» сброшена. Нажми «Сохранить».",
        "Tab «{}» reset. Click «Save».",
    ),
    "note_capture_prompt": (
        "Нажми клавишу/комбо или кнопку мыши (Esc — отмена)…",
        "Press a key/combo or a mouse button (Esc to cancel)…",
    ),
    "note_capture_caught": (
        "Поймал: {} / {}. Нажми «Сохранить».",
        "Caught: {} / {}. Click «Save».",
    ),
    "note_preview_dl": (
        "Скачиваю голос для прослушивания…",
        "Downloading the voice to preview…",
    ),
    "note_piper_dl": (
        "Скачиваю голос «{}»… применится после перезапуска.",
        "Downloading voice «{}»… applies after restart.",
    ),
    "note_premium": (
        "Открыл «Озвучивание»: скачай русский голос (Enhanced/Premium), затем выбери "
        "«macOS» в списке голосов. Применится после перезапуска.",
        "Opened «Spoken Content»: download a voice (Enhanced/Premium), then pick "
        "«macOS» in the voice list. Applies after restart.",
    ),
}


def _detect_ui_lang() -> str:
    """System locale → 'ru' if the preferred language is Russian, else 'en'."""
    try:
        langs = NSLocale.preferredLanguages()
        code = str(langs[0]) if langs and len(langs) else ""
    except Exception:  # noqa: BLE001 - never let locale probing break the window
        code = ""
    return "ru" if code.lower().startswith("ru") else "en"


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


# (config value, (ru label, en label)) — the picker shows the label, stores the value.
# Selection is read/written by *index* so translated labels never break Save.
LLM_BACKENDS = [
    ("ollama", ("Локально — Ollama (бесплатно, без ключа)", "Local — Ollama (free, no key)")),
    ("claude_warm", ("Claude Max (подписка)", "Claude Max (subscription)")),
    ("anthropic", ("Claude API (нужен ключ)", "Claude API (needs a key)")),
    ("claude_cli", ("Claude CLI", "Claude CLI")),
]
STT_BACKENDS = ["auto", "mlx", "faster-whisper"]
STT_MODELS = ["tiny", "base", "small", "medium", "large"]
LANGS = ["auto", "ru", "en"]
KINDS = ["mouse_side", "keyboard", "mouse"]
# TTS voice picker: (backend, piper_voice, (ru label, en label)). "system" = macOS
# voices; "piper" = local neural, auto-downloaded on save/first use. Index-mapped.
TTS_VOICES = [
    ("system", "", ("macOS (системный голос)", "macOS (system voice)")),
    ("piper", "ru_RU-irina-medium", ("Piper: Irina — нейро (RU, жен.)", "Piper: Irina — neural (RU, female)")),
    ("piper", "ru_RU-denis-medium", ("Piper: Денис — нейро (RU, муж.)", "Piper: Denis — neural (RU, male)")),
    ("piper", "ru_RU-ruslan-medium", ("Piper: Руслан — нейро (RU, муж.)", "Piper: Ruslan — neural (RU, male)")),
    ("piper", "ru_RU-dmitri-medium", ("Piper: Дмитрий — нейро (RU, муж.)", "Piper: Dmitri — neural (RU, male)")),
]
W = 520
H = 440


class SettingsWindow(NSObject):
    def init(self):
        self = objc.super(SettingsWindow, self).init()
        if self is not None:
            self._window = None
            self._preview_speaker = None  # plays a sample when the voice changes
            self._rules = []              # per-prompt model rules (rows): each = dict of controls
            self._apply_cb = None         # controller hook to apply cheap settings live
            self._capture_monitor = None  # active NSEvent monitor while catching a key
            self._uilang = "ru"           # interface language ('ru' | 'en')
            self._rebuilding = False      # True while swapping windows for a language change
        return self

    @objc.python_method
    def set_apply_callback(self, cb):
        self._apply_cb = cb

    @objc.python_method
    def _t(self, key):
        """Translate a chrome string key for the current interface language."""
        return STR[key][0 if self._uilang == "ru" else 1]

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
        self._uilang = self._read().get("ui_language") or _detect_ui_lang()
        idx = 0 if self._uilang == "ru" else 1

        def T(key):
            return STR[key][idx]

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, W, H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_(T("win_title"))
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self)
        root = win.contentView()

        tabs = NSTabView.alloc().initWithFrame_(NSMakeRect(10, 48, W - 20, H - 58))
        root.addSubview_(tabs)

        stack = [None]   # the current tab's vertical NSStackView (Auto-Layout, auto-aligns)

        def add_tab(key):
            container = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, W - 28, H - 96))
            v = NSStackView.alloc().init()
            v.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
            v.setAlignment_(NSLayoutAttributeLeading)
            v.setSpacing_(8)
            v.setTranslatesAutoresizingMaskIntoConstraints_(False)
            container.addSubview_(v)
            NSLayoutConstraint.activateConstraints_([
                v.topAnchor().constraintEqualToAnchor_constant_(container.topAnchor(), 16),
                v.leadingAnchor().constraintEqualToAnchor_constant_(container.leadingAnchor(), 18),
            ])
            item = NSTabViewItem.alloc().initWithIdentifier_(key)
            item.setLabel_(T(key))
            item.setView_(container)
            tabs.addTabViewItem_(item)
            stack[0] = v

        def label(s, bold=False, gray=False, width=None):
            f = NSTextField.labelWithString_(s)
            f.setFont_(NSFont.boldSystemFontOfSize_(13) if bold else NSFont.systemFontOfSize_(11 if gray else 12))
            if gray:
                f.setTextColor_(NSColor.secondaryLabelColor())
            if width is not None:
                f.widthAnchor().constraintEqualToConstant_(width).setActive_(True)
            return f

        def header(key):
            stack[0].addArrangedSubview_(label(T(key), bold=True))

        def hint(key):
            stack[0].addArrangedSubview_(label(T(key), gray=True))

        def row(label_key, *controls):
            h = NSStackView.alloc().init()
            h.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
            h.setAlignment_(NSLayoutAttributeCenterY)
            h.setSpacing_(8)
            h.addArrangedSubview_(label(T(label_key) if label_key else "", width=150))
            for c in controls:
                h.addArrangedSubview_(c)
            stack[0].addArrangedSubview_(h)
            return h

        def popup(items, w=300):
            p = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, w, 26), False)
            p.addItemsWithTitles_(items)
            p.widthAnchor().constraintEqualToConstant_(w).setActive_(True)
            return p

        def field(w=300):
            t = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, w, 22))
            t.widthAnchor().constraintEqualToConstant_(w).setActive_(True)
            return t

        def checkbox(key):
            return NSButton.checkboxWithTitle_target_action_(T(key), None, None)

        def button(key, action, w):
            b = NSButton.buttonWithTitle_target_action_(T(key), self, action)
            b.widthAnchor().constraintEqualToConstant_(w).setActive_(True)
            return b

        # ---- LLM tab ----
        add_tab("tab_llm")
        header("llm_header")
        self._backend = popup(self._backend_labels())
        self._backend.setTarget_(self)
        self._backend.setAction_("llmBackendChanged:")
        row("engine", self._backend)
        hint("llm_hint")
        # The two model rows share one slot — only the relevant one is shown.
        self._ollama = field()
        self._ollama_row = row("ollama_model", self._ollama)
        self._claude = field()
        self._claude_row = row("claude_model", self._claude)
        header("rules_header")
        hint("rules_hint")
        self._sectors = list(sectors())
        self._rules_stack = NSStackView.alloc().init()
        self._rules_stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        self._rules_stack.setAlignment_(NSLayoutAttributeLeading)
        self._rules_stack.setSpacing_(6)
        stack[0].addArrangedSubview_(self._rules_stack)
        self._add_rule_btn = button("add_rule", "addRule:", 180)
        stack[0].addArrangedSubview_(self._add_rule_btn)
        stack[0].addArrangedSubview_(button("reset_tab", "resetLlm:", 200))

        # ---- Speech (STT) tab ----
        add_tab("tab_stt")
        header("stt_header")
        self._stt_backend = popup(STT_BACKENDS)
        row("engine", self._stt_backend)
        hint("stt_engine_hint")
        self._stt_model = popup(STT_MODELS)
        row("model", self._stt_model)
        hint("stt_model_hint")
        self._lang = popup(LANGS)
        row("language", self._lang)
        hint("stt_lang_hint")
        stack[0].addArrangedSubview_(button("reset_tab", "resetStt:", 200))

        # ---- Voice (TTS) tab ----
        add_tab("tab_voice")
        header("voice_header")
        self._tts_enabled = checkbox("tts_enabled")
        self._tts_enabled.setTarget_(self)
        self._tts_enabled.setAction_("ttsEnabledChanged:")
        stack[0].addArrangedSubview_(self._tts_enabled)
        self._tts_voice = popup(self._voice_labels())
        self._tts_voice.setTarget_(self)
        self._tts_voice.setAction_("ttsVoiceChanged:")  # play a sample on change
        row("voice", self._tts_voice)
        self._prem = button("premium", "downloadPremium:", 290)
        row("", self._prem)
        self._tts_kind = popup(KINDS, w=110)
        self._tts_key = field(w=90)
        self._cap_tts = button("catch", "captureTts:", 100)
        row("tts_button", self._tts_kind, self._tts_key, self._cap_tts)
        hint("tts_hint")
        stack[0].addArrangedSubview_(button("reset_tab", "resetVoice:", 200))

        # ---- Triggers tab ----
        add_tab("tab_triggers")
        header("trig_header")
        self._wheel_kind = popup(KINDS, w=110)
        self._wheel_key = field(w=90)
        self._cap_wheel = button("catch", "captureWheel:", 100)
        row("trig_button", self._wheel_kind, self._wheel_key, self._cap_wheel)
        hint("trig_hint")
        header("misc_header")
        self._concurrent = checkbox("concurrent")
        stack[0].addArrangedSubview_(self._concurrent)
        stack[0].addArrangedSubview_(button("reset_tab", "resetTriggers:", 200))

        # ---- Language tab ----
        add_tab("tab_lang")
        header("lang_header")
        self._uilang_popup = popup(["Русский", "English"], w=200)
        self._uilang_popup.setTarget_(self)
        self._uilang_popup.setAction_("languageChanged:")
        self._uilang_popup.selectItemAtIndex_(0 if self._uilang == "ru" else 1)
        row("lang_row", self._uilang_popup)
        hint("lang_hint")

        # ---- Save + note (always visible, below the tabs) ----
        self._note = NSTextField.labelWithString_("")
        self._note.setFrame_(NSMakeRect(16, 15, W - 160, 18))
        self._note.setFont_(NSFont.systemFontOfSize_(11))
        self._note.setTextColor_(NSColor.secondaryLabelColor())
        root.addSubview_(self._note)

        save = NSButton.buttonWithTitle_target_action_(T("save"), self, "save:")
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
    def _write(self, data):
        self._path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @objc.python_method
    def _load(self):
        data = self._read()
        self._uilang = data.get("ui_language") or _detect_ui_lang()
        self._uilang_popup.selectItemAtIndex_(0 if self._uilang == "ru" else 1)
        llm = data.get("llm", {})
        hk = data.get("hotkey", {})
        tts = data.get("tts", {})
        tts_hk = tts.get("hotkey", {})
        self._select_backend(self._backend, llm.get("backend", "ollama"))
        self._apply_llm_visibility(llm.get("backend", "ollama"))
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
        self._select_voice(tts)
        self._tts_enabled.setState_(1 if tts.get("enabled", True) else 0)
        self._apply_tts_enabled()
        self._concurrent.setState_(1 if data.get("concurrent", False) else 0)
        for r in list(self._rules):   # clear any existing rule rows
            self._rules_stack.removeView_(r["row"])
        self._rules = []
        for key, ov in (data.get("sector_models") or {}).items():
            if isinstance(ov, dict):  # skip the "_comment" string
                self._make_rule_row(key, ov.get("backend", "ollama"), ov.get("model", ""))
        self._refresh_add_button()
        self._note.setStringValue_("")

    def save_(self, _sender):  # noqa: N802
        data = self._read()
        data["ui_language"] = self._uilang
        data.setdefault("llm", {})
        data["llm"]["backend"] = self._backend_value(self._backend)
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
        # per-prompt model rules -> sector_models
        sm = {}
        for r in self._rules:
            key = self._rule_sector_key(r)
            if key:
                sm[key] = {
                    "backend": self._backend_value(r["engine"]),
                    "model": str(r["model"].stringValue()).strip(),
                }
        existing = data.get("sector_models")
        if isinstance(existing, dict) and "_comment" in existing:
            sm["_comment"] = existing["_comment"]
        data["sector_models"] = sm
        try:
            self._write(data)
        except OSError as exc:  # disk/permissions — tell the user, don't throw into ObjC
            log.warning("could not write %s: %s", self._path(), exc)
            self._note.setStringValue_(self._t("note_save_fail").format(exc))
            return
        applied = False
        if self._apply_cb is not None:
            try:
                self._apply_cb()
                applied = True
            except Exception as exc:  # noqa: BLE001 - never let live-apply break Save
                log.warning("live-apply failed: %s", exc)
        self._note.setStringValue_(
            self._t("note_saved_applied" if applied else "note_saved_restart")
        )
        if backend == "piper":
            self._maybe_download_piper(piper_voice)

    # -- LLM backend helpers (index-mapped so translated labels are safe) ------

    @objc.python_method
    def _backend_labels(self):
        idx = 0 if self._uilang == "ru" else 1
        return [pair[idx] for _v, pair in LLM_BACKENDS]

    @objc.python_method
    def _select_backend(self, popup, value):
        i = next((i for i, (v, _p) in enumerate(LLM_BACKENDS) if v == value), 0)
        popup.selectItemAtIndex_(i)

    @objc.python_method
    def _backend_value(self, popup):
        i = int(popup.indexOfSelectedItem())
        return LLM_BACKENDS[i][0] if 0 <= i < len(LLM_BACKENDS) else "ollama"

    @objc.python_method
    def _apply_llm_visibility(self, backend: str):
        """Show only the model row that applies to the chosen backend. NSStackView
        collapses a hidden arranged row, so no empty gap is left."""
        is_ollama = backend == "ollama"
        self._ollama_row.setHidden_(not is_ollama)
        self._claude_row.setHidden_(is_ollama)

    def llmBackendChanged_(self, _sender):  # noqa: N802
        self._apply_llm_visibility(self._backend_value(self._backend))

    # -- interface language (#43/#53) ----------------------------------------

    def languageChanged_(self, _sender):  # noqa: N802
        new = "ru" if int(self._uilang_popup.indexOfSelectedItem()) == 0 else "en"
        if new == self._uilang:
            return
        self._uilang = new
        try:  # persist immediately; other unsaved form edits are intentionally not written
            data = self._read()
            data["ui_language"] = new
            self._write(data)
        except OSError as exc:
            log.warning("could not persist ui_language: %s", exc)
        # Rebuild on the next runloop tick, after this popup's action settles.
        self.performSelector_withObject_afterDelay_("rebuildLang:", None, 0.0)

    def rebuildLang_(self, _arg=None):  # noqa: N802
        """Swap the window for a freshly-built one in the new language, in place."""
        old = self._window
        if old is None:
            return
        frame = old.frame()
        self._window = None
        self._build()
        self._load()
        self._window.setFrame_display_(frame, True)
        self._rebuilding = True   # so the old window's close doesn't drop activation policy
        old.close()
        self._rebuilding = False
        self._window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    # -- per-tab reset to defaults (#51) -------------------------------------
    # Each button resets only its own tab's controls to the config dataclass
    # defaults (the canonical "standard"); nothing is saved until the user hits
    # «Сохранить», so a reset can still be backed out by closing the window.

    def resetLlm_(self, _sender):  # noqa: N802
        from ...core.config import LLMConfig

        d = LLMConfig()
        self._select_backend(self._backend, d.backend)
        self._apply_llm_visibility(d.backend)
        self._ollama.setStringValue_(d.ollama_model)
        self._claude.setStringValue_(d.model)
        for r in list(self._rules):  # drop every per-prompt rule
            self._rules_stack.removeView_(r["row"])
        self._rules = []
        self._refresh_add_button()
        self._note.setStringValue_(self._t("note_reset").format(self._t("tab_llm")))

    def resetStt_(self, _sender):  # noqa: N802
        from ...core.config import STTConfig

        d = STTConfig()
        self._stt_backend.selectItemWithTitle_(d.backend)
        self._stt_model.selectItemWithTitle_(d.model)
        self._lang.selectItemWithTitle_("ru")
        self._note.setStringValue_(self._t("note_reset").format(self._t("tab_stt")))

    def resetVoice_(self, _sender):  # noqa: N802
        from ...core.config import TTSConfig

        d = TTSConfig()
        self._tts_enabled.setState_(1 if d.enabled else 0)
        self._select_voice({"backend": d.backend, "piper_voice": d.piper_voice})
        self._tts_kind.selectItemWithTitle_(d.hotkey.kind)
        self._tts_key.setStringValue_(d.hotkey.key)
        self._apply_tts_enabled()
        self._note.setStringValue_(self._t("note_reset").format(self._t("tab_voice")))

    def resetTriggers_(self, _sender):  # noqa: N802
        from ...core.config import HotkeyConfig

        d = HotkeyConfig()
        self._wheel_kind.selectItemWithTitle_(d.kind)
        self._wheel_key.setStringValue_(d.key)
        self._concurrent.setState_(0)
        self._note.setStringValue_(self._t("note_reset").format(self._t("tab_triggers")))

    # -- per-prompt model rules ----------------------------------------------

    @objc.python_method
    def _rule_sector_key(self, rule):
        label = str(rule["prompt"].titleOfSelectedItem())
        return next((s.key for s in self._sectors if s.label == label), None)

    @objc.python_method
    def _first_unassigned(self):
        assigned = {self._rule_sector_key(r) for r in self._rules}
        return next((s.key for s in self._sectors if s.key not in assigned), None)

    @objc.python_method
    def _refresh_add_button(self):
        self._add_rule_btn.setEnabled_(self._first_unassigned() is not None)

    @objc.python_method
    def _make_rule_row(self, sector_key, backend, model):
        """Build one rule row — [промпт ▾] [движок ▾] [модель] [✕] — and track it."""
        h = NSStackView.alloc().init()
        h.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        h.setAlignment_(NSLayoutAttributeCenterY)
        h.setSpacing_(6)
        prompt = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 130, 26), False)
        prompt.addItemsWithTitles_([s.label for s in self._sectors])
        prompt.widthAnchor().constraintEqualToConstant_(130).setActive_(True)
        lbl = next((s.label for s in self._sectors if s.key == sector_key), None)
        if lbl:
            prompt.selectItemWithTitle_(lbl)
        engine = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 150, 26), False)
        engine.addItemsWithTitles_(self._backend_labels())
        engine.widthAnchor().constraintEqualToConstant_(150).setActive_(True)
        self._select_backend(engine, backend)
        model_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 110, 22))
        model_field.widthAnchor().constraintEqualToConstant_(110).setActive_(True)
        model_field.setStringValue_(str(model or ""))
        delete = NSButton.buttonWithTitle_target_action_("✕", self, "deleteRule:")
        delete.widthAnchor().constraintEqualToConstant_(32).setActive_(True)
        for c in (prompt, engine, model_field, delete):
            h.addArrangedSubview_(c)
        self._rules.append(
            {"row": h, "prompt": prompt, "engine": engine, "model": model_field, "delete": delete}
        )
        self._rules_stack.addArrangedSubview_(h)

    def addRule_(self, _sender):  # noqa: N802
        key = self._first_unassigned()
        if key is None:
            return
        backend = self._backend_value(self._backend)
        model = str(self._ollama.stringValue()) if backend == "ollama" else str(self._claude.stringValue())
        self._make_rule_row(key, backend, model)  # default to the base config
        self._refresh_add_button()

    def deleteRule_(self, sender):  # noqa: N802
        rule = next((r for r in self._rules if r["delete"] == sender), None)
        if rule is None:
            return
        self._rules_stack.removeView_(rule["row"])
        self._rules.remove(rule)
        self._refresh_add_button()

    @objc.python_method
    def _apply_tts_enabled(self):
        """Disable the voice + read-aloud-button controls when TTS is off."""
        on = bool(self._tts_enabled.state())
        for ctl in (self._tts_voice, self._prem, self._tts_kind, self._tts_key, self._cap_tts):
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
        button.setTitle_(self._t("catching"))
        self._note.setStringValue_(self._t("note_capture_prompt"))
        mask = NSEventMaskKeyDown | NSEventMaskOtherMouseDown | NSEventMaskRightMouseDown

        def handler(event):
            kind, key = _capture_kind_key(event)
            if kind is None:
                return None  # unrecognized — keep waiting
            if kind != "cancel":
                kind_popup.selectItemWithTitle_(kind)
                key_field.setStringValue_(key)
                self._note.setStringValue_(self._t("note_capture_caught").format(kind, key))
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
                    self._note.setStringValue_(self._t("note_preview_dl"))
                self._preview_speaker = PiperSpeaker(piper_voice, cache)
            else:
                from .tts import Speaker

                self._preview_speaker = Speaker("")  # macOS, best for the language
            self._preview_speaker.toggle("Привет! Это пример выбранного голоса.")
        except Exception as exc:  # noqa: BLE001 - preview must never break the window
            log.warning("voice preview failed: %s", exc)

    # -- TTS voice helpers (index-mapped) ------------------------------------

    @objc.python_method
    def _voice_labels(self):
        idx = 0 if self._uilang == "ru" else 1
        return [pair[idx] for _b, _pv, pair in TTS_VOICES]

    @objc.python_method
    def _select_voice(self, tts: dict):
        """Select the dropdown row matching the saved (backend, piper_voice)."""
        backend = tts.get("backend", "system")
        pv = tts.get("piper_voice", "ru_RU-irina-medium")
        i = next(
            (i for i, (b, p, _l) in enumerate(TTS_VOICES) if b == backend and (b != "piper" or p == pv)),
            0,
        )
        self._tts_voice.selectItemAtIndex_(i)

    @objc.python_method
    def _selected_voice(self):
        """Map the dropdown selection to (backend, piper_voice)."""
        i = int(self._tts_voice.indexOfSelectedItem())
        b, p, _l = TTS_VOICES[i] if 0 <= i < len(TTS_VOICES) else TTS_VOICES[0]
        return b, p

    @objc.python_method
    def _maybe_download_piper(self, voice_name: str) -> None:
        """Fetch the Piper voice now (in the background) if it isn't cached yet."""
        if not voice_name:
            return
        from ...core.config import app_support_dir

        cache = app_support_dir() / "piper"
        if (cache / f"{voice_name}.onnx").exists():
            return
        self._note.setStringValue_(self._t("note_piper_dl").format(voice_name))

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
        self._note.setStringValue_(self._t("note_premium"))

    def windowWillClose_(self, _notif):  # noqa: N802
        if self._capture_monitor is not None:
            NSEvent.removeMonitor_(self._capture_monitor)
            self._capture_monitor = None
        if self._rebuilding:
            return  # a language rebuild swaps windows; keep the regular policy
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
