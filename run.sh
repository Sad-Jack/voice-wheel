#!/usr/bin/env bash
# Quick launch for Voice Wheel. Run:  ./run.sh
#
# Supervises exactly one app instance and guarantees nothing it spawned is left
# running. The app is launched in its OWN process group (set -m), so on stop /
# restart / freeze we kill the whole group — the app together with every child it
# forked (a warm `claude`, transient CLI calls, …) — however the app dies, even
# on SIGKILL. We also own the Ollama process we start (and stop it on exit).
set -e
set -m   # monitor mode: each background job gets its own process group
cd "$(dirname "$0")"   # project dir, regardless of where it's called from

SUPPORT="$HOME/Library/Application Support/VoiceWheel"
HEARTBEAT="$SUPPORT/heartbeat"          # liveness file the app touches every second
FREEZE_DIR="$SUPPORT"                   # where freeze traces go (#49)
PGID_FILE="$SUPPORT/app.pgid"           # last app process-group id, for a stale sweep
STALE_AFTER=15   # seconds with no heartbeat = main thread hung -> kill + restart
GRACE=12         # ignore the heartbeat for the first N seconds (boot / warm-up)
mkdir -p "$SUPPORT" 2>/dev/null || true

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

MY_PGID="$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')"   # our own group — never kill it

# Kill the whole process group: TERM first (lets the app unload the ollama model
# and reap its own children), wait briefly, then KILL whatever is still standing.
group_kill() {   # $1 = process-group id
  [ -z "$1" ] && return 0
  if [ "$1" = "$MY_PGID" ]; then   # safety: app somehow shares our group -> don't suicide
    kill -TERM "$APP_PID" 2>/dev/null || true
    return 0
  fi
  kill -TERM -"$1" 2>/dev/null || true
  for _ in 1 2 3 4 5 6; do
    kill -0 -"$1" 2>/dev/null || return 0   # group empty -> done
    sleep 0.5
  done
  kill -KILL -"$1" 2>/dev/null || true
}

# --- kill stragglers from a previous run (e.g. if run.sh itself was force-killed,
#     its cleanup never ran and left the app + children orphaned) ---
if [ -f "$PGID_FILE" ]; then
  OLD_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
  [ -n "$OLD_PGID" ] && [ "$OLD_PGID" != "$MY_PGID" ] && kill -KILL -"$OLD_PGID" 2>/dev/null || true
  rm -f "$PGID_FILE"
fi
pkill -f "voice_wheel" 2>/dev/null || true
sleep 0.5
# SIGTERM is unreliable on a Cocoa app; force-kill any survivor so it releases the
# single-instance lock (flock) before we relaunch — otherwise the fresh start would
# see the lock held and exit.
pkill -9 -f "voice_wheel" 2>/dev/null || true

# --- ensure the local LLM (Ollama) is running, if that's the backend. Track
#     whether WE start it: if so, we stop it on exit (we own its lifecycle). An
#     already-running serve (brew/launchd) is left alone — not ours to stop. ---
OLLAMA_PID=""
if grep -q '"backend"[[:space:]]*:[[:space:]]*"ollama"' config.json 2>/dev/null; then
  if ! curl -s --max-time 1 http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "▸ Запускаю Ollama…"
    if brew services start ollama >/dev/null 2>&1; then
      :   # brew/launchd manages it — leave it running on exit
    else
      nohup ollama serve >/dev/null 2>&1 &
      OLLAMA_PID=$!   # ours -> stop it on exit
    fi
    sleep 1
  fi
fi

APP_PID=""
APP_PGID=""
cleanup() {
  group_kill "$APP_PGID"
  # If WE started ollama, stop it too (its model runner dies with it). An external
  # serve we leave running — the app already unloaded the model on its SIGTERM.
  if [ -n "$OLLAMA_PID" ]; then
    kill "$OLLAMA_PID" 2>/dev/null || true
    sleep 0.3
    kill -9 "$OLLAMA_PID" 2>/dev/null || true
  fi
  rm -f "$PGID_FILE"
  exit 0
}
trap cleanup INT TERM

echo "▶ Voice Wheel запускается…  (Ctrl+C или «Выход» в меню-баре — остановить)"

set +e   # the loop handles non-zero exits itself
while true; do
  rm -f "$HEARTBEAT"
  env PYTHONPATH=src "$PY" -u -m voice_wheel &
  APP_PID=$!
  APP_PGID="$(ps -o pgid= -p "$APP_PID" 2>/dev/null | tr -d ' ')"
  [ -z "$APP_PGID" ] && APP_PGID="$APP_PID"
  echo "$APP_PGID" > "$PGID_FILE"
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
        group_kill "$APP_PGID"
        hung=1
        break
      fi
    fi
  done
  wait "$APP_PID" 2>/dev/null; code=$?
  group_kill "$APP_PGID"   # reap any children a crashed/exited app left behind
  if [ "$hung" -eq 0 ] && [ "$code" -eq 0 ]; then
    echo "✓ Остановлено («Выход»)."
    cleanup
  fi
  echo "↻ Перезапуск (код $code)…"
  sleep 1
done
