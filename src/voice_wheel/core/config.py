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
from typing import Any

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
    backend: str = "auto"  # 'auto' (mlx on Apple Silicon, else faster-whisper) | 'mlx' | 'faster-whisper'
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
class TTSConfig:
    enabled: bool = True
    backend: str = "piper"  # "piper" (local neural, auto-downloaded) | "system" (macOS voices)
    voice: str = ""  # system backend: exact voice name to force; empty = best for the language
    piper_voice: str = "ru_RU-irina-medium"  # piper backend: which neural voice to use
    hotkey: HotkeyConfig = field(default_factory=lambda: HotkeyConfig(kind="mouse_side", key="4"))


@dataclass
class Config:
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    language: str = "ru"  # mutable at runtime via the tray toggle
    ui_language: str = ""  # interface language 'ru'|'en'; "" = follow the system locale
    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    sector_models: dict = field(default_factory=dict)  # sector_key -> {backend, model}
    concurrent: bool = False  # allow recording a new one while a previous is processing
    max_context_chars: int = 6000
    auto_paste: bool = False
    history_limit: int = 10
    source_path: Path | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
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
            ui_language=str(raw.get("ui_language", "")),
            stt=STTConfig(**_pick(raw.get("stt"), STTConfig)),
            llm=LLMConfig(**_pick(raw.get("llm"), LLMConfig)),
            tts=_parse_tts(raw.get("tts")),
            sector_models=_parse_sector_models(raw.get("sector_models")),
            concurrent=bool(raw.get("concurrent", False)),
            max_context_chars=int(raw.get("max_context_chars", 6000)),
            auto_paste=bool(raw.get("auto_paste", False)),
            history_limit=int(raw.get("history_limit", 10)),
            source_path=path,
        )


def _parse_sector_models(section: Any) -> dict:
    """Keep only {sector_key: {backend, model}} entries (drop _comment etc.)."""
    if not isinstance(section, dict):
        return {}
    out = {}
    for k, v in section.items():
        if not k.startswith("_") and isinstance(v, dict):
            out[k] = {kk: vv for kk, vv in v.items() if kk in ("backend", "model")}
    return out


def _parse_tts(section: Any) -> TTSConfig:
    if not isinstance(section, dict):
        return TTSConfig()
    hk = section.get("hotkey")
    hotkey = (
        HotkeyConfig(**_pick(hk, HotkeyConfig))
        if isinstance(hk, dict)
        else HotkeyConfig(kind="mouse_side", key="4")
    )
    return TTSConfig(
        enabled=bool(section.get("enabled", True)),
        backend=str(section.get("backend", "system")),
        voice=str(section.get("voice", "")),
        piper_voice=str(section.get("piper_voice", "ru_RU-irina-medium")),
        hotkey=hotkey,
    )


def _pick(section: Any, dc_type: type) -> dict[str, Any]:
    """Keep only keys that are real fields of ``dc_type`` (drops _comment, typos)."""
    if not isinstance(section, dict):
        return {}
    allowed = {f.name for f in dc_type.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    return {k: v for k, v in section.items() if k in allowed}


def _discover_config_path() -> Path | None:
    root = _project_root()
    for name in ("config.json", "config.example.json"):
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def _project_root() -> Path:
    """Walk up to the project root (marker: pyproject.toml / config.example.json).

    Robust to where config.py lives in the package tree.
    """
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() or (parent / "config.example.json").exists():
            return parent
    return p.parents[3]  # fallback
