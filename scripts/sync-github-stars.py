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


def validate_catalog(catalog: dict) -> None:
    if catalog.get('schema_version') != 1:
        raise ValueError('Unsupported catalog version')
    categories = catalog['categories']
    ids = {c['id'] for c in categories}
    slugs = {c['slug'] for c in categories}
    if len(ids) != len(categories) or len(slugs) != len(categories):
        raise ValueError('Duplicate category ID or slug')
    if any(not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or slug == 'readme' for slug in slugs):
        raise ValueError('Unsafe category slug')
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
            unknown.append(repo['name'])
        else:
            groups[classified['category']].append({**classified, **repo})
    if unknown:
        raise ValueError('Public stars need classification in docs/stars/catalog.json; no files written: ' + ', '.join(sorted(unknown)))
    if not seen:
        raise ValueError('Empty public star inventory; retaining the last good export')
    return groups


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
    lines = ['## ⭐ Starred Repos', '',
        f'<a href="https://github.com/{account}?tab=stars"><picture><source media="(prefers-color-scheme: dark)" srcset="https://www.shieldcn.dev/badge/All-stars-24292F.svg?variant=branded&amp;size=sm&amp;mode=dark"><img alt="Browse all stars" src="https://www.shieldcn.dev/badge/All-stars-24292F.svg?variant=branded&amp;size=sm&amp;mode=light"></picture></a>', '',
        f"{sum(len(v) for v in groups.values()):,} public repositories · {len(catalog['categories'])} categories · [Browse the catalog](docs/stars/README.md)", '']
    for c in catalog['categories']:
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
    lines = ['# Starred repositories by primary use', '', GENERATED, '',
        f"**{sum(len(v) for v in groups.values()):,} public repositories across {len(catalog['categories'])} Sol categories.**", '',
        'Describe the outcome you need, choose a family below, then open its category. Each repository has one primary category.', '',
        'For agents: [catalog.json](catalog.json) contains stable repository and category IDs, URLs, French usage summaries, French/English search keywords, README evidence quotes and review flags. Search the `purpose`, `description` and `keywords` fields with the requested task, then verify the match against `evidence_quote`. Category definitions explain the boundaries.', '',
        'A review flag means the evidence or category boundary needs checking, not that the repository is unclassified. The snapshot is public-only. See [maintenance instructions](../../scripts/README-stars.md) for refresh and classification updates.', '']
    families = dict.fromkeys(c['family'] for c in catalog['categories'])
    for family in families:
        lines.extend([f'## {family}', ''])
        for c in catalog['categories']:
            if c['family'] == family:
                lines.append(f"- [{c['emoji']} {c['name']}]({c['slug']}.md) · {len(groups[c['id']])} repositories")
                lines.append(f"  - {c['description']}")
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def export(stars: list[dict], catalog: dict, output_dir: Path, readme: Path) -> None:
    groups = group_stars(stars, catalog)
    outputs = {output_dir / f"{c['slug']}.md": render_list(c, groups[c['id']]) for c in catalog['categories']}
    outputs[output_dir / 'README.md'] = render_index(catalog, groups)
    outputs[readme] = replace_readme_section(readme.read_text(encoding='utf-8'), render_readme(catalog, groups))
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob('*.md'):
        if path not in outputs and (GENERATED in path.read_text() or 'Agent note: generated from the authenticated GitHub stars list' in path.read_text()):
            path.unlink()
    for path, text in outputs.items():
        path.write_text(text, encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--readme', type=Path, default=Path('README.md'))
    parser.add_argument('--catalog', type=Path, default=Path('docs/stars/catalog.json'))
    parser.add_argument('--offline', action='store_true', help='Render the reviewed public snapshot without API calls')
    args = parser.parse_args()
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
