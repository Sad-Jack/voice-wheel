"""Configuration loading.

Reads ``config.json`` from the project root (falling back to
``config.example.json``), merged over built-in defaults. Unknown keys (and the
``_comment`` keys in the example) are ignored, so the example file doubles as
documentation without breaking loading.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

APP_NAME = "VoiceWheel"


def app_support_dir() -> Path:
    """Per-user data dir (~/Library/Application Support/VoiceWheel), created on demand."""
    d = Path.home() / "Library" / "Application Support" / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass(frozen=True)
class HotkeyConfig:
    kind: str = "keyboard"  # 'keyboard' | 'mouse'
    key: str = "f8"


@dataclass(frozen=True)
class STTConfig:
    backend: str = "mlx"  # 'mlx' | 'faster-whisper'
    model: str = "small"
    fallback: str = "faster-whisper"


@dataclass(frozen=True)
class LLMConfig:
    backend: str = "ollama"  # 'ollama' (local, fast, stable) | 'claude_warm' (Max sub) | 'claude_cli' | 'anthropic'
    model: str = "claude-haiku-4-5"  # for claude_cli / anthropic / claude_warm
    ollama_model: str = "qwen2.5:7b"
    ollama_url: str = "http://localhost:11434"
    max_tokens: int = 1024


@dataclass(frozen=True)
class DefaultMode:
    ring: str = "transform"  # 'dictate' | 'transform' | 'context'
    sector: str = "normalize"  # 'normalize' | 'formal' | 'short' | 'friendly'


@dataclass
class Config:
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    language: str = "ru"  # mutable at runtime via the tray toggle
    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    default_mode: DefaultMode = field(default_factory=DefaultMode)
    max_context_chars: int = 6000
    auto_paste: bool = False
    history_limit: int = 10
    source_path: Optional[Path] = None

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        """Load from ``path`` or auto-discover config.json / config.example.json."""
        path = path or _discover_config_path()
        raw: dict[str, Any] = {}
        if path and path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover - defensive
                raise RuntimeError(f"Could not read config at {path}: {exc}") from exc
        return cls(
            hotkey=HotkeyConfig(**_pick(raw.get("hotkey"), HotkeyConfig)),
            language=raw.get("language", "ru"),
            stt=STTConfig(**_pick(raw.get("stt"), STTConfig)),
            llm=LLMConfig(**_pick(raw.get("llm"), LLMConfig)),
            default_mode=DefaultMode(**_pick(raw.get("default_mode"), DefaultMode)),
            max_context_chars=int(raw.get("max_context_chars", 6000)),
            auto_paste=bool(raw.get("auto_paste", False)),
            history_limit=int(raw.get("history_limit", 10)),
            source_path=path,
        )


def _pick(section: Any, dc_type: type) -> dict[str, Any]:
    """Keep only keys that are real fields of ``dc_type`` (drops _comment, typos)."""
    if not isinstance(section, dict):
        return {}
    allowed = {f.name for f in dc_type.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    return {k: v for k, v in section.items() if k in allowed}


def _discover_config_path() -> Optional[Path]:
    root = _project_root()
    for name in ("config.json", "config.example.json"):
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def _project_root() -> Path:
    # src/voice_wheel/config.py -> project root is two parents up from the package.
    return Path(__file__).resolve().parents[2]
