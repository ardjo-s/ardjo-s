# Star catalog schema

`catalog.json` is the only source of truth for classification. Generated Markdown and `stars.json` are derived from it plus (on a live run) public GitHub star membership and metadata.

Schema version: `1`.

## Root

| Field | Type | Meaning |
|-------|------|---------|
| `schema_version` | number | Must be `1`. |
| `account` | string | GitHub login whose public stars are catalogued (`ardjo-s`). |
| `classification` | string | Label of the baseline Sol review (`Sol final`). |
| `snapshot` | string | Date of that baseline (`2026-10-31`). Later additions keep their own `evidence_read_at`. |
| `categories` | array | Category definitions in canonical family order. The profile README, index, category pages and `stars.json` must use this same order. |
| `repositories` | array | One object per classified public repository. Sorted by `name` case-insensitively in the file. |

## Category

| Field | Type | Meaning |
|-------|------|---------|
| `id` | string | Stable id (`category_01` … `category_26`). `unsorted` is reserved for unclassified live stars and must not appear here. |
| `name` | string | English heading shown on the profile. |
| `slug` | string | File stem for `docs/stars/{slug}.md`. `[a-z0-9]+(-[a-z0-9]+)*`, not `readme`. |
| `emoji` | string | Heading prefix. |
| `family` | string | Group used by the index and README order. |
| `description` | string | One-line English blurb on the profile. |
| `definition` | string | French boundary rules for classifiers. |

## Repository

| Field | Type | Meaning |
|-------|------|---------|
| `id` | string | GitHub repository node id. Matching is by this id, so renames keep the category. |
| `name` | string | Canonical `owner/repo`. |
| `url` | string | Must be `https://github.com/{name}`. |
| `description` | string | Public GitHub description at classification time (live export overwrites for generated pages). |
| `category` | string | Exactly one `categories[].id`. |
| `purpose` | string | French usage summary. |
| `keywords` | string[] | French and/or English search terms, often including GitHub topics. |
| `review_required` | boolean | Evidence or boundary is uncertain; the repo is still classified. |
| `evidence_quote` | string | Exact excerpt that justified the category. |
| `evidence_status` | string | How the evidence was read (`read`, `readme_read_excerpt`, …). |
| `archived` | boolean | GitHub archived flag at classification time. |
| `fork` | boolean | GitHub fork flag at classification time. |

Optional on later additions:

| Field | Type | Meaning |
|-------|------|---------|
| `evidence_url` | string | Page that was read. |
| `evidence_read_at` | string | ISO date of that read. |
| `evidence_sha256` | string | Digest of retrieved README bytes when recorded. |
| `classification_source` | string | Workflow run, `jev:<date>` when TypeSafe System One accepted a low-confidence row, or other provenance. |
| `review_candidates` | string[] | Present on auto-classified low-confidence rows: the top two existing category ids (chosen first, runner-up second). |
| `review_resolution` | object | Recorded boundary decision (category, reviewer, approval). |

Original Sol rows omit `classification_source`. Do not rewrite those objects unless a human asks.

Auto-classified rows (from `scripts/classify-github-stars.py`) always have `classification_source`. They use an existing `categories[].id` only — the classifier never adds a category. Low-confidence rows may be accepted by a TypeSafe System One (Jev) second pass (`jev:<date>`): Jev chooses a category first, then a follow-up noul names that pick. Accept when Jev agrees with the classifier top-1 or wins a top-2 duel; Jev cannot add a category. Rows still doubtful after that are not written to `catalog.json` and stay on `unsorted.md` with the two candidate names (à trancher). `purpose` on published auto rows may be English (taken from the public description). `review_required` plus `review_candidates` on a human row means the boundary still needs checking; the repository is still classified.

Domain rules (mail, mobile/simulator, 3D skills, generic agent skills packs, inference gateways, and so on) attach a reason only when the rule's tokens match the repository name, description or topics. README body text does not fire those reasons. Domain-specific skills follow their domain; generic agent skills packs not tied to a specific domain go to Agent Methods, Skills & Configuration. Curated `awesome-*` lists follow the list's subject, not the generic software-directory bucket.

## Generated `stars.json`

Produced by `scripts/sync-github-stars.py`. Not a classification source.

```json
{
  "schema_version": 1,
  "account": "ardjo-s",
  "repository_count": 0,
  "categories": [{"id": "category_01", "name": "AI Coding Agents", "slug": "ai-coding-agents", "count": 0}],
  "repositories": [
    {
      "id": "R_kgDO...",
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "description": "…",
      "category": "AI Coding Agents",
      "category_id": "category_01",
      "archived": false,
      "fork": false
    }
  ]
}
```

Repositories are sorted by `name` case-insensitively. `id` is the GitHub node id used for matching. `categories` follows family order, including `unsorted` last when live stars are unclassified. Counts are generated; do not copy live totals into this example. Live membership can be smaller than the catalog when stars were removed.
