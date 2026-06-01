# Voice Wheel / AI Voice Clipboard

A macOS-wide **voice clipboard**. Hold a side mouse button, speak, pick a mode on
the radial wheel around your cursor, release — and a finished, paste-ready result
is in your clipboard for `⌘V` into any app.

> The value isn't speech-to-text. It's **`intent + style → ready-to-paste result`.**

A pure-PyObjC menu-bar agent (no Dock icon). The overlay never steals focus, so
the result pastes into whatever app you were in. Runs fully local and free by
default (Ollama for the LLM, Whisper for speech, Piper for voice) — no API key
required.

---

## How it works

Hold the trigger → a neon wheel appears at the cursor and recording starts → move
the mouse to aim → release:

- **Center** → plain dictation (speech → text, no LLM).
- **Inner ring (a sector)** → the transcript is processed by that sector's prompt.
- **Outer ring (a sector)** → your clipboard is used as **context** + your spoken
  instruction → that sector's prompt → result.
- **Cursor outside the wheel** → **✕ cancel**, nothing happens.

Default sectors (by direction): **Нормализация** (up) · **Деловой** (right) ·
**Кратко** (down) · **Дружелюбно** (left). A colored pulse flashes at the cursor
when done: 🟢 ok · 🟠 raw text saved (LLM unavailable) · 🔴 failed.

**Read aloud:** press the TTS button (default side button **#4**) to speak the
**selected** text in any app (or the clipboard if nothing is selected) — a local
neural voice, offline. Press again to stop.

---

## Quick start

Full, step-by-step instructions (incl. permissions and what auto-downloads) are
in **[SETUP.md](docs/SETUP.md)**. The short version:

```bash
python3.12 -m venv ~/.venvs/voice-wheel-312
~/.venvs/voice-wheel-312/bin/pip install -r requirements.txt

brew install ollama && brew services start ollama
ollama pull qwen2.5:7b

./run.sh
```

Grant **Microphone**, **Accessibility**, and **Input Monitoring** to the app
launching Python (your terminal in dev), then restart. The menu-bar icon is
**red until ready**, **green** when live.

The Whisper model and the Piper voice **download themselves on first run** — no
manual step.

---

## Features

- Radial wheel overlay (non-activating `NSPanel`) — never steals focus.
- Side-mouse-button trigger via a Quartz event tap (on a dedicated thread).
- **STT:** `mlx-whisper` (Apple Silicon) / `faster-whisper` (fallback), Russian by default.
- **LLM:** Ollama (local, default) · Claude Max (`claude_warm`/`claude_cli`) · Anthropic API. Per-sector model override.
- **TTS read-aloud:** Piper local neural voice (default) or macOS voices; speaks the selection or clipboard.
- Menu-bar agent: color-coded ready state, **History** (re-copy a past result), **Settings**, Quit.
- Native **Settings** window — edit everything without touching JSON.
- Prompts as editable `.md` files; concurrent-recording toggle; cancel gesture.

---

## LLM backends

Set `llm.backend` in **Settings** (or `config.json`):

| backend | speed | cost | notes |
|---|---|---|---|
| `ollama` (default) | ~2s | free, local | needs Ollama + a model (`qwen2.5:7b`). Private, no key. |
| `claude_warm` | ~2–13s (jitter) | free w/ Claude Max | spawns the `claude` CLI on press so startup hides behind recording. Best quality. |
| `anthropic` | ~1–2s | paid | needs `ANTHROPIC_API_KEY`. Fastest. |
| `claude_cli` | ~5–10s | free w/ Claude Max | simple one-shot CLI call. |

---

## Voice (TTS)

Choose in **Settings → Голос**:

- **Piper** (default) — local **neural** voices, offline, free. RU: Irina, Денис, Руслан, Дмитрий. The chosen voice auto-downloads (~63 MB) on first use.
- **macOS** — system voices. For natural ones, use the "download premium voices" button (opens the system pane; Apple gives no API to fetch them silently).

The design for the upcoming three-connection-type settings is in
**[SETTINGS.md](docs/SETTINGS.md)**.

---

## Customize

**Sectors / prompts** — the `prompts/` folder. Each `N-Label.md` is one sector:
number = order, filename = label, body = the processing prompt. The wheel splits
into as many sectors as there are files. Edit to change behavior, add `5-QA.md`
to add a sector, delete one to remove it. **Restart to apply.**

**Trigger** — Settings, or `config.json → hotkey`:

```jsonc
{"kind": "mouse_side", "key": "3"}      // side button (3 = back, 4 = forward) — default
{"kind": "keyboard",   "key": "cmd+б"}  // a key or combo (combos dodge macOS media keys like F7–F9)
{"kind": "mouse",      "key": "middle"} // left / right / middle
```

---

## Project layout

```
src/voice_wheel/
  __main__.py            entry: `python -m voice_wheel` (picks platform by sys.platform)
  core/                  platform-agnostic (no PyObjC)
    config, modes, pipeline, llm, claude_warm, stt, recorder,
    history, job_tracker, wheel_geometry, piper_tts
  hostos/macos/          PyObjC (UI/IO under macOS)
    macos_app, wheel_overlay, mouse_tap, triggers, pulse,
    settings, tray, tts, clipboard
prompts/                 sector prompts (N-Label.md)
tests/                   core unit tests (pytest)
```

`core/` never imports `hostos/`; `hostos/ → core`. See
**[ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Troubleshooting

- **Trigger does nothing / icon stays red** → grant **Accessibility**, restart.
- **Empty result (red ping)** → grant **Microphone**; a <0.35s tap is skipped on purpose.
- **Raw text instead of processed (orange ping)** → LLM backend unreachable (start Ollama / pull the model / set the API key).
- **Stuck spinner** → press the trigger again; a new press self-heals.

More in **[SETUP.md](docs/SETUP.md)**.

---

## Docs

- **[SETUP.md](docs/SETUP.md)** — install & configure on a fresh Mac.
- **[SETTINGS.md](docs/SETTINGS.md)** — settings design (current + v2 vision).
- **[FEATURES.md](docs/FEATURES.md)** — feature tracker.
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** — architecture & tech-debt log.
