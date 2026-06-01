"""Settings window (NSWindow) — edit config.json from a GUI instead of by hand.

Opened from the menu-bar. The app is an accessory (no Dock icon); while the
settings window is open we switch to a regular activation policy so it can take
focus, and switch back when it closes. Save writes config.json (other keys are
preserved); cheap settings apply live, the rest on the next restart.

The window is split into tabs (LLM / Речь / Голос / Триггеры / Язык). Below the
tabs sits a permanent bar: «Сброс» (resets the active tab to defaults) on the
left and «Сохранить» on the right. Save is disabled until something changes,
then turns green; saving disables it again — that button state IS the
"saved / unsaved" feedback (no status text needed).

Interface language (#43/#53): every chrome string goes through ``T(key)`` /
``self._t(key)`` from ``i18n``. Changing it in the «Язык» tab takes effect on
Save, which restarts the whole app so the menu bar and everything else switch
too. Dropdowns whose labels are translated (LLM engines, TTS voices) map
selection by *index*, not title, so a language switch can't break Save.
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
    NSComboBox,
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
    NSLineBreakByWordWrapping,
    NSPopUpButton,
    NSScrollView,
    NSSecureTextField,
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
from Foundation import NSMakeRect, NSObject

from ...core.config import (
    STTConfig,
    TTSConfig,
    _project_root,
    app_support_dir,
    read_env,
    write_env_key,
)
from ...core.modes import load_sectors, prompts_dir
from .i18n import detect_ui_lang, resolve_lang
from .i18n import t as _tr

log = logging.getLogger(__name__)


class _FlippedView(NSView):
    """Top-left origin so tab content lays out top-to-bottom regardless of height."""

    def isFlipped(self):  # noqa: N802
        return True

    def mouseDown_(self, event):  # noqa: N802
        # Clicking empty space commits the active field and drops focus, so a text
        # field / combo doesn't stay "stuck" with the caret after you click away.
        win = self.window()
        if win is not None:
            win.makeFirstResponder_(win)
        objc.super(_FlippedView, self).mouseDown_(event)


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
    ("ollama", ("Ollama", "Ollama")),
    ("claude_warm", ("Claude (подписка)", "Claude (subscription)")),
    ("anthropic", ("Claude API (нужен ключ)", "Claude API (needs a key)")),
    ("openai", ("OpenAI API (нужен ключ)", "OpenAI API (needs a key)")),
    ("claude_cli", ("Claude CLI", "Claude CLI")),
]
STT_BACKENDS = ["auto", "mlx", "faster-whisper"]
STT_MODELS = ["tiny", "base", "small", "medium", "large"]
# Recommended models per connection (#39). The combos are editable — these are
# just suggestions in the dropdown; a custom model can still be typed.
OLLAMA_MODELS = ["qwen2.5:7b", "qwen2.5:3b", "llama3.1:8b", "qwen2.5:14b"]
ANTHROPIC_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-5"]
OPENAI_MODELS = ["gpt-4o-mini", "gpt-4o"]
CC_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-5"]
LANGS = ["auto", "ru", "en"]
# Friendly mouse-button picker (#mouse-selector): (kind, key, (ru, en)). Index-mapped;
# a «Поймать» of an unlisted button appends a custom item. Side-button NUMBERS depend
# on the mouse, so these are common defaults — others are added by capture.
MOUSE_BUTTONS = [
    ("mouse", "right", ("Правая кнопка", "Right button")),
    ("mouse", "middle", ("Средняя кнопка", "Middle button")),
    ("mouse_side", "3", ("Боковая 3 (назад)", "Side 3 (back)")),
    ("mouse_side", "4", ("Боковая 4 (вперёд)", "Side 4 (forward)")),
    ("mouse_side", "5", ("Боковая 5", "Side 5")),
]


def _hotkey_bindings(raw):
    """Normalize a config 'hotkey' (legacy single {kind,key} or a list) to a list of dicts."""
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [b for b in raw if isinstance(b, dict)]
    return []


# Connection type (#36): the three radio types group the underlying LLM backends.
#   api → anthropic | openai · ollama → ollama · cc (Claude Code) → claude_warm | claude_cli
def _conn_type_of(backend: str) -> str:
    if backend == "ollama":
        return "ollama"
    if backend in ("anthropic", "openai"):
        return "api"
    return "cc"  # claude_warm / claude_cli


# TTS voice picker: (backend, piper_voice, (ru label, en label)). "system" = macOS
# voices; "piper" = local neural, auto-downloaded on save/first use. Index-mapped.
TTS_VOICES = [
    ("system", "", ("macOS (системный голос)", "macOS (system voice)")),
    ("piper", "ru_RU-irina-medium", ("Piper: Irina — нейро (RU, жен.)", "Piper: Irina — neural (RU, female)")),
    ("piper", "ru_RU-denis-medium", ("Piper: Денис — нейро (RU, муж.)", "Piper: Denis — neural (RU, male)")),
    ("piper", "ru_RU-ruslan-medium", ("Piper: Руслан — нейро (RU, муж.)", "Piper: Ruslan — neural (RU, male)")),
    ("piper", "ru_RU-dmitri-medium", ("Piper: Дмитрий — нейро (RU, муж.)", "Piper: Dmitri — neural (RU, male)")),
]
# Suggested keyboard combos, pre-filled into the keyboard trigger rows but left
# OFF by default — the user ticks the row to enable (the active default trigger
# stays the side mouse button). Chosen for a hold-to-record key: left-hand
# reachable so the right hand stays free for the trackpad, emit no text, and
# don't clash with macOS shortcuts. ⌘ keeps the char stable for pynput's matching
# and ⌃ suppresses text; ⌃⌘Z / ⌃⌘X aren't standard system shortcuts.
WHEEL_KB_DEFAULT = "cmd+ctrl+z"  # ⌃⌘Z — запись/колесо
TTS_KB_DEFAULT = "cmd+ctrl+x"    # ⌃⌘X — озвучка

W = 580  # widened from 520 to fit 7 tabs + the per-prompt rule rows comfortably
H = 464  # +24 over the original 440 for the top restart banner (the old bottom
         # banner gap was reclaimed, so the window grew less than the banner's height)


class SettingsWindow(NSObject):
    def init(self):
        self = objc.super(SettingsWindow, self).init()
        if self is not None:
            self._window = None
            self._preview_speaker = None  # plays a sample when the voice changes
            self._rules = []              # per-prompt model rules (rows): each = dict of controls
            self._apply_cb = None         # controller hook to apply cheap settings live
            self._restart_cb = None       # controller hook to restart the app (language change)
            self._capture_monitor = None  # active NSEvent monitor while catching a key
            self._uilang = "ru"           # language THIS window is rendered in ('ru' | 'en')
            self._dirty = False           # any unsaved change? drives the Save button state
            self._save_btn = None
            self._tabs = None
            self._baseline = None         # form snapshot at load -> Save = (form != baseline)
            self._restart_warn = None     # always-visible "saving will restart" label
            self._last_provider = "Anthropic"   # for per-provider model memory (#F2)
            self._model_by_provider = {}
            self._pull_result = None      # (ok, model) handoff from the ollama-pull thread
        return self

    @objc.python_method
    def set_apply_callback(self, cb):
        self._apply_cb = cb

    @objc.python_method
    def select_tab(self, tab_id):
        """Show a specific tab by identifier (used to restore the tab after a restart)."""
        if self._tabs is not None and tab_id:
            self._tabs.selectTabViewItemWithIdentifier_(tab_id)

    @objc.python_method
    def set_restart_callback(self, cb):
        self._restart_cb = cb

    @objc.python_method
    def _t(self, key):
        """Translate a chrome string key for the current interface language."""
        return _tr(key, self._uilang)

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
        self._uilang = resolve_lang(self._read().get("ui_language"))

        def T(key):
            return _tr(key, self._uilang)

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

        # Tabs sit between the bottom button bar (top ≈42) and the top restart
        # banner. y=54 leaves a ~12px gap above the buttons (the old bottom-banner
        # gap is gone), top ≈418 sits just under the banner.
        tabs = NSTabView.alloc().initWithFrame_(NSMakeRect(10, 54, W - 20, H - 100))
        root.addSubview_(tabs)
        self._tabs = tabs

        stack = [None]   # the current tab's vertical NSStackView (Auto-Layout, auto-aligns)

        def add_tab(key, scroll=False):
            tab_w, tab_h = W - 28, H - 138  # tracks the tabs frame height (− tab bar/insets)
            v = NSStackView.alloc().init()
            v.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
            v.setAlignment_(NSLayoutAttributeLeading)
            v.setSpacing_(8)
            v.setTranslatesAutoresizingMaskIntoConstraints_(False)
            doc = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, tab_w, tab_h))
            doc.addSubview_(v)
            cons = [
                v.topAnchor().constraintEqualToAnchor_constant_(doc.topAnchor(), 16),
                v.leadingAnchor().constraintEqualToAnchor_constant_(doc.leadingAnchor(), 18),
            ]
            if scroll:
                # The document view grows with its content; the scroll view shows a
                # vertical scroller only when it overflows the tab (autohide).
                doc.setTranslatesAutoresizingMaskIntoConstraints_(False)
                sv = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, tab_w, tab_h))
                sv.setHasVerticalScroller_(True)
                sv.setHasHorizontalScroller_(False)
                sv.setDrawsBackground_(False)
                sv.setAutohidesScrollers_(True)
                sv.setDocumentView_(doc)
                cons += [
                    doc.widthAnchor().constraintEqualToAnchor_(sv.contentView().widthAnchor()),
                    doc.bottomAnchor().constraintEqualToAnchor_constant_(v.bottomAnchor(), 16),
                ]
                view = sv
            else:
                view = doc
            NSLayoutConstraint.activateConstraints_(cons)
            item = NSTabViewItem.alloc().initWithIdentifier_(key)
            item.setLabel_(T(key))
            item.setView_(view)
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
            # Wrap long explanatory text within the tab instead of letting the
            # single-line label run off the right edge (container W-28, leading 18).
            wrap_w = W - 68
            lab = label(T(key), gray=True)
            lab.setUsesSingleLineMode_(False)
            lab.setLineBreakMode_(NSLineBreakByWordWrapping)
            lab.setMaximumNumberOfLines_(0)
            lab.setPreferredMaxLayoutWidth_(wrap_w)
            lab.widthAnchor().constraintLessThanOrEqualToConstant_(wrap_w).setActive_(True)
            stack[0].addArrangedSubview_(lab)

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

        def combo(items, w=300):
            # editable: pick a recommendation from the dropdown, or type a custom one
            c = NSComboBox.alloc().initWithFrame_(NSMakeRect(0, 0, w, 26))
            c.addItemsWithObjectValues_(items)
            c.setCompletes_(True)
            c.widthAnchor().constraintEqualToConstant_(w).setActive_(True)
            return c

        def checkbox(key):
            return NSButton.checkboxWithTitle_target_action_(T(key), None, None)

        def button(key, action, w):
            b = NSButton.buttonWithTitle_target_action_(T(key), self, action)
            b.widthAnchor().constraintEqualToConstant_(w).setActive_(True)
            return b

        def trig_row(key, *controls):
            # a trigger row whose label is an on/off checkbox; off = row locked
            cb = NSButton.checkboxWithTitle_target_action_(T(key), self, "triggerToggled:")
            cb.widthAnchor().constraintEqualToConstant_(150).setActive_(True)
            h = NSStackView.alloc().init()
            h.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
            h.setAlignment_(NSLayoutAttributeCenterY)
            h.setSpacing_(8)
            h.addArrangedSubview_(cb)
            for c in controls:
                h.addArrangedSubview_(c)
            stack[0].addArrangedSubview_(h)
            return cb

        # ---- LLM tab (scrollable: base config + up to one rule per prompt) ----
        add_tab("tab_llm", scroll=True)
        header("llm_header")
        hint("llm_hint")

        # Connection type: three radios; only the selected type's settings show (#36).
        self._conn_radios = []
        for tkey, lblkey in (("api", "conn_api"), ("ollama", "conn_ollama"), ("cc", "conn_cc")):
            rb = NSButton.radioButtonWithTitle_target_action_(T(lblkey), self, "connTypeChanged:")
            stack[0].addArrangedSubview_(rb)
            self._conn_radios.append((rb, tkey))

        def group():
            g = NSStackView.alloc().init()
            g.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
            g.setAlignment_(NSLayoutAttributeLeading)
            g.setSpacing_(6)
            stack[0].addArrangedSubview_(g)
            return g

        # -- Direct API group: provider + key + model (#36/#38) --
        self._grp_api = group()
        prev, stack[0] = stack[0], self._grp_api
        self._provider = popup(["Anthropic", "OpenAI"], w=160)
        self._provider.setTarget_(self)
        self._provider.setAction_("providerChanged:")
        row("provider", self._provider)
        # masked key (#F4) + a plain mirror toggled by «Показать»
        self._api_key = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 180, 22))
        self._api_key.widthAnchor().constraintEqualToConstant_(180).setActive_(True)
        self._api_key_plain = field(w=180)
        self._api_key_plain.setHidden_(True)
        self._api_show = NSButton.checkboxWithTitle_target_action_(
            T("show_key"), self, "toggleKeyVisibility:"
        )
        row("api_key", self._api_key, self._api_key_plain, self._api_show)
        self._api_model = combo(ANTHROPIC_MODELS, w=250)  # provider switch updates the list
        row("model", self._api_model)
        hint("api_key_hint")
        stack[0] = prev

        # -- Ollama group: pick the model + URL. Downloading, installed list and
        #    status/restart live on the «Модели» tab (no duplicate controls here). --
        self._grp_ollama = group()
        prev, stack[0] = stack[0], self._grp_ollama
        # A pure selector of INSTALLED models (filled live from /api/tags) — no
        # free-text. Download / manage models on the «Модели» tab.
        self._ollama = popup([], w=200)
        row("model", self._ollama)
        self._ollama_url = field(w=250)
        row("ollama_url", self._ollama_url)
        hint("ollama_hint")
        # optional bearer token for a remote/hosted Ollama behind auth (kept in .env)
        self._ollama_token = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 250, 22))
        self._ollama_token.widthAnchor().constraintEqualToConstant_(250).setActive_(True)
        row("ollama_token", self._ollama_token)
        hint("ollama_token_hint")
        hint("llm_models_pointer")
        stack[0] = prev

        # -- Claude Code group: model --
        self._grp_cc = group()
        prev, stack[0] = stack[0], self._grp_cc
        self._cc_model = combo(CC_MODELS, w=250)
        row("model", self._cc_model)
        hint("cc_hint")
        stack[0] = prev

        # ---- Models tab: one place to download & manage local Ollama models
        #      (live status + restart, installed list, pull). The LLM tab just picks.
        add_tab("tab_models", scroll=True)
        header("models_header")
        self._ollama_state = None
        self._ollama_status = label("", gray=True)
        stack[0].addArrangedSubview_(self._ollama_status)
        self._ollama_action = NSButton.buttonWithTitle_target_action_("", self, "ollamaAction:")
        self._ollama_action.widthAnchor().constraintEqualToConstant_(200).setActive_(True)
        self._ollama_action.setHidden_(True)  # only shown for Install/Start
        st_btns = NSStackView.alloc().init()
        st_btns.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        st_btns.setSpacing_(8)
        st_btns.addArrangedSubview_(self._ollama_action)
        st_btns.addArrangedSubview_(button("ollama_restart_btn", "restartOllama:", 190))
        st_btns.addArrangedSubview_(button("ollama_recheck_btn", "recheckOllama:", 110))
        stack[0].addArrangedSubview_(st_btns)
        stack[0].addArrangedSubview_(label(T("models_installed_header"), bold=True))
        # A row per installed model — "• name (size)  [✕]" — so each can be deleted.
        self._models_installed = NSStackView.alloc().init()
        self._models_installed.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        self._models_installed.setAlignment_(NSLayoutAttributeLeading)
        self._models_installed.setSpacing_(4)
        self._installed_rows = []
        stack[0].addArrangedSubview_(self._models_installed)
        stack[0].addArrangedSubview_(label(T("models_download_header"), bold=True))
        self._models_pull = combo(OLLAMA_MODELS, w=220)
        self._models_dl_btn = button("models_pull_btn", "downloadOllama:", 110)
        dl_row = NSStackView.alloc().init()
        dl_row.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        dl_row.setSpacing_(8)
        dl_row.addArrangedSubview_(self._models_pull)
        dl_row.addArrangedSubview_(self._models_dl_btn)
        stack[0].addArrangedSubview_(dl_row)
        hint("models_download_hint")
        stack[0].addArrangedSubview_(button("ollama_library_btn", "openOllamaLibrary:", 250))

        # ---- Prompts tab: the wheel's sectors (count + folder access) and the
        #      optional per-prompt model rules. Read FRESH from the folder so a
        #      just-added prompt shows here without a restart (wheel applies on restart).
        add_tab("tab_prompts", scroll=True)
        self._sectors = list(load_sectors())
        header("prompts_header")
        self._prompts_label = label("", gray=True)
        stack[0].addArrangedSubview_(self._prompts_label)
        prompt_btns = NSStackView.alloc().init()
        prompt_btns.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        prompt_btns.setSpacing_(8)
        prompt_btns.addArrangedSubview_(button("open_prompts_folder", "openPromptsFolder:", 230))
        prompt_btns.addArrangedSubview_(button("refresh_prompts", "refreshPrompts:", 110))
        stack[0].addArrangedSubview_(prompt_btns)
        hint("prompts_hint")
        self._refresh_prompts_label()
        header("rules_header")
        hint("rules_hint")
        self._rules_stack = NSStackView.alloc().init()
        self._rules_stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        self._rules_stack.setAlignment_(NSLayoutAttributeLeading)
        self._rules_stack.setSpacing_(6)
        stack[0].addArrangedSubview_(self._rules_stack)
        self._add_rule_btn = button("add_rule", "addRule:", 180)
        stack[0].addArrangedSubview_(self._add_rule_btn)

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
        # read-aloud trigger: keyboard row + mouse row, each with an on/off checkbox
        stack[0].addArrangedSubview_(label(T("tts_button"), bold=True))
        self._tts_kb = field(w=170)
        self._cap_tts_kb = button("catch", "captureTtsKb:", 100)
        self._tts_kb_on = trig_row("trig_kb", self._tts_kb, self._cap_tts_kb)
        self._tts_ms = popup(self._mouse_labels(), w=200)
        self._tts_ms_map = [(k, key) for k, key, _ in MOUSE_BUTTONS]
        self._cap_tts_ms = button("catch", "captureTtsMs:", 90)
        self._tts_ms_on = trig_row("trig_mouse", self._tts_ms, self._cap_tts_ms)
        hint("trig_check_hint")

        # ---- Triggers tab ----
        add_tab("tab_triggers")
        header("trig_header")
        self._wheel_kb = field(w=170)
        self._cap_wheel_kb = button("catch", "captureWheelKb:", 100)
        self._wheel_kb_on = trig_row("trig_kb", self._wheel_kb, self._cap_wheel_kb)
        self._wheel_ms = popup(self._mouse_labels(), w=200)
        self._wheel_ms_map = [(k, key) for k, key, _ in MOUSE_BUTTONS]
        self._cap_wheel_ms = button("catch", "captureWheelMs:", 90)
        self._wheel_ms_on = trig_row("trig_mouse", self._wheel_ms, self._cap_wheel_ms)
        hint("trig_hint")
        hint("trig_check_hint")
        header("misc_header")
        self._concurrent = checkbox("concurrent")
        stack[0].addArrangedSubview_(self._concurrent)

        # ---- Language tab ----
        add_tab("tab_lang")
        header("lang_header")  # 🌐 Язык интерфейса — the dropdown sits right under it
        self._uilang_popup = popup(["Русский", "English"], w=200)
        self._uilang_popup.selectItemAtIndex_(0 if self._uilang == "ru" else 1)
        stack[0].addArrangedSubview_(self._uilang_popup)
        hint("lang_hint")

        # ---- always-visible restart banner, pinned to the TOP above the tabs so the
        #      user always knows which settings cost a restart. Fully static (same text
        #      and weight always) and wraps to 2 lines, so it never shifts or truncates.
        self._restart_warn = NSTextField.labelWithString_(T("restart_warn_global"))
        self._restart_warn.setFrame_(NSMakeRect(16, H - 44, W - 32, 34))
        self._restart_warn.setFont_(NSFont.systemFontOfSize_(11))
        self._restart_warn.setTextColor_(NSColor.systemOrangeColor())
        self._restart_warn.setUsesSingleLineMode_(False)
        self._restart_warn.setLineBreakMode_(NSLineBreakByWordWrapping)
        self._restart_warn.setMaximumNumberOfLines_(2)
        root.addSubview_(self._restart_warn)

        # ---- bottom bar: Reset (left) · note · Save (right) ----
        reset_btn = NSButton.buttonWithTitle_target_action_(
            T("reset_tab"), self, "resetCurrentTab:"
        )
        reset_btn.setFrame_(NSMakeRect(16, 12, 96, 30))
        root.addSubview_(reset_btn)

        self._note = NSTextField.labelWithString_("")
        # Sits between Reset (left) and Save (right); wraps to 2 lines so longer
        # status messages (downloading, errors, refresh notes) aren't truncated.
        self._note.setFrame_(NSMakeRect(116, 8, W - 250, 32))
        self._note.setFont_(NSFont.systemFontOfSize_(11))
        self._note.setTextColor_(NSColor.secondaryLabelColor())
        self._note.setUsesSingleLineMode_(False)
        self._note.setLineBreakMode_(NSLineBreakByWordWrapping)
        self._note.setMaximumNumberOfLines_(2)
        root.addSubview_(self._note)

        self._save_btn = NSButton.buttonWithTitle_target_action_(T("save"), self, "save:")
        self._save_btn.setFrame_(NSMakeRect(W - 130, 12, 116, 30))
        root.addSubview_(self._save_btn)

        self._window = win
        self._conn_radios[1][0].setState_(1)  # default to Ollama; _load re-applies
        self._apply_conn_visibility()
        self._wire_dirty()
        self._set_tooltips()
        self._capture_baseline()

    @objc.python_method
    def _set_tooltips(self):
        """Short hover hints (#41) on the key controls — `NSView.setToolTip_`."""
        t = self._t
        for rb, tkey in self._conn_radios:
            rb.setToolTip_(t({"api": "tip_conn_api", "ollama": "tip_conn_ollama",
                              "cc": "tip_conn_cc"}[tkey]))
        pairs = (
            (self._provider, "tip_provider"), (self._api_key, "tip_api_key"),
            (self._api_key_plain, "tip_api_key"),
            (self._api_model, "tip_model"), (self._ollama, "tip_model"),
            (self._ollama_url, "tip_ollama_url"), (self._models_pull, "tip_model"),
            (self._cc_model, "tip_model"), (self._stt_backend, "tip_stt_backend"),
            (self._stt_model, "tip_stt_model"), (self._lang, "tip_stt_lang"),
            (self._tts_enabled, "tip_tts_enabled"), (self._tts_voice, "tip_tts_voice"),
            (self._prem, "tip_premium"), (self._tts_kb, "tip_tts_trigger"),
            (self._tts_ms, "tip_mouse_btn"), (self._wheel_kb, "tip_wheel_trigger"),
            (self._wheel_ms, "tip_mouse_btn"), (self._concurrent, "tip_concurrent"),
            (self._uilang_popup, "tip_uilang"),
            (self._cap_wheel_kb, "tip_catch"), (self._cap_wheel_ms, "tip_catch"),
            (self._cap_tts_kb, "tip_catch"), (self._cap_tts_ms, "tip_catch"),
            (self._wheel_kb_on, "tip_trig_toggle"), (self._wheel_ms_on, "tip_trig_toggle"),
            (self._tts_kb_on, "tip_trig_toggle"), (self._tts_ms_on, "tip_trig_toggle"),
        )
        for ctl, key in pairs:
            ctl.setToolTip_(t(key))

    # -- prompts (= wheel sectors) --------------------------------------------

    @objc.python_method
    def _refresh_prompts_label(self):
        self._prompts_label.setStringValue_(self._t("prompts_count").format(len(self._sectors)))

    def openPromptsFolder_(self, _sender):  # noqa: N802
        from AppKit import NSWorkspace
        from Foundation import NSURL

        d = prompts_dir()
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # noqa: BLE001 - best effort
            log.warning("prompts folder open: %s", exc)
        NSWorkspace.sharedWorkspace().openURL_(NSURL.fileURLWithPath_(str(d)))

    def refreshPrompts_(self, _sender):  # noqa: N802
        """Re-read the prompts folder so a just-added file shows in the list (and is
        assignable in a new rule) without restarting. The wheel applies on restart."""
        self._sectors = list(load_sectors())
        self._refresh_prompts_label()
        self._note.setStringValue_(self._t("prompts_refreshed"))

    # -- dirty tracking (Save button reflects unsaved changes) ----------------

    @objc.python_method
    def _wire_dirty(self):
        """Any user edit -> mark dirty (Save turns green). Programmatic value sets
        in _load don't fire these, so loading leaves the form clean."""
        for p in (self._stt_backend, self._stt_model, self._lang, self._wheel_ms,
                  self._tts_ms, self._uilang_popup, self._ollama):
            p.setTarget_(self)
            p.setAction_("markDirty:")
        self._concurrent.setTarget_(self)
        self._concurrent.setAction_("markDirty:")
        for f in (self._api_key, self._api_key_plain, self._api_model, self._ollama_token,
                  self._ollama_url, self._cc_model, self._wheel_kb, self._tts_kb):
            f.setDelegate_(self)  # controlTextDidChange_ fires per keystroke

    @objc.python_method
    def _set_dirty(self, flag):
        self._dirty = bool(flag)
        if self._save_btn is None:
            return
        self._save_btn.setEnabled_(self._dirty)
        self._save_btn.setBezelColor_(NSColor.systemGreenColor() if self._dirty else None)

    @objc.python_method
    def _full_snapshot(self):
        """The whole form's saveable state — every tab's snapshot + the API key."""
        return tuple(
            self._tab_snapshot(t)
            for t in ("tab_llm", "tab_stt", "tab_voice", "tab_triggers", "tab_lang")
        )

    @objc.python_method
    def _capture_baseline(self):
        """Remember the current form as the 'saved' state; Save goes disabled."""
        self._baseline = self._full_snapshot()
        self._set_dirty(False)

    @objc.python_method
    def _recompute_dirty(self):
        """Save reflects whether the form actually differs from the saved state, so
        reverting a change (or a reset that lands back on the saved values) disarms it."""
        self._set_dirty(self._full_snapshot() != self._baseline)

    @objc.python_method
    def _restart_changed(self, old, new_lang, new_wheel, new_tts, new_stt_backend, new_stt_model):
        """Do these new values differ from the saved config in a way that needs a
        restart? — language / triggers / STT, none of which can be swapped live.
        Used by save_ to decide whether to relaunch. The top banner is a static,
        always-visible reminder, so it doesn't depend on this."""
        return (
            new_lang != resolve_lang(old.get("ui_language"))
            or self._trigger_sig(old.get("hotkey")) != self._trigger_sig(new_wheel)
            or self._trigger_sig(old.get("tts", {}).get("hotkey")) != self._trigger_sig(new_tts)
            or str(old.get("stt", {}).get("backend", STTConfig.backend)) != new_stt_backend
            or str(old.get("stt", {}).get("model", STTConfig.model)) != new_stt_model
        )

    def markDirty_(self, _sender):  # noqa: N802
        self._recompute_dirty()

    def controlTextDidChange_(self, _notif):  # noqa: N802
        self._recompute_dirty()

    def comboBoxSelectionDidChange_(self, _notif):  # noqa: N802
        self._recompute_dirty()  # picking a recommendation from a model combo

    # -- trigger rows (keyboard + mouse, both live; #54) ----------------------

    # -- friendly mouse-button picker (index-mapped popup) --------------------

    @objc.python_method
    def _mouse_labels(self):
        idx = 0 if self._uilang == "ru" else 1
        return [pair[idx] for _k, _key, pair in MOUSE_BUTTONS]

    @objc.python_method
    def _mouse_custom_label(self, kind, key):
        return self._t("mouse_custom_side" if kind == "mouse_side" else "mouse_custom_btn").format(key)

    @objc.python_method
    def _reset_mouse_popup(self, popup, mapping):
        popup.removeAllItems()
        popup.addItemsWithTitles_(self._mouse_labels())
        mapping[:] = [(k, key) for k, key, _ in MOUSE_BUTTONS]

    @objc.python_method
    def _select_mouse(self, popup, mapping, kind, key):
        """Select the (kind,key) button; an unlisted one (e.g. a captured side №6)
        is appended as a custom item so it round-trips."""
        target = (str(kind), str(key))
        for i, mk in enumerate(mapping):
            if mk == target:
                popup.selectItemAtIndex_(i)
                return
        popup.addItemWithTitle_(self._mouse_custom_label(kind, key))
        mapping.append(target)
        popup.selectItemAtIndex_(len(mapping) - 1)

    @objc.python_method
    def _mouse_value(self, popup, mapping):
        i = int(popup.indexOfSelectedItem())
        return mapping[i] if 0 <= i < len(mapping) else ("mouse_side", "3")

    # -- trigger rows (keyboard + mouse, both live; #54/#58) ------------------

    @objc.python_method
    def _fill_trigger(self, kb_on, kb_field, ms_on, ms_popup, ms_map, raw, default_ms_key,
                      default_kb_key=""):
        """Spread a config 'hotkey' (legacy single or a list) across the two rows;
        a present binding ticks that row's on/off checkbox.

        ``default_kb_key`` is a *suggested* keyboard combo shown in the keyboard row
        when the config has no keyboard binding — pre-filled but left OFF (the row's
        checkbox stays unticked, so it isn't saved/active until the user enables it).
        A real keyboard binding in the config overrides the suggestion and ticks it."""
        bindings = _hotkey_bindings(raw)
        kb_field.setStringValue_(default_kb_key); kb_on.setState_(0)
        self._reset_mouse_popup(ms_popup, ms_map)
        self._select_mouse(ms_popup, ms_map, "mouse_side", default_ms_key)
        ms_on.setState_(0)
        if not bindings:  # fresh/empty config -> the side-button binding, enabled
            ms_on.setState_(1)
            return
        for b in bindings:
            kind = str(b.get("kind", ""))
            key = str(b.get("key", ""))
            if kind == "keyboard":
                kb_field.setStringValue_(key); kb_on.setState_(1)
            elif kind in ("mouse_side", "mouse"):
                self._select_mouse(ms_popup, ms_map, kind, key); ms_on.setState_(1)

    @objc.python_method
    def _collect_trigger(self, kb_on, kb_field, ms_on, ms_popup, ms_map):
        """The two rows -> a list of bindings (an off/locked row is skipped)."""
        out = []
        if bool(kb_on.state()):
            combo = str(kb_field.stringValue()).strip()
            if combo:
                out.append({"kind": "keyboard", "key": combo})
        if bool(ms_on.state()):
            kind, key = self._mouse_value(ms_popup, ms_map)
            out.append({"kind": kind, "key": key})
        return out

    @objc.python_method
    def _trigger_sig(self, raw):
        """Order-independent signature of a trigger's bindings, so a legacy single
        {kind,key} and the equivalent one-item list compare equal."""
        return frozenset(
            (str(b.get("kind", "")), str(b.get("key", ""))) for b in _hotkey_bindings(raw)
        )

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
        self._uilang_popup.selectItemAtIndex_(0 if self._uilang == "ru" else 1)
        llm = data.get("llm", {})
        tts = data.get("tts", {})
        backend = llm.get("backend", "ollama")
        ctype = _conn_type_of(backend)
        for rb, tkey in self._conn_radios:
            rb.setState_(1 if tkey == ctype else 0)
        self._provider.selectItemWithTitle_("OpenAI" if backend == "openai" else "Anthropic")
        self._refresh_api_models()
        model = str(llm.get("model", "claude-haiku-4-5"))
        self._api_model.setStringValue_(model)
        self._cc_model.setStringValue_(model)
        # per-provider model memory (#F2): the loaded provider keeps its model, the
        # other starts at its own default.
        self._last_provider = str(self._provider.titleOfSelectedItem())
        self._model_by_provider = {"Anthropic": ANTHROPIC_MODELS[0], "OpenAI": OPENAI_MODELS[0]}
        self._model_by_provider[self._last_provider] = model
        self._ollama_model_value = str(llm.get("ollama_model", "qwen2.5:7b"))
        self._refresh_ollama_model_popup()  # shows the saved model now; the live check adds the rest
        self._ollama_url.setStringValue_(str(llm.get("ollama_url", "http://localhost:11434")))
        self._ollama_token.setStringValue_(self._read_env().get("OLLAMA_API_KEY", ""))
        self._set_api_key(self._read_env().get(self._provider_env_var(), ""))
        self._api_show.setState_(0)
        self._api_key.setHidden_(False)
        self._api_key_plain.setHidden_(True)
        self._apply_conn_visibility()
        self._start_ollama_check()  # populate the Models tab (status + installed list) on open
        stt = data.get("stt", {})
        self._stt_backend.selectItemWithTitle_(stt.get("backend", "auto"))
        self._stt_model.selectItemWithTitle_(str(stt.get("model", "small")))
        self._lang.selectItemWithTitle_(data.get("language", "ru"))
        self._fill_trigger(self._wheel_kb_on, self._wheel_kb, self._wheel_ms_on,
                           self._wheel_ms, self._wheel_ms_map, data.get("hotkey"), "3",
                           WHEEL_KB_DEFAULT)
        self._fill_trigger(self._tts_kb_on, self._tts_kb, self._tts_ms_on,
                           self._tts_ms, self._tts_ms_map, tts.get("hotkey"), "4",
                           TTS_KB_DEFAULT)
        self._select_voice(tts)
        self._tts_enabled.setState_(1 if tts.get("enabled", True) else 0)
        self._refresh_trigger_states()
        self._concurrent.setState_(1 if data.get("concurrent", False) else 0)
        for r in list(self._rules):   # clear any existing rule rows
            self._rules_stack.removeView_(r["row"])
        self._rules = []
        for key, ov in (data.get("sector_models") or {}).items():
            if isinstance(ov, dict):  # skip the "_comment" string
                self._make_rule_row(key, ov.get("backend", "ollama"), ov.get("model", ""))
        self._refresh_add_button()
        self._note.setStringValue_("")
        self._capture_baseline()

    def save_(self, _sender):  # noqa: N802
        old = self._read()
        new_lang = "ru" if int(self._uilang_popup.indexOfSelectedItem()) == 0 else "en"
        data = self._read()
        data["ui_language"] = new_lang
        data.setdefault("llm", {})
        ctype = self._selected_conn_type()
        if ctype == "ollama":
            data["llm"]["backend"] = "ollama"
            data["llm"]["ollama_model"] = str(self._ollama.titleOfSelectedItem() or "").strip()
            url = str(self._ollama_url.stringValue()).strip()
            data["llm"]["ollama_url"] = url or "http://localhost:11434"
        elif ctype == "api":
            data["llm"]["backend"] = self._current_backend()  # anthropic | openai
            data["llm"]["model"] = str(self._api_model.stringValue()).strip()
            self._write_env_key(self._provider_env_var(), self._api_key_value().strip())
        else:  # Claude Code
            data["llm"]["backend"] = "claude_warm"
            data["llm"]["model"] = str(self._cc_model.stringValue()).strip()
        # optional Ollama bearer token (remote/hosted auth) -> .env, applies at once
        self._write_env_key("OLLAMA_API_KEY", str(self._ollama_token.stringValue()).strip())
        data.setdefault("stt", {})
        data["stt"]["backend"] = str(self._stt_backend.titleOfSelectedItem())
        data["stt"]["model"] = str(self._stt_model.titleOfSelectedItem())
        data["language"] = str(self._lang.titleOfSelectedItem())
        data["hotkey"] = self._collect_trigger(
            self._wheel_kb_on, self._wheel_kb, self._wheel_ms_on,
            self._wheel_ms, self._wheel_ms_map,
        )
        if not data["hotkey"]:  # never let the wheel become un-triggerable (F1)
            self._note.setStringValue_(self._t("note_no_trigger"))
            return
        data.setdefault("tts", {})
        data["tts"]["enabled"] = bool(self._tts_enabled.state())
        data["tts"]["hotkey"] = self._collect_trigger(
            self._tts_kb_on, self._tts_kb, self._tts_ms_on,
            self._tts_ms, self._tts_ms_map,
        )
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
        # Some settings can't be swapped live: the language (menu bar + all chrome),
        # the triggers (the event tap / pynput listeners) and the STT model (Whisper
        # reload). When any of those changed, restart the app — that applies them
        # cleanly, instead of asking the user to quit and relaunch by hand (#50).
        needs_restart = self._restart_changed(
            old, new_lang, data["hotkey"], data["tts"]["hotkey"],
            data["stt"]["backend"], data["stt"]["model"],
        )
        if needs_restart and self._restart_cb is not None:
            try:  # so the restarted app can reopen settings on the tab we were on
                (app_support_dir() / "reopen_settings").write_text(
                    str(self._tabs.selectedTabViewItem().identifier()), encoding="utf-8"
                )
            except OSError as exc:
                log.debug("could not write reopen marker: %s", exc)
            self._note.setStringValue_(self._t("note_restarting"))
            self._set_dirty(False)
            self._restart_cb()  # cleans up + re-execs; does not return
            return
        if self._apply_cb is not None:
            try:
                self._apply_cb()
            except Exception as exc:  # noqa: BLE001 - never let live-apply break Save
                log.warning("live-apply failed: %s", exc)
        self._capture_baseline()  # the just-saved form is the new baseline
        # Warn (don't block) if the cloud LLM was chosen but no key is set (#F5).
        if ctype == "api" and not self._api_key_value().strip():
            self._note.setStringValue_(self._t("note_api_no_key"))
        else:
            self._note.setStringValue_("")
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

    # -- connection type (#36): radios + per-type setting groups --------------

    @objc.python_method
    def _selected_conn_type(self):
        for rb, tkey in self._conn_radios:
            if rb.state():
                return tkey
        return "ollama"

    @objc.python_method
    def _apply_conn_visibility(self):
        """Show only the selected type's settings group (NSStackView collapses the
        hidden ones, so there's no empty gap)."""
        t = self._selected_conn_type()
        self._grp_api.setHidden_(t != "api")
        self._grp_ollama.setHidden_(t != "ollama")
        self._grp_cc.setHidden_(t != "cc")

    @objc.python_method
    def _current_backend(self):
        """The backend value implied by the current type + provider (for rule defaults)."""
        t = self._selected_conn_type()
        if t == "ollama":
            return "ollama"
        if t == "api":
            return "openai" if str(self._provider.titleOfSelectedItem()) == "OpenAI" else "anthropic"
        return "claude_warm"

    @objc.python_method
    def _current_model(self):
        t = self._selected_conn_type()
        if t == "ollama":
            return str(self._ollama.titleOfSelectedItem() or "")
        if t == "api":
            return str(self._api_model.stringValue())
        return str(self._cc_model.stringValue())

    def connTypeChanged_(self, sender):  # noqa: N802
        for rb, _ in self._conn_radios:
            rb.setState_(1 if rb == sender else 0)
        self._apply_conn_visibility()
        if self._selected_conn_type() == "ollama":
            self._start_ollama_check()
        self._recompute_dirty()

    @objc.python_method
    def _provider_models(self):
        return OPENAI_MODELS if str(self._provider.titleOfSelectedItem()) == "OpenAI" else ANTHROPIC_MODELS

    @objc.python_method
    def _refresh_api_models(self):
        self._api_model.removeAllItems()
        self._api_model.addItemsWithObjectValues_(self._provider_models())

    def providerChanged_(self, _sender):  # noqa: N802
        # Remember the model per provider so switching back restores it (#F2),
        # instead of silently clobbering a typed/custom model.
        self._model_by_provider[self._last_provider] = str(self._api_model.stringValue())
        new_provider = str(self._provider.titleOfSelectedItem())
        self._last_provider = new_provider
        self._refresh_api_models()
        self._api_model.setStringValue_(
            self._model_by_provider.get(new_provider) or self._provider_models()[0]
        )
        self._set_api_key(self._read_env().get(self._provider_env_var(), ""))
        self._recompute_dirty()

    # -- API key field: masked + «Показать» reveal (#F4) ----------------------

    @objc.python_method
    def _api_key_value(self):
        f = self._api_key_plain if not self._api_key_plain.isHidden() else self._api_key
        return str(f.stringValue())

    @objc.python_method
    def _set_api_key(self, value):
        self._api_key.setStringValue_(value)
        self._api_key_plain.setStringValue_(value)

    def toggleKeyVisibility_(self, sender):  # noqa: N802
        if bool(sender.state()):  # reveal: copy into the plain field and show it
            self._api_key_plain.setStringValue_(str(self._api_key.stringValue()))
            self._api_key.setHidden_(True)
            self._api_key_plain.setHidden_(False)
        else:  # re-mask
            self._api_key.setStringValue_(str(self._api_key_plain.stringValue()))
            self._api_key_plain.setHidden_(True)
            self._api_key.setHidden_(False)

    # -- Ollama model download (#39) ------------------------------------------

    @staticmethod
    def _bearer(token):
        token = (token or "").strip()
        return {"Authorization": f"Bearer {token}"} if token else {}

    @objc.python_method
    def _ollama_token_value(self):
        return str(self._ollama_token.stringValue()).strip()

    def downloadOllama_(self, _sender):  # noqa: N802
        model = str(self._models_pull.stringValue()).strip()
        if not model:
            return
        url = str(self._ollama_url.stringValue()).strip() or "http://localhost:11434"
        token = self._ollama_token_value()
        self._models_dl_btn.setEnabled_(False)
        self._note.setStringValue_(self._t("models_downloading").format(model))
        threading.Thread(target=self._pull_ollama, args=(model, url, token), daemon=True).start()

    @objc.python_method
    def _pull_ollama(self, model, url, token):
        """Stream the pull from Ollama's /api/pull so we can show live % progress.
        Each JSON line carries total/completed bytes; we push the percent to the note
        on the main thread, throttled to whole-percent changes."""
        import requests

        ok, error, last_pct = False, False, -1
        try:
            with requests.post(f"{url}/api/pull", json={"model": model, "stream": True},
                               stream=True, timeout=(5, 1800), headers=self._bearer(token)) as r:
                r.raise_for_status()
                for raw in r.iter_lines():
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        continue
                    if obj.get("error"):
                        log.warning("ollama pull %s: %s", model, obj.get("error"))
                        error = True
                        break
                    total, done = obj.get("total") or 0, obj.get("completed") or 0
                    if total:
                        pct = int(done * 100 / total)
                        if pct != last_pct:
                            last_pct = pct
                            self._pull_progress = (model, pct, done / 1e9, total / 1e9)
                            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                                "ollamaPullProgress:", None, False)
            ok = not error
        except Exception as exc:  # noqa: BLE001 - ollama down / network / timeout
            log.warning("ollama pull %s failed: %s", model, exc)
            ok = False
        self._pull_result = (ok, model)
        self.performSelectorOnMainThread_withObject_waitUntilDone_("ollamaPullDone:", None, False)

    def ollamaPullProgress_(self, _arg):  # noqa: N802
        model, pct, done_gb, total_gb = self._pull_progress
        self._note.setStringValue_(
            self._t("models_downloading_pct").format(model, pct, done_gb, total_gb)
        )

    def ollamaPullDone_(self, _arg):  # noqa: N802
        ok, model = self._pull_result
        self._models_dl_btn.setEnabled_(True)
        self._note.setStringValue_(
            self._t("note_ollama_pulled" if ok else "note_ollama_pull_fail").format(model)
        )
        if ok:
            have = [str(self._models_pull.itemObjectValueAtIndex_(i))
                    for i in range(self._models_pull.numberOfItems())]
            if model not in have:
                self._models_pull.addItemWithObjectValue_(model)
            self._start_ollama_check()  # refresh installed list, status, and the LLM picker

    # -- Ollama status / install / restart (Models tab) -----------------------

    def recheckOllama_(self, _sender):  # noqa: N802
        self._start_ollama_check()

    @objc.python_method
    def _start_ollama_check(self):
        """Probe (in the background) whether Ollama is installed/running, its version
        and which models are installed, then reflect it on the Models tab."""
        self._ollama_status.setStringValue_(self._t("ollama_checking"))
        self._ollama_status.setTextColor_(NSColor.secondaryLabelColor())
        self._set_installed_message(self._t("models_installed_loading"))
        url = str(self._ollama_url.stringValue()).strip() or "http://localhost:11434"
        token = self._ollama_token_value()
        threading.Thread(target=self._check_ollama, args=(url, token), daemon=True).start()

    @objc.python_method
    def _check_ollama(self, url, token):
        import os
        import shutil

        installed = shutil.which("ollama") is not None or any(
            os.path.exists(p) for p in ("/usr/local/bin/ollama", "/opt/homebrew/bin/ollama")
        )
        headers = self._bearer(token)
        running, version, models = False, "", []
        try:
            import requests

            tags = requests.get(f"{url}/api/tags", timeout=1.5, headers=headers)
            running = True
            models = [(str(m.get("name", "")), int(m.get("size", 0)))
                      for m in (tags.json().get("models") or [])]
            try:
                version = str(requests.get(f"{url}/api/version", timeout=1.5,
                                           headers=headers).json().get("version", ""))
            except Exception:  # noqa: BLE001 - version is a nice-to-have
                version = ""
        except Exception:  # noqa: BLE001 - any failure = not reachable
            running = False
        self._ollama_state = "running" if running else ("not_running" if installed else "not_installed")
        self._ollama_version = version
        self._ollama_models = sorted(models)
        self.performSelectorOnMainThread_withObject_waitUntilDone_("ollamaStatusUpdated:", None, False)

    def ollamaStatusUpdated_(self, _arg):  # noqa: N802
        version = getattr(self, "_ollama_version", "")
        if self._ollama_state == "running" and version:
            self._ollama_status.setStringValue_(self._t("ollama_running_v").format(version))
            self._ollama_status.setTextColor_(NSColor.systemGreenColor())
        else:
            text_key, color = {
                "running": ("ollama_running", NSColor.systemGreenColor()),
                "not_running": ("ollama_not_running", NSColor.systemOrangeColor()),
                "not_installed": ("ollama_not_installed", NSColor.systemRedColor()),
            }.get(self._ollama_state, ("ollama_checking", NSColor.secondaryLabelColor()))
            self._ollama_status.setStringValue_(self._t(text_key))
            self._ollama_status.setTextColor_(color)
        if self._ollama_state == "not_installed":
            self._ollama_action.setTitle_(self._t("ollama_install_btn"))
            self._ollama_action.setHidden_(False)
        elif self._ollama_state == "not_running":
            self._ollama_action.setTitle_(self._t("ollama_start_btn"))
            self._ollama_action.setHidden_(False)
        else:
            self._ollama_action.setHidden_(True)
        self._update_installed_models()
        if self._ollama_state == "running":
            self._refresh_ollama_model_popup()
            for r in getattr(self, "_rules", []):  # rule rows on Ollama -> installed list
                if self._backend_value(r["engine"]) == "ollama":
                    self._refresh_rule_model_combo(r)

    @objc.python_method
    def _refresh_ollama_model_popup(self):
        """The LLM-tab model picker is a pure selector of INSTALLED models (download /
        manage on the Models tab). The configured model is kept selectable even if it
        isn't installed (so opening settings never silently changes the saved value)."""
        desired = str(self._ollama.titleOfSelectedItem() or "") or getattr(
            self, "_ollama_model_value", "")
        items = [name for name, _ in getattr(self, "_ollama_models", [])]
        if desired and desired not in items:
            items.insert(0, desired)
        self._ollama.removeAllItems()
        self._ollama.addItemsWithTitles_(items)
        if desired:
            self._ollama.selectItemWithTitle_(desired)

    @objc.python_method
    def _clear_installed(self):
        for v in list(self._models_installed.arrangedSubviews()):
            self._models_installed.removeView_(v)
        self._installed_rows = []

    @objc.python_method
    def _set_installed_message(self, text):
        self._clear_installed()
        lab = NSTextField.labelWithString_(text)
        lab.setFont_(NSFont.systemFontOfSize_(11))
        lab.setTextColor_(NSColor.secondaryLabelColor())
        self._models_installed.addArrangedSubview_(lab)

    @objc.python_method
    def _update_installed_models(self):
        models = getattr(self, "_ollama_models", [])
        if self._ollama_state != "running":
            self._set_installed_message("—")
            return
        if not models:
            self._set_installed_message(self._t("models_installed_none"))
            return

        def _sz(n):
            gb = n / 1e9
            return f"{gb:.1f} GB" if gb >= 0.1 else f"{n / 1e6:.0f} MB"

        self._clear_installed()
        for name, size in models:
            h = NSStackView.alloc().init()
            h.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
            h.setAlignment_(NSLayoutAttributeCenterY)
            h.setSpacing_(8)
            lab = NSTextField.labelWithString_(f"• {name}  ({_sz(size)})")
            lab.setFont_(NSFont.systemFontOfSize_(11))
            lab.setTextColor_(NSColor.secondaryLabelColor())
            lab.widthAnchor().constraintEqualToConstant_(260).setActive_(True)  # align the ✕
            btn = NSButton.buttonWithTitle_target_action_("✕", self, "deleteModel:")
            btn.widthAnchor().constraintEqualToConstant_(30).setActive_(True)
            btn.setToolTip_(self._t("model_delete_tip"))
            h.addArrangedSubview_(lab)
            h.addArrangedSubview_(btn)
            self._models_installed.addArrangedSubview_(h)
            self._installed_rows.append({"model": name, "btn": btn, "row": h})

    def deleteModel_(self, sender):  # noqa: N802
        from AppKit import NSAlert, NSAlertFirstButtonReturn

        rule = next((r for r in self._installed_rows if r["btn"] == sender), None)
        if rule is None:
            return
        model = rule["model"]
        alert = NSAlert.alloc().init()
        alert.setMessageText_(self._t("model_delete_confirm_title").format(model))
        alert.setInformativeText_(self._t("model_delete_confirm_body"))
        alert.addButtonWithTitle_(self._t("model_delete_btn"))  # default = Delete
        alert.addButtonWithTitle_(self._t("cancel"))
        if alert.runModal() != NSAlertFirstButtonReturn:
            return
        sender.setEnabled_(False)
        self._note.setStringValue_(self._t("model_removing").format(model))
        threading.Thread(target=self._remove_ollama, args=(model,), daemon=True).start()

    @objc.python_method
    def _remove_ollama(self, model):
        import subprocess

        ok = False
        try:
            proc = subprocess.run(["ollama", "rm", model], capture_output=True, text=True, timeout=60)
            ok = proc.returncode == 0
            if not ok:
                log.warning("ollama rm %s: %s", model, (proc.stderr or proc.stdout or "")[:200])
        except Exception as exc:  # noqa: BLE001 - ollama missing / not running / timeout
            log.warning("ollama rm %s failed: %s", model, exc)
        self._remove_result = (ok, model)
        self.performSelectorOnMainThread_withObject_waitUntilDone_("ollamaRemoveDone:", None, False)

    def ollamaRemoveDone_(self, _arg):  # noqa: N802
        ok, model = self._remove_result
        self._note.setStringValue_(
            self._t("model_removed" if ok else "model_remove_fail").format(model)
        )
        self._start_ollama_check()  # refresh installed list + status + the model pickers

    def ollamaAction_(self, _sender):  # noqa: N802
        if self._ollama_state == "not_installed":
            from AppKit import NSWorkspace
            from Foundation import NSURL

            NSWorkspace.sharedWorkspace().openURL_(
                NSURL.URLWithString_("https://ollama.com/download")
            )
        elif self._ollama_state == "not_running":
            self._note.setStringValue_(self._t("ollama_starting"))
            threading.Thread(target=self._start_ollama_serve, daemon=True).start()

    def restartOllama_(self, _sender):  # noqa: N802
        self._note.setStringValue_(self._t("ollama_restarting"))
        threading.Thread(target=self._restart_ollama_serve, daemon=True).start()

    def openOllamaLibrary_(self, _sender):  # noqa: N802
        from AppKit import NSWorkspace
        from Foundation import NSURL

        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_("https://ollama.com/library"))

    @objc.python_method
    def _start_ollama_serve(self):
        import subprocess
        import time

        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("ollama serve failed: %s", exc)
        time.sleep(2.0)  # let it bind the port, then re-check on the main thread
        self.performSelectorOnMainThread_withObject_waitUntilDone_("recheckOllama:", None, False)

    @objc.python_method
    def _restart_ollama_serve(self):
        """Restart the Ollama daemon: prefer brew (the usual managed service), else
        kill + relaunch. Re-checks afterwards so the user sees the state change."""
        import shutil
        import subprocess
        import time

        try:
            if shutil.which("brew"):
                subprocess.run(["brew", "services", "restart", "ollama"],
                               capture_output=True, timeout=60)
            else:
                subprocess.run(["pkill", "-x", "ollama"], capture_output=True)
                time.sleep(1.0)
                subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("ollama restart failed: %s", exc)
        time.sleep(2.0)
        self.performSelectorOnMainThread_withObject_waitUntilDone_("recheckOllama:", None, False)

    # -- API key storage in .env (#38) ----------------------------------------

    @objc.python_method
    def _provider_env_var(self):
        return "OPENAI_API_KEY" if str(self._provider.titleOfSelectedItem()) == "OpenAI" else "ANTHROPIC_API_KEY"

    @objc.python_method
    def _env_path(self):
        return _project_root() / ".env"

    @objc.python_method
    def _read_env(self) -> dict:
        return read_env(self._env_path())

    @objc.python_method
    def _write_env_key(self, var: str, value: str) -> None:
        try:
            write_env_key(self._env_path(), var, value)
        except OSError as exc:
            log.warning("could not write .env: %s", exc)

    # -- per-tab reset to defaults (#51) -------------------------------------
    # «Сброс» (bottom bar) resets the *active* tab's controls to the config
    # dataclass defaults; nothing is saved until «Сохранить», so a reset can
    # still be backed out by closing the window.

    def resetCurrentTab_(self, _sender):  # noqa: N802
        ident = str(self._tabs.selectedTabViewItem().identifier())
        reset = {
            "tab_llm": self.resetLlm_,
            "tab_stt": self.resetStt_,
            "tab_voice": self.resetVoice_,
            "tab_triggers": self.resetTriggers_,
            "tab_lang": self.resetLang_,
        }.get(ident)
        if reset is None:
            return
        reset(_sender)
        # Save reflects the whole form vs the saved baseline, so a reset that lands
        # back on the saved values leaves Save disabled (nothing to save).
        self._recompute_dirty()

    @objc.python_method
    def _tab_snapshot(self, ident):
        """A comparable view of a tab's config-relevant control values, so a reset
        that lands on values already in place doesn't needlessly arm Save."""
        if ident == "tab_llm":
            rules = tuple(
                (self._rule_sector_key(r), self._backend_value(r["engine"]),
                 str(r["model"].stringValue()))
                for r in self._rules
            )
            return (self._selected_conn_type(), str(self._provider.titleOfSelectedItem()),
                    self._api_key_value(), str(self._api_model.stringValue()),
                    str(self._ollama.titleOfSelectedItem() or ""), str(self._ollama_url.stringValue()),
                    str(self._ollama_token.stringValue()), str(self._cc_model.stringValue()), rules)
        if ident == "tab_stt":
            return (str(self._stt_backend.titleOfSelectedItem()),
                    str(self._stt_model.titleOfSelectedItem()),
                    str(self._lang.titleOfSelectedItem()))
        if ident == "tab_voice":
            return (int(self._tts_enabled.state()), int(self._tts_voice.indexOfSelectedItem()),
                    int(self._tts_kb_on.state()), str(self._tts_kb.stringValue()),
                    int(self._tts_ms_on.state()), self._mouse_value(self._tts_ms, self._tts_ms_map))
        if ident == "tab_triggers":
            return (int(self._wheel_kb_on.state()), str(self._wheel_kb.stringValue()),
                    int(self._wheel_ms_on.state()), self._mouse_value(self._wheel_ms, self._wheel_ms_map),
                    int(self._concurrent.state()))
        if ident == "tab_lang":
            return (int(self._uilang_popup.indexOfSelectedItem()),)
        return ()

    def resetLlm_(self, _sender):  # noqa: N802
        from ...core.config import LLMConfig

        d = LLMConfig()  # default backend = ollama
        for rb, tkey in self._conn_radios:
            rb.setState_(1 if tkey == _conn_type_of(d.backend) else 0)
        self._provider.selectItemWithTitle_("Anthropic")
        self._refresh_api_models()
        self._api_model.setStringValue_(d.model)
        self._cc_model.setStringValue_(d.model)
        self._ollama_model_value = d.ollama_model
        self._refresh_ollama_model_popup()
        self._ollama_url.setStringValue_(d.ollama_url)
        self._apply_conn_visibility()
        for r in list(self._rules):  # drop every per-prompt rule
            self._rules_stack.removeView_(r["row"])
        self._rules = []
        self._refresh_add_button()

    def resetStt_(self, _sender):  # noqa: N802
        from ...core.config import STTConfig

        d = STTConfig()
        self._stt_backend.selectItemWithTitle_(d.backend)
        self._stt_model.selectItemWithTitle_(d.model)
        self._lang.selectItemWithTitle_("ru")

    def resetVoice_(self, _sender):  # noqa: N802
        from ...core.config import TTSConfig

        d = TTSConfig()
        self._tts_enabled.setState_(1 if d.enabled else 0)
        self._select_voice({"backend": d.backend, "piper_voice": d.piper_voice})
        self._fill_trigger(
            self._tts_kb_on, self._tts_kb, self._tts_ms_on, self._tts_ms, self._tts_ms_map,
            [{"kind": h.kind, "key": h.key} for h in d.hotkeys], "4", TTS_KB_DEFAULT,
        )
        self._refresh_trigger_states()

    def resetTriggers_(self, _sender):  # noqa: N802
        from ...core.config import HotkeyConfig

        d = HotkeyConfig()
        self._fill_trigger(
            self._wheel_kb_on, self._wheel_kb, self._wheel_ms_on, self._wheel_ms, self._wheel_ms_map,
            [{"kind": d.kind, "key": d.key}], "3", WHEEL_KB_DEFAULT,
        )
        self._concurrent.setState_(0)
        self._refresh_trigger_states()

    def resetLang_(self, _sender):  # noqa: N802
        default = detect_ui_lang()  # back to the system default
        self._uilang_popup.selectItemAtIndex_(0 if default == "ru" else 1)

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
        prompt.setTarget_(self)
        prompt.setAction_("markDirty:")
        lbl = next((s.label for s in self._sectors if s.key == sector_key), None)
        if lbl:
            prompt.selectItemWithTitle_(lbl)
        engine = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 150, 26), False)
        engine.addItemsWithTitles_(self._backend_labels())
        engine.widthAnchor().constraintEqualToConstant_(150).setActive_(True)
        engine.setTarget_(self)
        engine.setAction_("ruleEngineChanged:")  # repopulate the model dropdown + mark dirty
        self._select_backend(engine, backend)
        # editable combo: dropdown lists the engine's models (installed ones for
        # Ollama), but you can still type a custom name.
        model_combo = NSComboBox.alloc().initWithFrame_(NSMakeRect(0, 0, 150, 26))
        model_combo.widthAnchor().constraintEqualToConstant_(150).setActive_(True)
        model_combo.setCompletes_(True)
        model_combo.addItemsWithObjectValues_(self._rule_models_for(backend))
        model_combo.setStringValue_(str(model or ""))
        model_combo.setDelegate_(self)
        delete = NSButton.buttonWithTitle_target_action_("✕", self, "deleteRule:")
        delete.widthAnchor().constraintEqualToConstant_(32).setActive_(True)
        for c in (prompt, engine, model_combo, delete):
            h.addArrangedSubview_(c)
        self._rules.append(
            {"row": h, "prompt": prompt, "engine": engine, "model": model_combo, "delete": delete}
        )
        self._rules_stack.addArrangedSubview_(h)

    @objc.python_method
    def _rule_models_for(self, backend):
        """The model suggestions for a rule's chosen engine — installed Ollama models
        (or the curated defaults if none are known yet), else the per-provider lists."""
        if backend == "ollama":
            installed = [name for name, _ in getattr(self, "_ollama_models", [])]
            return installed or OLLAMA_MODELS
        return {"anthropic": ANTHROPIC_MODELS, "openai": OPENAI_MODELS,
                "claude_warm": CC_MODELS, "claude_cli": CC_MODELS}.get(backend, [])

    @objc.python_method
    def _refresh_rule_model_combo(self, rule):
        cb = rule["model"]
        cur = str(cb.stringValue())
        cb.removeAllItems()
        cb.addItemsWithObjectValues_(self._rule_models_for(self._backend_value(rule["engine"])))
        cb.setStringValue_(cur)

    def ruleEngineChanged_(self, sender):  # noqa: N802
        rule = next((r for r in self._rules if r["engine"] == sender), None)
        if rule is not None:
            self._refresh_rule_model_combo(rule)
        self.markDirty_(sender)

    def addRule_(self, _sender):  # noqa: N802
        key = self._first_unassigned()
        if key is None:
            return
        # default a new rule to the base connection's backend + model
        self._make_rule_row(key, self._current_backend(), self._current_model())
        self._refresh_add_button()
        self._recompute_dirty()

    def deleteRule_(self, sender):  # noqa: N802
        rule = next((r for r in self._rules if r["delete"] == sender), None)
        if rule is None:
            return
        self._rules_stack.removeView_(rule["row"])
        self._rules.remove(rule)
        self._refresh_add_button()
        self._recompute_dirty()

    @objc.python_method
    def _refresh_trigger_states(self):
        """Each trigger row's checkbox enables/disables its own controls; an off row
        is locked. The TTS rows (and voice/premium) are additionally gated on the
        master 'TTS enabled' checkbox."""
        tts_on = bool(self._tts_enabled.state())
        self._tts_voice.setEnabled_(tts_on)
        self._prem.setEnabled_(tts_on)
        rows = (
            (self._wheel_kb_on, (self._wheel_kb, self._cap_wheel_kb), True),
            (self._wheel_ms_on, (self._wheel_ms, self._cap_wheel_ms), True),
            (self._tts_kb_on, (self._tts_kb, self._cap_tts_kb), tts_on),
            (self._tts_ms_on, (self._tts_ms, self._cap_tts_ms), tts_on),
        )
        for cb, controls, gate in rows:
            cb.setEnabled_(gate)
            enabled = gate and bool(cb.state())
            for c in controls:
                c.setEnabled_(enabled)

    def triggerToggled_(self, _sender):  # noqa: N802
        self._refresh_trigger_states()
        self._recompute_dirty()

    def ttsEnabledChanged_(self, _sender):  # noqa: N802
        self._refresh_trigger_states()
        self._recompute_dirty()

    # -- key capture ("Поймать") ---------------------------------------------
    # Two flavours: keyboard-only (writes a combo into the keyboard field) and
    # mouse-only (writes kind+key into the mouse row). Filtering by accepted kind
    # means the keyboard «Поймать» ignores mouse clicks and vice-versa.

    def captureWheelKb_(self, _sender):  # noqa: N802
        self._begin_capture(_sender, "keyboard",
                            lambda k, key: self._wheel_kb.setStringValue_(key))

    def captureWheelMs_(self, _sender):  # noqa: N802
        self._begin_capture(_sender, "mouse",
                            lambda k, key: self._select_mouse(self._wheel_ms, self._wheel_ms_map, k, key))

    def captureTtsKb_(self, _sender):  # noqa: N802
        self._begin_capture(_sender, "keyboard",
                            lambda k, key: self._tts_kb.setStringValue_(key))

    def captureTtsMs_(self, _sender):  # noqa: N802
        self._begin_capture(_sender, "mouse",
                            lambda k, key: self._select_mouse(self._tts_ms, self._tts_ms_map, k, key))

    @objc.python_method
    def _begin_capture(self, button, accept, write):
        """Catch the next key/combo (accept='keyboard') or mouse button
        (accept='mouse') and hand (kind, key) to ``write``. (A side button already
        bound to a trigger is swallowed by our event tap — press Esc to cancel.)"""
        if self._capture_monitor is not None:
            return  # already catching
        old_title = str(button.title())
        button.setTitle_(self._t("catching"))
        self._note.setStringValue_(self._t("note_capture_prompt"))
        if accept == "keyboard":
            mask = NSEventMaskKeyDown
            wanted = ("keyboard",)
        else:
            mask = NSEventMaskOtherMouseDown | NSEventMaskRightMouseDown
            wanted = ("mouse_side", "mouse")

        def handler(event):
            kind, key = _capture_kind_key(event)
            if kind is None:
                return None  # unrecognized — keep waiting
            if kind != "cancel" and kind in wanted:
                write(kind, key)
                self._note.setStringValue_(self._t("note_capture_caught").format(kind, key))
                self._recompute_dirty()
            elif kind != "cancel":
                return None  # wrong device for this row — keep waiting
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
        self._recompute_dirty()

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
        backend = tts.get("backend", TTSConfig.backend)  # single source of truth (#H1)
        pv = tts.get("piper_voice", TTSConfig.piper_voice)
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
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
