"""Protect curated classifications, public-only exports and existing profile styling."""
import copy
import importlib.util
import hashlib
import json
from io import StringIO
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
        catalog_n = len(self.catalog['repositories'])
        self.assertEqual(len(groups), 26)
        self.assertGreater(catalog_n, 0)
        self.assertEqual(sum(map(len, groups.values())), catalog_n)
        self.assertFalse(any(r.get('private') for r in self.catalog['repositories']))
        self.assertNotIn(stars.UNSORTED_ID, groups)

    def test_original_sol_records_are_unchanged(self):
        original = [r for r in self.catalog['repositories'] if 'classification_source' not in r]
        self.assertEqual(len(original), 1299)
        self.assertEqual(sum(r['review_required'] for r in original), 235)
        payload = json.dumps(sorted(original, key=lambda r: r['id']), ensure_ascii=False, sort_keys=True)
        self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), 'e5c74a1d4fd15843bbfae462e6da497a0fb7cba80fb3a7591aa2e5bbd7efc1ab')
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
            if r.get('classification_source') == 'https://github.com/ardjo-s/ardjo-s/actions/runs/43613859551'
        ]
        self.assertEqual(len(additions_2026_11_14), 79)
        self.assertEqual(sum(r['review_required'] for r in additions_2026_11_14), 3)
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
        live_unsorted = [
            r for r in self.catalog['repositories']
            if r.get('classification_source') == 'https://github.com/ardjo-s/ardjo-s/actions/runs/43636181890'
        ]
        self.assertEqual(len(live_unsorted), 6)
        self.assertEqual(sum(r['review_required'] for r in live_unsorted), 0)
        self.assertEqual(
            {r['name'] for r in live_unsorted},
            {
                'arjun988/blender-skills',
                'maillab/cloud-mail',
                'MobAI-App/simslim',
                'ricocc/ricoui-blocks',
                'rinkitadhana/openside',
                'standardagents/spec',
            },
        )
        self.assertEqual(
            {r['name']: r['category'] for r in live_unsorted},
            {
                'arjun988/blender-skills': 'category_23',
                'maillab/cloud-mail': 'category_19',
                'MobAI-App/simslim': 'category_12',
                'ricocc/ricoui-blocks': 'category_11',
                'rinkitadhana/openside': 'category_10',
                'standardagents/spec': 'category_03',
            },
        )
        for repo in live_unsorted:
            self.assertTrue(repo['evidence_quote'])
            self.assertEqual(repo['url'], f"https://github.com/{repo['name']}")
            self.assertEqual(repo['evidence_read_at'], '2026-11-14')
        additions_2026_11_15 = [
            r for r in self.catalog['repositories']
            if r.get('classification_source') == 'human:2026-11-15'
        ]
        self.assertEqual(len(additions_2026_11_15), 102)
        self.assertEqual(sum(r['review_required'] for r in additions_2026_11_15), 3)
        by_name = {r['name']: r for r in additions_2026_11_15}
        self.assertEqual(by_name['agentgateway/agentgateway']['category'], 'category_07')
        self.assertEqual(by_name['awesome-foss/awesome-sysadmin']['category'], 'category_15')
        self.assertEqual(by_name['apple/coreai-models']['category'], 'category_06')
        self.assertTrue(by_name['apple/coreai-models']['review_required'])
        self.assertTrue(by_name['Narcooo/inkos']['review_required'])
        self.assertTrue(by_name['GoogleChrome/modern-web-guidance-src']['review_required'])
        self.assertEqual(by_name['ashishps1/awesome-system-design-resources']['category'], 'category_15')
        audit_corrections = {
            'NVIDIA-AI-Blueprints/video-search-and-summarization': 'category_10',
            'assistant-ui/assistant-ui': 'category_11',
            'pipecat-ai/ios-little-voices': 'category_09',
            'nexu-io/html-anything': 'category_10',
            'datawhalechina/zero-to-sglang': 'category_07',
            'typesafe-ai/skills': 'category_03',
            'huggingface/skills': 'category_03',
            'jxnl/dots': 'category_13',
            'ashishps1/awesome-system-design-resources': 'category_15',
            '1Password/for-open-source': 'category_18',
            'OpenCoworkAI/open-codesign': 'category_11',
            'agentes-chat/agentes-chat': 'category_02',
            'blader/humanizer': 'category_03',
            'dontriskit/awesome-ai-software-engineering': 'category_03',
            'hjunhuh/awesome-rust': 'category_13',
            'mvanhorn/printing-press-library': 'category_04',
            'tuan3w/linearapp_clone': 'category_11',
            'EveryInc/tend': 'category_01',
            'ooolzhas/annotatekit': 'category_12',
            '21st-dev/21st-sdk-examples': 'category_26',
        }
        for name, category in audit_corrections.items():
            repo = by_name[name]
            self.assertEqual(repo['category'], category, name)
            self.assertFalse(repo['review_required'], name)
            candidates = repo.get('review_candidates') or []
            self.assertTrue(candidates and candidates[0] != repo['category'], name)
        for repo in additions_2026_11_15:
            if repo['name'] == '21st-dev/21st-sdk-examples':
                self.assertEqual(repo['evidence_status'], 'unavailable_404_metadata_only')
            else:
                self.assertTrue(repo['evidence_quote'])
            self.assertEqual(repo['url'], f"https://github.com/{repo['name']}")
            self.assertIn('classification_source', repo)
            self.assertNotEqual(repo['category'], stars.UNSORTED_ID)
        low_published = {
            'miuuyy/Astra-Ares': 'category_03',
            'WordPress/openverse': 'category_13',
        }
        by_all = {r['name']: r for r in self.catalog['repositories']}
        for name, category in low_published.items():
            repo = by_all[name]
            self.assertEqual(repo['category'], category, name)
            self.assertTrue(repo['review_required'], name)
            self.assertEqual(repo['classification_confidence'], 'low', name)
            self.assertTrue(repo.get('review_candidates'), name)
            self.assertNotEqual(repo['category'], stars.UNSORTED_ID)

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

    def test_starred_pagination_dedupes_and_refetches_once(self):
        def repo(node, name):
            return {
                'node_id': node,
                'full_name': name,
                'html_url': f'https://github.com/{name}',
                'private': False,
                'description': name,
            }

        first = repo('A', 'owner/alpha')
        shifted = repo('B', 'Leonxlnx/procedural-fire')
        extra = repo('C', 'owner/gamma')
        login = {'login': 'ardjo-s'}
        with patch.object(
            stars,
            'request_json',
            side_effect=[
                login,
                [first, shifted],
                [shifted, extra],
                [],
                [first, shifted],
                [extra],
                [],
            ],
        ) as mocked, patch.object(stars.sys, 'stderr', StringIO()) as stderr:
            result = stars.fetch_stars('test-token', 'ardjo-s')
        self.assertEqual([row['name'] for row in result], [
            'owner/alpha',
            'Leonxlnx/procedural-fire',
            'owner/gamma',
        ])
        self.assertEqual(len({row['id'] for row in result}), 3)
        self.assertGreaterEqual(mocked.call_count, 5)
        messages = stderr.getvalue()
        self.assertIn('Leonxlnx/procedural-fire', messages)
        self.assertIn('Re-fetching', messages)

    def test_group_stars_skips_duplicate_live_ids(self):
        known = self.catalog['repositories'][0]
        duplicate = {**known, 'description': 'shifted page copy'}
        with patch.object(stars.sys, 'stderr'):
            grouped = stars.group_stars([known, duplicate], self.catalog)
        repos = grouped[known['category']]
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0]['name'], known['name'])

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

    def test_check_preserves_unknown_id_when_name_matches_catalog(self):
        known = self.catalog['repositories'][0]
        reused = {
            **known,
            'id': 'NEW_NODE',
            'description': 'Recreated under the same name',
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'docs/stars'
            output.mkdir(parents=True)
            readme = root / 'README.md'
            readme.write_text('profile before\n## ⭐ Starred Repos\nold\n')
            with patch.object(stars.sys, 'stderr'):
                stars.export([reused], self.catalog, output, readme)
                snapshot = json.loads((output / 'stars.json').read_text())
                row = next(item for item in snapshot['repositories'] if item['name'] == known['name'])
                self.assertEqual(row['id'], 'NEW_NODE')
                self.assertEqual(row['category_id'], stars.UNSORTED_ID)
                reconstructed = stars.snapshot_stars(self.catalog, snapshot)
                self.assertEqual(reconstructed[0]['id'], 'NEW_NODE')
                stars.check_committed_export(output, readme, ROOT / 'docs/stars/catalog.json')

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
            unsorted = (output / 'unsorted.md').read_text()
            self.assertTrue((output / 'unsorted.md').exists())
            self.assertIn('**0 repositories.**', unsorted)
            self.assertNotIn('à trancher', unsorted)
            self.assertNotIn('- [', unsorted)
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
            catalog_n = len(self.catalog['repositories'])
            review_n = sum(r['review_required'] for r in self.catalog['repositories'])
            self.assertEqual(len(re.findall(r'^- \[', rendered, re.M)), catalog_n)
            self.assertEqual(rendered.count(' · review needed'), review_n)
            snapshot = json.loads((output / 'stars.json').read_text())
            self.assertEqual(snapshot['repository_count'], catalog_n)
            self.assertTrue(all(row.get('id') for row in snapshot['repositories']))
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

    def test_live_export_preserves_existing_unsorted_notes(self):
        known = self.catalog['repositories'][0]
        unknown = {
            **known,
            'id': 'NEW',
            'name': 'owner/new',
            'url': 'https://github.com/owner/new',
            'description': 'Fresh star',
        }
        later = {
            **known,
            'id': 'NEWER',
            'name': 'owner/later',
            'url': 'https://github.com/owner/later',
            'description': 'Another fresh star',
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / 'README.md'
            readme.write_text('profile\n## ⭐ Starred Repos\nold\n')
            output = root / 'docs/stars'
            output.mkdir(parents=True)
            with patch.object(stars.sys, 'stderr'):
                stars.export(
                    [known, unknown],
                    self.catalog,
                    output,
                    readme,
                    unsorted_notes={'owner/new': ['Security', 'Developer Tools']},
                )
            notes = stars.load_unsorted_notes(output / 'stars.json')
            self.assertEqual(notes, {'owner/new': ['Security', 'Developer Tools']})
            with patch.object(stars.sys, 'stderr'):
                stars.export(
                    [known, unknown, later],
                    self.catalog,
                    output,
                    readme,
                    unsorted_notes=notes or None,
                )
            page = (output / 'unsorted.md').read_text()
            self.assertNotIn('## À trancher', page)
            self.assertIn('## Stars', page)
            self.assertIn('owner/new', page)
            self.assertIn('owner/later', page)
            self.assertNotIn('à trancher', page)
            snapshot = json.loads((output / 'stars.json').read_text())
            by_name = {row['name']: row for row in snapshot['repositories']}
            self.assertEqual(
                by_name['owner/new']['review_candidate_names'],
                ['Security', 'Developer Tools'],
            )
            self.assertNotIn('review_candidate_names', by_name['owner/later'])


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
