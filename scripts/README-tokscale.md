# Tokscale profile embed

## What updates automatically?

| Piece | What it does | Needs your Mac? |
|-------|----------------|-----------------|
| **Tokscale embed URL** | Serves fresh SVG after `submit` | Data comes from your machine |
| **launchd (recommended)** | Runs the shell script every 12 hours | Yes (Mac awake) |
| **Codex+ cron (optional)** | Agent runs the same script | Yes + Codex app / local runner |
| **GitHub Action** | Bumps `&v=YYYYMMDDHH` every 12h so GitHub reloads the image | No (runs on GitHub) |

Tokscale does **not** pull Cursor usage from the cloud by itself. You still need `cursor sync` + `submit` on a machine where you use Cursor/Codex/Droid.

**Claude:** models used in **Cursor** or **Droid** already appear under those clients. **Claude app / Code** sessions live under `~/Library/Application Support/Claude/…` — run `import-claude-sessions-for-tokscale.sh` (called automatically from `tokscale-sync-and-submit.sh`) to link them into `~/.claude/projects` for the `claude` client.

## launchd vs Codex+ automation

| | **launchd** | **Codex+ cron** |
|--|-------------|-----------------|
| Coût | Gratuit | Tokens Codex (même avec prompt minimal) |
| Fiabilité | Exécute le script directement | Dépend de l’agent qui suit le prompt |
| Où gérer | macOS LaunchAgents | Codex app → Automations |
| Bon pour | Sync toutes les 12 h (déterministe) | OK si tu veux tout voir dans Codex |

**Recommandation :** `launchd` pour le sync ; garde la **GitHub Action** pour le cache image. N’active pas les deux en parallèle (double `submit`).

Codex automation (paused by default): `~/.codex/automations/daily-tokscale-profile-sync/` — set `status = "ACTIVE"` in `automation.toml` only if you drop launchd.

## One-time: 12-hour sync on macOS (recommended)

```bash
chmod +x scripts/install-tokscale-daily-sync.sh
./scripts/install-tokscale-daily-sync.sh
```

Manual run:

```bash
./scripts/tokscale-sync-and-submit.sh
```

After install, reload the job:

```bash
launchctl bootout "gui/$(id -u)/com.ardjo.tokscale-sync" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.ardjo.tokscale-sync.plist
```

Optional API token (headless submit): `export TOKSCALE_API_TOKEN=tt_xxx` from [tokscale.ai](https://tokscale.ai) Settings → API Tokens.

## Light / dark embed

The README uses `<picture>` + `prefers-color-scheme`:

- Light UI → `theme=light`
- Dark UI → `theme=dark`

GitHub profile must allow `<picture>` (supported on github.com).

## GitHub Action

`.github/workflows/tokscale-embed-refresh.yml` runs at 07:00 and 19:00 UTC and updates all `&v=YYYYMMDDHH` in the embed URLs.

**Embed vs `submit`:** the card shows stats for Tokscale’s rolling window (e.g. `06/06 → 05/26`, **103 active days** in that window). `tokscale submit` prints **all-time** totals (e.g. **121 active days**). **Current streak 0** means no consecutive UTC days with usage after the last active day (here through **05/26**) — not a broken sync.
