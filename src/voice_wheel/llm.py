"""LLM processing — several backends, selected by ``config.llm.backend``.

- ``claude_warm`` (default): the clever trick. On button press we spawn a
  persistent ``claude`` CLI process in stream-json mode; its ~5s startup overlaps
  with the user speaking. On release we send the prompt to the already-warm
  process and get a reply in ~2-3s. Each recording spawns a FRESH process, so
  there's no context bleed between requests. Runs on the Claude Max subscription
  — no API key. Falls back to a one-shot CLI call if not pre-warmed.

- ``claude_cli``: one-shot ``claude -p`` per call (simple, but ~5-10s each).

- ``ollama``: a local model (free, no key, fully private). Clean system/user
  split. Lower RU quality than Claude but fast.

- ``anthropic``: the Anthropic API with a key (fastest + best, needs billing).

Two hard-won CLI rules (apply to claude_warm/claude_cli): run from a neutral dir
so the project context doesn't leak in, and put the instruction in the user
message — NOT in --append-system-prompt (the CLI flags that as injection).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading

from .config import LLMConfig, app_support_dir

_CLI_BACKENDS = ("claude_warm", "claude_cli")


def _terminate(proc) -> None:
    try:
        if proc.stdin:
            proc.stdin.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.terminate()
    except Exception:  # noqa: BLE001
        pass


class LLMUnavailableError(RuntimeError):
    """Raised when the selected backend isn't usable."""


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._cfg = config
        self._backend = getattr(config, "backend", "claude_warm")
        self._client = None  # anthropic.Anthropic, lazily built
        self._claude = None  # resolved path to the claude CLI
        self._ollama_ok = None
        self._proc = None  # pre-warmed claude stream-json process
        self._reader = None  # background thread draining its stdout
        self._result_event = None
        self._result_holder = None
        self._proc_lock = threading.Lock()

    @property
    def available(self) -> bool:
        if self._backend in _CLI_BACKENDS:
            return self._claude_path() is not None
        if self._backend == "ollama":
            return self._ollama_reachable()
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def warm_up(self) -> None:
        if self._backend == "ollama":
            try:
                self._complete_ollama("Ты помощник.", "ок")  # loads the model into RAM
            except Exception:  # noqa: BLE001
                pass
        elif self._backend == "anthropic" and self.available:
            self._ensure_client()
        # claude_warm/claude_cli: nothing to pre-warm globally (per-press prewarm).

    def complete(self, system: str, user: str) -> str:
        if self._backend == "claude_warm":
            return self._complete_warm(system, user)
        if self._backend == "claude_cli":
            return self._complete_cli(system, user)
        if self._backend == "ollama":
            return self._complete_ollama(system, user)
        return self._complete_api(system, user)

    # -- pre-warm lifecycle (claude_warm) -------------------------------------

    def prewarm(self) -> None:
        """Spawn the stream-json process now so its startup hides behind recording.

        A background thread drains stdout immediately — otherwise the child blocks
        writing its boot output and never finishes warming up during the wait.
        """
        if self._backend != "claude_warm":
            return
        claude = self._claude_path()
        if not claude:
            return
        with self._proc_lock:
            self._kill_proc_locked()
            try:
                proc = subprocess.Popen(
                    [
                        claude, "-p",
                        "--input-format", "stream-json",
                        "--output-format", "stream-json",
                        "--model", self._cfg.model,
                        "--strict-mcp-config",
                        "--verbose",
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    cwd=self._workdir(),
                    bufsize=1,
                )
            except Exception:  # noqa: BLE001
                self._proc = None
                return
            self._proc = proc
            self._result_event = threading.Event()
            self._result_holder = {}
            self._reader = threading.Thread(
                target=self._reader_loop,
                args=(proc, self._result_event, self._result_holder),
                daemon=True,
            )
            self._reader.start()

    def discard_prewarm(self) -> None:
        """Kill an unused pre-warmed process (e.g. dictate ring used no LLM)."""
        with self._proc_lock:
            self._kill_proc_locked()

    def _kill_proc_locked(self) -> None:
        if self._proc is not None:
            _terminate(self._proc)
            self._proc = None
        self._reader = None
        self._result_event = None
        self._result_holder = None

    @staticmethod
    def _reader_loop(proc, event, holder) -> None:
        """Continuously drain stdout from spawn time; capture the result event."""
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
        except Exception:  # noqa: BLE001
            pass
        finally:
            event.set()  # unblock the waiter even if the stream closed early

    def _complete_warm(self, system: str, user: str) -> str:
        with self._proc_lock:
            proc, event, holder = self._proc, self._result_event, self._result_holder
            self._proc = None  # take ownership (reader thread keeps running)
            self._reader = None
            self._result_event = None
            self._result_holder = None
        if proc is None or proc.poll() is not None or event is None:
            return self._complete_cli(system, user)  # not pre-warmed -> one-shot
        try:
            content = f"{system}\n\n{user}"
            msg = json.dumps(
                {"type": "user", "message": {"role": "user", "content": content}}
            )
            proc.stdin.write(msg + "\n")
            proc.stdin.flush()
            if not event.wait(timeout=90):
                raise RuntimeError("warm claude: timeout")
            result = (holder or {}).get("result")
            if not result:
                raise RuntimeError("warm claude: no result")
            return result
        finally:
            _terminate(proc)

    # -- one-shot CLI backend -------------------------------------------------

    def _claude_path(self):
        if self._claude is not None:
            return self._claude or None
        found = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
        self._claude = found if os.path.exists(found) else ""
        return self._claude or None

    def _workdir(self) -> str:
        d = app_support_dir() / "llm-cwd"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _complete_cli(self, system: str, user: str) -> str:
        claude = self._claude_path()
        if not claude:
            raise LLMUnavailableError("`claude` CLI not found (install Claude Code).")
        prompt = f"{system}\n\n{user}"
        proc = subprocess.run(
            [claude, "-p", "--model", self._cfg.model, "--strict-mcp-config"],
            input=prompt,
            cwd=self._workdir(),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:200]
            raise RuntimeError(f"claude CLI error: {detail}")
        return proc.stdout.strip()

    # -- ollama backend -------------------------------------------------------

    def _ollama_reachable(self) -> bool:
        if self._ollama_ok:
            return True
        try:
            import requests

            requests.get(f"{self._cfg.ollama_url}/api/tags", timeout=2)
            self._ollama_ok = True
        except Exception:  # noqa: BLE001
            self._ollama_ok = False
        return bool(self._ollama_ok)

    def _complete_ollama(self, system: str, user: str) -> str:
        import requests

        resp = requests.post(
            f"{self._cfg.ollama_url}/api/chat",
            json={
                "model": self._cfg.ollama_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": self._cfg.max_tokens},
            },
            timeout=120,
        )
        resp.raise_for_status()
        return str(resp.json().get("message", {}).get("content", "")).strip()

    # -- anthropic backend ----------------------------------------------------

    def _complete_api(self, system: str, user: str) -> str:
        client = self._ensure_client()
        message = client.messages.create(
            model=self._cfg.model,
            max_tokens=self._cfg.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in message.content if b.type == "text").strip()

    def _ensure_client(self):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMUnavailableError("ANTHROPIC_API_KEY is not set.")
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic()
        return self._client
