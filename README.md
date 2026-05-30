# Voice Wheel / AI Voice Clipboard

A macOS-wide **voice clipboard**. Hold a side mouse button, speak, pick a mode on the radial wheel around your cursor, release — and a finished, paste-ready result is in your clipboard for `Cmd+V` into any app.

> The value is not speech-to-text. It's `intent + style → ready-to-paste result`.

## How it works

Hold the trigger → a wheel appears at the cursor and recording starts → move the mouse to aim → release:

- **Center** → plain dictation (speech → text, no LLM).
- **Sector** → the transcript is processed by that sector's prompt, then put in the clipboard. Default sectors: **Нормализация** (up) · **Деловой** (right) · **Кратко** (down) · **Дружелюбно** (left).

A pulse flashes at the cursor when the result is ready.

## Requirements

- **macOS** on Apple Silicon (developed against 15.7.3).
- **Python 3.11 or 3.12** (mlx-whisper / faster-whisper may lack 3.14 wheels).
- An LLM backend (default is local **Ollama** — free, no key). See [LLM backends](#llm-backends).

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json        # optional: tweak settings

# default LLM backend — local, free:
brew install ollama && brew services start ollama
ollama pull qwen2.5:7b
```

## macOS permissions (the app is silent without them)

Grant these to **the binary that launches Python** (your terminal during dev):

| Permission | Why |
|---|---|
| **Microphone** | record your voice |
| **Accessibility** | global mouse/key capture via the event tap |
| **Input Monitoring** | detect the trigger button |

System Settings → Privacy & Security → (each pane). The app pops the Accessibility prompt on first run.

## Run

Quick way (finds the venv, starts Ollama if needed, runs one fresh instance):

```bash
./run.sh
```

Or manually:

```bash
PYTHONPATH=src python -m voice_wheel.macos_app
```

Hold your trigger (default: side mouse button #3 — configurable in `config.json`), speak, release. Result lands in the clipboard.

First, sanity-check the overlay doesn't steal focus:

```bash
python spikes/overlay_focus_spike.py   # see the PASS/FAIL checklist in its docstring
```

## LLM backends

Set `llm.backend` in `config.json`:

| backend | speed | cost | notes |
|---|---|---|---|
| `ollama` (default) | ~2s, stable | free, local | needs Ollama + a model (`qwen2.5:7b`). Private, no key. |
| `claude_warm` | ~2–13s (rate-limit jitter) | free w/ Claude Max | spawns `claude` CLI on press so startup hides behind recording. Best quality. |
| `anthropic` | ~1–2s | paid | needs `ANTHROPIC_API_KEY`. Fastest + best. |
| `claude_cli` | ~5–10s | free w/ Claude Max | simple one-shot CLI call. |

## Customize (no GUI — just edit files)

**Sectors / prompts** — the `prompts/` folder. Each `N-Label.md` is one sector:
number = order, filename = label, file body = the processing prompt. The wheel
splits into as many sectors as there are files.

```bash
prompts/
  1-Нормализация.md   # body: "Нормализуй распознанную речь: ..."
  2-Деловой.md
  3-Кратко.md
  4-Дружелюбно.md
```

Edit a file to change how that sector processes text; add `5-QA.md` to add a
sector; delete one to remove it. **Restart the app to apply.**

**Trigger** — `config.json` → `hotkey`:

```jsonc
{"kind": "mouse_side", "key": "3"}   // side button (3 = back, 4 = forward) — default
{"kind": "keyboard",   "key": "f8"}  // hold a key (any pynput key name)
{"kind": "mouse",      "key": "middle"}  // left / right / middle
```

**LLM backend** — `config.json` → `llm.backend` (see the table above). Restart after editing.

## Troubleshooting

- **Trigger does nothing** → grant **Accessibility** to the binary running Python, then restart (the app pops the prompt on first run).
- **No audio / always empty (red ping)** → grant **Microphone**; check the mic isn't muted.
- **Sectors return raw text (orange ping)** → the LLM backend isn't reachable. For `ollama`: `brew services start ollama`, then `ollama list` (run `ollama pull qwen2.5:7b` if missing). For `anthropic`: set `ANTHROPIC_API_KEY`.
- **`claude_warm` is slow / jittery** → Claude Max rate limits; switch to `ollama` for consistent speed.
- **Stuck spinner / trigger frozen** → just press the trigger again; a new press self-heals any stuck state.

## Project layout

```
src/voice_wheel/
  macos_app.py     # controller: trigger → record → wheel → process → clipboard → pulse
  wheel_overlay.py # the radial wheel (non-activating NSPanel)
  mouse_tap.py     # side-button trigger (Quartz event tap)
  pulse.py         # completion pulse at the cursor
  recorder.py      # in-memory audio capture (sounddevice)
  stt.py           # speech-to-text (mlx-whisper, faster-whisper fallback)
  modes.py         # rings/sectors + prompts
  pipeline.py      # routing: dictate / transform / context
  llm.py           # LLM backends (ollama / claude_warm / claude_cli / anthropic)
  clipboard.py     # NSPasteboard read/write + previous-clipboard stack
  history.py       # SQLite, last N results
  config.py        # config loading
spikes/            # overlay focus de-risk
tests/             # pipeline / modes / clipboard / history
config.example.json
FEATURES.md        # feature tracker
```
