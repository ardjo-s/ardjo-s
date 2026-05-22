# Tokscale profile embed — stay up to date

The README image is loaded from `tokscale.ai`. GitHub caches images aggressively.

## 1. Push fresh stats to Tokscale (on your Mac)

```bash
chmod +x scripts/tokscale-sync-and-submit.sh
./scripts/tokscale-sync-and-submit.sh
```

Requires `bunx tokscale` and Cursor login (`bunx tokscale cursor status`).

Optional for non-interactive submit: `export TOKSCALE_API_TOKEN=tt_xxx` (Settings → API Tokens on tokscale.ai).

## 2. Optional: run every 6 hours (macOS)

```bash
(crontab -l 2>/dev/null; echo "0 */6 * * * $HOME/CODE/ardjo-s/scripts/tokscale-sync-and-submit.sh >> /tmp/tokscale-sync.log 2>&1") | crontab -
```

Adjust the path if the repo lives elsewhere.

## 3. GitHub Action (this repo)

Workflow `.github/workflows/tokscale-embed-refresh.yml` updates `&v=` in the embed URL twice per day so GitHub reloads the SVG after you have submitted locally.

Enable Actions on `ardjo-s/ardjo-s` if the workflow does not run.

## Full-width image

The embed uses `width="100%"` so the SVG scales to the profile README column width (Tokscale SVG is 680px wide; it stretches on GitHub).
