#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.bun/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"
[[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]] && source "${NVM_DIR:-$HOME/.nvm}/nvm.sh"

command -v bunx >/dev/null 2>&1 || {
  echo "tokscale-sync-and-submit: bunx not found" >&2
  exit 1
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT/scripts/import-claude-sessions-for-tokscale.sh"

bunx tokscale cursor sync
bunx tokscale submit

# Optional immediate refresh; the hourly workflow is the fallback if gh is absent
# or this machine is not authenticated with Actions write permission.
if command -v gh >/dev/null 2>&1; then
  gh workflow run tokscale-embed-refresh.yml --repo ardjo-s/ardjo-s --ref main ||
    echo "Tokscale submitted; image refresh will use the hourly schedule." >&2
fi
