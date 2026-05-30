#!/usr/bin/env bash
# Quick launch for Voice Wheel. Run:  ./run.sh
# Finds the venv, makes sure Ollama is up, restarts the app fresh (one instance).
set -e
cd "$(dirname "$0")"   # project dir, regardless of where it's called from

# --- pick the Python interpreter (project .venv preferred, then the dev venv) ---
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -x "$HOME/.venvs/voice-wheel-312/bin/python" ]; then
  PY="$HOME/.venvs/voice-wheel-312/bin/python"
else
  echo "✗ Нет venv. Создай его:"
  echo "    python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# --- ensure the local LLM (Ollama) is running, if that's the backend ---
if grep -q '"backend"[[:space:]]*:[[:space:]]*"ollama"' config.json 2>/dev/null; then
  if ! curl -s --max-time 1 http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "▸ Запускаю Ollama…"
    brew services start ollama >/dev/null 2>&1 || (nohup ollama serve >/dev/null 2>&1 &) || true
    sleep 1
  fi
fi

# --- one clean instance ---
pkill -f "voice_wheel" 2>/dev/null || true
sleep 0.5

echo "▶ Voice Wheel запускается…  (Ctrl+C или «Выход» в меню-баре — остановить)"
exec env PYTHONPATH=src "$PY" -u -m voice_wheel
