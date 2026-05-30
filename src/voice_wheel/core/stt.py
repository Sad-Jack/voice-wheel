"""Speech-to-text with a warm, reusable model.

Default backend is **mlx-whisper** (Apple MLX, runs on the GPU/ANE — markedly
faster than faster-whisper on Apple Silicon). **faster-whisper** (int8 on CPU) is
the fallback, used either by config or automatically if mlx import/transcribe
fails.

Models are loaded once and kept warm. mlx-whisper caches loaded weights via an
internal lru_cache; faster-whisper keeps a single ``WhisperModel`` instance.
``warm_up()`` runs a throwaway transcribe at boot so the first real request isn't
the slow one.
"""

from __future__ import annotations

import logging

import numpy as np

from .config import STTConfig
from .recorder import SAMPLE_RATE

log = logging.getLogger(__name__)

# size -> mlx-community HF repo
_MLX_REPOS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
}


class STTEngine:
    def __init__(self, config: STTConfig) -> None:
        self._cfg = config
        self._backend = self._resolve(config.backend)
        self._fw_model = None  # faster-whisper WhisperModel, lazily built
        log.info("STT backend: %s (model %s)", self._backend, config.model)

    @staticmethod
    def _resolve(backend: str) -> str:
        """'auto' -> mlx on Apple Silicon (if installed), else faster-whisper."""
        if backend != "auto":
            return backend
        import importlib.util
        import platform as _plat

        if (
            _plat.system() == "Darwin"
            and _plat.machine() == "arm64"
            and importlib.util.find_spec("mlx_whisper") is not None
        ):
            return "mlx"
        return "faster-whisper"

    def transcribe(self, audio: np.ndarray, language: str) -> str:
        if audio.size == 0:
            return ""
        lang = None if language in ("auto", "", None) else language
        if self._backend == "mlx":
            try:
                return self._transcribe_mlx(audio, lang)
            except Exception as exc:  # noqa: BLE001 - fall back to CPU engine
                log.warning("mlx-whisper failed (%s); falling back to faster-whisper", exc)
                self._backend = self._cfg.fallback
        return self._transcribe_faster_whisper(audio, lang)

    def warm_up(self) -> None:
        """Pre-load/compile so the first real transcribe is fast. Errors are non-fatal."""
        dummy = np.zeros(SAMPLE_RATE // 2, dtype="float32")  # 0.5s of silence
        try:
            self.transcribe(dummy, "ru")
        except Exception as exc:  # noqa: BLE001
            log.warning("STT warm-up skipped: %s", exc)

    # -- backends -------------------------------------------------------------

    def _transcribe_mlx(self, audio: np.ndarray, language: str | None) -> str:
        import mlx_whisper

        repo = _MLX_REPOS.get(self._cfg.model, _MLX_REPOS["small"])
        result = mlx_whisper.transcribe(
            audio, path_or_hf_repo=repo, language=language
        )
        return str(result.get("text", "")).strip()

    def _transcribe_faster_whisper(self, audio: np.ndarray, language: str | None) -> str:
        if self._fw_model is None:
            from faster_whisper import WhisperModel

            self._fw_model = WhisperModel(
                self._cfg.model, device="cpu", compute_type="int8"
            )
        segments, _info = self._fw_model.transcribe(
            audio, language=language, beam_size=1
        )
        return "".join(seg.text for seg in segments).strip()
