"""Deterministic unsorted-star classifier: existing categories only, PR #14 fixtures."""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stars = load('stars', 'sync-github-stars.py')
classify = load('classify_stars', 'classify-github-stars.py')

PR14_FIXTURES = {
    'arjun988/blender-skills': 'category_23',
    'maillab/cloud-mail': 'category_19',
    'MobAI-App/simslim': 'category_12',
    'ricocc/ricoui-blocks': 'category_11',
    'rinkitadhana/openside': 'category_10',
    'standardagents/spec': 'category_03',
}
PR14_NAMES = {
    'arjun988/blender-skills': 'Games & 3D',
    'maillab/cloud-mail': 'Knowledge & Productivity',
    'MobAI-App/simslim': 'App, Web & Mobile Development',
    'ricocc/ricoui-blocks': 'UI & Product Design',
    'rinkitadhana/openside': 'Image, Video & Presentations',
    'standardagents/spec': 'Agent Methods, Skills & Configuration',
}


class StarClassifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'docs/stars/catalog.json').read_text())
        cls.features = json.loads(
            (ROOT / 'scripts/testdata/pr14_classify_fixtures.json').read_text()
        )
        held = copy.deepcopy(cls.catalog)
        held['repositories'] = [
            repo for repo in held['repositories'] if repo['name'] not in PR14_FIXTURES
        ]
        cls.held_catalog = held
        cls.index = classify.CatalogIndex(held)
        cls.category_ids = {category['id'] for category in held['categories']}

    def test_pr14_fixtures_match_human_categories(self):
        misses = []
        for name, expected in PR14_FIXTURES.items():
            decision = classify.classify_repo(self.index, name, self.features[name])
            if decision['category'] != expected:
                misses.append((name, expected, decision['category'], decision['category_name']))
            self.assertIn(decision['category'], self.category_ids)
            self.assertNotEqual(decision['category'], stars.UNSORTED_ID)
            if decision['review_required']:
                self.assertEqual(len(decision['review_candidates']), 2)
                self.assertEqual(decision['review_candidates'][0], decision['category'])
                self.assertTrue(set(decision['review_candidates']) <= self.category_ids)
        self.assertEqual(misses, [], msg=f'fixture misses: {misses}')
        self.assertEqual(
            {name: classify.classify_repo(self.index, name, self.features[name])['category'] for name in PR14_FIXTURES},
            PR14_FIXTURES,
        )
        self.assertEqual(
            {name: classify.classify_repo(self.index, name, self.features[name])['category_name'] for name in PR14_FIXTURES},
            PR14_NAMES,
        )

    def test_never_creates_a_category(self):
        self.assertEqual(len(self.held_catalog['categories']), 26)
        decision = classify.classify_repo(
            self.index,
            'arjun988/blender-skills',
            self.features['arjun988/blender-skills'],
        )
        self.assertIn(decision['category'], self.category_ids)
        with self.assertRaisesRegex(ValueError, 'unknown category|refusing'):
            classify.insert_records(copy.deepcopy(self.held_catalog), [{
                'id': 'NEW',
                'name': 'owner/new',
                'url': 'https://github.com/owner/new',
                'description': '',
                'category': 'category_99',
                'purpose': '',
                'keywords': [],
                'review_required': True,
                'evidence_quote': 'x',
                'evidence_status': 'description_only',
                'archived': False,
                'fork': False,
            }])

    def test_low_confidence_keeps_a_category_and_names_two_candidates(self):
        decision = classify.classify_repo(self.index, 'owner/generic', {
            'description': 'A starred repository.',
            'topics': [],
            'language': '',
            'readme': 'Hello world.',
        })
        self.assertIn(decision['category'], self.category_ids)
        self.assertTrue(decision['review_required'])
        self.assertEqual(decision['confidence'], 'low')
        self.assertEqual(len(decision['review_candidates']), 2)
        self.assertEqual(len(set(decision['review_candidates'])), 2)
        self.assertTrue(set(decision['review_candidates']) <= self.category_ids)

    def test_domain_skill_follows_games_not_generic_methods(self):
        decision = classify.classify_repo(
            self.index,
            'arjun988/blender-skills',
            self.features['arjun988/blender-skills'],
        )
        self.assertEqual(decision['category'], 'category_23')
        self.assertIn('Games & 3D', decision['reason'] + decision['category_name'])

    def test_apply_classifies_unsorted_snapshot_and_passes_check(self):
        catalog = copy.deepcopy(self.held_catalog)
        snapshot_repos = []
        for repo in catalog['repositories'][:8]:
            snapshot_repos.append({
                'id': repo['id'],
                'name': repo['name'],
                'url': repo['url'],
                'description': repo.get('description') or '',
                'category': next(c['name'] for c in catalog['categories'] if c['id'] == repo['category']),
                'category_id': repo['category'],
                'archived': False,
                'fork': False,
            })
        for name, expected in PR14_FIXTURES.items():
            features = self.features[name]
            snapshot_repos.append({
                'id': f'UNSORTED-{name}',
                'name': name,
                'url': f'https://github.com/{name}',
                'description': features.get('description') or '',
                'category': 'Unsorted / to classify',
                'category_id': stars.UNSORTED_ID,
                'archived': False,
                'fork': False,
            })
        snapshot = {'repositories': snapshot_repos}
        decisions, records = classify.classify_unsorted(
            catalog,
            snapshot,
            features_by_name=self.features,
            token='',
        )
        self.assertEqual(len(decisions), 6)
        self.assertEqual({row['name']: row['category'] for row in records}, PR14_FIXTURES)
        catalog, conflicts = classify.insert_records(catalog, records)
        self.assertEqual(conflicts, [])
        assigned = {repo['name']: repo['category'] for repo in catalog['repositories'] if repo['name'] in PR14_FIXTURES}
        self.assertEqual(assigned, PR14_FIXTURES)
        self.assertTrue(all(repo.get('classification_source') for repo in catalog['repositories'] if repo['name'] in PR14_FIXTURES))
        body = classify.render_pr_body(decisions, source='test')
        self.assertIn('| Repository | Category | Confidence | Reason |', body)
        self.assertIn('arjun988/blender-skills', body)
        self.assertNotIn('enable auto-merge', body.casefold())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'docs/stars'
            output.mkdir(parents=True)
            readme = root / 'README.md'
            readme.write_text('profile\n## ⭐ Starred Repos\nold\n')
            live = []
            for row in snapshot_repos:
                live.append({
                    'id': row['id'],
                    'name': row['name'],
                    'url': row['url'],
                    'description': row['description'],
                    'archived': False,
                    'fork': False,
                })
            catalog_path = output / 'catalog.json'
            classify.write_catalog(catalog_path, catalog)
            stars.export(live, catalog, output, readme)
            self.assertFalse((output / 'unsorted.md').exists())
            exported = json.loads((output / 'stars.json').read_text())
            got = {
                row['name']: row['category_id']
                for row in exported['repositories']
                if row['name'] in PR14_FIXTURES
            }
            self.assertEqual(got, PR14_FIXTURES)
            stars.check_committed_export(output, readme, catalog_path)

    def test_name_collision_with_new_node_id_is_a_conflict(self):
        catalog = copy.deepcopy(self.held_catalog)
        existing = catalog['repositories'][0]
        record = {
            'id': 'BRAND_NEW_NODE',
            'name': existing['name'],
            'url': existing['url'],
            'description': 'Recreated under the same name',
            'category': existing['category'],
            'purpose': 'conflict',
            'keywords': [],
            'review_required': True,
            'evidence_quote': 'x',
            'evidence_status': 'description_only',
            'archived': False,
            'fork': False,
        }
        before = len(catalog['repositories'])
        catalog, conflicts = classify.insert_records(catalog, [record])
        self.assertEqual(len(catalog['repositories']), before)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]['id'], 'BRAND_NEW_NODE')
        self.assertEqual(conflicts[0]['existing_id'], existing['id'])
        body = classify.render_pr_body([], source='test', conflicts=conflicts)
        self.assertIn('Name conflicts', body)
        self.assertIn(existing['name'], body)

    def test_private_repo_features_are_not_copied_into_the_catalog(self):
        with patch.object(classify, 'request_optional', return_value={
            'full_name': 'owner/secret',
            'private': True,
            'description': 'internal readme should not leak',
            'node_id': 'PRIVATE_NODE',
        }):
            features = classify.fetch_features('owner/secret', 'token', {
                'id': 'PRIVATE_NODE',
                'name': 'owner/secret',
                'url': 'https://github.com/owner/secret',
                'description': 'public snapshot leftover',
            })
        self.assertTrue(features['private'])
        self.assertEqual(features['description'], '')
        self.assertEqual(features['readme'], '')
        catalog = copy.deepcopy(self.held_catalog)
        snapshot = {'repositories': [{
            'id': 'PRIVATE_NODE',
            'name': 'owner/secret',
            'url': 'https://github.com/owner/secret',
            'description': 'public snapshot leftover',
            'category_id': stars.UNSORTED_ID,
            'archived': False,
            'fork': False,
        }]}
        decisions, records = classify.classify_unsorted(
            catalog,
            snapshot,
            features_by_name={'owner/secret': features},
            token='',
        )
        self.assertEqual(len(records), 0)
        self.assertTrue(decisions[0]['skipped'])
        catalog, conflicts = classify.insert_records(catalog, records)
        self.assertEqual(conflicts, [])
        self.assertFalse(any(repo['name'] == 'owner/secret' for repo in catalog['repositories']))

    def test_empty_unsorted_is_a_noop(self):
        snapshot = json.loads((ROOT / 'docs/stars/stars.json').read_text())
        classified_only = {
            'repositories': [
                row for row in snapshot['repositories']
                if row.get('category_id') != stars.UNSORTED_ID
            ]
        }
        decisions, records = classify.classify_unsorted(self.catalog, classified_only, token='')
        self.assertEqual(decisions, [])
        self.assertEqual(records, [])

    def test_classifier_workflow_is_idempotent_and_never_automerge(self):
        workflow = (ROOT / '.github/workflows/classify-github-stars.yml').read_text()
        self.assertIn('auto/classify-stars', workflow)
        self.assertIn('--head auto/classify-stars', workflow)
        self.assertNotIn('${GITHUB_REPOSITORY_OWNER}:auto/classify-stars', workflow)
        self.assertIn('workflow_run', workflow)
        self.assertIn('GH_STARS_TOKEN', workflow)
        self.assertIn('docs/stars/unsorted.md', workflow)
        self.assertNotIn('auto-merge', workflow.casefold())
        self.assertNotIn('gh pr merge', workflow)
        self.assertGreaterEqual(workflow.count("python3 -m unittest discover -s scripts -p 'test_*.py'"), 2)
        self.assertIn('--check', workflow)
        self.assertIn("github.event.workflow_run.event == 'pull_request'", workflow)
        sync = (ROOT / '.github/workflows/sync-github-stars.yml').read_text()
        self.assertIn('classify-github-stars.py', sync)
        self.assertIn('test_star_classifier.py', sync)


if __name__ == '__main__':
    unittest.main()
