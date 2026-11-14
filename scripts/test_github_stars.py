"""Protect curated classifications, public-only exports and existing profile styling."""
import copy
import importlib.util
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stars', ROOT / 'scripts/sync-github-stars.py')
stars = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stars)


class StarsTest(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / 'docs/stars/catalog.json').read_text())

    def test_snapshot_is_complete_and_unique(self):
        stars.validate_catalog(self.catalog)
        groups = stars.group_stars(self.catalog['repositories'], self.catalog)
        self.assertEqual(len(groups), 26)
        self.assertEqual(sum(map(len, groups.values())), 1452)
        self.assertEqual(sum(r['review_required'] for r in self.catalog['repositories']), 249)
        self.assertFalse(any(r.get('private') for r in self.catalog['repositories']))
        self.assertNotIn(stars.UNSORTED_ID, groups)

    def test_original_sol_records_are_unchanged(self):
        original = [r for r in self.catalog['repositories'] if 'classification_source' not in r]
        self.assertEqual(len(original), 1315)
        self.assertEqual(sum(r['review_required'] for r in original), 245)
        payload = json.dumps(sorted(original, key=lambda r: r['id']), ensure_ascii=False, sort_keys=True)
        self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), 'a70d953d74fb3c15fdb1c327071f48805e1ed65d77b3e1979e881ed4d04b13c9')
        additions_2026_11_05 = [
            r for r in self.catalog['repositories']
            if r.get('evidence_read_at') == '2026-11-05'
        ]
        self.assertEqual(len(additions_2026_11_05), 56)
        self.assertEqual(sum(r['review_required'] for r in additions_2026_11_05), 0)
        for repo in additions_2026_11_05:
            self.assertTrue(repo['evidence_quote'])
            self.assertTrue(repo['evidence_url'].startswith(repo['url'] + '/blob/'))
            self.assertRegex(repo['evidence_sha256'], r'^[0-9a-f]{64}$')
            self.assertIn('classification_source', repo)
            if 'review_resolution' in repo:
                resolution = repo['review_resolution']
                self.assertEqual(resolution['category'], repo['category'])
                self.assertEqual(resolution['reviewer'], 'Astra')
                self.assertEqual(resolution['approved_by'], 'Ardjo')
                self.assertTrue(resolution['previous_reason'])
        self.assertEqual(sum('review_resolution' in r for r in additions_2026_11_05), 4)
        additions_2026_11_14 = [
            r for r in self.catalog['repositories']
            if r.get('evidence_read_at') == '2026-11-14'
        ]
        self.assertEqual(len(additions_2026_11_14), 81)
        self.assertEqual(sum(r['review_required'] for r in additions_2026_11_14), 4)
        names = {r['name'] for r in additions_2026_11_14}
        self.assertIn('anthropics/claude-cookbooks', names)
        self.assertIn('anthropics/courses', names)
        self.assertIn('crewAIInc/crewAI', names)
        self.assertIn('microsoft/autogen', names)
        self.assertNotIn('anthropics/anthropic-cookbook', names)
        for repo in additions_2026_11_14:
            self.assertTrue(repo['evidence_quote'])
            self.assertTrue(repo['url'].startswith('https://github.com/'))
            self.assertEqual(repo['url'], f"https://github.com/{repo['name']}")
            self.assertIn('classification_source', repo)

    def test_renamed_repository_keeps_reviewed_category(self):
        repo = copy.deepcopy(self.catalog['repositories'][0])
        category = repo.pop('category')
        repo['name'] = 'new-owner/new-name'
        repo['url'] = 'https://github.com/new-owner/new-name'
        grouped = stars.group_stars([repo], self.catalog)
        self.assertEqual(list(grouped), [category])
        self.assertEqual(grouped[category][0]['name'], 'new-owner/new-name')

    def test_public_fetch_pages_without_exposing_private_stars(self):
        public = {'node_id': 'PUBLIC', 'full_name': 'owner/public', 'html_url': 'https://github.com/owner/public', 'private': False}
        private = {**public, 'node_id': 'PRIVATE', 'full_name': 'owner/private', 'private': True}
        with patch.object(stars, 'request_json', side_effect=[{'login': 'ardjo-s'}, [private], [{'repo': public}], []]):
            result = stars.fetch_stars('test-token', 'ardjo-s')
        self.assertEqual([r['name'] for r in result], ['owner/public'])
        with patch.object(stars, 'request_json', return_value={'login': 'someone-else'}):
            with self.assertRaisesRegex(ValueError, 'owner'):
                stars.fetch_stars('test-token', 'ardjo-s')

    def test_empty_inventory_never_overwrites_last_good_files(self):
        known = self.catalog['repositories'][0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / 'README.md'
            readme.write_text('profile before\n## ⭐ Starred Repos\nlast good\n')
            output = root / 'docs/stars'
            output.mkdir(parents=True)
            old = output / 'old.md'
            old.write_text(stars.GENERATED + '\nlast good')
            with self.assertRaisesRegex(ValueError, 'Empty public star inventory'):
                stars.export([], self.catalog, output, readme)
            self.assertEqual(old.read_text(), stars.GENERATED + '\nlast good')
            self.assertIn('last good', readme.read_text())

    def test_unknown_stars_export_to_unsorted_without_blocking(self):
        known = self.catalog['repositories'][0]
        unknown = {**known, 'id': 'NEW', 'name': 'owner/new', 'url': 'https://github.com/owner/new', 'description': 'Fresh star'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / 'README.md'
            readme.write_text('profile before\n## ⭐ Starred Repos\nlast good\n')
            output = root / 'docs/stars'
            output.mkdir(parents=True)
            old = output / 'old.md'
            old.write_text(stars.GENERATED + '\nlast good')
            with patch.object(stars.sys, 'stderr'):
                stars.export([known, unknown], self.catalog, output, readme)
            self.assertFalse(old.exists())
            unsorted = (output / 'unsorted.md').read_text()
            self.assertIn('owner/new', unsorted)
            self.assertIn(stars.GENERATED, unsorted)
            self.assertIn('Unsorted / to classify', readme.read_text())
            self.assertIn('1 unsorted', readme.read_text())
            snapshot = json.loads((output / 'stars.json').read_text())
            names = [row['name'] for row in snapshot['repositories']]
            self.assertEqual(names, sorted(names, key=str.casefold))
            self.assertIn('owner/new', names)
            self.assertEqual(
                next(row for row in snapshot['repositories'] if row['name'] == 'owner/new')['category_id'],
                stars.UNSORTED_ID,
            )

    def test_invalid_assignment_or_duplicate_is_rejected(self):
        for change in ['category', 'duplicate', 'slug']:
            catalog = copy.deepcopy(self.catalog)
            if change == 'category':
                catalog['repositories'][0]['category'] = 'missing'
            elif change == 'duplicate':
                catalog['repositories'].append(catalog['repositories'][0])
            else:
                catalog['categories'][0]['slug'] = '../README'
            with self.subTest(change=change), self.assertRaises(ValueError):
                stars.validate_catalog(catalog)

    def test_export_preserves_profile_and_manual_docs_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'docs/stars'
            output.mkdir(parents=True)
            readme = root / 'README.md'
            prefix = '<div align="center">social badges</div>\n<!-- tokscale-embed-start -->\n<picture>cards</picture>\n<!-- tokscale-embed-end -->\n\n'
            suffix = '## Other work\nKeep this too.\n'
            readme.write_text(prefix + '## ⭐ Starred Repos\nold categories\n\n' + suffix)
            manual = output / 'manual.md'
            manual.write_text('Handwritten notes')
            stale = output / 'stale.md'
            stale.write_text('Agent note: generated from the authenticated GitHub stars list; do not edit manually.')
            stars.export(self.catalog['repositories'], self.catalog, output, readme)
            first = {p.relative_to(root): p.read_bytes() for p in [*root.rglob('*.md'), output / 'stars.json']}
            stars.export(self.catalog['repositories'], self.catalog, output, readme)
            second = {p.relative_to(root): p.read_bytes() for p in [*root.rglob('*.md'), output / 'stars.json']}
            self.assertEqual(first, second)
            self.assertTrue(readme.read_text().startswith(prefix))
            self.assertTrue(readme.read_text().endswith(suffix))
            self.assertEqual(manual.read_text(), 'Handwritten notes')
            self.assertFalse(stale.exists())
            self.assertFalse((output / 'unsorted.md').exists())
            self.assertEqual(readme.read_text().count('<div style="margin-top: 10px;">'), 26)
            self.assertEqual(readme.read_text().count('variant=outline'), 52)
            self.assertEqual(readme.read_text().count('<picture>'), 54)
            self.assertLess(
                readme.read_text().index('AI Engineering & Learning'),
                readme.read_text().index('Voice, Audio & Music'),
            )
            for href in re.findall(r'href="(docs/stars/[^"#]+)', readme.read_text()):
                self.assertTrue((root / href).is_file(), href)
            rendered = '\n'.join((output / f"{c['slug']}.md").read_text() for c in self.catalog['categories'])
            self.assertEqual(len(re.findall(r'^- \[', rendered, re.M)), 1452)
            self.assertEqual(rendered.count(' · review needed'), 249)
            snapshot = json.loads((output / 'stars.json').read_text())
            self.assertEqual(snapshot['repository_count'], 1452)
            self.assertEqual(
                [row['name'] for row in snapshot['repositories']],
                sorted((row['name'] for row in snapshot['repositories']), key=str.casefold),
            )
            self.assertEqual(
                [row['id'] for row in snapshot['categories']],
                [category['id'] for category in stars.ordered_categories(self.catalog)],
            )
            self.assertLess(
                [row['id'] for row in snapshot['categories']].index('category_26'),
                [row['id'] for row in snapshot['categories']].index('category_09'),
            )

    def test_catalog_categories_follow_family_order(self):
        self.assertEqual(
            [category['id'] for category in self.catalog['categories']],
            [category['id'] for category in stars.ordered_categories(self.catalog)],
        )
        self.assertEqual(
            [category['id'] for category in self.catalog['categories']].index('category_26'),
            8,
        )

    def test_committed_export_is_internally_consistent(self):
        stars.check_committed_export(ROOT / 'docs/stars', ROOT / 'README.md', ROOT / 'docs/stars/catalog.json')

    def test_validate_export_fails_on_orphans_duplicates_and_count_mismatch(self):
        known = self.catalog['repositories'][0]
        other = next(repo for repo in self.catalog['repositories'] if repo['category'] != known['category'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'docs/stars'
            output.mkdir(parents=True)
            readme = root / 'README.md'
            readme.write_text('profile\n## ⭐ Starred Repos\nold\n')
            stars.export(self.catalog['repositories'], self.catalog, output, readme)
            groups = stars.group_stars(self.catalog['repositories'], self.catalog)
            page = output / f"{next(c['slug'] for c in self.catalog['categories'] if c['id'] == known['category'])}.md"
            original = page.read_text()
            page.write_text(original.replace(f"- [{known['name']}]", f"- [{known['name']}-gone]", 1))
            with self.assertRaisesRegex(ValueError, 'inconsistent|missing'):
                stars.validate_export(self.catalog, groups, output, readme)
            page.write_text(original + original[original.index('- ['):original.index('\n', original.index('- [')) + 1])
            with self.assertRaisesRegex(ValueError, 'inconsistent|duplicate'):
                stars.validate_export(self.catalog, groups, output, readme)
            page.write_text(original.replace('**' + str(len(groups[known['category']])) + ' repositories.**', '**0 repositories.**', 1))
            with self.assertRaisesRegex(ValueError, 'inconsistent|count'):
                stars.validate_export(self.catalog, groups, output, readme)
            page.write_text(original)
            other_page = output / f"{next(c['slug'] for c in self.catalog['categories'] if c['id'] == other['category'])}.md"
            other_text = other_page.read_text()
            other_page.write_text(other_text + f"- [{known['name']}](https://github.com/{known['name']}): Duplicate row.\n")
            with self.assertRaisesRegex(ValueError, 'inconsistent|duplicate'):
                stars.validate_export(self.catalog, groups, output, readme)


if __name__ == '__main__':
    unittest.main()
