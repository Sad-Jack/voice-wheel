"""Cross-thread bookkeeping shared between the UI thread and STT/LLM workers.

Three pieces of state used to live as bare attributes on the macOS controller
(``_gen`` / ``_inflight`` / ``_results``), mutated from both the main thread and
background worker threads. It worked under the GIL, but the contract was
implicit and easy to break with a future edit. This makes it explicit, owns it
in one place behind a lock, and — being pure Python — unit-testable.

- **generation**: a cycle id. Each new recording bumps it. In non-concurrent
  mode, a worker whose captured generation is stale (a newer recording has since
  started) drops its result instead of clobbering the clipboard.
- **inflight**: how many jobs are processing right now — drives the spinner.
- **results**: finished payloads the worker hands back, in order, for the main
  thread to display.

Platform-agnostic on purpose: a future Windows controller reuses the same logic.
"""

from __future__ import annotations

import threading
from collections import deque

Payload = tuple[str, str]  # (color, note) for the completion ping


class JobTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._inflight = 0
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

    # -- inflight count (spinner) --------------------------------------------

    def begin(self) -> int:
        """Register a job as started; return the new inflight count."""
        with self._lock:
            self._inflight += 1
            return self._inflight

    def finish(self) -> int:
        """Register a job as finished; return the remaining inflight count."""
        with self._lock:
            self._inflight = max(0, self._inflight - 1)
            return self._inflight

    @property
    def inflight(self) -> int:
        with self._lock:
            return self._inflight

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
        """Drop inflight bookkeeping and pending results (non-concurrent press)."""
        with self._lock:
            self._inflight = 0
            self._results.clear()
