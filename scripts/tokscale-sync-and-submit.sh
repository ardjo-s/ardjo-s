#!/usr/bin/env bash
# Refresh Tokscale data (Cursor API + local sessions) and push to tokscale.ai for the profile embed.
set -euo pipefail

if ! command -v bunx >/dev/null 2>&1; then
  echo "tokscale-sync-and-submit: bunx not found" >&2
  exit 1
fi

echo "Syncing Cursor usage into Tokscale cache..."
bunx tokscale cursor sync

echo "Submitting usage to Tokscale (updates embed + profile)..."
bunx tokscale submit

echo "Done. Embed: https://tokscale.ai/api/embed/ardjo-s/svg?view=3d&theme=dark"
