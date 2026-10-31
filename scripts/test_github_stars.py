"""Protect curated classifications, public-only exports and existing profile styling."""
import copy
import importlib.util
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
        self.assertEqual(sum(map(len, groups.values())), 1315)
        self.assertEqual(sum(r['review_required'] for r in self.catalog['repositories']), 245)
        self.assertFalse(any(r.get('private') for r in self.catalog['repositories']))

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

    def test_unknown_or_empty_inventory_never_overwrites_last_good_files(self):
        known = self.catalog['repositories'][0]
        unknown = {**known, 'id': 'NEW', 'name': 'owner/new', 'url': 'https://github.com/owner/new'}
        for inventory in [[], [known, unknown]]:
            with self.subTest(inventory=bool(inventory)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                readme = root / 'README.md'
                readme.write_text('profile before\n## ⭐ Starred Repos\nlast good\n')
                output = root / 'docs/stars'
                output.mkdir(parents=True)
                old = output / 'old.md'
                old.write_text(stars.GENERATED + '\nlast good')
                with self.assertRaises(ValueError):
                    stars.export(inventory, self.catalog, output, readme)
                self.assertEqual(old.read_text(), stars.GENERATED + '\nlast good')
                self.assertIn('last good', readme.read_text())

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
            first = {p.relative_to(root): p.read_bytes() for p in root.rglob('*.md')}
            stars.export(self.catalog['repositories'], self.catalog, output, readme)
            second = {p.relative_to(root): p.read_bytes() for p in root.rglob('*.md')}
            self.assertEqual(first, second)
            self.assertTrue(readme.read_text().startswith(prefix))
            self.assertTrue(readme.read_text().endswith(suffix))
            self.assertEqual(manual.read_text(), 'Handwritten notes')
            self.assertFalse(stale.exists())
            self.assertEqual(readme.read_text().count('<div style="margin-top: 10px;">'), 26)
            self.assertEqual(readme.read_text().count('variant=outline'), 52)
            self.assertEqual(readme.read_text().count('<picture>'), 54)
            for href in re.findall(r'href="(docs/stars/[^"#]+)', readme.read_text()):
                self.assertTrue((root / href).is_file(), href)
            rendered = '\n'.join((output / f"{c['slug']}.md").read_text() for c in self.catalog['categories'])
            self.assertEqual(len(re.findall(r'^- \[', rendered, re.M)), 1315)
            self.assertEqual(rendered.count(' · review needed'), 245)


if __name__ == '__main__':
    unittest.main()
