# Voice Wheel — Архитектура и тех-долг

Аудит от 2026-05-31. Здесь — устройство проекта и трекер архитектурных задач (отдельно от `FEATURES.md`, который про продуктовые фичи).

## Карта проекта (2506 строк)

```
src/voice_wheel/
  __main__.py            вход: python -m voice_wheel; по sys.platform выбирает реализацию
  core/                  платформо-независимое ядро (без PyObjC)
    config.py            загрузка/парсинг config.json, dataclass-ы настроек, _project_root
    modes.py             секторы из prompts/*.md, сборка system/user-промптов
    pipeline.py          роутинг: dictate / transform / context → текст результата
    job_tracker.py       межпоточное состояние: generation/inflight/results (под локом)
    llm.py               4 бэкенда (ollama/claude_warm/claude_cli/anthropic) + per-sector модель
    stt.py               распознавание: mlx-whisper / faster-whisper / auto
    recorder.py          захват аудио (sounddevice) в numpy-буфер
    history.py           SQLite, последние результаты
  platform/macos/        всё PyObjC (UI/IO под macOS)
    macos_app.py         КОНТРОЛЛЕР: жизненный цикл, триггеры, запись, обработка, трей-хендлеры
    wheel_overlay.py     радиальное колесо (NSPanel + отрисовка + геометрия выбора)
    pulse.py             спиннер обработки + цветной пинг завершения
    settings.py          окно настроек (NSWindow) → пишет config.json
    tray.py              иконка меню-бара (NSStatusItem): статус, история, выход
    tts.py               озвучка буфера (AVSpeechSynthesizer + определение языка)
    mouse_tap.py         перехват боковых кнопок мыши (Quartz CGEventTap)
    clipboard.py         буфер обмена (NSPasteboard) + стек «вернуть прошлый»
```

**Здоровые стороны (НЕ трогаем):** направление зависимостей верное (`core` не знает про `platform`; `platform → core`), циклов нет, бизнес-логика отделена от UI/IO, ядро тестируемо (23 теста), линтер+CI зелёные.

## Трекер задач

Приоритет: 🔴 P1 (важно) · 🟠 P2 · 🟡 P3 (мелочь). Статус: ✅ done · ⬜ todo

| № | Задача | Приоритет | Статус |
|---|--------|-----------|--------|
| A1 | Ленивая загрузка секторов (убрать побочку на импорте) | 🟠 P2 | ✅ |
| A2 | Удалить мёртвый код (`RING_RADII`, `DEAD_ZONE_RADIUS`, `_cfg_language_hint`) | 🟡 P3 | ✅ |
| A3 | Разбить god-контроллер `macos_app.py` (извлечь `TriggerManager`) | 🔴 P1 | ✅ |
| A4 | Формализовать межпоточное состояние (`_gen`/`_inflight`/`_results`) | 🟠 P2 | ✅ |
| A11 | ⚡ CGEventTap на выделенном потоке (был фриз) | 🔴 P1 | ✅ |
| A5 | Извлечь `ClaudeWarmProcess` из `llm.py` | 🟠 P2 | ✅ |
| A6 | `wheel_overlay.py`: геометрия → `core/wheel_geometry.py` + тесты | 🟡 P3 | ✅ |
| A7 | Пакет `platform/` тенит stdlib `platform` → переименовать | 🟡 P3 | ⬜ |
| A8 | `Clipboard` Protocol в core (явная зависимость pipeline) | 🟡 P3 | ✅ |
| A9 | Сузить/залогировать широкие `except Exception` (20 шт) | 🟡 P3 | ✅ |
| A10 | Добавить `ruff` (линтер) + минимальный CI | 🟡 P3 | ✅ |

---

## Подробный разбор

### A1 — Ленивая загрузка секторов ✅ (сделано)
**Было:** `modes.py` на уровне модуля выполнял `SECTORS = tuple(load_sectors())` — то есть **просто `import modes` читал и при необходимости создавал файлы** в `prompts/`. Побочный эффект на импорте: сюрприз для тестов/тулинга, неявно, не перезагружается.
**Стало:** ленивый `sectors()` с кэшем + `reload_sectors()`. Импорт ничего не трогает; файлы читаются при первом обращении.
**Trade-off:** консьюмеры зовут `sectors()` вместо глобала `SECTORS` — мелкий churn (поправил `wheel_overlay`, тесты).

### A2 — Мёртвый код ✅ (сделано)
`RING_RADII` и `DEAD_ZONE_RADIUS` в `modes.py` остались от старого дизайна колеса (новый `wheel_overlay` держит свои радиусы) — 0 использований. `_cfg_language_hint()` возвращал просто `"ru"`. Удалено.

### A3 — God-контроллер `macos_app.py` 🔴 P1 ✅ (сделано)
**Результат:** вынес `TriggerManager` в `platform/macos/triggers.py` (121 стр). `macos_app` похудел **412 → 309 строк**; весь перехват кнопок/клавиш + async-`_fire` теперь в одном изолированном модуле. Контроллер просто строит список триггеров и зовёт `TriggerManager.start(...)`. Поведение идентично (async-dispatch сохранён — фриз не вернётся).

**Проблема (была):** один класс `VoiceWheel` (412 строк) делает **всё**: создаёт сервисы, регистрирует триггеры (Quartz-tap + pynput + `_dispatch`), ведёт запись (`onPress`/`onTick`/`onRelease`), обработку (`_process`/`finishProcessing`), хендлеры трея (`_on_reuse`/`_on_restore`/`onTts`), плюс модульные `_load_dotenv`/`_ensure_accessibility`/`main`.
**Почему важно:** самый хрупкий код (активный event-tap + потоки) перемешан с рутиной. Любая правка рядом рискует задеть ввод (мы уже ловили фриз). Тяжело читать и тестировать.
**Решение:** извлечь `platform/macos/triggers.py` → `TriggerManager`, который владеет tap'ом, pynput-листенерами и асинхронным `_dispatch`; принимает карту `{action: (press, release)}`. Контроллер худеет до ~300 строк и становится тонким оркестратором.
**Trade-off:** трогаем хрупкий event-tap. Делать аккуратно, с сохранением async-dispatch, и **ты тестируешь нажатия после**.
**Шаги:** (1) вынести `_dispatch` + `_start_listener` + `_start_pynput` в `TriggerManager`; (2) контроллер передаёт свои `onPress_/onRelease_/onTts_`; (3) запустить, проверить колесо/озвучку/боковые кнопки.

### A11 — CGEventTap на выделенном потоке 🔴 P1 ✅ (сделано)
**Проблема (нашли в бою):** активный tap висел на **главном** run loop вместе с таймером колеса (60fps) и открытием/закрытием аудио. Когда главный поток занят в момент события — windowserver ждёт ответа tap'а → **фриз/beachball** (интермиттентно, всплыл «при попытке отменить»).
**Решение:** `mouse_tap.SideButtonTap` теперь поднимает **свой CFRunLoop на daemon-потоке** (`CGEventTapCreate` + `CFRunLoopRun()`). Колбэк бежит на этом потоке и только перекидывает работу в главный через `performSelectorOnMainThread`. Tap всегда отзывчив, что бы ни делал главный поток.
**Trade-off:** колбэк теперь на отдельном потоке — но он и так только диспетчерит (UI не трогает), так что безопасно.

### A4 — Межпоточное состояние 🟠 P2 ✅ (сделано)
**Результат:** вынес `_gen`/`_inflight`/`_results` в `core/job_tracker.py` (`JobTracker`) — один владелец, всё под `threading.Lock`, неявный GIL-контракт стал явным. API: `bump_generation()`/`generation`/`is_stale(gen)` (стейл-чек), `begin()`/`finish()`/`inflight` (спиннер), `push_result()`/`pop_result()` (очередь результатов), `reset()` (сброс при non-concurrent нажатии). Контроллер похудел и читается линейно; миграция 1:1 по поведению. Чистый Python → покрыл юнит-тестами, включая два concurrency-теста (8 потоков × begin/finish и push/pop — счётчик возвращается ровно в 0, ничего не теряется). Платформо-независимо: Windows-контроллер переиспользует.
**Trade-off:** лок на крошечных операциях (раз в запись, не в кадре) — стоимость ноль; зато контракт защищён от будущих правок.

### A5 — `ClaudeWarmProcess` из `llm.py` 🟠 P2 ✅ (сделано)
**Результат:** вынес весь warm-процесс (spawn/reader-thread/complete/discard) в `core/claude_warm.py` (`ClaudeWarmProcess`, 122 стр). `llm.py` похудел **301 → 206 строк**; `LLMClient.prewarm/_complete_warm` теперь в 3 строки делегируют классу. Поведение сохранено.

**Проблема (была):** `llm.py` (301 стр) держит 4 бэкенда **и** всю возню с warm-процессом Claude (spawn stream-json, reader-thread, drain stdout, deque, prewarm/discard). Это самый сложный кусок, размазан по классу `LLMClient`.
**Решение:** вынести в отдельный класс `ClaudeWarmProcess` (start/send/result/kill). `LLMClient` просто им пользуется. Бэкенды можно позже разнести по `core/llm/` если разрастётся.
**Trade-off:** чище и тестируемее, но warm-логика тонкая — аккуратный перенос.

### A6 — `wheel_overlay.py`: геометрия vs отрисовка 🟡 P3
**Проблема:** 295 строк смешивают **чистую геометрию** (`selection_for`, `sector_index`, углы — это тестируемая логика!) с **PyObjC-отрисовкой** (`drawRect_`, glow, NSBezierPath) и управлением панелью.
**Решение:** вынести геометрию в `core/wheel_geometry.py` (чистый Python, без ObjC) — её можно покрыть юнит-тестами; `wheel_overlay` остаётся про отрисовку. Бонус: геометрия пригодится для Windows-оверлея (переиспользуемая).
**Trade-off:** небольшой churn; зато логика выбора секторов становится платформо-независимой и тестируемой.

### A7 — `platform/` тенит stdlib 🟡 P3
**Проблема:** наш пакет называется `platform`, как stdlib-модуль `platform`. Сейчас работает (absolute import в Py3 берёт stdlib), но это footgun: однажды кто-то сделает относительный импорт и поймает сюрприз.
**Решение:** переименовать `platform/` → `hostos/` (или `osimpl/`). Поправить импорты (`...hostos.macos`), `__main__`, тесты.
**Trade-off:** механический churn ради устранения латентной мины. Низкий приоритет.

### A8 — `Clipboard` Protocol 🟡 P3 ✅ (сделано)
**Результат:** объявил `ClipboardReader(Protocol)` прямо в `core/pipeline.py` (рядом с потребителем) — один метод `read_text() -> str | None`, ровно та поверхность, что нужна пайплайну (он читает контекст, но не пишет — запись/restore остаётся у вызывающего). `Pipeline.__init__` теперь аннотирован `clipboard: ClipboardReader` вместо duck-typing. Контракт явный, `core` по-прежнему не знает про платформенный `Clipboard`. Платформенный класс ему структурно соответствует — без наследования.
**Trade-off:** namespace-протокол узкий (read-only) намеренно: писать `Protocol` с `write_text` под несуществующего потребителя — преждевременно.

### A9 — Широкие `except Exception` 🟡 P3 ✅ (сделано)
Прошёлся по всем 20. Итог: каждый теперь **либо логирует, либо это намеренный teardown с комментарием**.
- **Логировали уже** (оставил): `stt` (warning при фоллбэке движка), `macos_app` (warning/exception в прогреве, TTS, обработке, accessibility), `triggers` (warning при незапуске tap'а), `tts`, `mouse_tap` (ошибка пробрасывается в `start()` → логирует `triggers`).
- **Молчали → добавил лог:** `claude_warm.spawn` (warning при провале Popen), `claude_warm._reader_loop` (debug), `llm.warm_up`/`_ollama_reachable` (debug), `settings._read` (warning при битом config.json).
- **Сузил очевидное:** `claude_warm._terminate` (cleanup) `Exception` → `(OSError, ValueError)`; `settings._read` ловит `FileNotFoundError` (тихо) отдельно от `(ValueError, OSError)` (warning).
Принцип: для desktop-app «не падать» — правильная политика; задача была сделать сбои **видимыми**, а не убрать защиту.

### A10 — Линтер + CI 🟡 P3 ✅ (сделано)
Добавил `ruff` (config в `pyproject.toml [tool.ruff.lint]`): `select = E,F,I,W,UP,B` (реальные баги + сортировка импортов + pyupgrade + bugbear), `ignore = E501,E702` (длинные строки и компактные `a(); b(); c()` в ObjC-отрисовке — намеренный стиль), `UP042` (StrEnum поменял бы семантику `Ring`). Автофиксы уже применил: убран мёртвый импорт, отсортированы импорты, `Optional[X] → X | None` по всему ядру. `ruff check` — зелёный. Группа `[project.optional-dependencies] dev` = `ruff,pytest`. CI: `.github/workflows/ci.yml` (push в main + PR) на `ubuntu-latest` — ставит `ruff pytest`, гоняет `ruff check src tests` + `PYTHONPATH=src pytest tests/`. Тяжёлые macOS/STT-деки в CI не нужны: `core/` ничего тяжёлого не импортит на загрузке, а AppKit-тест сам себя скипает (`pytest.importorskip`).

---

## ⛔ Что НЕ менять сейчас
- **Async-dispatch event-tap + модель потоков** — только что чинили фриз; код верный и хрупкий. Без реального тест-цикла не трогаем (кроме аккуратного A3 с твоей проверкой).
- **Никаких ABC-интерфейсов для платформ** до реального Windows — абстракцию проектируют против второй ОС, не наугад.
- **Не дробить `core` глубже** — текущая глубина оптимальна под размер.
