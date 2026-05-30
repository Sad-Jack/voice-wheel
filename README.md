# Voice Wheel / AI Voice Clipboard

A macOS-wide **voice clipboard**. Hold a configured key, speak, pick a processing **mode** around your cursor, release — and a finished, paste-ready result is in your clipboard for `Cmd+V` into any app.

> The value is not speech-to-text. It's `context + intent + style → ready-to-paste result`.

- **Ring (depth):** `dictate` (STT only) · `transform` (STT → LLM) · `context` (clipboard + STT → LLM)
- **Sector (style):** `clean` · `short` · `friendly` · `tech` (more later: prompt, qa)

This repo is built in staged phases — see [the plan](../../.claude/plans/voice-wheel-compiled-riddle.md). The radial wheel UI is Phase D; before that, the mode is taken from `default_mode` in your config.

---

## Requirements

- **macOS** on Apple Silicon (developed against 15.7.3).
- **Python 3.11 or 3.12 recommended.** Python 3.14 works for the core but `mlx-whisper` / `faster-whisper` may not ship wheels for it yet.
- An **Anthropic API key** (for `transform` / `context` modes): `export ANTHROPIC_API_KEY=sk-ant-...`

## Setup

```bash
cd "Voice Wheel : AI Voice Clipboard"
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json   # then edit if you like
```

## macOS permissions (required — the app is silent without them)

Grant these to **the app that launches Python** (your terminal during dev, e.g. Terminal.app or iTerm):

| Permission | Why | Where |
|---|---|---|
| **Microphone** | record your voice | System Settings → Privacy & Security → Microphone |
| **Input Monitoring** | detect the global hold key | System Settings → Privacy & Security → Input Monitoring |
| **Accessibility** | reliable global key capture (and optional auto-paste) | System Settings → Privacy & Security → Accessibility |

> Permissions attach to the binary hosting Python. If you switch Python versions or venvs, you may need to re-add them. A stable `.app` bundle (planned) avoids this.

## Run

**Phase 0 — overlay focus spike** (run this first; it proves the wheel won't steal focus):

```bash
python spikes/overlay_focus_spike.py
```

Move your mouse — a translucent ring follows the cursor. Click another app and type: focus must stay there. See the spike's docstring for the pass/fail checklist.

**Phase A — core dictation loop:**

```bash
python -m voice_wheel.app
```

Hold the configured key (default `f8`), speak in Russian, release. The transcription lands in your clipboard. A menu-bar icon gives you language toggle, history, and quit.

---

## Project layout

```
src/voice_wheel/      # application modules (one responsibility each)
spikes/               # de-risking experiments (overlay focus)
tests/                # unit tests for pipeline / modes / clipboard / history
config.example.json   # copy to config.json
```
