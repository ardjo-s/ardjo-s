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
AUDIT_FIXTURES = {
    'NVIDIA-AI-Blueprints/video-search-and-summarization': 'category_10',
    'assistant-ui/assistant-ui': 'category_11',
    'nexu-io/html-anything': 'category_10',
    'datawhalechina/zero-to-sglang': 'category_07',
    'typesafe-ai/skills': 'category_03',
    'huggingface/skills': 'category_03',
    'ashishps1/awesome-system-design-resources': 'category_15',
    '1Password/for-open-source': 'category_18',
    'OpenCoworkAI/open-codesign': 'category_11',
    'agentes-chat/agentes-chat': 'category_02',
    'blader/humanizer': 'category_03',
    'dontriskit/awesome-ai-software-engineering': 'category_03',
    'hjunhuh/awesome-rust': 'category_13',
    'mvanhorn/printing-press-library': 'category_04',
    'tuan3w/linearapp_clone': 'category_11',
    'ooolzhas/annotatekit': 'category_12',
    '21st-dev/21st-sdk-examples': 'category_26',
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
        cls.audit_features = json.loads(
            (ROOT / 'scripts/testdata/classify_audit_fixtures.json').read_text()
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

    def test_generic_agent_skills_pack_goes_to_agent_methods(self):
        features = self.audit_features['owner/generic-agent-skills']
        title = classify.title_token_set('owner/generic-agent-skills', features)
        rule = next(item for item in classify.DOMAIN_RULES if item['id'] == 'generic-agent-skills')
        self.assertTrue(classify.rule_matches(rule, title))
        decision = classify.classify_repo(self.index, 'owner/generic-agent-skills', features)
        self.assertEqual(decision['category'], 'category_03')
        self.assertIn('generic agent skills pack', decision['reason'])

    def test_generic_agent_skills_rule_yields_to_domain_skill(self):
        features = self.features['arjun988/blender-skills']
        title = classify.title_token_set('arjun988/blender-skills', features)
        generic = next(item for item in classify.DOMAIN_RULES if item['id'] == 'generic-agent-skills')
        self.assertFalse(classify.rule_matches(generic, title))
        decision = classify.classify_repo(self.index, 'arjun988/blender-skills', features)
        self.assertEqual(decision['category'], 'category_23')
        self.assertNotIn('generic agent skills pack', decision['reason'])

    def test_jev_prompt_mentions_generic_agent_skills_rule(self):
        self.assertIn(
            'Generic agent skills packs not tied to a specific domain go to Agent Methods, Skills & Configuration.',
            classify.JEV_CATEGORY_INSTRUCTIONS,
        )
        self.assertIn(
            'Generic agent skills packs not tied to a specific domain go to Agent Methods, Skills & Configuration.',
            classify.JEV_DUEL_INSTRUCTIONS,
        )
        questions = classify.jev_questions(self.catalog['categories'])
        self.assertIn(
            'Generic agent skills packs not tied to a specific domain',
            questions['category']['instructions'],
        )

    def test_audit_corrections_match_human_categories(self):
        held = copy.deepcopy(self.catalog)
        held['repositories'] = [
            repo for repo in held['repositories'] if repo['name'] not in AUDIT_FIXTURES
        ]
        index = classify.CatalogIndex(held)
        misses = []
        for name, expected in AUDIT_FIXTURES.items():
            decision = classify.classify_repo(index, name, self.audit_features[name])
            if decision['category'] != expected:
                misses.append((name, expected, decision['category'], decision['reason']))
        self.assertEqual(misses, [], msg=f'audit fixture misses: {misses}')

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
        published = {row['name']: row['category'] for row in records}
        doubtful = [row for row in decisions if row['review_required']]
        high = [row for row in decisions if not row['review_required']]
        self.assertEqual(set(published), set(PR14_FIXTURES))
        self.assertEqual(len(records), 6)
        for row in decisions:
            self.assertEqual(row['category'], PR14_FIXTURES[row['name']])
            self.assertIn(row['category'], self.category_ids)
        for record in records:
            self.assertIn(record.get('classification_rounds'), {1, 2, 3})
            if record['review_required']:
                self.assertEqual(record['classification_confidence'], 'low')
                self.assertTrue(record.get('review_candidates'))
            else:
                self.assertEqual(record.get('classification_confidence'), 'high')
        catalog, conflicts = classify.insert_records(catalog, records)
        self.assertEqual(conflicts, [])
        assigned = {repo['name']: repo['category'] for repo in catalog['repositories'] if repo['name'] in PR14_FIXTURES}
        self.assertEqual(assigned, published)
        self.assertTrue(all(repo.get('classification_source') for repo in catalog['repositories'] if repo['name'] in published))
        body = classify.render_pr_body(decisions, source='test')
        self.assertIn('| Repository | Category | Confidence | Rounds | Jev | Reason |', body)
        self.assertIn('## Enrichment loop', body)
        self.assertIn('arjun988/blender-skills', body)
        self.assertNotIn('enable auto-merge', body.casefold())
        self.assertNotIn('## À trancher', body)
        if doubtful:
            self.assertIn('## Low-confidence rows', body)
            for row in doubtful:
                self.assertIn(row['name'], body)
                self.assertIn(row['category_name'], body)
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
            notes = classify.unsorted_notes(decisions)
            stars.export(live, catalog, output, readme, unsorted_notes=notes)
            exported = json.loads((output / 'stars.json').read_text())
            got = {
                row['name']: row['category_id']
                for row in exported['repositories']
                if row['name'] in PR14_FIXTURES
            }
            for name in published:
                self.assertEqual(got[name], published[name])
            unsorted = (output / 'unsorted.md').read_text()
            self.assertTrue((output / 'unsorted.md').exists())
            self.assertNotIn('à trancher', unsorted)
            for name in PR14_FIXTURES:
                self.assertNotIn(name, unsorted)
                self.assertNotEqual(got[name], stars.UNSORTED_ID)
            self.assertIn('**0 repositories.**', unsorted)
            for row in doubtful:
                page = (output / f"{next(c['slug'] for c in catalog['categories'] if c['id'] == row['category'])}.md").read_text()
                self.assertIn(row['name'], page)
                self.assertIn('low confidence', page)
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

    def test_insert_records_never_overwrites_a_human_label(self):
        catalog = copy.deepcopy(self.held_catalog)
        human = copy.deepcopy(catalog['repositories'][0])
        human['classification_source'] = 'human:2026-11-15'
        original_category = human['category']
        catalog['repositories'][0] = human
        auto = {
            'id': human['id'],
            'name': human['name'],
            'url': human['url'],
            'description': 'auto should not win',
            'category': 'category_23' if original_category != 'category_23' else 'category_01',
            'purpose': 'overwrite attempt',
            'keywords': [],
            'review_required': True,
            'classification_confidence': 'low',
            'evidence_quote': 'x',
            'evidence_status': 'description_only',
            'archived': False,
            'fork': False,
            'classification_source': 'star-catalog-nn-v2',
        }
        before = len(catalog['repositories'])
        catalog, conflicts = classify.insert_records(catalog, [auto])
        self.assertEqual(conflicts, [])
        self.assertEqual(len(catalog['repositories']), before)
        kept = next(repo for repo in catalog['repositories'] if repo['id'] == human['id'])
        self.assertEqual(kept['category'], original_category)
        self.assertEqual(kept['classification_source'], 'human:2026-11-15')
        self.assertNotEqual(kept.get('purpose'), 'overwrite attempt')

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

    def test_classifier_workflow_merges_only_the_rolling_pr_with_guards(self):
        workflow = (ROOT / '.github/workflows/classify-github-stars.yml').read_text()
        self.assertIn('auto/classify-stars', workflow)
        self.assertIn('--head auto/classify-stars', workflow)
        self.assertNotIn('${GITHUB_REPOSITORY_OWNER}:auto/classify-stars', workflow)
        self.assertIn('workflow_run', workflow)
        self.assertIn('GH_STARS_TOKEN', workflow)
        self.assertIn('docs/stars/unsorted.md', workflow)
        self.assertNotIn('enable auto-merge', workflow.casefold())
        self.assertNotIn('gh pr merge --auto', workflow)
        self.assertNotIn('enablePullRequestAutoMerge', workflow)
        self.assertIn('gh pr merge', workflow)
        self.assertIn('--squash', workflow)
        self.assertIn('--match-head-commit', workflow)
        self.assertIn('head is', workflow)
        self.assertIn('auto/classify-stars', workflow)
        self.assertIn("git diff --name-only", workflow)
        self.assertIn(r'^(README\.md|docs/stars/.+)$', workflow)
        self.assertNotIn('à trancher rows were written into catalog.json', workflow)
        self.assertIn('catalog rows missing an existing category', workflow)
        self.assertGreaterEqual(workflow.count("python3 -m unittest discover -s scripts -p 'test_*.py'"), 3)
        self.assertGreaterEqual(workflow.count('--check'), 3)
        self.assertIn('Validate and squash-merge the rolling PR', workflow)
        merge_step = workflow.split('Validate and squash-merge the rolling PR', 1)[1]
        self.assertIn('--check', merge_step)
        self.assertIn("python3 -m unittest discover -s scripts -p 'test_*.py'", merge_step)
        self.assertIn('gh pr merge', merge_step)
        self.assertIn('--match-head-commit', merge_step)
        self.assertIn("github.event.workflow_run.event != 'pull_request'", workflow)
        self.assertIn('TYPESAFE_API_KEY: ${{ secrets.TYPESAFE_API_KEY }}', workflow)
        self.assertIn('Classify unsorted stars and refresh the rolling PR', workflow)
        self.assertIn('actions/cache@v4', workflow)
        self.assertIn('docs/stars/.classify-jev-cache.json', workflow)
        self.assertIn('classify-jev-cache-v1', workflow)
        gitignore = (ROOT / '.gitignore').read_text()
        self.assertIn('docs/stars/.classify-jev-cache.json', gitignore)
        self.assertNotIn('Only à trancher rows remain', workflow)
        self.assertIn('No unsorted public stars; nothing to propose.', workflow)
        self.assertIn('cancel-in-progress: false', workflow)
        classify_step = workflow.split('Classify unsorted stars and refresh the rolling PR', 1)[1]
        validate_step = workflow.split('Validate classifier and catalog', 1)[1].split('Classify unsorted stars', 1)[0]
        self.assertIn('TYPESAFE_API_KEY', classify_step.split('run:', 1)[0])
        self.assertNotIn('TYPESAFE_API_KEY', validate_step)
        body = classify.render_pr_body([], source='test')
        self.assertNotIn('enable auto-merge', body.casefold())
        self.assertIn('squash-merges this rolling PR', body)
        sync = (ROOT / '.github/workflows/sync-github-stars.yml').read_text()
        self.assertIn('classify-github-stars.py', sync)
        self.assertIn('test_star_classifier.py', sync)
        self.assertNotIn('TYPESAFE_API_KEY', sync)
        self.assertIn('*/10 * * * *', sync)
        self.assertIn('concurrency:', sync)
        self.assertIn('cancel-in-progress: false', sync)
        self.assertIn('GitHub stars export unchanged.', sync)
        self.assertIn("if: github.event_name == 'pull_request'", sync)
        tokscale = (ROOT / '.github/workflows/tokscale-embed-refresh.yml').read_text()
        self.assertNotIn('TYPESAFE_API_KEY', tokscale)


GENERIC_FEATURES = {
    'description': 'A starred repository.',
    'topics': [],
    'language': '',
    'readme': 'Hello world.',
}


def jev_choice_payload(choice: str) -> dict:
    return {
        'model': 'jev-latest',
        'answers': {
            'category': {
                'type': 'choice',
                'choice': choice,
                'confidence': 0.9,
                'probabilities': {choice: 0.9},
            },
        },
        'usage': {'input_tokens': 1, 'output_tokens': 1},
    }


def jev_noul_payload(noul: float) -> dict:
    return {
        'model': 'jev-latest',
        'answers': {
            'confident': {'type': 'noul', 'noul': noul},
        },
        'usage': {'input_tokens': 1, 'output_tokens': 1},
    }


def jev_payload(choice: str, noul: float) -> dict:
    payload = jev_choice_payload(choice)
    payload['answers'].update(jev_noul_payload(noul)['answers'])
    return payload


def jev_reply(payload: dict, choice: str, noul: float) -> dict:
    questions = payload['questions']
    if 'category' in questions:
        return jev_choice_payload(choice)
    if 'confident' in questions:
        return jev_noul_payload(noul)
    raise AssertionError(f'unexpected questions: {sorted(questions)}')


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

    def test_jev_choice_and_noul_are_separate_question_sets(self):
        cats = self.held['categories'][:2]
        self.assertEqual(set(classify.jev_questions(cats)), {'category'})
        noul = classify.jev_confident_questions('Games & 3D', 'Blender, Unreal, Godot.')
        self.assertEqual(set(noul), {'confident'})
        self.assertIn('Games & 3D', noul['confident']['criteria']['true'])
        self.assertIn('Games & 3D', noul['confident']['criteria']['false'])
        split = classify.parse_jev_choice(jev_choice_payload('Games & 3D'))
        self.assertEqual(split, 'Games & 3D')
        self.assertEqual(classify.parse_jev_noul(jev_noul_payload(0.82)), 0.82)
        self.assertIsNone(classify.parse_jev_noul(jev_choice_payload('Games & 3D')))
        self.assertIsNone(classify.parse_jev_choice(jev_noul_payload(0.82)))

    def test_jev_confident_accepts_and_clears_review(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        self.assertTrue(first['review_required'])
        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append((payload, api_key))
            return jev_reply(payload, 'Games & 3D', 0.82)

        decisions, records = self._classify(jev_request=fake)
        self.assertEqual(len(calls), 2)
        choice_payload, api_key = calls[0]
        noul_payload, noul_key = calls[1]
        self.assertEqual(api_key, 'test-key')
        self.assertEqual(noul_key, 'test-key')
        self.assertEqual(choice_payload['model'], classify.JEV_MODEL)
        self.assertEqual(set(choice_payload['questions']), {'category'})
        self.assertEqual(choice_payload['questions']['category']['type'], 'choice')
        self.assertEqual(set(choice_payload['questions']['category']['criteria']), self.category_names)
        self.assertEqual(set(noul_payload['questions']), {'confident'})
        self.assertEqual(noul_payload['questions']['confident']['type'], 'noul')
        self.assertEqual(noul_payload['questions']['confident']['instructions'], classify.JEV_CONFIDENT_INSTRUCTIONS)
        self.assertIn('Games & 3D', noul_payload['questions']['confident']['criteria']['true'])
        self.assertEqual(noul_payload['state']['chosen_category'], 'Games & 3D')
        self.assertEqual(choice_payload['state']['name'], 'owner/generic')
        self.assertIn('classifier_top3', choice_payload['state'])
        self.assertEqual(len(choice_payload['state']['classifier_top3']), 3)
        self.assertIn('human_examples', choice_payload['state'])
        self.assertNotIn('test-key', json.dumps(choice_payload))
        self.assertNotIn('test-key', json.dumps(noul_payload))
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
        self.assertEqual(decision['classification_rounds'], 1)
        self.assertEqual(records[0]['classification_rounds'], 1)
        self.assertEqual(records[0]['classification_confidence'], 'high')
        body = classify.render_pr_body(decisions, source='test')
        self.assertIn('| decided |', body)
        self.assertIn('Jev decided (review cleared): 1', body)
        self.assertIn('Published with low confidence (needs review): 0', body)

    def test_jev_agreement_accepts_matching_top1(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append(payload)
            return jev_reply(payload, first['category_name'], 0.65)

        decisions, records = self._classify(jev_request=fake)
        self.assertEqual(len(calls), 2)
        self.assertEqual(set(calls[0]['questions']), {'category'})
        self.assertEqual(len(calls[0]['questions']['category']['criteria']), 26)
        self.assertEqual(set(calls[1]['questions']), {'confident'})
        self.assertEqual(calls[1]['state']['chosen_category'], first['category_name'])
        decision = decisions[0]
        self.assertFalse(decision['review_required'])
        self.assertEqual(decision['category'], first['category'])
        self.assertEqual(decision['jev'], 'decided')
        self.assertEqual(records[0]['category'], first['category'])
        self.assertEqual(decision['classification_rounds'], 1)
        self.assertIn('agreed', decision['reason'])

    def test_jev_finalists_duel_accepts(self):
        features = {
            **GENERIC_FEATURES,
            'topics': ['example', 'demo'],
            'readme': ('Hello world notes. ' * 400),
        }
        first = classify.classify_repo(
            classify.CatalogIndex(self.held),
            'owner/generic',
            classify.metadata_features(features),
        )
        self.assertTrue(first['review_required'])
        other = next(
            name for name in self.category_names
            if name not in first['review_candidate_names']
        )
        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append(payload)
            questions = payload['questions']
            if 'category' in questions:
                if len(questions['category']['criteria']) == 2:
                    return jev_choice_payload(first['review_candidate_names'][1])
                return jev_choice_payload(other)
            chosen = payload['state'].get('chosen_category')
            if chosen == other:
                return jev_noul_payload(0.70)
            return jev_noul_payload(0.74)

        decisions, records = self._classify(jev_request=fake, features=features)
        self.assertEqual(len(calls), 4)
        self.assertEqual(set(calls[0]['questions']), {'category'})
        self.assertEqual(set(calls[1]['questions']), {'confident'})
        self.assertEqual(calls[1]['state']['chosen_category'], other)
        duel_choice = calls[2]
        duel_noul = calls[3]
        self.assertEqual(set(duel_choice['questions']['category']['criteria']), set(first['review_candidate_names']))
        # Round 1 only sends name and description, so the duel has no README yet.
        self.assertEqual(duel_choice['state']['readme_excerpt'], '')
        self.assertEqual(duel_choice['state']['topics'], [])
        self.assertIn('human_examples', duel_choice['state'])
        self.assertEqual(set(duel_noul['questions']), {'confident'})
        self.assertEqual(duel_noul['state']['chosen_category'], first['review_candidate_names'][1])
        self.assertIn(first['review_candidate_names'][1], duel_noul['questions']['confident']['criteria']['true'])
        decision = decisions[0]
        self.assertFalse(decision['review_required'])
        self.assertEqual(decision['category_name'], first['review_candidate_names'][1])
        self.assertEqual(decision['jev'], 'decided')
        self.assertIn('duel', decision['reason'])
        self.assertEqual(records[0]['category'], first['review_candidates'][1])
        self.assertEqual(decision['classification_rounds'], 1)

    def test_jev_finalists_duel_reject_publishes_best_available(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append(payload)
            return jev_reply(payload, first['review_candidate_names'][0], 0.4)

        decisions, records = self._classify(jev_request=fake)
        self.assertGreaterEqual(len(calls), 4)
        self.assertEqual(set(calls[0]['questions']), {'category'})
        self.assertEqual(set(calls[1]['questions']), {'confident'})
        decision = decisions[0]
        self.assertTrue(decision['review_required'])
        self.assertEqual(decision['confidence'], 'low')
        self.assertEqual(decision['classification_confidence'], 'low')
        self.assertEqual(decision['classification_rounds'], 3)
        self.assertEqual(decision['jev'], 'review')
        self.assertEqual(len(records), 1)
        self.assertEqual(decision['category_name'], first['review_candidate_names'][0])
        self.assertEqual(records[0]['category'], first['review_candidates'][0])
        self.assertEqual(records[0]['classification_confidence'], 'low')
        self.assertEqual(records[0]['classification_rounds'], 3)
        self.assertTrue(records[0]['review_required'])
        self.assertIn('published at low confidence', decision['reason'])
        self.assertNotIn('à trancher', decision['reason'])
        body = classify.render_pr_body(decisions, source='test')
        self.assertIn('## Low-confidence rows', body)
        self.assertIn('| needs review |', body)
        self.assertIn('Published with low confidence (needs review): 1', body)
        self.assertNotIn('## À trancher', body)
        self.assertIn(decision['category_name'], body)
        self.assertIn('| 3 |', body)

    def test_jev_unknown_category_rejected(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )

        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append(payload)
            return jev_reply(payload, 'Brand New Bucket', 0.99)

        decisions, records = self._classify(jev_request=fake)
        decision = decisions[0]
        self.assertEqual(decision['category'], first['category'])
        self.assertTrue(decision['review_required'])
        self.assertEqual(decision['confidence'], 'low')
        self.assertEqual(decision['jev'], 'review')
        self.assertIn('Brand New Bucket', decision['reason'])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['category'], first['category'])
        self.assertEqual(records[0]['classification_confidence'], 'low')
        self.assertEqual(decision['classification_rounds'], 3)
        self.assertEqual(len(self.held['categories']), len(self.catalog['categories']))
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(all('category' in payload['questions'] for payload in calls))
        self.assertFalse(any('confident' in payload['questions'] for payload in calls))

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
        self.assertEqual(decision['confidence'], 'low')
        self.assertEqual(decision['jev'], 'review')
        self.assertEqual(decision['classification_rounds'], 3)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['category'], first['category'])
        self.assertEqual(records[0]['classification_confidence'], 'low')
        self.assertEqual(records[0]['classification_rounds'], 3)

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
        self.assertEqual(decision['confidence'], 'low')
        self.assertEqual(decision['jev'], 'review')
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['category'], first['category'])
        self.assertEqual(records[0]['classification_confidence'], 'low')

        def empty(payload, api_key, **kwargs):
            return None

        decisions, records = self._classify(jev_request=empty)
        self.assertEqual(decisions[0]['category'], first['category'])
        self.assertTrue(decisions[0]['review_required'])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['classification_confidence'], 'low')

        def malformed(payload, api_key, **kwargs):
            return {'answers': {'category': {'type': 'choice'}, 'confident': {'type': 'noul'}}}

        decisions, records = self._classify(jev_request=malformed)
        self.assertEqual(decisions[0]['category'], first['category'])
        self.assertTrue(decisions[0]['review_required'])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['classification_confidence'], 'low')

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

    def test_human_rows_weigh_more_than_bot_rows(self):
        catalog = copy.deepcopy(self.held)
        catalog['repositories'] = [
            {
                'id': 'BOT-UI',
                'name': 'bot/shared-tokens',
                'url': 'https://github.com/bot/shared-tokens',
                'description': 'sharedtoken blender rig for games and 3D scenes',
                'category': 'category_11',
                'purpose': 'bot labelled UI',
                'keywords': ['sharedtoken', 'blender', 'games'],
                'review_required': False,
                'evidence_quote': 'sharedtoken blender rig',
                'evidence_status': 'description_only',
                'archived': False,
                'fork': False,
                'classification_source': 'https://github.com/ardjo-s/ardjo-s/actions/runs/1',
            },
            {
                'id': 'HUMAN-3D',
                'name': 'human/shared-tokens',
                'url': 'https://github.com/human/shared-tokens',
                'description': 'sharedtoken blender rig for games and 3D scenes',
                'category': 'category_23',
                'purpose': 'human labelled games',
                'keywords': ['sharedtoken', 'blender', 'games'],
                'review_required': False,
                'evidence_quote': 'sharedtoken blender rig',
                'evidence_status': 'description_only',
                'archived': False,
                'fork': False,
                'classification_source': 'human:2026-11-15',
            },
            {
                'id': 'HUMAN-FIX',
                'name': 'human/corrected-clip',
                'url': 'https://github.com/human/corrected-clip',
                'description': 'unrelated calendar notes app',
                'category': 'category_10',
                'purpose': 'corrected away from the bot pick',
                'keywords': ['notes'],
                'review_required': False,
                'evidence_quote': 'calendar notes',
                'evidence_status': 'description_only',
                'archived': False,
                'fork': False,
                'classification_source': 'human:2026-11-15',
                'review_candidates': ['category_03', 'category_10'],
            },
        ]
        self.assertTrue(classify.is_human_label(catalog['repositories'][1]))
        self.assertTrue(classify.is_human_correction(catalog['repositories'][2]))
        self.assertGreater(
            classify.member_weight(catalog['repositories'][1]),
            classify.member_weight(catalog['repositories'][0]),
        )
        self.assertGreater(
            classify.member_weight(catalog['repositories'][2]),
            classify.member_weight(catalog['repositories'][1]),
        )
        index = classify.CatalogIndex(catalog)
        features = {
            'description': 'sharedtoken blender rig for games and 3D scenes',
            'topics': ['blender', 'games'],
            'language': '',
            'readme': 'sharedtoken blender rig',
        }
        bot_catalog = copy.deepcopy(catalog)
        bot_catalog['repositories'][1]['classification_source'] = 'https://github.com/x/actions/runs/1'
        bot_index = classify.CatalogIndex(bot_catalog)
        score = lambda idx, cid: next(row['score'] for row in idx.score('owner/sharedtoken-rig', features) if row['category'] == cid)
        self.assertGreater(score(index, 'category_23'), score(bot_index, 'category_23'))
        examples = index.human_examples('owner/sharedtoken-rig', features, k=3)
        self.assertTrue(examples)
        self.assertTrue(any(row['name'] == 'human/shared-tokens' for row in examples))
        self.assertTrue(any(row['corrected'] for row in examples))

    def test_low_confidence_rows_are_published_and_tagged(self):
        catalog = copy.deepcopy(self.held)
        snapshot, features_by_name = self._unsorted()
        decisions, records = classify.classify_unsorted(
            catalog,
            snapshot,
            features_by_name=features_by_name,
            token='',
            typesafe_api_key='',
        )
        self.assertEqual(len(records), 1)
        self.assertTrue(decisions[0]['review_required'])
        self.assertEqual(decisions[0]['confidence'], 'low')
        self.assertEqual(records[0]['classification_confidence'], 'low')
        self.assertEqual(records[0]['classification_rounds'], 3)
        self.assertEqual(records[0]['category'], decisions[0]['category'])
        self.assertIn(records[0]['category'], {c['id'] for c in catalog['categories']})
        catalog, conflicts = classify.insert_records(catalog, records)
        self.assertEqual(conflicts, [])
        stored = next(repo for repo in catalog['repositories'] if repo['name'] == 'owner/generic')
        self.assertEqual(stored['classification_confidence'], 'low')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'docs/stars'
            output.mkdir(parents=True)
            readme = root / 'README.md'
            readme.write_text('profile\n## ⭐ Starred Repos\nold\n')
            live = [{
                'id': records[0]['id'],
                'name': 'owner/generic',
                'url': 'https://github.com/owner/generic',
                'description': 'A starred repository.',
                'archived': False,
                'fork': False,
            }]
            classify.write_catalog(output / 'catalog.json', catalog)
            stars.export(live, catalog, output, readme)
            unsorted = (output / 'unsorted.md').read_text()
            self.assertIn('**0 repositories.**', unsorted)
            self.assertNotIn('owner/generic', unsorted)
            self.assertNotIn('À trancher', unsorted)
            exported = json.loads((output / 'stars.json').read_text())
            row = next(item for item in exported['repositories'] if item['name'] == 'owner/generic')
            self.assertEqual(row['category_id'], decisions[0]['category'])
            self.assertEqual(row['classification_confidence'], 'low')
            slug = next(c['slug'] for c in catalog['categories'] if c['id'] == decisions[0]['category'])
            page = (output / f'{slug}.md').read_text()
            self.assertIn('owner/generic', page)
            self.assertIn('low confidence', page)
            profile = readme.read_text()
            self.assertIn('1 public repositories', profile)
            self.assertNotIn('unsorted', profile)
            stars.check_committed_export(output, readme, output / 'catalog.json')
        body = classify.render_pr_body(decisions, source='test')
        self.assertIn('## Low-confidence rows', body)
        self.assertIn('owner/generic', body)
        self.assertIn(decisions[0]['category_name'], body)
        self.assertNotIn('## À trancher', body)

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
        self.assertEqual(decisions[0]['classification_rounds'], 1)


class StarEnrichmentLoopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / 'docs/stars/catalog.json').read_text())
        cls.held = copy.deepcopy(cls.catalog)

    def _run(self, *, features=None, jev_request=None, api_key='test-key', cache_path=None):
        features = features or GENERIC_FEATURES
        snapshot = {'repositories': [{
            'id': 'UNSORTED-generic',
            'name': 'owner/generic',
            'url': 'https://github.com/owner/generic',
            'description': features.get('description') or '',
            'category': 'Unsorted / to classify',
            'category_id': stars.UNSORTED_ID,
            'archived': False,
            'fork': False,
        }]}
        return classify.classify_unsorted(
            copy.deepcopy(self.held),
            snapshot,
            features_by_name={'owner/generic': features},
            token='',
            typesafe_api_key=api_key,
            jev_request=jev_request,
            jev_cache_path=cache_path,
        )

    def test_round_one_metadata_omits_readme_and_topics(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', classify.metadata_features(GENERIC_FEATURES),
        )
        full = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        self.assertTrue(first['review_required'])
        stripped = classify.metadata_features(GENERIC_FEATURES)
        self.assertEqual(stripped['readme'], '')
        self.assertEqual(stripped['topics'], [])
        self.assertEqual(stripped['language'], '')
        self.assertEqual(stripped['homepage'], '')
        enriched = classify.enriched_features({
            **GENERIC_FEATURES,
            'homepage': 'https://example.com',
            'readme': 'X' * 8000,
            'topics': ['search'],
            'language': 'Python',
        })
        self.assertEqual(enriched['homepage'], 'https://example.com')
        self.assertEqual(enriched['topics'], ['search'])
        self.assertEqual(enriched['language'], 'Python')
        self.assertEqual(len(enriched['readme']), classify.ENRICHED_README_CHARS)
        self.assertLessEqual(len(enriched['readme']), len('X' * 8000))
        self.assertIn(full['category'], {c['id'] for c in self.held['categories']})

    def test_round_two_accepts_without_running_votes(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append(payload)
            # Reject every round-1 gate; accept on later, richer states.
            excerpt = (payload.get('state') or {}).get('readme_excerpt') or ''
            vote = (payload.get('state') or {}).get('vote')
            if vote or not excerpt:
                return jev_reply(payload, first['category_name'], 0.4)
            return jev_reply(payload, first['category_name'], 0.9)

        decisions, records = self._run(jev_request=fake)
        decision = decisions[0]
        self.assertFalse(decision['review_required'])
        self.assertEqual(decision['classification_rounds'], 2)
        self.assertEqual(decision['classification_confidence'], 'high')
        self.assertEqual(records[0]['classification_rounds'], 2)
        self.assertFalse(any((payload.get('state') or {}).get('vote') for payload in calls))

    def test_round_three_votes_agree_and_accept(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        pick = first['review_candidate_names'][0]
        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append(payload)
            state = payload.get('state') or {}
            if state.get('vote'):
                self.assertTrue(state.get('category_definitions') or state.get('human_examples') is not None)
                return jev_reply(payload, pick, 0.8)
            return jev_reply(payload, pick, 0.4)

        decisions, records = self._run(jev_request=fake)
        decision = decisions[0]
        self.assertFalse(decision['review_required'])
        self.assertEqual(decision['classification_rounds'], 3)
        self.assertEqual(decision['category_name'], pick)
        self.assertIn('3 Jev votes agreed', decision['reason'])
        self.assertGreaterEqual(sum(1 for payload in calls if (payload.get('state') or {}).get('vote')), 3)
        self.assertEqual(records[0]['classification_confidence'], 'high')
        body = classify.render_pr_body(decisions, source='test')
        self.assertIn('| 3 |', body)

    def test_round_three_votes_disagree_stay_low(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        names = first['review_candidate_names']
        calls = []

        def fake(payload, api_key, **kwargs):
            calls.append(payload)
            state = payload.get('state') or {}
            if state.get('vote') == 1:
                return jev_reply(payload, names[0], 0.8)
            if state.get('vote'):
                return jev_reply(payload, names[1], 0.8)
            return jev_reply(payload, names[0], 0.4)

        decisions, records = self._run(jev_request=fake)
        decision = decisions[0]
        self.assertTrue(decision['review_required'])
        self.assertEqual(decision['classification_rounds'], 3)
        self.assertEqual(records[0]['classification_confidence'], 'low')
        self.assertIn('did not agree', decision['reason'])

    def test_jev_cache_skips_identical_requests(self):
        first = classify.classify_repo(
            classify.CatalogIndex(self.held), 'owner/generic', GENERIC_FEATURES,
        )
        live_calls = []

        def fake(payload, api_key, **kwargs):
            live_calls.append(payload)
            return jev_reply(payload, first['category_name'], 0.9)

        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'jev-cache.json'
            first_decisions, _records = self._run(jev_request=fake, cache_path=cache)
            first_count = len(live_calls)
            self.assertGreater(first_count, 0)
            self.assertTrue(cache.is_file())
            cache_text = cache.read_text()
            self.assertNotIn('test-key', cache_text)
            second_decisions, _records = self._run(jev_request=fake, cache_path=cache)
            self.assertEqual(len(live_calls), first_count)
            self.assertEqual(first_decisions[0]['category'], second_decisions[0]['category'])
            self.assertEqual(first_decisions[0]['classification_rounds'], second_decisions[0]['classification_rounds'])

    def test_reclassify_replaces_auto_row_but_not_human(self):
        catalog = copy.deepcopy(self.held)
        auto = next(
            repo for repo in catalog['repositories']
            if repo.get('classification_source') and not classify.is_human_label(repo)
        )
        human = next(repo for repo in catalog['repositories'] if classify.is_human_label(repo))
        updated = {
            **auto,
            'category': 'category_23' if auto['category'] != 'category_23' else 'category_01',
            'classification_source': 'star-catalog-nn-v2',
            'classification_confidence': 'high',
            'classification_rounds': 2,
        }
        catalog, conflicts = classify.insert_records(catalog, [updated], replace_ids={auto['id']})
        self.assertEqual(conflicts, [])
        kept = next(repo for repo in catalog['repositories'] if repo['id'] == auto['id'])
        self.assertEqual(kept['category'], updated['category'])
        self.assertEqual(kept['classification_rounds'], 2)
        human_update = {
            **human,
            'category': 'category_23' if human['category'] != 'category_23' else 'category_01',
            'classification_source': 'star-catalog-nn-v2',
            'classification_rounds': 2,
        }
        before = human['category']
        catalog, conflicts = classify.insert_records(catalog, [human_update], replace_ids={human['id']})
        self.assertEqual(conflicts, [])
        stayed = next(repo for repo in catalog['repositories'] if repo['id'] == human['id'])
        self.assertEqual(stayed['category'], before)
        self.assertTrue(classify.is_human_label(stayed))




if __name__ == '__main__':
    unittest.main()
