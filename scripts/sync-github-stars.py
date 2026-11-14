#!/usr/bin/env python3
"""Render public GitHub stars using the reviewed Sol taxonomy, never legacy lists."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

API = 'https://api.github.com'
START = '<!-- starred-repos-start -->'
END = '<!-- starred-repos-end -->'
GENERATED = '<!-- generated: sol-star-catalog -->'
UNSORTED_ID = 'unsorted'
UNSORTED_CATEGORY = {
    'id': UNSORTED_ID,
    'name': 'Unsorted / to classify',
    'slug': 'unsorted',
    'emoji': '❔',
    'family': 'Unsorted',
    'description': 'Public stars not yet classified in catalog.json.',
}
FAMILY_ORDER = (
    'AI & Agents',
    'Creative Tools & Interfaces',
    'Development, Infrastructure & Data',
    'Knowledge, Research & Business',
    'Hardware & Devices',
    'Unsorted',
)
STALE_MARKERS = (
    'additions-2026-11-05',
    'anthropics/anthropic-cookbook',
    'Agent note: generated from the authenticated GitHub stars list',
)
REPO_ROW = re.compile(r'^- \[([^\]]+)\]\((https://github\.com/[^)]+)\)(.*)$', re.M)


def request_json(url: str, token: str) -> dict | list:
    request = urllib.request.Request(url)
    request.add_header('Accept', 'application/vnd.github+json')
    request.add_header('Authorization', f'Bearer {token}')
    request.add_header('X-GitHub-Api-Version', '2022-11-28')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code in {502, 503, 504} and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f'GitHub API {error.code} for {url}') from error


def fetch_stars(token: str, account: str) -> list[dict]:
    if request_json(f'{API}/user', token)['login'].casefold() != account.casefold():
        raise ValueError('The token must belong to the catalog owner')
    stars = []
    page = 1
    while True:
        rows = request_json(f'{API}/user/starred?per_page=100&page={page}', token)
        if not rows:
            return stars
        for row in rows:
            repo = row.get('repo', row)
            if repo['private']:
                continue
            stars.append({
                'id': repo['node_id'], 'name': repo['full_name'], 'url': repo['html_url'],
                'description': repo.get('description') or '',
                'archived': bool(repo.get('archived')), 'fork': bool(repo.get('fork')),
            })
        page += 1


def category_sort_key(category: dict) -> tuple[int, int]:
    try:
        family_index = FAMILY_ORDER.index(category['family'])
    except ValueError as error:
        raise ValueError(f"Unknown category family: {category['family']}") from error
    if category['id'] == UNSORTED_ID:
        return (family_index, 10**9)
    suffix = category['id'].removeprefix('category_')
    if not suffix.isdigit():
        raise ValueError(f"Unexpected category id: {category['id']}")
    return (family_index, int(suffix))


def ordered_categories(catalog: dict, groups: dict[str, list[dict]] | None = None) -> list[dict]:
    categories = list(catalog['categories'])
    if groups is not None and groups.get(UNSORTED_ID):
        categories.append(UNSORTED_CATEGORY)
    return sorted(categories, key=category_sort_key)


def validate_catalog(catalog: dict) -> None:
    if catalog.get('schema_version') != 1:
        raise ValueError('Unsupported catalog version')
    categories = catalog['categories']
    ids = {c['id'] for c in categories}
    slugs = {c['slug'] for c in categories}
    if len(ids) != len(categories) or len(slugs) != len(categories):
        raise ValueError('Duplicate category ID or slug')
    if UNSORTED_ID in ids or UNSORTED_CATEGORY['slug'] in slugs:
        raise ValueError('unsorted is reserved for unclassified live stars')
    if any(not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or slug == 'readme' for slug in slugs):
        raise ValueError('Unsafe category slug')
    for category in categories:
        if category['family'] not in FAMILY_ORDER or category['family'] == 'Unsorted':
            raise ValueError(f"Unknown category family: {category['family']}")
        category_sort_key(category)
    expected_ids = [c['id'] for c in ordered_categories(catalog)]
    actual_ids = [c['id'] for c in categories]
    if actual_ids != expected_ids:
        raise ValueError('catalog categories must be in family order')
    seen_ids, seen_names = set(), set()
    for repo in catalog['repositories']:
        if repo['category'] not in ids:
            raise ValueError(f"Unknown category for {repo['name']}")
        name = repo['name'].casefold()
        if repo['id'] in seen_ids or name in seen_names:
            raise ValueError(f"Duplicate repository: {repo['name']}")
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo['name']) or repo['url'] != f"https://github.com/{repo['name']}":
            raise ValueError(f"Invalid repository URL: {repo['name']}")
        seen_ids.add(repo['id'])
        seen_names.add(name)


def group_stars(stars: list[dict], catalog: dict) -> dict[str, list[dict]]:
    validate_catalog(catalog)
    by_id = {r['id']: r for r in catalog['repositories']}
    groups = defaultdict(list)
    unknown, seen = [], set()
    for repo in stars:
        if repo.get('private'):
            continue
        if repo['id'] in seen:
            raise ValueError(f"Duplicate live repository: {repo['name']}")
        seen.add(repo['id'])
        classified = by_id.get(repo['id'])
        if classified is None:
            unknown.append({
                **repo,
                'category': UNSORTED_ID,
                'review_required': True,
            })
        else:
            groups[classified['category']].append({**classified, **repo})
    if not seen:
        raise ValueError('Empty public star inventory; retaining the last good export')
    if unknown:
        unknown.sort(key=lambda r: r['name'].casefold())
        groups[UNSORTED_ID] = unknown
        names = ', '.join(r['name'] for r in unknown)
        print(
            f'Unclassified public stars exported to Unsorted / to classify: {names}',
            file=sys.stderr,
        )
    return groups


def visible_categories(catalog: dict, groups: dict[str, list[dict]]) -> list[dict]:
    return ordered_categories(catalog, groups)


def mini_description(value: str) -> str:
    value = html.escape(value.replace('\n', ' ').strip(), quote=False)
    if not value:
        return 'Starred repository.'
    sentence = value.split('. ', 1)[0].rstrip('.')
    return f'{sentence}.'


def render_list(category: dict, repos: list[dict]) -> str:
    lines = [
        f"# {category['emoji']} {category['name']}", '', f"> {category['description']}", '',
        f'**{len(repos)} repositories.** [Browse all categories →](README.md)', '', GENERATED, '',
        'Classified by primary use with Sol. [Structured catalog and evidence](catalog.json).',
        'A review flag marks uncertain evidence or category boundaries; every repository still has a category.', '',
        '## Stars', '',
    ]
    for repo in sorted(repos, key=lambda r: r['name'].casefold()):
        flags = ''.join([
            ' · archived' if repo.get('archived') else '',
            ' · fork' if repo.get('fork') else '',
            ' · review needed' if repo['review_required'] else '',
        ])
        lines.append(f"- [{repo['name']}]({repo['url']}){flags}: {mini_description(repo['description'])}")
    return '\n'.join(lines).rstrip() + '\n'


def badge(href: str, label: str, alt: str, outline: bool = False) -> str:
    variant = 'outline' if outline else 'branded'
    base = f'https://www.shieldcn.dev/badge/{label}-24292F.svg?variant={variant}&amp;size=sm'
    dark = base + ('&amp;color=ffffff' if outline else '') + '&amp;labelTextColor=ffffff&amp;mode=dark'
    light = base + ('&amp;color=111827' if outline else '') + '&amp;labelTextColor=111827&amp;mode=light'
    return (f'<a href="{html.escape(href, quote=True)}"><picture><source media="(prefers-color-scheme: dark)" srcset="{dark}">'
            f'<img alt="{html.escape(alt, quote=True)}" src="{light}"></picture></a>')


def render_readme(catalog: dict, groups: dict[str, list[dict]]) -> str:
    account = catalog['account']
    categories = visible_categories(catalog, groups)
    total = sum(len(v) for v in groups.values())
    unsorted_n = len(groups.get(UNSORTED_ID, []))
    summary = f"{total:,} public repositories · {len(catalog['categories'])} categories"
    if unsorted_n:
        summary += f' · {unsorted_n} unsorted'
    summary += ' · [Browse the catalog](docs/stars/README.md)'
    lines = ['## ⭐ Starred Repos', '',
        f'<a href="https://github.com/{account}?tab=stars"><picture><source media="(prefers-color-scheme: dark)" srcset="https://www.shieldcn.dev/badge/All-stars-24292F.svg?variant=branded&amp;size=sm&amp;mode=dark"><img alt="Browse all stars" src="https://www.shieldcn.dev/badge/All-stars-24292F.svg?variant=branded&amp;size=sm&amp;mode=light"></picture></a>', '',
        summary, '']
    families = dict.fromkeys(c['family'] for c in categories)
    for family in families:
        for c in categories:
            if c['family'] != family:
                continue
            path = f"docs/stars/{c['slug']}.md"
            lines.extend([
                f"### {c['emoji']} {c['name']}", '', c['description'] + '<br>',
                '<div style="margin-top: 10px;">',
                badge(path, 'Summary', f"Read {c['name']} summary", True) + ' ' + badge(path + '#stars', 'Open', f"Browse {c['name']} repositories"),
                '</div>', '',
            ])
    return '\n'.join(lines).rstrip() + '\n'


def replace_readme_section(readme: str, section: str) -> str:
    if START in readme or END in readme:
        if readme.count(START) != 1 or readme.count(END) != 1 or readme.index(START) > readme.index(END):
            raise ValueError('Invalid starred-repos markers')
        before, rest = readme.split(START, 1)
        _, after = rest.split(END, 1)
        return before + START + '\n' + section + END + after
    before, rest = readme.split('## ⭐ Starred Repos\n', 1)
    next_heading = re.search(r'^## ', rest, flags=re.M)
    after = rest[next_heading.start():] if next_heading else ''
    return before + START + '\n' + section + END + '\n' + ('\n' + after if after else '')


def render_index(catalog: dict, groups: dict[str, list[dict]]) -> str:
    categories = visible_categories(catalog, groups)
    total = sum(len(v) for v in groups.values())
    unsorted_n = len(groups.get(UNSORTED_ID, []))
    heading = f"**{total:,} public repositories across {len(catalog['categories'])} Sol categories.**"
    if unsorted_n:
        heading = (
            f"**{total:,} public repositories across {len(catalog['categories'])} Sol categories"
            f" plus {unsorted_n} unsorted.**"
        )
    lines = ['# Starred repositories by primary use', '', GENERATED, '',
        heading, '',
        'Describe the outcome you need, choose a family below, then open its category. Each repository has one primary category.', '',
        'For agents: [catalog.json](catalog.json) is the source of truth. [stars.json](stars.json) is the generated machine-readable snapshot (name, url, description, category). [schema.md](schema.md) documents the catalog fields. Search `purpose`, `description` and `keywords`, then verify against `evidence_quote`.', '',
        'A review flag means the evidence or category boundary needs checking, not that the repository is unclassified. Live stars missing from the catalog are exported to Unsorted / to classify instead of blocking the refresh. The snapshot is public-only. See [AGENTS.md](../../AGENTS.md) and [maintenance instructions](../../scripts/README-stars.md).', '']
    families = dict.fromkeys(c['family'] for c in categories)
    for family in families:
        lines.extend([f'## {family}', ''])
        for c in categories:
            if c['family'] == family:
                lines.append(f"- [{c['emoji']} {c['name']}]({c['slug']}.md) · {len(groups.get(c['id'], []))} repositories")
                lines.append(f"  - {c['description']}")
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def render_stars_json(catalog: dict, groups: dict[str, list[dict]]) -> str:
    categories = visible_categories(catalog, groups)
    repositories = []
    for category in categories:
        for repo in groups.get(category['id'], []):
            repositories.append({
                'id': repo['id'],
                'name': repo['name'],
                'url': repo['url'],
                'description': repo.get('description') or '',
                'category': category['name'],
                'category_id': category['id'],
                'archived': bool(repo.get('archived')),
                'fork': bool(repo.get('fork')),
            })
    repositories.sort(key=lambda row: row['name'].casefold())
    payload = {
        'schema_version': 1,
        'account': catalog['account'],
        'repository_count': len(repositories),
        'categories': [
            {
                'id': category['id'],
                'name': category['name'],
                'slug': category['slug'],
                'count': len(groups.get(category['id'], [])),
            }
            for category in categories
        ],
        'repositories': repositories,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + '\n'


def _page_repo_names(text: str) -> list[str]:
    body = text.split('## Stars', 1)[1] if '## Stars' in text else ''
    return [match.group(1) for match in REPO_ROW.finditer(body)]


def _collect_errors(errors: list[str], condition: bool, message: str) -> None:
    if condition:
        errors.append(message)


def validate_export(catalog: dict, groups: dict[str, list[dict]], output_dir: Path, readme: Path) -> None:
    validate_catalog(catalog)
    categories = ordered_categories(catalog, groups)
    errors: list[str] = []
    inventory_by_name: dict[str, dict] = {}
    for category in categories:
        for repo in groups.get(category['id'], []):
            name = repo['name']
            if name in inventory_by_name:
                errors.append(f'duplicate inventory name {name}')
            inventory_by_name[name] = category
    inventory_set = set(inventory_by_name)
    page_names: list[str] = []
    seen_page_names: set[str] = set()

    for category in categories:
        path = output_dir / f"{category['slug']}.md"
        if not path.is_file():
            errors.append(f"missing category page {path.name}")
            continue
        text = path.read_text(encoding='utf-8')
        expected = render_list(category, groups.get(category['id'], []))
        heading_count = re.search(r'\*\*(\d+) repositories\.\*\*', text)
        count = int(heading_count.group(1)) if heading_count else -1
        names = _page_repo_names(text)
        expected_names = sorted((repo['name'] for repo in groups.get(category['id'], [])), key=str.casefold)
        _collect_errors(errors, count != len(expected_names), f"{path.name}: count {count} != {len(expected_names)}")
        missing = [name for name in expected_names if name not in names]
        extra = [name for name in names if name not in expected_names]
        dupes = sorted({name for name in names if names.count(name) > 1})
        _collect_errors(errors, bool(missing), f"{path.name}: missing {missing[:8]}")
        _collect_errors(errors, bool(extra), f"{path.name}: extra {extra[:8]}")
        _collect_errors(errors, bool(dupes), f"{path.name}: duplicate rows {dupes[:8]}")
        _collect_errors(errors, text != expected, f"{path.name} does not match render_list")
        for name in names:
            if name in seen_page_names:
                errors.append(f'duplicate across categories: {name}')
            seen_page_names.add(name)
            page_names.append(name)

    expected_generated = {f"{category['slug']}.md" for category in categories} | {'README.md'}
    for path in sorted(output_dir.glob('*.md')):
        text = path.read_text(encoding='utf-8')
        generated = GENERATED in text or 'Agent note: generated from the authenticated GitHub stars list' in text
        if generated and path.name not in expected_generated:
            errors.append(f'stale generated file {path.name}')
        for marker in STALE_MARKERS:
            if marker in text:
                errors.append(f'{path.name} contains stale marker {marker}')

    unsorted_page = output_dir / f"{UNSORTED_CATEGORY['slug']}.md"
    _collect_errors(errors, not groups.get(UNSORTED_ID) and unsorted_page.exists(), 'stale unsorted.md')

    missing_pages = sorted(inventory_set - seen_page_names)
    extra_pages = sorted(seen_page_names - inventory_set)
    _collect_errors(errors, bool(missing_pages), f'missing from category pages: {missing_pages[:12]}')
    _collect_errors(errors, bool(extra_pages), f'orphans on category pages: {extra_pages[:12]}')
    _collect_errors(errors, len(page_names) != len(inventory_set), f'page row count {len(page_names)} != inventory {len(inventory_set)}')

    snapshot_path = output_dir / 'stars.json'
    if not snapshot_path.is_file():
        errors.append('missing stars.json')
    else:
        snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
        expected_snapshot = json.loads(render_stars_json(catalog, groups))
        _collect_errors(errors, snapshot != expected_snapshot, 'stars.json does not match render_stars_json')
        _collect_errors(
            errors,
            snapshot.get('repository_count') != len(inventory_set),
            f"stars.json count {snapshot.get('repository_count')} != inventory {len(inventory_set)}",
        )
        star_ids = [row['id'] for row in snapshot.get('categories', [])]
        expected_ids = [category['id'] for category in categories]
        _collect_errors(errors, star_ids != expected_ids, 'stars.json category order mismatch')
        for row, category in zip(snapshot.get('categories', []), categories):
            expected_count = len(groups.get(category['id'], []))
            if row.get('name') != category['name'] or row.get('slug') != category['slug'] or row.get('count') != expected_count:
                errors.append(f"stars.json category mismatch {row.get('id')}")
        star_names = [row['name'] for row in snapshot.get('repositories', [])]
        _collect_errors(errors, star_names != sorted(star_names, key=str.casefold), 'stars.json repositories are not sorted')
        _collect_errors(errors, set(star_names) != inventory_set or len(star_names) != len(inventory_set), 'stars.json name set mismatch')
        for row in snapshot.get('repositories', []):
            category = inventory_by_name.get(row['name'])
            if category is None:
                continue
            if row.get('category_id') != category['id'] or row.get('category') != category['name'] or row.get('url') != f"https://github.com/{row['name']}":
                errors.append(f"stars.json row mismatch {row['name']}")

    index_path = output_dir / 'README.md'
    if not index_path.is_file():
        errors.append('missing docs/stars/README.md')
    else:
        _collect_errors(
            errors,
            index_path.read_text(encoding='utf-8') != render_index(catalog, groups),
            'docs/stars/README.md does not match render_index',
        )

    readme_text = readme.read_text(encoding='utf-8')
    if START not in readme_text or END not in readme_text:
        errors.append('missing starred-repos markers in README.md')
    else:
        section = readme_text.split(START, 1)[1].split(END, 1)[0]
        _collect_errors(
            errors,
            section != '\n' + render_readme(catalog, groups),
            'README starred block does not match render_readme',
        )
        block = section
        for href in re.findall(r'href="(docs/stars/[^"#]+)', block):
            if not (readme.parent / href).is_file():
                errors.append(f'dead README link {href}')
        for marker in STALE_MARKERS:
            if marker in block:
                errors.append(f'README starred block contains stale marker {marker}')

    total = sum(len(repos) for repos in groups.values())
    _collect_errors(errors, total != len(inventory_set), f'group total {total} != inventory {len(inventory_set)}')

    if errors:
        raise ValueError('Export is inconsistent:\n- ' + '\n- '.join(errors))


def snapshot_stars(catalog: dict, snapshot: dict) -> list[dict]:
    """Rebuild the live inventory from stars.json so --check follows membership, not the full catalog."""
    by_id = {repo['id']: repo for repo in catalog['repositories']}
    by_name = {repo['name']: repo for repo in catalog['repositories']}
    stars = []
    for row in snapshot.get('repositories', []):
        classified = by_id.get(row.get('id')) or by_name.get(row.get('name'))
        if classified is None and row.get('category_id') != UNSORTED_ID:
            raise ValueError(f"generated snapshot has repo not in catalog: {row.get('name')}")
        stars.append({
            'id': classified['id'] if classified else row.get('id') or f"{UNSORTED_ID}:{row['name']}",
            'name': row['name'],
            'url': row['url'],
            'description': row.get('description') or '',
            'archived': bool(row.get('archived')),
            'fork': bool(row.get('fork')),
        })
    return stars


def check_committed_export(output_dir: Path, readme: Path, catalog_path: Path) -> None:
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    snapshot = json.loads((output_dir / 'stars.json').read_text(encoding='utf-8'))
    groups = group_stars(snapshot_stars(catalog, snapshot), catalog)
    validate_export(catalog, groups, output_dir, readme)
    root = readme.resolve().parent
    for relative in ('AGENTS.md', 'llms.txt', 'scripts/README-stars.md', 'docs/stars/schema.md'):
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        for marker in ('additions-2026-11-05', 'anthropics/anthropic-cookbook'):
            if marker in text:
                raise ValueError(f'{relative} contains stale marker {marker}')
        for match in re.finditer(r'(?:\]\(|href=")([^)"]+\.md)', text):
            target = match.group(1)
            if target.startswith(('http://', 'https://', '#')):
                continue
            resolved = (path.parent / target).resolve()
            if target.startswith('docs/stars/') or 'stars/' in target or resolved.parent == (root / 'docs/stars').resolve():
                if not resolved.is_file():
                    raise ValueError(f'dead link in {relative}: {target}')


def export(stars: list[dict], catalog: dict, output_dir: Path, readme: Path) -> None:
    groups = group_stars(stars, catalog)
    categories = visible_categories(catalog, groups)
    outputs = {output_dir / f"{c['slug']}.md": render_list(c, groups.get(c['id'], [])) for c in categories}
    outputs[output_dir / 'README.md'] = render_index(catalog, groups)
    outputs[output_dir / 'stars.json'] = render_stars_json(catalog, groups)
    outputs[readme] = replace_readme_section(readme.read_text(encoding='utf-8'), render_readme(catalog, groups))
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob('*.md'):
        if path not in outputs and (GENERATED in path.read_text() or 'Agent note: generated from the authenticated GitHub stars list' in path.read_text()):
            path.unlink()
    stale_unsorted = output_dir / f"{UNSORTED_CATEGORY['slug']}.md"
    if UNSORTED_ID not in groups and stale_unsorted.exists():
        stale_unsorted.unlink()
    for path, text in outputs.items():
        path.write_text(text, encoding='utf-8')
    validate_export(catalog, groups, output_dir, readme)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--readme', type=Path, default=Path('README.md'))
    parser.add_argument('--catalog', type=Path, default=Path('docs/stars/catalog.json'))
    parser.add_argument('--offline', action='store_true', help='Render the reviewed public snapshot without API calls')
    parser.add_argument('--check', action='store_true', help='Validate committed export without rewriting')
    args = parser.parse_args()
    if args.check:
        check_committed_export(args.output_dir, args.readme, args.catalog)
        return 0
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    if args.offline:
        stars = catalog['repositories']
    else:
        token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if not token:
            parser.error('GH_TOKEN or GITHUB_TOKEN is required unless --offline is used')
        stars = fetch_stars(token, catalog['account'])
    export(stars, catalog, args.output_dir, args.readme)
    return 0


if __name__ == '__main__':
    sys.exit(main())
