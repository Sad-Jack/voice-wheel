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
        "Откуда брать ИИ, который превращает речь в результат под промпт сектора.",
        "Where the AI that turns speech into the sector-prompt result comes from.",
    ),
    "conn_api": ("Прямой API (облако, по ключу)", "Direct API (cloud, by key)"),
    "conn_ollama": ("Ollama (локально, бесплатно)", "Ollama (local, free)"),
    "conn_cc": ("Claude Code (CLI, подписка Max)", "Claude Code (CLI, Max plan)"),
    "provider": ("Провайдер", "Provider"),
    "api_key": ("API-ключ", "API key"),
    "api_key_hint": (
        "Ключ хранится в .env (в .gitignore). Anthropic: console.anthropic.com → API Keys. "
        "OpenAI: platform.openai.com → API keys. Применяется сразу.",
        "The key is stored in .env (gitignored). Anthropic: console.anthropic.com → API Keys. "
        "OpenAI: platform.openai.com → API keys. Applies immediately.",
    ),
    "download": ("Скачать", "Download"),
    "note_ollama_pull": (
        "Скачиваю модель «{}»… (ollama pull, идёт в фоне)",
        "Downloading model «{}»… (ollama pull, in the background)",
    ),
    "note_ollama_pulled": ("Модель «{}» скачана.", "Model «{}» downloaded."),
    "note_ollama_pull_fail": (
        "Не удалось скачать «{}». Установлена и запущена ли Ollama? (ollama serve)",
        "Couldn't download «{}». Is Ollama installed and running? (ollama serve)",
    ),
    "ollama_url": ("URL", "URL"),
    "ollama_hint": (
        "Локальная модель через Ollama — должна быть установлена и запущена (ollama serve). "
        "URL обычно не трогаем.",
        "A local model via Ollama — it must be installed and running (ollama serve). "
        "The URL is usually left as-is.",
    ),
    "ollama_checking": ("Проверяю Ollama…", "Checking Ollama…"),
    "ollama_running": ("✅ Ollama запущена", "✅ Ollama is running"),
    "ollama_not_running": (
        "⚠️ Ollama установлена, но не запущена",
        "⚠️ Ollama is installed but not running",
    ),
    "ollama_not_installed": ("❌ Ollama не установлена", "❌ Ollama is not installed"),
    "ollama_install_btn": ("Установить Ollama…", "Install Ollama…"),
    "ollama_start_btn": ("Запустить Ollama", "Start Ollama"),
    "ollama_recheck_btn": ("Проверить", "Re-check"),
    "ollama_starting": ("Запускаю Ollama…", "Starting Ollama…"),
    "cc_hint": (
        "Через установленный claude CLI на подписке Max (без ключа). "
        "Установи Claude Code и выполни claude login.",
        "Via the installed claude CLI on the Max plan (no key). "
        "Install Claude Code and run claude login.",
    ),
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
        "⏱ Смена движка/модели распознавания перезапустит приложение при «Сохранить».",
        "⏱ Changing the recognition engine/model restarts the app on «Save».",
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
    "trig_check_hint": (
        "Галочка слева включает/выключает вид триггера; выключенный — заблокирован. "
        "Хотя бы один должен быть включён.",
        "The checkbox on the left enables/disables a trigger type; a disabled one is "
        "locked. At least one must be enabled.",
    ),
    "note_no_trigger": (
        "Включи хотя бы один триггер записи (клавиатуру или мышь).",
        "Enable at least one record trigger (keyboard or mouse).",
    ),
    "tip_trig_toggle": (
        "Галочка — включить/выключить этот вид триггера.",
        "Checkbox — enable/disable this trigger type.",
    ),
    "trig_restart": (
        "⏱ Смена триггера применится сразу: при «Сохранить» приложение перезапустится.",
        "⏱ A trigger change applies right away: the app restarts on «Save».",
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
    # first-run onboarding (#42)
    "onboard_title": (
        "Добро пожаловать в Voice Wheel!",
        "Welcome to Voice Wheel!",
    ),
    "onboard_body": (
        "Чтобы обрабатывать речь через ИИ, настрой подключение:\n\n"
        "1) Выбери способ — Ollama (локально, бесплатно), Прямой API (по ключу) "
        "или Claude Code.\n"
        "2) Выбери или скачай модель.\n"
        "3) Нажми «Сохранить».\n\n"
        "Без настройки распознавание речи всё равно работает — просто без обработки ИИ.",
        "To process speech with AI, set up a connection:\n\n"
        "1) Pick a type — Ollama (local, free), Direct API (by key), or Claude Code.\n"
        "2) Choose or download a model.\n"
        "3) Click «Save».\n\n"
        "Without setup, speech recognition still works — just without the AI step.",
    ),
    "onboard_open": ("Открыть настройки", "Open Settings"),
    "onboard_later": ("Позже", "Later"),
    # menu bar
    "menu_history": ("История", "History"),
    "menu_settings": ("Настройки…", "Settings…"),
    "menu_quit": ("Выход", "Quit"),
    "menu_empty": ("(пусто)", "(empty)"),
    # tooltips (#41) — short hover hints on the key controls
    "tip_conn_api": (
        "Облако по ключу: быстро и качественно, но платно и нужен интернет.",
        "Cloud by key: fast and high-quality, but paid and needs internet.",
    ),
    "tip_conn_ollama": (
        "Локально через Ollama: бесплатно и офлайн, нужна установленная Ollama.",
        "Local via Ollama: free and offline, needs Ollama installed.",
    ),
    "tip_conn_cc": (
        "Через claude CLI на подписке Max, без API-ключа.",
        "Via the claude CLI on the Max plan, no API key.",
    ),
    "tip_provider": (
        "Облачный провайдер: Anthropic (Claude) или OpenAI (GPT).",
        "Cloud provider: Anthropic (Claude) or OpenAI (GPT).",
    ),
    "tip_api_key": (
        "Ключ провайдера. Хранится в .env, применяется сразу.",
        "The provider's key. Stored in .env, applies immediately.",
    ),
    "tip_model": (
        "Конкретная модель: выбери рекомендацию или впиши свою.",
        "The specific model: pick a recommendation or type your own.",
    ),
    "tip_ollama_url": ("Адрес локального Ollama. Обычно не трогаем.", "Local Ollama address. Usually left as-is."),
    "tip_download": ("Скачать выбранную модель (ollama pull) в фоне.", "Download the selected model (ollama pull) in the background."),
    "tip_stt_backend": ("Чем распознаём речь. auto — оптимально под железо.", "The recognizer. auto picks the best for your hardware."),
    "tip_stt_model": ("Точность ↔ скорость. small — оптимум для русского.", "Accuracy ↔ speed. small is the Russian sweet spot."),
    "tip_stt_lang": ("Язык распознавания. auto — определять по речи.", "Recognition language. auto detects it from speech."),
    "tip_tts_enabled": ("Озвучивать выделенный текст / буфер по кнопке.", "Read the selection / clipboard aloud on the button."),
    "tip_tts_voice": ("Голос озвучки: Piper — локальный нейро, macOS — системный.", "TTS voice: Piper is local neural, macOS is the system voice."),
    "tip_premium": ("Открыть macOS, чтобы скачать премиум-голос.", "Open macOS to download a premium voice."),
    "tip_tts_trigger": ("Клавиша/кнопка, чтобы озвучить выделенное.", "Key/button to read the selection aloud."),
    "tip_wheel_trigger": (
        "Клавиша/кнопка, чтобы открыть колесо и начать запись.",
        "Key/button to open the wheel and start recording.",
    ),
    "tip_catch": (
        "Нажми, затем нужную клавишу/кнопку — поймаю автоматически.",
        "Click, then press the key/button you want — it's captured automatically.",
    ),
    "tip_concurrent": (
        "Разрешить новую запись, пока прошлая обрабатывается.",
        "Allow a new recording while the previous one is still processing.",
    ),
    "tip_uilang": (
        "Язык интерфейса. Применяется при «Сохранить» (перезапуск).",
        "Interface language. Applies on «Save» (restart).",
    ),
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
