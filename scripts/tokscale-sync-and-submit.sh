#!/usr/bin/env bash
# Refresh Tokscale data (Cursor API + local sessions) and push to tokscale.ai for the profile embed.
set -euo pipefail

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# launchd has a minimal PATH — load nvm/npm if present
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"
if [[ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]]; then
  # shellcheck source=/dev/null
  source "${NVM_DIR:-$HOME/.nvm}/nvm.sh"
fi
if [[ -s "$HOME/.zprofile" ]]; then
  # shellcheck source=/dev/null
  source "$HOME/.zprofile"
fi

if ! command -v bunx >/dev/null 2>&1; then
  log "ERROR: bunx not found (check nvm/node install)"
  exit 1
fi

log "Syncing Cursor usage into Tokscale cache..."
bunx tokscale cursor sync

log "Submitting usage to Tokscale (updates embed + profile)..."
bunx tokscale submit

log "OK — embed dark: https://tokscale.ai/api/embed/ardjo-s/svg?view=3d&theme=dark"
