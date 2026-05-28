#!/usr/bin/env bash
# Link Claude app / Code sessions into ~/.claude/projects for Tokscale.
set -euo pipefail

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
PROJECTS="$CLAUDE_HOME/projects"
APP_SUPPORT="$HOME/Library/Application Support/Claude"

mkdir -p "$PROJECTS"

linked=0
while IFS= read -r -d '' file; do
  session_dir=$(basename "$(dirname "$file")")
  session_id=$(basename "$file" .jsonl)
  dest_dir="$PROJECTS/claude-app-${session_dir}"
  mkdir -p "$dest_dir"
  ln -sf "$file" "$dest_dir/${session_id}.jsonl"
  linked=$((linked + 1))
done < <(find "$APP_SUPPORT" -path '*/.claude/projects/*/*.jsonl' -print0 2>/dev/null)

echo "import-claude-sessions: linked $linked session file(s) under $PROJECTS"
