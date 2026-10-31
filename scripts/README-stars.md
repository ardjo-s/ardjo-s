# Curated star categories

`docs/stars/catalog.json` is the source of truth for the Sol classification approved on 2026-10-31: 1,315 public repositories, 26 categories and one primary destination per repository. It preserves 245 review flags for uncertain evidence or boundaries; these repositories are already classified.

The profile keeps its existing headings, icons, spacing and light/dark ShieldCN badges. `Summary` opens a category overview; `Open` jumps to its repository list. These links refer to the curated pages in this repository. The native GitHub Star Lists are separate and have not been migrated by this change.

## Refresh

The existing scheduled workflow reads the owner's public stars, refreshes their metadata and renders the category pages and the marked `Starred Repos` section. It never derives categories from the older native GitHub lists. The introduction, social links and Tokscale block stay outside the generated markers.

```sh
python3 scripts/sync-github-stars.py --output-dir docs/stars
```

This needs the existing `GH_STARS_TOKEN` workflow secret, exposed as `GH_TOKEN`, belonging to the catalog owner. Local callers can use an already configured `GH_TOKEN` or `GITHUB_TOKEN`. Private stars are excluded before classification and publication. No GitHub lists are mutated.

Repositories are matched by stable GitHub node ID, so a rename or ownership transfer keeps its category. Removed stars disappear from the generated pages, while their reviewed assignments remain in the snapshot for a future re-star. An unknown public repository fails the refresh before any file is written, preserving the last good pages until it is classified. Empty inventories also fail safely.

To render the reviewed snapshot without network access:

```sh
python3 scripts/sync-github-stars.py --output-dir docs/stars --offline
```

The offline snapshot can differ from live metadata or star membership after its recorded date.

## Classify a new repository

1. Read its public README and determine its primary useful outcome using the category definitions.
2. Add one entry to `catalog.json` with the repository's stable node ID, canonical name and URL, category ID, public description, usage summary, search keywords and an exact evidence quote.
3. Preserve uncertainty with `review_required` and `evidence_status`; do not pretend weak evidence has become certain.
4. Refresh the export and run `python3 -m unittest discover -s scripts -p 'test_*.py'`.

The catalog's French usage summaries and French/English keywords support requests in either language. Human-facing category names and short descriptions retain the profile's English presentation.
