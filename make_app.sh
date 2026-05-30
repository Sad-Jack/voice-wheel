#!/usr/bin/env bash
# Build a double-clickable "Voice Wheel.app" (menu-bar agent) that wraps run.sh.
# Lightweight: the bundle references this project + its venv (not a distributable
# bundle yet — that's the full installer). Gives Finder double-click launch and a
# stable bundle id so macOS permissions persist across code changes.
set -e
cd "$(dirname "$0")"
PROJECT="$(pwd)"
APP="$PROJECT/Voice Wheel.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Voice Wheel</string>
  <key>CFBundleDisplayName</key><string>Voice Wheel</string>
  <key>CFBundleIdentifier</key><string>com.voicewheel.app</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleExecutable</key><string>voice-wheel</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Voice Wheel records your voice to transcribe it.</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/voice-wheel" <<LAUNCH
#!/bin/bash
# Launched by Finder/LaunchServices with a minimal env — set a full PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$HOME/.local/bin:\$PATH"
mkdir -p "\$HOME/Library/Logs"
cd "$PROJECT"
exec "$PROJECT/run.sh" >> "\$HOME/Library/Logs/VoiceWheel.log" 2>&1
LAUNCH
chmod +x "$APP/Contents/MacOS/voice-wheel"

# Refresh LaunchServices so the icon/bundle is recognized immediately.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
  -f "$APP" >/dev/null 2>&1 || true

echo "✓ Собрано: $APP"
echo "  Двойной клик в Finder — запуск. Логи: ~/Library/Logs/VoiceWheel.log"
