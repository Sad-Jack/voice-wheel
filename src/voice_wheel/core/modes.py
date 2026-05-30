"""Rings, sectors, and prompt assembly — sectors are loaded from `prompts/*.md`.

Each Markdown file in the prompts folder = one sector. The filename drives the
label and order: `1-Нормализация.md` → order 1, label "Нормализация". The file
body = the processing instruction. The wheel divides into as many sectors as
there are files; add/remove/edit files to change the wheel (restart to apply).

- **Ring** = depth: dictate (center, STT only) · transform (STT→LLM) ·
  context (clipboard + STT→LLM, ring #13).
- **Sector** = style: one per prompt file.

A small universal tail is appended to every prompt so output stays paste-ready
(only the result, no chatter) regardless of what the user writes in the file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

PROMPTS_DIRNAME = "prompts"


class Ring(str, Enum):
    DICTATE = "dictate"
    TRANSFORM = "transform"
    CONTEXT = "context"


@dataclass(frozen=True)
class Sector:
    key: str       # slug, used in history/logging and selection routing
    label: str     # display name on the wheel
    prompt: str    # processing instruction (file body)
    order: int     # sort position



# Appended to every sector prompt to keep output paste-ready.
_OUTPUT_TAIL = (
    "Верни только готовый результат — без пояснений, без markdown, без кавычек. "
    "Сохраняй смысл и не выбрасывай части. Отвечай на языке исходного текста "
    "или того, чего требует контекст."
)

_CONTEXT_PREFIX = (
    "Используй текст из буфера обмена как контекст, а голосовую инструкцию — как "
    "намерение пользователя."
)

# Seeded on first run if the prompts folder is empty (filename -> body).
DEFAULT_PROMPTS: dict[str, str] = {
    "1-Нормализация.md": (
        "Нормализуй распознанную речь: исправь ошибки распознавания и восстанови "
        "правильные слова — особенно англицизмы и технические термины, которые "
        "распознаватель мог исказить (например «пул-реквест», «деплой», «фронтенд», "
        "«коммит», «дедлайн», «митинг», «стейджинг»). Расставь пунктуацию, сделай "
        "текст чистым и читаемым. Сохрани исходный смысл и формулировки."
    ),
    "2-Деловой.md": (
        "Перепиши как вежливый деловой, официальный ответ коллеге. Чётко, "
        "уважительно, без жаргона и лишних эмоций."
    ),
    "3-Кратко.md": (
        "Сократи до короткого, ёмкого варианта. Сохрани главный смысл, убери воду."
    ),
    "4-Дружелюбно.md": (
        "Перепиши живо и дружелюбно, без официоза. Не делай слишком длинно."
    ),
}


def prompts_dir() -> Path:
    from .config import _project_root

    return _project_root() / PROMPTS_DIRNAME


def load_sectors(directory: Path | None = None) -> list[Sector]:
    """Load sectors from the prompts folder, seeding defaults if it's empty."""
    directory = directory or prompts_dir()
    files = _ensure_prompts(directory)
    sectors: list[Sector] = []
    for f in files:
        order, label = _parse_name(f.stem)
        try:
            body = f.read_text(encoding="utf-8").strip()
        except OSError:  # pragma: no cover - defensive
            continue
        if body:
            sectors.append(Sector(key=_slug(label), label=label, prompt=body, order=order))
    sectors.sort(key=lambda s: (s.order, s.label))
    if not sectors:  # last-resort in-memory fallback
        sectors = _memory_defaults()
    return sectors


def _ensure_prompts(directory: Path) -> list[Path]:
    try:
        if not directory.exists() or not any(directory.glob("*.md")):
            directory.mkdir(parents=True, exist_ok=True)
            for name, body in DEFAULT_PROMPTS.items():
                (directory / name).write_text(body + "\n", encoding="utf-8")
        return sorted(directory.glob("*.md"))
    except OSError as exc:  # pragma: no cover - read-only fs etc.
        log.warning("prompts folder unavailable (%s); using in-memory defaults", exc)
        return []


def _memory_defaults() -> list[Sector]:
    out = []
    for name, body in DEFAULT_PROMPTS.items():
        order, label = _parse_name(Path(name).stem)
        out.append(Sector(key=_slug(label), label=label, prompt=body, order=order))
    out.sort(key=lambda s: (s.order, s.label))
    return out


def _parse_name(stem: str) -> tuple[int, str]:
    """'1-Деловой' -> (1, 'Деловой'); 'Tech' -> (999, 'Tech')."""
    prefix, sep, rest = stem.partition("-")
    if sep and prefix.strip().isdigit():
        return int(prefix), rest.strip() or stem
    return 999, stem


def _slug(label: str) -> str:
    return "_".join(label.strip().lower().split())


# Sectors load lazily from prompts/ on first access — no file I/O at import time.
# Edit files in prompts/ and restart (or call reload_sectors()) to change the wheel.
_cache: tuple | None = None


def sectors() -> tuple[Sector, ...]:
    global _cache
    if _cache is None:
        _cache = tuple(load_sectors())
    return _cache


def reload_sectors() -> None:
    global _cache
    _cache = None


def sector_keys() -> tuple[str, ...]:
    return tuple(s.key for s in sectors())


def get_sector(key: str) -> Sector | None:
    return next((s for s in sectors() if s.key == key), None)


def build_system_prompt(ring: Ring, sector_key: str) -> str:
    """System instruction for an LLM ring: the sector's prompt + universal tail."""
    sector = get_sector(sector_key)
    style = sector.prompt if sector else ""
    if ring is Ring.TRANSFORM:
        return f"{style}\n\n{_OUTPUT_TAIL}"
    if ring is Ring.CONTEXT:
        return f"{_CONTEXT_PREFIX} {style}\n\n{_OUTPUT_TAIL}"
    raise ValueError(f"Ring {ring} does not use the LLM")


def build_user_message(transcript: str, context: str | None = None) -> str:
    if context:
        return (
            f"Контекст (буфер обмена):\n{context}\n\n"
            f"Голосовая инструкция:\n{transcript}"
        )
    return transcript


def normalize_ring(value: str) -> Ring:
    try:
        return Ring(value)
    except ValueError:
        return Ring.TRANSFORM


def normalize_sector(value: str) -> str:
    keys = sector_keys()
    return value if value in keys else (keys[0] if keys else value)
