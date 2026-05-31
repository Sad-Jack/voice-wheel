"""Interface translations (RU/EN) shared by the settings window and the menu bar.

Every user-facing chrome string lives in ``STR`` as a ``(ru, en)`` pair. The
language is chosen by the user (settings → «Язык») or follows the system locale
by default; it is stored in ``config.json`` as ``ui_language`` and applied at
launch, so a change takes effect after the app restarts (see settings save).

``t(key, lang)`` resolves a string; ``resolve_lang`` turns a stored value (which
may be empty = "follow the system") into a concrete ``'ru'`` / ``'en'``.
"""

from __future__ import annotations

STR = {
    # window / tabs
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
    "reset_tab": ("Сброс", "Reset"),
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
    "stt_restart": (
        "⏱ Движок и модель распознавания применяются после перезапуска.",
        "⏱ Recognition engine and model apply after a restart.",
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
    "trig_kb": ("Клавиатура", "Keyboard"),
    "trig_mouse": ("Мышь", "Mouse"),
    "trig_hint": (
        "Обе строки работают одновременно. «Поймать» → нажми нужную клавишу/комбо или кнопку мыши.",
        "Both rows are live at once. «Catch» → press the key/combo or mouse button you want.",
    ),
    "trig_mouse_hint": (
        "Мышь можно оставить пустой, если её нет — хватит клавиатуры.",
        "Leave the mouse row empty if you have no mouse — the keyboard is enough.",
    ),
    "trig_restart": (
        "⏱ Триггеры применяются после перезапуска приложения.",
        "⏱ Triggers apply after the app restarts.",
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
        "Меняет язык всего приложения (меню и настройки). По умолчанию — как в системе.",
        "Changes the language of the whole app (menu and settings). Defaults to your system.",
    ),
    "lang_restart_warn": (
        "⚠️ После «Сохранить» приложение перезапустится, чтобы сменить язык.",
        "⚠️ After «Save» the app will restart to change the language.",
    ),
    # buttons / runtime notes
    "catch": ("Поймать", "Catch"),
    "catching": ("нажми…", "press…"),
    "save": ("Сохранить", "Save"),
    "note_save_fail": ("⚠️ Не удалось сохранить: {}", "⚠️ Couldn't save: {}"),
    "note_restarting": (
        "Сохранено. Перезапускаю приложение…",
        "Saved. Restarting the app…",
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
    # menu bar
    "menu_history": ("История", "History"),
    "menu_settings": ("Настройки…", "Settings…"),
    "menu_quit": ("Выход", "Quit"),
    "menu_empty": ("(пусто)", "(empty)"),
    # console
    "ready_msg": (
        "Voice Wheel готов. Зажми {}, говори, отпусти. "
        "Центр = текст, сектор = стиль. Ctrl+C для выхода.",
        "Voice Wheel ready. Hold {}, speak, release. "
        "Center = text, sector = style. Ctrl+C to quit.",
    ),
}


def detect_ui_lang() -> str:
    """System locale → 'ru' if the preferred language is Russian, else 'en'."""
    try:
        from Foundation import NSLocale

        langs = NSLocale.preferredLanguages()
        code = str(langs[0]) if langs and len(langs) else ""
    except Exception:  # noqa: BLE001 - never let locale probing break startup
        code = ""
    return "ru" if code.lower().startswith("ru") else "en"


def resolve_lang(value: str | None) -> str:
    """A stored ui_language ("", 'ru', 'en') → a concrete 'ru'/'en' (detect if empty)."""
    if value in ("ru", "en"):
        return value
    return detect_ui_lang()


def t(key: str, lang: str) -> str:
    """Translate a chrome-string key for the given interface language."""
    return STR[key][0 if lang == "ru" else 1]
