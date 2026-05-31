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

# --- supervised run: auto-restart on crash or freeze (heartbeat watchdog, #48) ---
HEARTBEAT="$HOME/Library/Application Support/VoiceWheel/heartbeat"
FREEZE_DIR="$HOME/Library/Application Support/VoiceWheel"   # where freeze traces go (#49)
STALE_AFTER=15   # seconds with no heartbeat = main thread hung -> kill + restart
GRACE=12         # ignore the heartbeat for the first N seconds (boot / warm-up)

pkill -f "voice_wheel" 2>/dev/null || true
sleep 0.5
echo "▶ Voice Wheel запускается…  (Ctrl+C или «Выход» в меню-баре — остановить)"

APP_PID=""
cleanup() { [ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null; exit 0; }
trap cleanup INT TERM

set +e   # the loop handles non-zero exits itself
while true; do
  rm -f "$HEARTBEAT"
  env PYTHONPATH=src "$PY" -u -m voice_wheel &
  APP_PID=$!
  started=$(date +%s)
  hung=0
  while kill -0 "$APP_PID" 2>/dev/null; do
    sleep 3
    now=$(date +%s)
    [ $((now - started)) -lt "$GRACE" ] && continue
    if [ -f "$HEARTBEAT" ]; then
      age=$(( now - $(stat -f %m "$HEARTBEAT" 2>/dev/null || echo "$now") ))
      if [ "$age" -gt "$STALE_AFTER" ]; then
        # Snapshot the frozen process BEFORE killing it, so we can diagnose #49.
        FREEZE_LOG="$FREEZE_DIR/freeze-$(date +%Y%m%d-%H%M%S).txt"
        echo "⚠️  Зависание (нет heartbeat ${age}с) — снимаю трейс и перезапускаю…"
        sample "$APP_PID" 3 -file "$FREEZE_LOG" >/dev/null 2>&1 \
          && echo "  📄 трейс фриза сохранён: $FREEZE_LOG  (пришли этот файл)"
        kill -9 "$APP_PID" 2>/dev/null
        hung=1
        break
      fi
    fi
  done
  wait "$APP_PID"; code=$?
  if [ "$hung" -eq 0 ] && [ "$code" -eq 0 ]; then
    echo "✓ Остановлено («Выход»)."
    break
  fi
  echo "↻ Перезапуск (код $code)…"
  sleep 1
done
