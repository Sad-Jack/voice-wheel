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

- ``openai``: the OpenAI API with a key (``OPENAI_API_KEY``). Chat Completions;
  OpenAI caches long prompts automatically, so no explicit cache_control.

Two hard-won CLI rules (apply to claude_warm/claude_cli): run from a neutral dir
so the project context doesn't leak in, and put the instruction in the user
message — NOT in --append-system-prompt (the CLI flags that as injection).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

from .claude_warm import ClaudeWarmProcess
from .config import LLMConfig, app_support_dir

log = logging.getLogger(__name__)

_CLI_BACKENDS = ("claude_warm", "claude_cli")


class LLMUnavailableError(RuntimeError):
    """Raised when the selected backend isn't usable."""


class LLMClient:
    def __init__(self, config: LLMConfig, sector_models: dict | None = None) -> None:
        self._cfg = config
        self._backend = getattr(config, "backend", "ollama")
        self._sector_models = sector_models or {}  # sector_key -> {backend, model}
        self._client = None  # anthropic.Anthropic, lazily built
        self._openai = None  # openai.OpenAI, lazily built
        self._claude = None  # resolved path to the claude CLI
        self._ollama_ok = None
        self._warm = None  # ClaudeWarmProcess, spawned on prewarm() for claude_warm

    @property
    def available(self) -> bool:
        return self._backend_available(self._backend)

    def available_for(self, sector_key) -> bool:
        backend, _ = self._effective(sector_key)
        return self._backend_available(backend)

    def _backend_available(self, backend: str) -> bool:
        if backend in _CLI_BACKENDS:
            return self._claude_path() is not None
        if backend == "ollama":
            return self._ollama_reachable()
        if backend == "openai":
            return bool(os.environ.get("OPENAI_API_KEY"))
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def _effective(self, sector_key) -> tuple[str, str]:
        """Resolve (backend, model) for a sector — its override or the default."""
        ov = (self._sector_models.get(sector_key) or {}) if sector_key else {}
        backend = ov.get("backend") or self._backend
        model = ov.get("model") or (
            self._cfg.ollama_model if backend == "ollama" else self._cfg.model
        )
        return backend, model

    def warm_up(self) -> None:
        if self._backend == "ollama":
            try:
                self._complete_ollama("Ты помощник.", "ок")  # loads the model into RAM
            except Exception as exc:  # noqa: BLE001 - warm-up is best-effort, not fatal
                log.debug("ollama warm-up skipped: %s", exc)
        elif self._backend == "anthropic" and self.available:
            self._ensure_client()
        elif self._backend == "openai" and self.available:
            self._ensure_openai()  # build the client now (skip first-call TLS stall)
        # claude_warm/claude_cli: nothing to pre-warm globally (per-press prewarm).

    def complete(self, system: str, user: str, sector_key: str | None = None) -> str:
        backend, model = self._effective(sector_key)
        if backend == "claude_warm":
            # use the prewarmed process only when it matches the default model
            if model == self._cfg.model:
                return self._complete_warm(system, user)
            return self._complete_cli(system, user, model)
        if backend == "claude_cli":
            return self._complete_cli(system, user, model)
        if backend == "ollama":
            return self._complete_ollama(system, user, model)
        if backend == "openai":
            return self._complete_openai(system, user, model)
        return self._complete_api(system, user, model)

    # -- pre-warm lifecycle (claude_warm) -------------------------------------

    def prewarm(self) -> None:
        """Spawn the warm process now so its startup hides behind recording time."""
        if self._backend != "claude_warm":
            return
        claude = self._claude_path()
        if not claude:
            return
        self._warm = ClaudeWarmProcess(claude, self._cfg.model, self._workdir())
        self._warm.spawn()

    def discard_prewarm(self) -> None:
        """Kill an unused pre-warmed process (e.g. dictate ring used no LLM)."""
        if self._warm is not None:
            self._warm.discard()
            self._warm = None

    def _complete_warm(self, system: str, user: str) -> str:
        warm, self._warm = self._warm, None
        if warm is None or not warm.is_warm():
            if warm is not None:
                warm.discard()
            return self._complete_cli(system, user, self._cfg.model)  # not pre-warmed
        return warm.complete(f"{system}\n\n{user}")

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

    def _complete_cli(self, system: str, user: str, model: str | None = None) -> str:
        claude = self._claude_path()
        if not claude:
            raise LLMUnavailableError("`claude` CLI not found (install Claude Code).")
        prompt = f"{system}\n\n{user}"
        proc = subprocess.run(
            [claude, "-p", "--model", model or self._cfg.model, "--strict-mcp-config"],
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
        except Exception as exc:  # noqa: BLE001 - any error = treat ollama as unreachable
            log.debug("ollama not reachable at %s: %s", self._cfg.ollama_url, exc)
            self._ollama_ok = False
        return bool(self._ollama_ok)

    def _complete_ollama(self, system: str, user: str, model: str | None = None) -> str:
        import requests

        resp = requests.post(
            f"{self._cfg.ollama_url}/api/chat",
            json={
                "model": model or self._cfg.ollama_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "keep_alive": "30m",  # keep the model in RAM — avoids reload stalls
                "options": {"temperature": 0.3, "num_predict": self._cfg.max_tokens},
            },
            timeout=(5, 60),  # (connect, read) — fail fast instead of hanging
        )
        resp.raise_for_status()
        return str(resp.json().get("message", {}).get("content", "")).strip()

    # -- anthropic backend ----------------------------------------------------

    def _complete_api(self, system: str, user: str, model: str | None = None) -> str:
        client = self._ensure_client()
        message = client.messages.create(
            model=model or self._cfg.model,
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

    # -- openai backend -------------------------------------------------------

    def _complete_openai(self, system: str, user: str, model: str | None = None) -> str:
        client = self._ensure_openai()
        resp = client.chat.completions.create(
            model=model or self._cfg.model,
            max_tokens=self._cfg.max_tokens,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    def _ensure_openai(self):
        if not os.environ.get("OPENAI_API_KEY"):
            raise LLMUnavailableError("OPENAI_API_KEY is not set.")
        if self._openai is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # package not installed
                raise LLMUnavailableError(
                    "the `openai` package is not installed (pip install openai)."
                ) from exc
            self._openai = OpenAI()
        return self._openai
