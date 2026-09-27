#!/usr/bin/env bash
# 毎朝 6:00 に run.sh を実行するよう登録する（macOS: launchd / Linux: cron）
# 使い方: ./install.sh [HH] [MM]   例: ./install.sh 6 0
#         ./install.sh --uninstall
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
HOUR="${1:-6}"; MIN="${2:-0}"
LABEL="com.bobchan.morning-news"
CRON_TAG="# morning-news (bobchan)"
chmod +x "$DIR/run.sh" "$DIR/morning_news.py"

if [[ "$(uname)" == "Darwin" ]]; then
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  launchctl unload "$PLIST" 2>/dev/null || true
  if [[ "${1:-}" == "--uninstall" ]]; then rm -f "$PLIST"; echo "削除しました"; exit 0; fi
  mkdir -p "$HOME/Library/LaunchAgents"
  cat >"$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$DIR/run.sh</string></array>
  <key>StartCalendarInterval</key><dict>
    <key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MIN</integer>
  </dict>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.err</string>
</dict></plist>
PL
  mkdir -p "$DIR/logs"
  launchctl load "$PLIST"
  echo "launchd に登録しました: 毎日 $HOUR:$(printf %02d "$MIN")（スリープ中だった場合は復帰時に実行）"
else
  CURRENT="$(crontab -l 2>/dev/null | grep -v -F "$CRON_TAG" || true)"
  if [[ "${1:-}" == "--uninstall" ]]; then
    printf '%s\n' "$CURRENT" | crontab -; echo "削除しました"; exit 0
  fi
  printf '%s\n%s\n' "$CURRENT" "$MIN $HOUR * * * $DIR/run.sh $CRON_TAG" | sed '/^$/d' | crontab -
  echo "cron に登録しました: 毎日 $HOUR:$(printf %02d "$MIN")"
  crontab -l | grep -F "$CRON_TAG"
fi
