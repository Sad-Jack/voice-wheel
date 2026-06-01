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



# Labels for the two inputs in the user message. The prompt files key off exactly
# these markers (their BASE section explains each), so the transport and the prompts
# share one contract — keep them in sync.
VOICE_LABEL = "ГОЛОС:"    # the user's own transcribed speech (their intent)
BUFFER_LABEL = "БУФЕР:"   # external clipboard text — may be someone else's words

# Common preamble seeded into every default prompt. Self-contained: it defines the
# ГОЛОС/БУФЕР contract, the three modes, and the paste-ready output rule — so the
# code no longer injects a prefix/tail (the prompt owns its whole behaviour).
_DEFAULT_BASE = (
    "Ты часть Voice Wheel. После этого промпта придёт вход с метками:\n"
    "ГОЛОС: — моя речь (из распознавания, бывают ошибки). "
    "БУФЕР: — текст из буфера обмена. Каждый может присутствовать или нет.\n\n"
    "Режимы (по тому, что пришло):\n"
    "- Только ГОЛОС → обрабатывай ГОЛОС.\n"
    "- Только БУФЕР → обрабатывай БУФЕР как сам материал.\n"
    "- ГОЛОС + БУФЕР → ГОЛОС это моё намерение, БУФЕР это контекст. БУФЕР может быть "
    "чужим текстом — не выдавай его за моё и не пиши от его лица.\n\n"
    "Восстанавливай искажённые распознаванием слова по смыслу, убирай «эээ», повторы "
    "и оговорки. Правь форму, не содержание — ничего не выдумывай. Пиши от первого "
    "лица, как написал бы я.\n\n"
    "Вывод: только готовый результат — без преамбул, кавычек, пояснений и markdown "
    "(если сам результат не код). Если нет ни ГОЛОСА, ни БУФЕРА — ничего не пиши."
)


def _seed(label: str, body: str) -> str:
    return f"{_DEFAULT_BASE}\n\n# === SECTOR: {label} ===\n{body}"


# Seeded on first run if the prompts folder is empty (filename -> body). Each is the
# shared BASE + a sector-specific instruction, so a fresh install works out of the box.
DEFAULT_PROMPTS: dict[str, str] = {
    "1-Нормализация.md": _seed(
        "Нормализация",
        "Приведи текст в чистый читаемый вид: исправь грамматику и пунктуацию, "
        "выстрой связный порядок мыслей, убери мусор и повторы. Сохрани мой смысл, "
        "тон и стиль — не делай формальнее и ничего не добавляй.",
    ),
    "2-Деловой.md": _seed(
        "Деловой",
        "Перепиши как вежливый деловой ответ коллеге: чётко, уважительно, без "
        "жаргона и лишних эмоций.",
    ),
    "3-Кратко.md": _seed(
        "Кратко",
        "Сократи до короткого, ёмкого варианта. Сохрани главный смысл, убери воду.",
    ),
    "4-Дружелюбно.md": _seed(
        "Дружелюбно",
        "Перепиши живо и дружелюбно, без официоза. Не делай слишком длинно.",
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
# Edit files in prompts/ and restart the app to change the wheel.
_cache: tuple | None = None


def sectors() -> tuple[Sector, ...]:
    global _cache
    if _cache is None:
        _cache = tuple(load_sectors())
    return _cache


def sector_keys() -> tuple[str, ...]:
    return tuple(s.key for s in sectors())


def get_sector(key: str) -> Sector | None:
    return next((s for s in sectors() if s.key == key), None)


def build_system_prompt(ring: Ring, sector_key: str) -> str:
    """The processing instruction for an LLM ring — the sector's authored prompt,
    as-is. The prompt body owns output format and how to treat ГОЛОС vs БУФЕР; the
    transport only labels the two inputs (see ``build_user_message``). The system
    prompt is the same for transform and context (what differs is whether БУФЕР is
    present in the user message), which also lets prompt caching reuse it."""
    if ring not in (Ring.TRANSFORM, Ring.CONTEXT):
        raise ValueError(f"Ring {ring} does not use the LLM")
    sector = get_sector(sector_key)
    return sector.prompt if sector else ""


def build_user_message(transcript: str, context: str | None = None) -> str:
    """Label the two inputs so the model never conflates them: ``ГОЛОС:`` is the
    user's own speech (their intent), ``БУФЕР:`` is external clipboard text that may
    be someone else's words. Either may be absent — speech-only (no-context
    transform), buffer-only (spoke nothing), or both. ГОЛОС leads (the intent),
    БУФЕР follows as reference material."""
    speech = (transcript or "").strip()
    buf = (context or "").strip()
    parts = []
    if speech:
        parts.append(f"{VOICE_LABEL}\n{speech}")
    if buf:
        parts.append(f"{BUFFER_LABEL}\n{buf}")
    return "\n\n".join(parts)


def normalize_ring(value: str) -> Ring:
    try:
        return Ring(value)
    except ValueError:
        return Ring.TRANSFORM


def normalize_sector(value: str) -> str:
    keys = sector_keys()
    return value if value in keys else (keys[0] if keys else value)
