# Tokscale profile embed

## What updates automatically?

| Piece | What it does | Needs your Mac? |
|-------|----------------|-----------------|
| **Tokscale embed URL** | Serves fresh SVG after `submit` | Data comes from your machine |
| **launchd (recommended)** | Runs the shell script every 12 hours | Yes (Mac awake) |
| **Codex+ cron (optional)** | Agent runs the same script | Yes + Codex app / local runner |
| **GitHub Action** | Saves validated light/dark SVGs hourly; keeps the last good images on failure | No (runs on GitHub) |

Tokscale does **not** pull Cursor usage from the cloud by itself. You still need `cursor sync` + `submit` on a machine where you use Cursor/Codex/Droid.

**Claude:** models used in **Cursor** or **Droid** already appear under those clients. **Claude app / Code** sessions live under `~/Library/Application Support/Claude/…` — run `import-claude-sessions-for-tokscale.sh` (called automatically from `tokscale-sync-and-submit.sh`) to link them into `~/.claude/projects` for the `claude` client.

## launchd vs Codex+ automation

| | **launchd** | **Codex+ cron** |
|--|-------------|-----------------|
| Coût | Gratuit | Tokens Codex (même avec prompt minimal) |
| Fiabilité | Exécute le script directement | Dépend de l’agent qui suit le prompt |
| Où gérer | macOS LaunchAgents | Codex app → Automations |
| Bon pour | Sync toutes les 12 h (déterministe) | OK si tu veux tout voir dans Codex |

**Recommandation :** `launchd` pour le sync ; garde la **GitHub Action** pour les images. N’active pas launchd et Codex+ en parallèle (double `submit`).

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

- Light UI → `assets/tokscale/light.svg`
- Dark UI → `assets/tokscale/dark.svg`

GitHub profile must allow `<picture>` (supported on github.com).

## GitHub Action

`.github/workflows/tokscale-embed-refresh.yml` runs hourly at minute 23 (GitHub may delay scheduled runs), and supports manual dispatch. After a successful submit, the local sync script also requests a refresh when authenticated `gh` is available. Update the local checkout to get that hook; without it the hourly refresh still works.

The workflow downloads both cards with 90-second request timeouts and retries, validates the SVGs, and commits only changed images. A failed download or validation fails the Action visibly without publishing either card, preserving the last good images. The README no longer depends on GitHub's image proxy fetching Tokscale within its short timeout. Upstream caches and the frequency of your local submissions still determine data freshness.

Standard `ubuntu-latest` runners are free for this public repository, so this job does not require private-repository Actions minutes or Celesto credits. No extra token or service is required; publishing uses the built-in `GITHUB_TOKEN`.

Manual refresh: `gh workflow run tokscale-embed-refresh.yml --repo ardjo-s/ardjo-s --ref main`.
Local verification: `python3 -m unittest discover -s scripts -p 'test_tokscale_embed.py'`.

**Embed vs `submit`:** the card shows stats for Tokscale’s rolling window (e.g. `06/06 → 05/26`, **103 active days** in that window). `tokscale submit` prints **all-time** totals (e.g. **121 active days**). **Current streak 0** means no consecutive UTC days with usage after the last active day (here through **05/26**) — not a broken sync.
