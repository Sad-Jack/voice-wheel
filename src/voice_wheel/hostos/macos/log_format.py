"""Pure formatting for the «Логи» feed — one human line per event dict.

Lives apart from the settings window so it's unit-testable without building any
AppKit objects (it imports only i18n + stdlib). Presentation only; the event
store and ordering live in ``core.event_log``. The i18n keys stay here (platform
layer), resolved through ``i18n.t``.
"""

from __future__ import annotations

import time

from .i18n import t as _tr

# error categories that have a dedicated «человеческая» i18n string; anything else
# falls back to «err_other» (keep in sync with core.event_log.classify_error).
_KNOWN_CATS = {"auth", "rate_limit", "unreachable", "model", "stt", "other"}


def _short(s, n: int = 160) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def format_log_line(ev: dict, lang: str) -> str:
    """One human line for an event dict (see ``core.event_log``):
    ``"HH:MM:SS  <icon> <kind> → «…»"``. Newest-first ordering is the caller's job."""
    def tr(key: str) -> str:
        return _tr(key, lang)

    t = ev.get("t")
    ts = time.strftime("%H:%M:%S", time.localtime(t)) if t else "--:--:--"
    kind = ev.get("kind", "")
    if kind == "dictate":
        body = f'🎤 {tr("log_dictation")} → «{_short(ev.get("result") or ev.get("transcript"))}»'
    elif kind == "transform":
        sector = ev.get("sector") or "?"
        body = f'🎤 {tr("log_recorded")} → 🧠 {sector} → «{_short(ev.get("result"))}»'
    elif kind == "context":
        sector = ev.get("sector") or "?"
        body = (f'📋 {tr("log_buffer")} · 🎤 {tr("log_recorded")} → 🧠 {sector} '
                f'→ «{_short(ev.get("result"))}»')
    elif kind == "tts":
        body = f'🔊 {tr("log_spoken")}: «{_short(ev.get("text"))}»'
    elif kind == "crash":
        body = f'💥 {tr("log_crash")}: {_short(ev.get("message"), 200)}'
    else:  # error
        cat = ev.get("cat") or "other"
        human = tr(f"err_{cat}" if cat in _KNOWN_CATS else "err_other")
        body = f'⚠️ {tr("log_error")}: {human} — {_short(ev.get("message"), 160)}'
    return f"{ts}  {body}"
