"""Ring / sector definitions and prompt assembly.

- **Ring** = processing depth: dictate (STT only) · transform (STT→LLM) ·
  context (clipboard + STT→LLM).
- **Sector** = style: clean · short · friendly · tech (prompt/qa come later).

Prompts follow the spec (§21): preserve meaning, fix recognition errors, never
invent facts, hedge when context is thin. They are factored into a constant base
(per ring) + a style line (per sector) so the *system* prompt stays constant and
can be prompt-cached, while the variable transcript/context rides in the *user*
message.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Ring(str, Enum):
    DICTATE = "dictate"
    TRANSFORM = "transform"
    CONTEXT = "context"


@dataclass(frozen=True)
class Sector:
    key: str
    label: str


# Simplified model: the wheel CENTER = dictate (STT only); each SECTOR = an LLM
# transform with a preset style. Four sectors laid out as directions
# (up / right / down / left), in this order.
SECTORS: tuple[Sector, ...] = (
    Sector("normalize", "Нормализация"),  # up
    Sector("formal", "Деловой"),          # right
    Sector("short", "Кратко"),            # down
    Sector("friendly", "Дружелюбно"),     # left
)
SECTOR_KEYS = tuple(s.key for s in SECTORS)

# Ring radii in logical px (spec §8). dead-zone < 40px → default/cancel.
RING_RADII = {
    Ring.DICTATE: (40, 90),
    Ring.TRANSFORM: (90, 150),
    Ring.CONTEXT: (150, 220),
}
DEAD_ZONE_RADIUS = 40

# Per-sector style line, woven into the base prompt.
_STYLE = {
    "normalize": (
        "Нормализуй распознанную речь: исправь ошибки распознавания и восстанови "
        "правильные слова — особенно англицизмы и технические термины, которые "
        "распознаватель мог исказить (например «пул-реквест», «деплой», «фронтенд», "
        "«коммит», «дедлайн», «митинг»). Расставь пунктуацию, сделай текст чистым и "
        "читаемым. Сохрани исходный смысл и формулировки, ничего не добавляй от себя."
    ),
    "formal": "Преврати в вежливый деловой, официальный ответ коллеге. Чётко, уважительно, без жаргона и эмоций.",
    "short": "Сделай короткий, сжатый ответ. Сохрани главный смысл, пиши ясно и без воды.",
    "friendly": "Пиши живо и дружелюбно, без официоза. Не делай текст слишком длинным.",
    "tech": "Пиши технически, структурно и без эмоций. Если есть проблема или неясность — сформулируй её аккуратно.",
}

_LANG_LINE = (
    "Отвечай на том языке, на котором сформулирована мысль или которого требует контекст."
)

_TRANSFORM_BASE = (
    "Ты обрабатываешь распознанную речь пользователя. {style} "
    "Не добавляй новые факты. Если данных не хватает — пиши осторожно. "
    f"{_LANG_LINE} Верни только готовый текст, без пояснений и кавычек."
)

_CONTEXT_BASE = (
    "Используй текст из буфера обмена как контекст, а голосовую инструкцию — как "
    "намерение пользователя. Напиши готовый ответ. {style} "
    "Сохраняй смысл, не выдумывай факты. Если контекста недостаточно — пиши осторожно. "
    f"{_LANG_LINE} Верни только готовый текст, без пояснений и кавычек."
)


def build_system_prompt(ring: Ring, sector: str) -> str:
    """Constant (cacheable) system instruction for an LLM ring + sector."""
    style = _STYLE.get(sector, _STYLE["normalize"])
    if ring is Ring.TRANSFORM:
        return _TRANSFORM_BASE.format(style=style)
    if ring is Ring.CONTEXT:
        return _CONTEXT_BASE.format(style=style)
    raise ValueError(f"Ring {ring} does not use the LLM")


def build_user_message(transcript: str, context: str | None = None) -> str:
    """Variable per-request payload (transcript, plus clipboard context for ring 3)."""
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
    return value if value in SECTOR_KEYS else SECTOR_KEYS[0]
