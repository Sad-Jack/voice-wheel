"""In-memory audio capture with sounddevice.

Records mono float32 at 16 kHz (what Whisper expects) into a list of numpy
chunks while the key is held; ``stop()`` concatenates and returns the buffer.
Nothing touches disk.
"""

from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16_000
CHANNELS = 1
DTYPE = "float32"


class Recorder:
    def __init__(self, sample_rate: int = SAMPLE_RATE) -> None:
        self.sample_rate = sample_rate
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._frames = []
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._callback,
            )
            self._stream.start()
            self._recording = True

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        # Runs on a PortAudio thread — do the minimum: copy and stash.
        self._frames.append(indata.copy())

    def stop(self) -> np.ndarray:
        """Stop capture and return the recorded mono float32 buffer."""
        with self._lock:
            if not self._recording:
                return np.zeros(0, dtype=DTYPE)
            self._recording = False
            assert self._stream is not None
            self._stream.stop()
            self._stream.close()
            self._stream = None
            frames, self._frames = self._frames, []
        if not frames:
            return np.zeros(0, dtype=DTYPE)
        return np.concatenate(frames, axis=0).reshape(-1).astype(DTYPE, copy=False)


def trim_silence(
    audio: np.ndarray, threshold: float = 0.01, pad: int = 1600
) -> np.ndarray:
    """Trim leading/trailing near-silence by amplitude. ``pad`` keeps a little headroom."""
    if audio.size == 0:
        return audio
    loud = np.where(np.abs(audio) > threshold)[0]
    if loud.size == 0:
        return audio
    start = max(0, int(loud[0]) - pad)
    end = min(audio.size, int(loud[-1]) + pad)
    return audio[start:end]
