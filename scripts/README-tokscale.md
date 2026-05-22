# Tokscale profile embed

## What updates automatically?

| Piece | What it does | Needs your Mac? |
|-------|----------------|-----------------|
| **Tokscale embed URL** | Serves fresh SVG after `submit` | Data comes from your machine |
| **launchd (daily)** | `cursor sync` + `submit` | Yes (~08:00, Mac awake) |
| **GitHub Action** | Bumps `&v=` daily so GitHub reloads the image | No (runs on GitHub) |

Tokscale does **not** pull Cursor usage from the cloud by itself. You still need `cursor sync` + `submit` on a machine where you use Cursor/Codex/Droid.

## One-time: daily sync on macOS

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
