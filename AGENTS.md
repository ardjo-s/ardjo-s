# AGENTS.md

GitHub profile README for [ardjo-s](https://github.com/ardjo-s). This repository is the public homepage: social links, a Tokscale usage embed, and a curated catalog of public starred repositories.

## Layout

| Path | Role |
|------|------|
| `README.md` | Profile. Hand-edit only outside generated markers. |
| `docs/stars/catalog.json` | Source of truth for star classification. |
| `docs/stars/schema.md` | Catalog field reference. |
| `docs/stars/stars.json` | Generated machine-readable snapshot. |
| `docs/stars/*.md` | Generated category pages (except `schema.md`). |
| `scripts/sync-github-stars.py` | Live or offline star export. |
| `scripts/classify-github-stars.py` | Assign unsorted live stars to existing catalog categories. |
| `scripts/README-stars.md` | Human maintainer notes for stars. |
| `assets/tokscale/` | Generated Tokscale SVGs. Do not hand-edit. |
| `scripts/refresh-tokscale-embed.py` | Downloads and validates those SVGs. |
| `scripts/README-tokscale.md` | Tokscale maintainer notes. |
| `llms.txt` | Index of files agents should read first. |

## Stars sync

`docs/stars/catalog.json` assigns every public star exactly one category, matched by GitHub node ID (renames keep their category). The scheduled workflow in `.github/workflows/sync-github-stars.yml` fetches the owner's public stars with `GH_STARS_TOKEN` (exposed as `GH_TOKEN`) and regenerates the README stars section plus `docs/stars/*.md` and `docs/stars/stars.json`.

Unknown live stars no longer fail the job. They are written to **Unsorted / to classify** and warned on stderr. A follow-up workflow classifies them into an existing category and opens one rolling PR; Ardjo merges it. Empty live inventories still fail so the last good export is kept. Private stars are dropped before export. Duplicate items from a starred-list page shift are skipped (with one re-fetch) instead of failing the job.

```sh
# Offline: render the catalog snapshot (no network)
python3 scripts/sync-github-stars.py --output-dir docs/stars --offline

# Live: requires GH_TOKEN or GITHUB_TOKEN belonging to ardjo-s
python3 scripts/sync-github-stars.py --output-dir docs/stars

# Fail on orphans, duplicates, count mismatches or stale generated files
python3 scripts/sync-github-stars.py --output-dir docs/stars --check

# Assign unsorted stars to existing categories (never creates a category)
python3 scripts/classify-github-stars.py --output-dir docs/stars --offline --features-json scripts/testdata/pr14_classify_fixtures.json

python3 -m unittest discover -s scripts -p 'test_*.py'
```

Never edit the README between `<!-- starred-repos-start -->` and `<!-- starred-repos-end -->`, nor any `docs/stars` file that contains `<!-- generated: sol-star-catalog -->`. Change `catalog.json` (and tests if counts change), then run the script.

## Unsorted classification loop

`.github/workflows/classify-github-stars.yml` runs after a successful stars sync on `main` (and when `docs/stars/unsorted.md` is pushed). It no-ops when unsorted is empty. Otherwise `scripts/classify-github-stars.py` scores each unsorted repo from its description, topics, language and README excerpt against already-classified catalog rows plus the documented domain rules (skills follow their domain; host/cloud is not the purpose). Low-confidence picks stay classified and set `review_required` with the top two category ids.

The job regenerates the export, runs `--check`, and opens or updates **one** rolling PR on `auto/classify-stars`. It never creates a second PR, never enables auto-merge, and never merges. Classify by hand in `catalog.json` if you disagree with a proposal.

If the job authenticates with `GITHUB_TOKEN`, GitHub only opens that PR when **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests** is enabled (leave workflow permissions at read/write for contents and pull requests). `GH_STARS_TOKEN` can open the PR without that checkbox if it has contents and pull-request write. Do not change Tokscale secrets or branch protection for this loop.

## Tokscale

Do not edit `assets/tokscale/light.svg` or `assets/tokscale/dark.svg`. Do not change Tokscale workflow secrets, the embed markers in `README.md`, or branch protection. Local submit and hourly image refresh are documented in `scripts/README-tokscale.md`.

```sh
python3 -m unittest discover -s scripts -p 'test_tokscale_embed.py'
```

## Rules

- Never print, commit, or rotate repository secrets (`GH_STARS_TOKEN`, Tokscale tokens).
- Never merge pull requests unless a human explicitly asks.
- Keep one primary category per repository. Domain-specific skills follow their domain (video → Image/Video, Unreal → Games & 3D, security audits → Security).
- Preserve original Sol records (`classification_source` absent). New records carry their own evidence date and source run.
- Do not deploy.
