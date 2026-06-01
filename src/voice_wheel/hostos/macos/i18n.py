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
    "tab_prompts": ("Промпты", "Prompts"),
    "tab_keys": ("Ключи", "Keys"),
    "tab_logs": ("Логи", "Logs"),
    "keys_header": ("🔑 Ключи и токены", "🔑 Keys & tokens"),
    "keys_hint": (
        "Секреты хранятся в .env (в .gitignore), применяются сразу. Введи ключ — и "
        "соответствующее подключение станет доступным в LLM и правилах. Anthropic: "
        "console.anthropic.com → API Keys. OpenAI: platform.openai.com → API keys.",
        "Secrets are stored in .env (gitignored), applied immediately. Enter a key and "
        "the matching connection becomes available in LLM and rules. Anthropic: "
        "console.anthropic.com → API Keys. OpenAI: platform.openai.com → API keys.",
    ),
    "key_anthropic": ("Claude (Anthropic)", "Claude (Anthropic)"),
    "key_openai": ("OpenAI", "OpenAI"),
    "key_ollama": ("Ollama (токен)", "Ollama (token)"),
    "keys_pointer": (
        "Ключи и токены — на вкладке «Ключи».",
        "Keys & tokens are on the «Keys» tab.",
    ),
    "keys_redirect_btn": (
        "⚠️ Нет ключа — добавить на вкладке «Ключи»",
        "⚠️ No key — add one on the «Keys» tab",
    ),
    # LLM tab
    "llm_header": ("🧠 Обработка речи (LLM)", "🧠 Speech processing (LLM)"),
    "engine": ("Движок", "Engine"),
    "llm_hint": (
        "Откуда брать ИИ, который превращает речь в результат под промпт сектора.",
        "Where the AI that turns speech into the sector-prompt result comes from.",
    ),
    "conn_api": ("Прямой API", "Direct API"),
    "conn_ollama": ("Ollama", "Ollama"),
    "conn_cc": ("Claude Code CLI", "Claude Code CLI"),
    "provider": ("Провайдер", "Provider"),
    "show_key": ("Показать", "Show"),
    "note_api_no_key": (
        "⚠️ Ключ не задан — облачный LLM работать не будет. Добавь ключ на вкладке «Ключи».",
        "⚠️ No key set — the cloud LLM won't work. Add a key on the «Keys» tab.",
    ),
    "note_ollama_pulled": ("Модель «{}» скачана.", "Model «{}» downloaded."),
    "note_ollama_pull_fail": (
        "Не удалось скачать «{}». Установлена и запущена ли Ollama? (ollama serve)",
        "Couldn't download «{}». Is Ollama installed and running? (ollama serve)",
    ),
    "ollama_url": ("URL", "URL"),
    "ollama_hint": (
        "Модель через Ollama — должна быть установлена и запущена. Адрес сервера "
        "(URL) и проверка доступности — на вкладке «Модели».",
        "A model via Ollama — it must be installed and running. The server address "
        "(URL) and the reachability check live on the «Models» tab.",
    ),
    "ollama_url_hint": (
        "Адрес Ollama-сервера, к которому обращаемся: локальный (по умолчанию "
        "http://localhost:11434) или свой удалённый. «Проверить» — пингует адрес и "
        "показывает статус ниже (доступен / нет).",
        "The Ollama server we talk to: local (default http://localhost:11434) or your "
        "own remote one. «Re-check» pings the address and shows the status below "
        "(reachable / not).",
    ),
    "ollama_no_models_btn": ("⚠️ Нет моделей — открыть «Модели»", "⚠️ No models — open «Models»"),
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
    "ollama_running_v": ("✅ Ollama запущена · v{}", "✅ Ollama is running · v{}"),
    "ollama_restart_btn": ("Перезапустить Ollama", "Restart Ollama"),
    "ollama_restarting": ("Перезапускаю Ollama…", "Restarting Ollama…"),
    # Models tab
    "tab_models": ("Модели", "Models"),
    "models_header": ("📦 Локальные модели (Ollama)", "📦 Local models (Ollama)"),
    "models_installed_header": ("Установлено:", "Installed:"),
    "models_installed_none": (
        "Пока ничего не скачано. Выбери модель ниже и нажми «Скачать».",
        "Nothing downloaded yet. Pick a model below and press «Download».",
    ),
    "models_installed_loading": ("Загружаю список…", "Loading list…"),
    "models_download_header": ("Скачать модель:", "Download a model:"),
    "models_download_hint": (
        "Выбери предложенную модель или впиши своё имя (например «llama3.1:8b») — она "
        "скачается локально через Ollama. Дефолт для русского — qwen2.5:7b. Прогресс — "
        "в строке снизу; по готовности появится в списке выше.",
        "Pick a suggested model or type your own (e.g. «llama3.1:8b») — it downloads "
        "locally via Ollama. The Russian default is qwen2.5:7b. Progress shows below; "
        "once done it appears in the list above.",
    ),
    "ollama_library_btn": ("🔗 Библиотека моделей Ollama", "🔗 Ollama model library"),
    "model_delete_tip": ("Удалить эту модель", "Delete this model"),
    "model_delete_confirm_title": ("Удалить «{}»?", "Delete «{}»?"),
    "model_delete_confirm_body": (
        "Модель будет удалена из Ollama и освободит место. Скачать заново можно в любой момент.",
        "The model will be removed from Ollama, freeing disk space. You can re-download it anytime.",
    ),
    "model_delete_btn": ("Удалить", "Delete"),
    "cancel": ("Отмена", "Cancel"),
    "model_removing": ("🗑 Удаляю «{}»…", "🗑 Removing «{}»…"),
    "model_removed": ("✅ Модель «{}» удалена.", "✅ Model «{}» removed."),
    "model_remove_fail": ("❌ Не удалось удалить «{}».", "❌ Couldn't remove «{}»."),
    "models_pull_btn": ("Скачать", "Download"),
    "models_downloading": ("⏳ Скачиваю «{}»… (может занять минуты)", "⏳ Downloading «{}»… (may take minutes)"),
    "models_downloading_pct": (
        "⏳ «{}» · {}%  ({:.1f}/{:.1f} GB)",
        "⏳ «{}» · {}%  ({:.1f}/{:.1f} GB)",
    ),
    "llm_models_pointer": (
        "Скачивание и список установленных моделей — на вкладке «Модели».",
        "Downloading and the installed-models list live on the «Models» tab.",
    ),
    "cc_hint": (
        "Зовём локальный `claude` (Claude Code) на твоей подписке Pro/Max — без ключа. "
        "Нужны установка и вход (кнопки ниже).",
        "Calls the local `claude` (Claude Code) on your Pro/Max plan — no key. Needs "
        "install + login (buttons below).",
    ),
    "claude_checking": ("Проверяю Claude Code…", "Checking Claude Code…"),
    "claude_ok": ("🟢 Claude Code установлен ({})", "🟢 Claude Code installed ({})"),
    "claude_missing": ("🔴 Claude Code не установлен", "🔴 Claude Code not installed"),
    "cc_install_btn": ("Как установить…", "How to install…"),
    "cc_login_btn": ("Войти / настроить (Терминал)", "Log in / set up (Terminal)"),
    "cc_login_note": (
        "Открыл Терминал — войди там (откроется браузер). После входа нажми «Проверить».",
        "Opened Terminal — log in there (a browser opens). Then click «Re-check».",
    ),
    "prompts_header": ("🧩 Промпты — секторы колеса", "🧩 Prompts — wheel sectors"),
    "prompts_count": ("Сейчас промптов: {}", "Prompts now: {}"),
    "prompts_hint": (
        "Каждый файл «N-Название.md» в папке промптов = один сектор колеса (N задаёт "
        "порядок). Добавь / переименуй / удали файл, затем перезапусти приложение, "
        "чтобы колесо обновилось. Список здесь обновляется кнопкой «Обновить».",
        "Each «N-Name.md» file in the prompts folder = one wheel sector (N sets the "
        "order). Add / rename / delete a file, then restart the app to update the "
        "wheel. The list here refreshes with «Refresh».",
    ),
    "open_prompts_folder": ("📂 Открыть папку промптов", "📂 Open prompts folder"),
    "refresh_prompts": ("Обновить", "Refresh"),
    "prompts_refreshed": (
        "Список промптов обновлён. Колесо обновится после перезапуска приложения.",
        "Prompt list refreshed. The wheel updates after an app restart.",
    ),
    "rules_header": ("🎛 Модель на каждый промпт", "🎛 Model per prompt"),
    "rules_hint": (
        "Каждый промпт по умолчанию использует базовую модель (вкладка LLM). Раскрой "
        "промпт, чтобы задать ему свою модель; оставишь как базовую — будет наследовать её.",
        "Every prompt uses the base model (LLM tab) by default. Expand a prompt to give "
        "it its own model; leave it as base and it keeps inheriting the base.",
    ),
    "prompt_inherits_base": ("как базовая", "as base"),
    "reset_tab": ("Сброс", "Reset"),
    # Speech tab
    "stt_header": ("🎙 Распознавание (речь → текст)", "🎙 Recognition (speech → text)"),
    "stt_engine_hint": (
        "Чем распознаём речь:\n"
        "• auto — выбирает сам: mlx на Apple Silicon, faster-whisper на остальных. Рекомендуется.\n"
        "• mlx — Apple MLX на GPU/Neural Engine: быстрее всего, только чипы M-серии.\n"
        "• faster-whisper — на CPU (int8): работает везде, медленнее. Запасной вариант.",
        "Speech recognizer:\n"
        "• auto — picks for you: mlx on Apple Silicon, faster-whisper elsewhere. Recommended.\n"
        "• mlx — Apple MLX on the GPU/Neural Engine: fastest, M-series chips only.\n"
        "• faster-whisper — CPU (int8): runs anywhere, slower. Fallback.",
    ),
    "model": ("Модель", "Model"),
    "stt_model_hint": (
        "Размер модели — точность против скорости и памяти:\n"
        "• tiny / base — очень быстро, грубо. Для коротких команд.\n"
        "• small — баланс качества и скорости, оптимум для русского. Рекомендуется.\n"
        "• medium — заметно точнее, но медленнее и требует больше памяти.\n"
        "• large — максимум точности, самая тяжёлая (для мощных Mac).",
        "Model size — accuracy vs. speed and memory:\n"
        "• tiny / base — very fast, rough. For short commands.\n"
        "• small — balanced, the Russian sweet spot. Recommended.\n"
        "• medium — noticeably more accurate, but slower and heavier.\n"
        "• large — top accuracy, heaviest (for powerful Macs).",
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
    # Triggers tab
    "trig_header": ("⌨️ Триггер записи (колесо)", "⌨️ Record trigger (wheel)"),
    "trig_kb": ("Клавиатура", "Keyboard"),
    "trig_mouse": ("Мышь", "Mouse"),
    "trig_hint": (
        "Обе строки работают одновременно. «Поймать» → нажми нужную клавишу/комбо или кнопку мыши.",
        "Both rows are live at once. «Catch» → press the key/combo or mouse button you want.",
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
    "tip_mouse_btn": (
        "Кнопка мыши для триггера. «Поймать» → нажми реальную кнопку, и мы её определим.",
        "The mouse button for the trigger. «Catch» → press the real button and we'll detect it.",
    ),
    "mouse_custom_side": ("Боковая {}", "Side button {}"),
    "mouse_custom_btn": ("Кнопка мыши {}", "Mouse button {}"),
    "misc_header": ("⚙️ Прочее", "⚙️ Other"),
    "concurrent": (
        "Запись во время обработки (concurrent)",
        "Record while a result is processing (concurrent)",
    ),
    # Language tab
    "lang_header": ("🌐 Язык интерфейса", "🌐 Interface language"),
    "lang_hint": (
        "Меняет язык всего приложения (меню и настройки). По умолчанию — как в системе.",
        "Changes the language of the whole app (menu and settings). Defaults to your system.",
    ),
    "restart_warn_global": (
        "⚠️ Изменения языка, триггеров и модели распознавания (STT) применяются "
        "только после перезапуска приложения — он произойдёт автоматически при «Сохранить».",
        "⚠️ Changes to the language, triggers and recognition model (STT) take effect "
        "only after a restart — it happens automatically on «Save».",
    ),
    # Logs tab
    "logs_header": ("🗒 Логи", "🗒 Logs"),
    "logs_hint": (
        "Что приложение делало в последнее время: диктовки, обработки, озвучка и "
        "ошибки. Свежие — снизу, прокрути вверх для истории. Обновляется само.",
        "What the app did recently: dictations, transforms, speech and errors. "
        "Newest at the bottom — scroll up for history. Refreshes itself.",
    ),
    "logs_clear": ("Очистить", "Clear"),
    "logs_empty": (
        "Пока пусто. Сделай диктовку или обработку — здесь появится запись.",
        "Nothing yet. Do a dictation or a transform — it will show up here.",
    ),
    "log_dictation": ("Диктовка", "Dictation"),
    "log_recorded": ("Записано", "Recorded"),
    "log_buffer": ("Буфер был", "Buffer used"),
    "log_spoken": ("Озвучено", "Spoken"),
    "log_error": ("Ошибка", "Error"),
    "log_crash": ("Сбой", "Crash"),
    # human-readable error categories (also reused for the «не работает» key status)
    "err_auth": ("ключ не работает", "key not working"),
    "err_rate_limit": ("превышен лимит запросов", "rate limit exceeded"),
    "err_unreachable": ("сервер недоступен", "server unreachable"),
    "err_model": ("модель не найдена", "model not found"),
    "err_stt": ("речь не распознана", "speech not recognized"),
    "err_other": ("ошибка", "error"),
    "key_not_working": ("⚠️ ключ не работает", "⚠️ key not working"),
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
        "1) Выбери способ — Ollama (бесплатно), Прямой API (по ключу) "
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
    "tip_model": (
        "Конкретная модель: выбери рекомендацию или впиши свою.",
        "The specific model: pick a recommendation or type your own.",
    ),
    "tip_ollama_url": ("Адрес Ollama — локальной или удалённой (свой сервер). Обычно не трогаем.", "Ollama address — local or remote (your own server). Usually left as-is."),
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
