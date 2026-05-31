"""Local neural TTS via Piper — offline, free, no key.

Mirrors the macOS ``Speaker`` interface (``toggle`` / ``stop``) so the controller
can swap backends freely. The neural voice model is downloaded on first use
(~60 MB) and cached; after that it's fully offline. Synthesis is ~10x faster than
realtime, but we still run synth + playback on a background thread so the UI never
blocks, and play through sounddevice (already a dependency, cross-platform).

Heavy imports (piper, sounddevice, numpy) are done lazily inside methods so that
importing this module stays cheap and the core package remains test-friendly.
"""

from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

DEFAULT_VOICE = "ru_RU-irina-medium"


class PiperSpeaker:
    def __init__(self, voice_name: str, cache_dir) -> None:
        self._voice_name = voice_name or DEFAULT_VOICE
        self._cache = cache_dir
        self._voice = None  # lazily loaded PiperVoice (download + load on first use)
        self._gen = 0       # bump to supersede/stop the current utterance
        self._playing = False
        self._lock = threading.Lock()

    def toggle(self, text: str | None) -> str:
        """Main-thread only. Returns 'speaking' | 'stopped' | 'empty'."""
        with self._lock:
            already_playing = self._playing
            if already_playing:
                self._gen += 1
                self._playing = False
        if already_playing:
            self._stop_playback()
            return "stopped"

        text = (text or "").strip()
        if not text:
            return "empty"
        with self._lock:
            self._gen += 1
            gen = self._gen
            self._playing = True
        threading.Thread(target=self._speak, args=(text, gen), daemon=True).start()
        return "speaking"

    def stop(self) -> None:
        """Main-thread only. Stop any ongoing speech and free the audio device."""
        with self._lock:
            self._gen += 1
            self._playing = False
        self._stop_playback()

    # -- background -----------------------------------------------------------

    def _speak(self, text: str, gen: int) -> None:
        try:
            import numpy as np

            voice = self._ensure_voice()
            chunks = list(voice.synthesize(text))
            if not chunks:
                return
            audio = np.concatenate([c.audio_float_array for c in chunks])
            rate = chunks[0].sample_rate
            with self._lock:
                if gen != self._gen:
                    return  # superseded or stopped before playback started
            import sounddevice as sd

            sd.play(audio, samplerate=rate)
            sd.wait()  # blocks this background thread until done (or sd.stop())
        except Exception as exc:  # noqa: BLE001 - TTS must never crash the app
            log.warning("piper TTS failed: %s", exc)
        finally:
            with self._lock:
                if gen == self._gen:
                    self._playing = False

    def _ensure_voice(self):
        if self._voice is None:
            from pathlib import Path

            from piper import PiperVoice
            from piper.download_voices import download_voice

            cache = Path(self._cache)
            cache.mkdir(parents=True, exist_ok=True)
            model = cache / f"{self._voice_name}.onnx"
            if not model.exists():
                log.info("downloading piper voice %s …", self._voice_name)
                download_voice(self._voice_name, cache)
            self._voice = PiperVoice.load(str(model))
        return self._voice

    @staticmethod
    def _stop_playback() -> None:
        try:
            import sounddevice as sd

            sd.stop()
        except Exception as exc:  # noqa: BLE001
            log.debug("sounddevice stop: %s", exc)
