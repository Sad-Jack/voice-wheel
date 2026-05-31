"""Cross-thread bookkeeping shared between the UI thread and STT/LLM workers.

State used to live as bare attributes on the macOS controller (``_gen`` /
``_inflight`` / ``_results``), mutated from both the main thread and background
worker threads. It worked under the GIL, but the contract was implicit and easy
to break. This makes it explicit, owns it in one place behind a lock, and — being
pure Python — unit-testable.

- **generation**: a cycle id. Each new recording bumps it. In non-concurrent
  mode, a worker whose captured generation is stale (a newer recording has since
  started) drops its result instead of clobbering the clipboard.
- **active jobs (tokens)**: a *set* of tokens, one per in-flight job — drives the
  spinner. A set, not a counter, so that a superseded job finishing late can't
  zero out a newer one's count: ``reset()`` forgets the old tokens and their
  later ``finish(token)`` becomes a no-op.
- **results**: finished payloads the worker hands back, in order, to display.

Platform-agnostic on purpose: a future Windows controller reuses the same logic.
"""

from __future__ import annotations

import threading
from collections import deque

Payload = tuple[str, str, int]  # (color, note, token) handed back per finished job


class JobTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._active: set[int] = set()   # tokens of jobs still keeping the spinner alive
        self._next_token = 0
        self._results: deque[Payload] = deque()

    # -- generation (staleness) ----------------------------------------------

    def bump_generation(self) -> int:
        """Start a new cycle; return the new generation id (main thread)."""
        with self._lock:
            self._generation += 1
            return self._generation

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def is_stale(self, gen: int) -> bool:
        """True if a newer cycle started since ``gen`` was captured (worker)."""
        with self._lock:
            return gen != self._generation

    # -- active jobs (spinner) -----------------------------------------------

    def begin(self) -> int:
        """Register a job as started; return its token (pass back to finish())."""
        with self._lock:
            self._next_token += 1
            self._active.add(self._next_token)
            return self._next_token

    def finish(self, token: int) -> int:
        """Mark a job done; return how many jobs are still active. A token that was
        already forgotten (a superseded cycle) is a no-op — so a stale job can't
        prematurely zero out the count of a newer one and stop the spinner."""
        with self._lock:
            self._active.discard(token)
            return len(self._active)

    @property
    def inflight(self) -> int:
        with self._lock:
            return len(self._active)

    # -- results queue --------------------------------------------------------

    def push_result(self, payload: Payload) -> None:
        """Hand a finished payload back to the main thread (worker)."""
        with self._lock:
            self._results.append(payload)

    def pop_result(self) -> Payload | None:
        """Take the next finished payload, or None if there's none (main thread)."""
        with self._lock:
            if not self._results:
                return None
            return self._results.popleft()

    def reset(self) -> None:
        """Supersede the current non-concurrent cycle: forget its in-flight jobs
        (their later finish() becomes a no-op) and drop its pending results. The
        spinner keeps running until the *new* cycle's job actually finishes."""
        with self._lock:
            self._active.clear()
            self._results.clear()
