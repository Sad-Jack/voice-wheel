"""A small structured event log — what the app did and any errors — surfaced in
the settings «Логи» tab.

Events come from worker threads (STT/LLM pipeline), the main thread (TTS), and
the crash hook, so the store is thread-safe. It keeps the last N events in
memory (what the tab shows) and mirrors them to a JSONL file so the log survives
an app restart. Platform-agnostic (stdlib only) — lives in ``core`` so both the
pipeline and the controller can write to it.

Kinds:
  dictate    — center: speech -> clipboard, no LLM
  transform  — sector: speech -> LLM(prompt) -> clipboard
  context    — outer ring: clipboard-as-context + speech -> LLM -> clipboard
  tts        — text read aloud
  error      — something failed (auth / unreachable / model / timeout / stt / …)
  crash      — an unhandled exception
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path

_MAX = 1000              # events kept in memory / shown in the tab (scroll back this far)
_MAX_BYTES = 5 * 1024 * 1024  # hard ceiling on the JSONL file (~5 MB) — see _compact


def classify_error(message: str) -> str:
    """Rough bucket for an error message, for the log icon and key-status (#14)."""
    s = (message or "").lower()
    if s.startswith("stt:") or "transcribe" in s or "whisper" in s:
        return "stt"
    if any(k in s for k in ("401", "403", "unauthorized", "authentication",
                            "invalid api key", "invalid x-api-key", "no api key",
                            "permission", "api key")):
        return "auth"
    if any(k in s for k in ("429", "rate limit", "rate_limit", "quota", "overloaded",
                            "insufficient_quota")):
        return "rate_limit"
    if any(k in s for k in ("connection", "timed out", "timeout", "refused",
                            "unreachable", "max retries", "getaddrinfo", "connect")):
        return "unreachable"
    if any(k in s for k in ("404", "not found", "does not exist", "no such model",
                            "model '")):
        return "model"
    return "other"


class EventLog:
    def __init__(
        self,
        path: Path | None = None,
        maxlen: int = _MAX,
        max_bytes: int = _MAX_BYTES,
    ) -> None:
        self._path = Path(path) if path else None
        self._buf: deque = deque(maxlen=maxlen)
        self._max_bytes = max_bytes
        self._lock = threading.Lock()
        if self._path is not None:
            self._load_tail()

    def _load_tail(self) -> None:
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines[-self._buf.maxlen:]:
            line = line.strip()
            if not line:
                continue
            try:
                self._buf.append(json.loads(line))
            except ValueError:
                continue

    def add(self, kind: str, level: str = "info", **fields) -> dict:
        event = {"t": time.time(), "kind": kind, "level": level, **fields}
        with self._lock:
            self._buf.append(event)
        if self._path is not None:
            try:
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
                if self._max_bytes and self._path.stat().st_size > self._max_bytes:
                    self._compact()
            except OSError:
                pass
        return event

    def _compact(self) -> None:
        """Keep the file bounded: rewrite it with only the most recent events (the
        in-memory tail), so a long-running app never lets the log grow past the cap.
        Atomic via a temp file so a crash mid-write can't corrupt the log."""
        with self._lock:
            items = list(self._buf)
        body = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in items)
        try:
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            pass

    def recent(self, n: int | None = None) -> list:
        """Newest first."""
        with self._lock:
            items = list(self._buf)
        items.reverse()
        return items[:n] if n else items

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
        if self._path is not None:
            try:
                self._path.write_text("", encoding="utf-8")
            except OSError:
                pass


# Process-wide singleton. ``init`` points it at a file (the app does this at
# startup); until then events accumulate in memory only.
EVENTS = EventLog()


def init(path: Path) -> None:
    global EVENTS  # noqa: PLW0603 - one process-wide log by design
    EVENTS = EventLog(path=path)


def log_event(kind: str, level: str = "info", **fields) -> dict:
    return EVENTS.add(kind, level=level, **fields)
