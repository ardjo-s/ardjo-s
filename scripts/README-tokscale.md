# Tokscale profile embed

## What updates automatically?

| Piece | What it does | Needs your Mac? |
|-------|----------------|-----------------|
| **Tokscale embed URL** | Serves fresh SVG after `submit` | Data comes from your machine |
| **launchd (recommended)** | Runs the shell script at ~08:00 | Yes (Mac awake) |
| **Codex+ cron (optional)** | Agent runs the same script | Yes + Codex app / local runner |
| **GitHub Action** | Bumps `&v=` daily so GitHub reloads the image | No (runs on GitHub) |

Tokscale does **not** pull Cursor usage from the cloud by itself. You still need `cursor sync` + `submit` on a machine where you use Cursor/Codex/Droid.

## launchd vs Codex+ automation

| | **launchd** | **Codex+ cron** |
|--|-------------|-----------------|
| Coût | Gratuit | Tokens Codex (même avec prompt minimal) |
| Fiabilité | Exécute le script directement | Dépend de l’agent qui suit le prompt |
| Où gérer | macOS LaunchAgents | Codex app → Automations |
| Bon pour | Sync quotidien déterministe | OK si tu veux tout voir dans Codex |

**Recommandation :** `launchd` pour le sync ; garde la **GitHub Action** pour le cache image. N’active pas les deux en parallèle (double `submit`).

Codex automation (paused by default): `~/.codex/automations/daily-tokscale-profile-sync/` — set `status = "ACTIVE"` in `automation.toml` only if you drop launchd.

## One-time: daily sync on macOS (recommended)

```bash
chmod +x scripts/install-tokscale-daily-sync.sh
./scripts/install-tokscale-daily-sync.sh
```

Manual run:

```bash
./scripts/tokscale-sync-and-submit.sh
```

Optional API token (headless submit): `export TOKSCALE_API_TOKEN=tt_xxx` from [tokscale.ai](https://tokscale.ai) Settings → API Tokens.

## Light / dark embed

The README uses `<picture>` + `prefers-color-scheme`:

- Light UI → `theme=light`
- Dark UI → `theme=dark`

GitHub profile must allow `<picture>` (supported on github.com).

## GitHub Action

`.github/workflows/tokscale-embed-refresh.yml` runs daily at 07:00 UTC and updates all `&v=YYYYMMDD` in the embed URLs.
