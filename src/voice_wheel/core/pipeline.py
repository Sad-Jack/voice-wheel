"""The processing pipeline: ring/sector + audio (+ clipboard) -> result text.

Routing by ring (spec §4–5):
  - dictate   : STT only, never calls the LLM (keeps the latency budget tiny).
  - transform : STT -> LLM(style).
  - context   : clipboard-as-context + STT -> LLM(style + context).

If an LLM ring is requested but no API key is configured, it degrades
gracefully to the raw transcript (Phase A is usable without a key).

This module is read-only with respect to the clipboard (it reads context). The
caller owns *writing* the result and saving the previous clipboard, so the
save/restore stack stays in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .modes import (
    Ring,
    build_system_prompt,
    build_user_message,
    normalize_ring,
    normalize_sector,
)

if TYPE_CHECKING:  # keep runtime imports light (no numpy/AppKit) for testability
    import numpy as np

    from .config import Config
    from .llm import LLMClient
    from .stt import STTEngine


class ClipboardReader(Protocol):
    """The only thing the pipeline needs from a platform clipboard (read context)."""

    def read_text(self) -> str | None:
        ...


@dataclass(frozen=True)
class PipelineResult:
    ring: str
    sector: str
    transcript: str
    result: str
    used_context: bool = False
    context_truncated: bool = False
    llm_skipped: bool = False  # an LLM ring degraded to raw transcript (no backend)
    error: str | None = None   # STT/LLM failed; result falls back to transcript


class Pipeline:
    def __init__(
        self,
        stt: STTEngine,
        llm: LLMClient,
        clipboard: ClipboardReader,  # platform clipboard (read context before overwrite)
        config: Config,
    ) -> None:
        self._stt = stt
        self._llm = llm
        self._clipboard = clipboard
        self._config = config

    def run(self, audio: np.ndarray, ring: str, sector: str) -> PipelineResult:
        ring_e = normalize_ring(ring)
        sector = normalize_sector(sector)

        try:
            transcript = self._stt.transcribe(audio, self._config.language)
        except Exception as exc:  # noqa: BLE001 - surface as a failure, never crash
            return PipelineResult(
                ring=ring_e.value, sector=sector, transcript="", result="",
                error=f"STT: {exc}",
            )

        # Dictate, or the sector's LLM backend is unavailable -> raw transcript.
        if ring_e is Ring.DICTATE or not self._llm.available_for(sector):
            return PipelineResult(
                ring=ring_e.value,
                sector=sector,
                transcript=transcript,
                result=transcript,
                llm_skipped=ring_e is not Ring.DICTATE,
            )

        context: str | None = None
        truncated = False
        if ring_e is Ring.CONTEXT:
            context = self._clipboard.read_text() or ""
            limit = self._config.max_context_chars
            if len(context) > limit:
                context = context[:limit]
                truncated = True

        system = build_system_prompt(ring_e, sector)
        user = build_user_message(transcript, context)
        try:
            result = self._llm.complete(system, user, sector)
        except Exception as exc:  # noqa: BLE001 - keep the dictation, don't lose it
            return PipelineResult(
                ring=ring_e.value, sector=sector, transcript=transcript,
                result=transcript,  # fallback: at least keep what was said
                used_context=ring_e is Ring.CONTEXT, context_truncated=truncated,
                error=str(exc),
            )

        return PipelineResult(
            ring=ring_e.value,
            sector=sector,
            transcript=transcript,
            result=result,
            used_context=ring_e is Ring.CONTEXT,
            context_truncated=truncated,
        )
