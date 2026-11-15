"""Deterministic unsorted-star classifier: existing categories only, PR #14 fixtures."""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
import urllib.error
from io import StringIO
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
QUALITY_FIXTURES = {
    'agentgateway/agentgateway': 'category_07',
    'awesome-foss/awesome-sysadmin': 'category_15',
    'apple/coreai-models': 'category_06',
    'avelino/awesome-go': 'category_13',
    'pluja/awesome-privacy': 'category_18',
    'rust-lang/rust-clippy': 'category_14',
    'zachlatta/freeflow': 'category_09',
    'trymirai/uzu': 'category_07',
    'lukasz-madon/awesome-remote-job': 'category_20',
    'steven2358/awesome-generative-ai': 'category_26',
}
BANNED_REASONS = {
    'agentgateway/agentgateway': ('domain-specific 3d/game skill', 'blender/unreal/game-pipeline'),
    'awesome-foss/awesome-sysadmin': ('mail/inbox',),
    'apple/coreai-models': ('mobile/simulator',),
}


class StarClassifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'docs/stars/catalog.json').read_text())
        cls.features = json.loads(
            (ROOT / 'scripts/testdata/pr14_classify_fixtures.json').read_text()
        )
        cls.quality_features = json.loads(
            (ROOT / 'scripts/testdata/classify_quality_fixtures.json').read_text()
        )
        hold_names = set(PR14_FIXTURES) | set(QUALITY_FIXTURES)
        held = copy.deepcopy(cls.catalog)
        held['repositories'] = [
            repo for repo in held['repositories'] if repo['name'] not in hold_names
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

    def test_quality_fixtures_match_human_categories_without_canned_reasons(self):
        misses = []
        for name, expected in QUALITY_FIXTURES.items():
            decision = classify.classify_repo(self.index, name, self.quality_features[name])
            if decision['category'] != expected:
                misses.append((name, expected, decision['category'], decision['reason']))
            self.assertIn(decision['category'], self.category_ids)
            ranked = self.index.score(name, self.quality_features[name])
            top_reasons = next(row['reasons'] for row in ranked if row['category'] == decision['category'])
            rule_reasons = ' '.join(
                part for part in top_reasons if not part.startswith('nearest classified neighbour')
            ).casefold()
            for banned in BANNED_REASONS.get(name, ()):
                self.assertNotIn(banned, rule_reasons, msg=f'{name} rule reason leaked {banned!r}: {top_reasons}')
        self.assertEqual(misses, [], msg=f'quality fixture misses: {misses}')

    def test_hyphenated_awesome_needles_match_underscore_tokens(self):
        remote = self.quality_features['lukasz-madon/awesome-remote-job']
        title = classify.title_token_set('lukasz-madon/awesome-remote-job', remote)
        self.assertIn('remote_job', title)
        self.assertEqual(classify.awesome_subject('lukasz-madon/awesome-remote-job', title)[0], 'category_20')
        gen = self.quality_features['steven2358/awesome-generative-ai']
        self.assertEqual(
            classify.awesome_subject(
                'steven2358/awesome-generative-ai',
                classify.title_token_set('steven2358/awesome-generative-ai', gen),
            )[0],
            'category_26',
        )

    def test_audio_podcast_does_not_claim_video_output(self):
        features = {
            'description': 'Podcast recording and editing. Export MP3 audio.',
            'topics': ['podcast', 'audio'],
            'language': '',
            'readme': 'Record voice notes and export WAV or MP3.',
        }
        title = classify.title_token_set('owner/pod-audio', features)
        for rule in classify.DOMAIN_RULES:
            if rule['category'] == 'category_10':
                self.assertFalse(classify.rule_matches(rule, title), msg=rule['id'])
        decision = classify.classify_repo(self.index, 'owner/pod-audio', features)
        self.assertNotIn('output is video', decision['reason'])

    def test_domain_rules_ignore_readme_noise(self):
        title = classify.title_token_set('awesome-foss/awesome-sysadmin', self.quality_features['awesome-foss/awesome-sysadmin'])
        self.assertNotIn('mail', title)
        self.assertNotIn('inbox', title)
        self.assertTrue(classify.is_awesome_list('awesome-foss/awesome-sysadmin'))
        self.assertEqual(
            classify.awesome_subject('awesome-foss/awesome-sysadmin', title)[0],
            'category_15',
        )
        mail_rule = next(rule for rule in classify.DOMAIN_RULES if rule['id'] == 'mail')
        self.assertFalse(classify.rule_matches(mail_rule, title))
        query = set(classify.query_document('awesome-foss/awesome-sysadmin', self.quality_features['awesome-foss/awesome-sysadmin']))
        self.assertIn('mail', query)

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
            typesafe_api_key='',
        )
        self.assertEqual(len(decisions), 6)
        self.assertEqual({row['name']: row['category'] for row in records}, PR14_FIXTURES)
        catalog, conflicts = classify.insert_records(catalog, records)
        self.assertEqual(conflicts, [])
        assigned = {repo['name']: repo['category'] for repo in catalog['repositories'] if repo['name'] in PR14_FIXTURES}
        self.assertEqual(assigned, PR14_FIXTURES)
        self.assertTrue(all(repo.get('classification_source') for repo in catalog['repositories'] if repo['name'] in PR14_FIXTURES))
        body = classify.render_pr_body(decisions, source='test')
        self.assertIn('| Repository | Category | Confidence | Jev | Reason |', body)
        self.assertIn('## Jev second pass', body)
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
            typesafe_api_key='',
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
        decisions, records = classify.classify_unsorted(
            self.catalog, classified_only, token='', typesafe_api_key='',
        )
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
        self.assertIn('TYPESAFE_API_KEY: ${{ secrets.TYPESAFE_API_KEY }}', workflow)
        self.assertIn('Classify unsorted stars and refresh the rolling PR', workflow)
        classify_step = workflow.split('Classify unsorted stars and refresh the rolling PR', 1)[1]
        validate_step = workflow.split('Validate classifier and catalog', 1)[1].split('Classify unsorted stars', 1)[0]
        self.assertIn('TYPESAFE_API_KEY', classify_step.split('run:', 1)[0])
        self.assertNotIn('TYPESAFE_API_KEY', validate_step)
        sync = (ROOT / '.github/workflows/sync-github-stars.yml').read_text()
        self.assertIn('classify-github-stars.py', sync)
        self.assertIn('test_star_classifier.py', sync)
        self.assertNotIn('TYPESAFE_API_KEY', sync)
        tokscale = (ROOT / '.github/workflows/tokscale-embed-refresh.yml').read_text()
        self.assertNotIn('TYPESAFE_API_KEY', tokscale)


GENERIC_FEATURES = {
    'description': 'A starred repository.',
    'topics': [],
    'language': '',
    'readme': 'Hello world.',
}


def jev_payload(choice: str, noul: float) -> dict:
    return {
        'model': 'jev-latest',
        'answers': {
            'category': {
                'type': 'choice',
                'choice': choice,
                'confidence': 0.9,
                'probabilities': {choice: 0.9},
            },
            'confident': {'type': 'noul', 'noul': noul},
        },
        'usage': {'input_tokens': 1, 'output_tokens': 1},
    }


class StarJevGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'docs/stars/catalog.json').read_text())
        cls.category_names = {category['name'] for category in cls.catalog['categories']}
        cls.held = copy.deepcopy(cls.catalog)

    def _unsorted(self, name='owner/generic', features=None, node_id='UNSORTED-generic'):
        features = features or GENERIC_FEATURES
        snapshot = {'repositories': [{
            'id': node_id,
            'name': name,
            'url': f'https://github.com/{name}',
            'description': features.get('description') or '',
            'category': 'Unsorted / to classify',
            'category_id': stars.UNSORTED_ID,
            'archived': False,
            'fork': False,
        }]}
        return snapshot, {name: features}

    def _classify(self, *, api_key='test-key', jev_request=None, snapshot=None, features=None, name='owner/generic'):
        catalog = copy.deepcopy(self.held)
        if snapshot is None:
            snapshot, features_by_name = self._unsorted(name, features)
        else:
            features_by_name = features
        return classify.classify_unsorted(
            catalog,
            snapshot,
            features_by_name=features_by_name,
            token='',
            typesafe_api_key=api_key,
            jev_request=jev_request,
        )

    def test_jev_confident_accepts_and_clears_review(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        self.assertTrue(first['review_required'])
        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append((payload, api_key))
            return jev_payload('Games & 3D', 0.82)

        decisions, records = self._classify(jev_request=fake)
        self.assertEqual(len(calls), 1)
        payload, api_key = calls[0]
        self.assertEqual(api_key, 'test-key')
        self.assertEqual(payload['model'], classify.JEV_MODEL)
        self.assertEqual(set(payload['questions']), {'category', 'confident'})
        self.assertEqual(payload['questions']['category']['type'], 'choice')
        self.assertEqual(set(payload['questions']['category']['criteria']), self.category_names)
        self.assertEqual(payload['questions']['confident']['type'], 'noul')
        self.assertEqual(payload['questions']['confident']['instructions'], classify.JEV_CONFIDENT_INSTRUCTIONS)
        self.assertEqual(payload['state']['name'], 'owner/generic')
        self.assertIn('classifier_top3', payload['state'])
        self.assertEqual(len(payload['state']['classifier_top3']), 3)
        self.assertNotIn('test-key', json.dumps(payload))
        decision = decisions[0]
        self.assertEqual(decision['category_name'], 'Games & 3D')
        self.assertEqual(decision['category'], 'category_23')
        self.assertFalse(decision['review_required'])
        self.assertEqual(decision['confidence'], 'high')
        self.assertEqual(decision['jev'], 'decided')
        self.assertEqual(decision['review_candidates'], [])
        self.assertTrue(decision['classification_source'].startswith('jev:'))
        self.assertIn('classifier', decision['reason'])
        self.assertIn('jev', decision['reason'])
        self.assertEqual(records[0]['category'], 'category_23')
        self.assertFalse(records[0]['review_required'])
        self.assertNotIn('review_candidates', records[0])
        self.assertTrue(records[0]['classification_source'].startswith('jev:'))
        body = classify.render_pr_body(decisions, source='test')
        self.assertIn('| decided |', body)
        self.assertIn('Jev decided (review cleared): 1', body)
        self.assertIn('Still need review: 0', body)

    def test_jev_low_confidence_keeps_classifier_pick(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append(payload)
            return jev_payload('Games & 3D', 0.4)

        decisions, records = self._classify(jev_request=fake)
        self.assertEqual(len(calls), 1)
        decision = decisions[0]
        self.assertEqual(decision['category'], first['category'])
        self.assertEqual(decision['category_name'], first['category_name'])
        self.assertTrue(decision['review_required'])
        self.assertEqual(decision['jev'], 'review')
        self.assertEqual(records[0]['category'], first['category'])
        self.assertTrue(records[0]['review_required'])
        self.assertEqual(records[0]['review_candidates'], first['review_candidates'])
        self.assertFalse(records[0]['classification_source'].startswith('jev:'))
        self.assertIn('keeping classifier pick', decision['reason'])
        body = classify.render_pr_body(decisions, source='test')
        self.assertIn('| review |', body)
        self.assertIn('Still need review: 1', body)

    def test_jev_unknown_category_rejected(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )

        def fake(payload, api_key, **kwargs):
            return jev_payload('Brand New Bucket', 0.99)

        decisions, records = self._classify(jev_request=fake)
        decision = decisions[0]
        self.assertEqual(decision['category'], first['category'])
        self.assertTrue(decision['review_required'])
        self.assertEqual(decision['jev'], 'review')
        self.assertIn('Brand New Bucket', decision['reason'])
        self.assertEqual(records[0]['category'], first['category'])
        self.assertTrue(records[0]['review_required'])
        self.assertNotEqual(records[0]['category'], 'category_99')
        self.assertEqual(len(self.held['categories']), len(self.catalog['categories']))

    def test_jev_missing_key_falls_back(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )

        def boom(*args, **kwargs):
            self.fail('Jev must not be called when the API key is missing')

        with patch.dict('os.environ', {'TYPESAFE_API_KEY': ''}, clear=False):
            decisions, records = self._classify(api_key='', jev_request=boom)
        decision = decisions[0]
        self.assertEqual(decision['category'], first['category'])
        self.assertTrue(decision['review_required'])
        self.assertEqual(decision['jev'], 'review')
        self.assertEqual(records[0]['category'], first['category'])
        self.assertTrue(records[0]['review_required'])
        self.assertFalse(records[0]['classification_source'].startswith('jev:'))

    def test_jev_api_error_falls_back(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )

        def explode(payload, api_key, **kwargs):
            raise urllib.error.HTTPError(classify.JEV_URL, 503, 'unavailable', hdrs=None, fp=None)

        stderr = StringIO()
        with patch('sys.stderr', stderr):
            decisions, records = self._classify(jev_request=explode)
        self.assertNotIn('test-key', stderr.getvalue())
        decision = decisions[0]
        self.assertEqual(decision['category'], first['category'])
        self.assertTrue(decision['review_required'])
        self.assertEqual(decision['jev'], 'review')
        self.assertEqual(records[0]['category'], first['category'])
        self.assertTrue(records[0]['review_required'])
        self.assertFalse(records[0]['classification_source'].startswith('jev:'))

        def empty(payload, api_key, **kwargs):
            return None

        decisions, records = self._classify(jev_request=empty)
        self.assertEqual(decisions[0]['category'], first['category'])
        self.assertTrue(decisions[0]['review_required'])

        def malformed(payload, api_key, **kwargs):
            return {'answers': {'category': {'type': 'choice'}, 'confident': {'type': 'noul'}}}

        decisions, records = self._classify(jev_request=malformed)
        self.assertEqual(decisions[0]['category'], first['category'])
        self.assertTrue(decisions[0]['review_required'])

    def test_request_jev_posts_systemone_and_swallows_http_errors(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(jev_payload('Games & 3D', 0.9)).encode()

        def fake_open(request, timeout=None):
            captured['url'] = request.full_url
            captured['timeout'] = timeout
            captured['method'] = request.get_method()
            captured['body'] = json.loads(request.data.decode())
            captured['authorization'] = request.get_header('Authorization')
            return FakeResponse()

        with patch('urllib.request.urlopen', side_effect=fake_open):
            result = classify.request_jev(
                {'state': {'name': 'owner/x'}, 'model': 'jev-latest', 'questions': {'category': {'type': 'choice'}}},
                'secret-key-value',
            )
        self.assertEqual(captured['url'], classify.JEV_URL)
        self.assertEqual(captured['method'], 'POST')
        self.assertEqual(captured['timeout'], classify.JEV_TIMEOUT)
        self.assertEqual(captured['authorization'], 'Bearer secret-key-value')
        self.assertEqual(captured['body']['model'], 'jev-latest')
        self.assertEqual(result['answers']['category']['choice'], 'Games & 3D')

        def boom(request, timeout=None):
            raise urllib.error.HTTPError(classify.JEV_URL, 500, 'err', hdrs=None, fp=None)

        stderr = StringIO()
        with patch('urllib.request.urlopen', side_effect=boom), patch('sys.stderr', stderr):
            self.assertIsNone(classify.request_jev({'state': {}, 'model': 'jev-latest', 'questions': {'q': {}}}, 'secret-key-value'))
        self.assertNotIn('secret-key-value', stderr.getvalue())
        self.assertIsNone(classify.request_jev({'state': {}}, ''))

    def test_jev_skips_high_confidence_first_pass(self):
        features = json.loads((ROOT / 'scripts/testdata/pr14_classify_fixtures.json').read_text())
        name = 'arjun988/blender-skills'
        first = classify.classify_repo(classify.CatalogIndex(self.held), name, features[name])
        if first['review_required']:
            self.skipTest('blender-skills fixture is low-confidence in this catalog')

        def boom(*args, **kwargs):
            self.fail('high-confidence first-pass rows must not call Jev')

        snapshot, features_by_name = self._unsorted(name, features[name], node_id='UNSORTED-blender')
        decisions, records = classify.classify_unsorted(
            copy.deepcopy(self.held),
            snapshot,
            features_by_name=features_by_name,
            token='',
            typesafe_api_key='test-key',
            jev_request=boom,
        )
        self.assertFalse(decisions[0]['review_required'])
        self.assertNotEqual(decisions[0].get('jev'), 'decided')
        self.assertEqual(records[0]['category'], first['category'])


if __name__ == '__main__':
    unittest.main()
