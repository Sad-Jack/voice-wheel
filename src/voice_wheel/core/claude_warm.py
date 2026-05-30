"""A pre-warmable single-shot ``claude`` CLI session (stream-json).

``spawn()`` launches the process so its ~5s startup overlaps with the user
speaking; a reader thread drains stdout from the start (else the child blocks on
its own boot output and never finishes warming). ``complete(prompt)`` sends one
message, waits for the reply, then kills the process — a FRESH process per
request, so there's no context bleed. Runs on the Claude Max subscription (no key).
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading

log = logging.getLogger(__name__)


def _terminate(proc) -> None:
    # Best-effort teardown — the process may already be dead; failures here are
    # expected and intentionally swallowed (narrowed to the OS/IO errors close()
    # and terminate() can raise, so a real bug wouldn't hide here).
    try:
        if proc.stdin:
            proc.stdin.close()
    except (OSError, ValueError):
        pass
    try:
        proc.terminate()
    except OSError:
        pass


class ClaudeWarmProcess:
    def __init__(self, claude_path: str, model: str, cwd: str) -> None:
        self._claude = claude_path
        self._model = model
        self._cwd = cwd
        self._proc = None
        self._reader = None
        self._event = None
        self._holder = None
        self._lock = threading.Lock()

    def spawn(self) -> None:
        with self._lock:
            self._kill_locked()
            try:
                proc = subprocess.Popen(
                    [
                        self._claude, "-p",
                        "--input-format", "stream-json",
                        "--output-format", "stream-json",
                        "--model", self._model,
                        "--strict-mcp-config",
                        "--verbose",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    cwd=self._cwd,
                    bufsize=1,
                )
            except Exception as exc:  # noqa: BLE001 - any spawn failure: stay usable via one-shot CLI
                log.warning("warm claude spawn failed: %s", exc)
                self._proc = None
                return
            self._proc = proc
            self._event = threading.Event()
            self._holder = {}
            self._reader = threading.Thread(
                target=self._reader_loop, args=(proc, self._event, self._holder), daemon=True
            )
            self._reader.start()

    def is_warm(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def complete(self, prompt: str, timeout: float = 90) -> str:
        with self._lock:
            proc, event, holder = self._proc, self._event, self._holder
            self._proc = self._reader = self._event = self._holder = None
        if proc is None or proc.poll() is not None or event is None:
            raise RuntimeError("warm claude: not running")
        try:
            msg = json.dumps({"type": "user", "message": {"role": "user", "content": prompt}})
            proc.stdin.write(msg + "\n")
            proc.stdin.flush()
            if not event.wait(timeout=timeout):
                raise RuntimeError("warm claude: timeout")
            result = (holder or {}).get("result")
            if not result:
                raise RuntimeError("warm claude: no result")
            return result
        finally:
            _terminate(proc)

    def discard(self) -> None:
        with self._lock:
            self._kill_locked()

    def _kill_locked(self) -> None:
        if self._proc is not None:
            _terminate(self._proc)
            self._proc = None
        self._reader = self._event = self._holder = None

    @staticmethod
    def _reader_loop(proc, event, holder) -> None:
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "result":
                    holder["result"] = str(obj.get("result", "")).strip()
                    event.set()
                    return
        except Exception as exc:  # noqa: BLE001 - reader thread must never raise
            log.debug("warm claude reader stopped: %s", exc)
        finally:
            event.set()  # unblock the waiter even if the stream closed early
