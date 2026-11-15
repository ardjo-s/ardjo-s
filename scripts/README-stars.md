# Curated star categories

`docs/stars/catalog.json` is the source of truth. The 2026-10-31 Sol review classified 1,315 public repositories into 26 categories (245 review flags). Later public stars were appended in dated batches inside the same file; they keep their own `evidence_read_at` and `classification_source`. Counts live in the catalog and in generated pages — do not copy them into this note.

The profile keeps its existing headings, icons, spacing and light/dark ShieldCN badges. `Summary` opens a category overview; `Open` jumps to its repository list. Native GitHub Star Lists are separate and have not been migrated.

Agent entry points: [AGENTS.md](../AGENTS.md), [llms.txt](../llms.txt), [catalog schema](../docs/stars/schema.md), generated [stars.json](../docs/stars/stars.json).

## Refresh

The scheduled workflow reads the owner's public stars, refreshes their metadata and renders the category pages, `stars.json`, and the marked `Starred Repos` section. It never derives categories from the older native GitHub lists. The introduction, social links and Tokscale block stay outside the generated markers.

```sh
python3 scripts/sync-github-stars.py --output-dir docs/stars
```

This needs the existing `GH_STARS_TOKEN` workflow secret, exposed as `GH_TOKEN`, belonging to the catalog owner. Local callers can use an already configured `GH_TOKEN` or `GITHUB_TOKEN`. Private stars are excluded before classification and publication. No GitHub lists are mutated.

Repositories are matched by stable GitHub node ID, so a rename or ownership transfer keeps its category. Removed stars disappear from the generated pages, while their reviewed assignments remain in the snapshot for a future re-star. Unknown public repositories are exported to **Unsorted / to classify** with a stderr warning; they no longer block the rest of the refresh. Empty inventories still fail safely. A starred-list page shift that repeats a repo id is skipped (and the list is fetched once more) instead of failing the job. `python3 scripts/sync-github-stars.py --output-dir docs/stars --check` fails the job if any repository is missing, duplicated, or counted twice.

The scheduled cron is every 10 minutes (`*/10 * * * *`) so a new star can reach the published list in about 15 minutes when GitHub honours the schedule. Hosted-runner schedules on this repository have historically been delayed to every four to eight hours, including the previous hourly cron and an earlier `*/15` attempt. The job does not commit when the export is unchanged, and overlapping syncs on `main` are serialized. After classify, every public star has exactly one existing category; `docs/stars/unsorted.md` is kept even when it has no rows.

To render the reviewed snapshot without network access:

```sh
python3 scripts/sync-github-stars.py --output-dir docs/stars --offline
```

The offline snapshot can differ from live metadata or star membership after its recorded date.

## Classify a new repository

Live unsorted stars are classified automatically by `scripts/classify-github-stars.py` (nearest classified neighbours plus the catalog domain rules). Domain-rule reasons require a name/description/topics match; README noise does not count. `awesome-*` lists follow their subject. Human corrections (`classification_source` starting `human:`) weigh more than bot rows and are never overwritten by an automatic pick. A confident name-and-description pick is published immediately. Otherwise up to three enrichment rounds run and stop as soon as a gate accepts a pick: README excerpt (~3 000 characters), topics, language and homepage, then human examples plus category definitions with three Jev votes. Jev is used only for new or explicitly reclassified below-threshold rows, when the `TYPESAFE_API_KEY` repository secret is set. It auto-accepts only on agreement with the classifier top-1 or a high-confidence override; otherwise it duels the top two finalists. Round 3 accepts only when three votes agree and meet the duel threshold. If every round fails, the best available existing category is still published (Jev duel winner if Jev answered, otherwise the classifier top-1) and tagged `classification_confidence: low` with `classification_rounds` so it can be found and corrected later. The rolling PR body lists those low-confidence rows and the rounds used. Identical Jev requests are cached in gitignored `docs/stars/.classify-jev-cache.json`. The workflow `.github/workflows/classify-github-stars.yml` runs after a successful sync on `main` when `docs/stars/unsorted.md` has repository rows, updates `catalog.json`, regenerates the export, runs `--check`, and opens or updates one rolling PR on `auto/classify-stars`. It then squash-merges that PR after checking the head branch, the diff paths (`README.md` and `docs/stars/**`), that every catalogued star uses an existing category, and that tests plus `--check` pass on that exact head SHA (`gh pr merge --squash --match-head-commit`). It does nothing when `unsorted.md` has no repository rows. It does not enable GitHub's auto-merge setting. The owner must add `TYPESAFE_API_KEY` for the Jev gate to be active.

To classify by hand instead:

1. Read its public README and determine its primary useful outcome using the category definitions in `catalog.json`.
2. Add one entry to `catalog.json` with the repository's stable node ID, canonical name and URL, category ID, public description, usage summary, search keywords and an exact evidence quote.
3. Preserve uncertainty with `review_required` and `evidence_status`; do not pretend weak evidence has become certain.
4. Refresh the export and run `python3 -m unittest discover -s scripts -p 'test_*.py'`.

Do not add a category. Domain-specific skills follow their domain. Generic agent skills packs not tied to a specific domain go to Agent Methods, Skills & Configuration. Low-confidence automatic picks are still published in an existing category and tagged `classification_confidence: low`. A later human correction in `catalog.json` sticks.

The catalog's French usage summaries and French/English keywords support requests in either language. Human-facing category names and short descriptions retain the profile's English presentation.

Do not edit generated Markdown or `stars.json` by hand.
