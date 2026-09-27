#!/usr/bin/env bash
# cron / launchd から呼ばれるラッパー。PATH を補い、ログを残す。
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p "$DIR/logs"
LOG="$DIR/logs/$(date +%Y-%m-%d).log"
{
  echo "=== $(date '+%F %T') start ==="
  python3 "$DIR/morning_news.py" "$@"
  echo "=== $(date '+%F %T') done ==="
} >>"$LOG" 2>&1
# 30日より古いログを削除
find "$DIR/logs" -name '*.log' -mtime +30 -delete 2>/dev/null || true
