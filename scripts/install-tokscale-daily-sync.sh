#!/usr/bin/env bash
# Install a launchd job: tokscale cursor sync + submit every 12 hours (Mac must be awake).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_SRC="$ROOT/scripts/com.ardjo.tokscale-sync.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.ardjo.tokscale-sync.plist"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "install-tokscale-daily-sync: macOS only" >&2
  exit 1
fi

chmod +x "$ROOT/scripts/tokscale-sync-and-submit.sh"
cp "$PLIST_SRC" "$PLIST_DST"
launchctl bootout "gui/$(id -u)/com.ardjo.tokscale-sync" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl enable "gui/$(id -u)/com.ardjo.tokscale-sync"
echo "Installed: $PLIST_DST (every 12h, logs in /tmp/tokscale-sync.log)"
