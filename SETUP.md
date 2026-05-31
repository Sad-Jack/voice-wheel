# Setup — what to install before Voice Wheel runs

A checklist for getting Voice Wheel working on a fresh Mac. Follow it top to
bottom. Most heavy assets (the Whisper model, the Piper voice) **download
themselves on first run** — what you install by hand is Python deps, Ollama, and
macOS permissions.

> TL;DR: Python 3.12 venv → `pip install -r requirements.txt` → Ollama + a model
> → grant 3 permissions → `./run.sh`.

---

## 0. Prerequisites

| Need | Notes |
|---|---|
| **macOS on Apple Silicon** | Developed against macOS 15.x. Intel may work via the `faster-whisper` STT fallback but isn't tested. |
| **Python 3.11 or 3.12** | **Not 3.13/3.14** — `mlx-whisper` / `faster-whisper` may lack wheels there. Check with `python3.12 --version`. |
| **Homebrew** | For installing Ollama. https://brew.sh |
| **~2 GB free disk** | Whisper `small` (~0.5 GB), a Piper voice (~63 MB), an Ollama model (`qwen2.5:7b` ≈ 4.7 GB). |

---

## 1. Python environment + dependencies

```bash
cd "<project folder>"
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

⚠️ **If the project path contains a `:` or spaces** (e.g. `Voice Wheel : AI Voice
Clipboard`), `python -m venv .venv` inside it can break. Put the venv elsewhere:

```bash
python3.12 -m venv ~/.venvs/voice-wheel-312
~/.venvs/voice-wheel-312/bin/pip install -r requirements.txt
```

`run.sh` looks for `.venv/` first, then `~/.venvs/voice-wheel-312/`.

What `requirements.txt` pulls in: PyObjC (Cocoa + Quartz), pynput, sounddevice +
numpy, **mlx-whisper** + **faster-whisper** (STT), **piper-tts** (neural voice),
anthropic + requests (LLM clients).

---

## 2. LLM backend — Ollama (the default: local, free, no key)

```bash
brew install ollama
brew services start ollama        # or: ollama serve
ollama pull qwen2.5:7b            # the default model
```

`run.sh` auto-starts Ollama if `config.json` uses the `ollama` backend.

**Other backends** (set `llm.backend` in the Settings window or `config.json`):
- `claude_warm` / `claude_cli` — need [Claude Code](https://claude.com/claude-code) installed and logged in (`claude login`); runs on a Claude Max subscription, no API key.
- `anthropic` — needs `ANTHROPIC_API_KEY` in the environment (or a `.env` file at the project root).

---

## 3. macOS permissions (the app is silent without them)

Grant these to **the binary that launches Python** — during development that's
your **terminal app** (Terminal/iTerm); for the bundled `.app` it's *Voice Wheel*.
System Settings → Privacy & Security:

| Permission | Pane | Why |
|---|---|---|
| **Microphone** | Microphone | record your voice |
| **Accessibility** | Accessibility | global mouse/key event tap + synthesize ⌘C for "speak selection" |
| **Input Monitoring** | Input Monitoring | detect the trigger button |

The app pops the Accessibility prompt on first launch. **After granting, restart
the app.** The menu-bar icon is **red until ready** and turns **green** once the
trigger is live and warm-up is done.

---

## 4. Run

```bash
./run.sh                 # finds the venv, starts Ollama if needed, one fresh instance
```

Or manually:

```bash
PYTHONPATH=src ~/.venvs/voice-wheel-312/bin/python -m voice_wheel
```

Double-clickable app (menu-bar agent, stable bundle id so permissions persist):

```bash
./make_app.sh            # builds "Voice Wheel.app" — double-click from Finder
```

---

## 5. What downloads automatically (no action needed)

| Asset | When | Size | Where |
|---|---|---|---|
| **Whisper STT model** (`small`) | first run (warm-up) | ~0.5 GB | Hugging Face cache |
| **Piper voice** (`ru_RU-irina-medium`) | first run (warm-up) | ~63 MB | `~/Library/Application Support/VoiceWheel/piper/` |

On first launch the console prints `Готовлю голос Piper (~60 МБ)…` while the voice
downloads; the menu-bar icon stays red until it's ready. **If you're offline**,
the voice can't download and TTS falls back to the macOS system voice — no crash.

Switching to another Piper voice in Settings downloads it on save. Premium macOS
voices can't be auto-downloaded (Apple gives no API) — the Settings button opens
the system pane so you can grab them manually.

---

## 6. Quick verification

```bash
PYTHONPATH=src ~/.venvs/voice-wheel-312/bin/python -m pytest tests/ -q   # 23 passing
```

Then: hold the trigger (default side button **#3**), say a sentence, release over
a sector → cleaned-up text should be in your clipboard for `⌘V`. Press **#4** with
text selected → it reads the selection aloud.

---

## 7. Troubleshooting

- **Trigger does nothing / icon stays red** → grant **Accessibility** to the binary running Python, then restart.
- **Always empty (red ping)** → grant **Microphone**; check the mic isn't muted; a too-short tap (<0.35s) is skipped on purpose.
- **Sectors return raw text (orange ping)** → the LLM backend isn't reachable. Ollama: `brew services start ollama` then `ollama list` (pull the model if missing).
- **No voice on ⌘4** → first run may still be downloading the voice (watch the console); or you're offline (it falls back to the macOS voice).
- **`python -m venv` failed** → the path has a `:`/space; use `~/.venvs/voice-wheel-312` (see step 1).

See [README.md](README.md) for usage and [SETTINGS.md](SETTINGS.md) for the
settings design.
