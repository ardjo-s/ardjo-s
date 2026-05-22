---
title: Tokscale profile README automation
date: 2026-05-22
status: completed
type: feat
---

# Tokscale profile README automation

## Problem

Profile README should show a full-width Tokscale 3D embed that stays current (daily) with light/dark variants. Bio text stays in GitHub Settings only. Sync must be reliable on macOS without burning Codex tokens.

## Scope

**In:**
- `README.md`: `<picture>` light/dark, image-only
- `scripts/tokscale-sync-and-submit.sh` with correct PATH for launchd
- `scripts/install-tokscale-daily-sync.sh` + `com.ardjo.tokscale-sync.plist`
- `.github/workflows/tokscale-embed-refresh.yml` daily cache bust for all embed URLs
- `scripts/README-tokscale.md` documenting launchd (recommended) vs Codex cron (optional, paused)
- Codex automation at `~/.codex/automations/daily-tokscale-profile-sync/` remains **PAUSED**

**Out:**
- Tokscale server-side cron (not available)
- GitHub Action running `tokscale submit` (no local Cursor credentials on runner)
- Bio text in README

## Decisions

| Decision | Rationale |
|----------|-----------|
| launchd over Codex cron for sync | Deterministic shell, zero tokens |
| GHA for `&v=` bump only | Refreshes GitHub image cache after local submit |
| `<picture>` + `prefers-color-scheme` | Native light/dark without JS |

## Implementation units

### IU-1: Harden local daily sync script

**Files:** `scripts/tokscale-sync-and-submit.sh`, `scripts/com.ardjo.tokscale-sync.plist`

- Source nvm or set PATH so `bunx` works under launchd
- Log success/failure with timestamp

**Test scenarios:**
- Manual run exits 0 when `bunx tokscale cursor status` is valid
- launchd EnvironmentVariables includes node/bunx path

### IU-2: README embed + workflow cache bust

**Files:** `README.md`, `.github/workflows/tokscale-embed-refresh.yml`

- Picture block with `theme=light` and `theme=dark` srcset
- Workflow replaces all `v=YYYYMMDD` on tokscale embed URLs

**Test scenarios:**
- `grep picture README.md` shows two sources
- Dry-run perl regex matches current README

### IU-3: Documentation

**Files:** `scripts/README-tokscale.md`

- launchd install vs Codex automation (do not run both)
- Link to Tokscale API token for headless submit

## Verification

```bash
./scripts/tokscale-sync-and-submit.sh
grep -E 'picture|prefers-color-scheme' README.md
```

## Deferred

- Auto-install launchd on user machine without explicit request
- PR for `~/.codex/automations` (outside ardjo-s repo)
