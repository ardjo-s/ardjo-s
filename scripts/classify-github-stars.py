#!/usr/bin/env python3
"""Assign unsorted public stars to existing catalog categories. Never create a category."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import importlib.util
import json
import math
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
STOP = {
    'a', 'an', 'the', 'and', 'or', 'of', 'to', 'for', 'in', 'on', 'with', 'from', 'by',
    'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'this', 'that', 'these',
    'those', 'it', 'its', 'at', 'into', 'over', 'under', 'than', 'then', 'so', 'if',
    'not', 'no', 'nor', 'your', 'you', 'we', 'our', 'their', 'they', 'them', 'he',
    'she', 'his', 'her', 'i', 'me', 'my', 'open', 'source', 'opensource', 'repo',
    'repository', 'github', 'project', 'tool', 'tools', 'using', 'used', 'use',
    'based', 'powered', 'built', 'build', 'building', 'make', 'making', 'app', 'apps',
    'application', 'applications', 'platform', 'platforms', 'library', 'libraries',
    'framework', 'frameworks', 'simple', 'easy', 'new', 'le', 'la', 'les', 'un',
    'une', 'des', 'de', 'du', 'et', 'ou', 'pour', 'dans', 'avec', 'sur', 'par',
    'ce', 'cette', 'ces', 'license', 'mit', 'badge', 'img', 'svg', 'png', 'jpg',
    'jpeg', 'html', 'http', 'https', 'www', 'com', 'org', 'div', 'align', 'center',
    'width', 'height', 'src', 'href', 'alt', 'blank', 'target', 'rel',
}
NEIGHBOUR_WEIGHT = 0.55
NEIGHBOUR_K = 5
REVIEW_GAP = 0.12
REVIEW_MIN_SCORE = 0.2
README_CHARS = 1800
CLASSIFIER_ID = 'star-catalog-nn-v2'
JEV_URL = 'https://api.typesafe.ai/v1/systemone'
JEV_MODEL = 'jev-latest'
JEV_TIMEOUT = 30
JEV_CONCURRENCY = 3
JEV_MAX_CALLS = 100
JEV_CONFIDENT_MIN = 0.65
JEV_README_CHARS = 800
JEV_CATEGORY_INSTRUCTIONS = (
    'Which existing catalog category is the primary useful outcome of this repository?'
)
JEV_CONFIDENT_INSTRUCTIONS = 'the chosen category clearly fits this repository'

# Domain rules from catalog definitions and AGENTS.md (skills follow their domain).
# Match name + description + topics only — README noise must not fire a reason.
DOMAIN_RULES = (
    {
        'id': 'games-3d-skill',
        'any': {'blender', 'unreal', 'unity', 'godot', 'game_development', '3d_models', 'gaussian_splat'},
        'also': {'skill', 'skills', 'addon', 'mcp'},
        'category': 'category_23',
        'boost': 0.28,
        'down': {'category_03': 0.08},
        'reason': 'domain-specific 3D/game skill follows Games & 3D',
    },
    {
        'id': 'games-3d',
        'any': {'blender', 'unreal', 'unity', 'godot', 'game_development', '3d_models'},
        'category': 'category_23',
        'boost': 0.18,
        'reason': 'Blender/Unreal/game-pipeline terms',
    },
    {
        'id': 'mail',
        'any': {'email', 'inbox', 'mailbox', 'messagerie', 'courrier'},
        'category': 'category_19',
        'boost': 0.2,
        'reason': 'mail/inbox is Knowledge & Productivity, not the host',
    },
    {
        'id': 'mail-name',
        'any': {'mail', 'cloud-mail', 'cloud_mail'},
        'also': {'email', 'inbox', 'mailbox', 'cloudflare_email'},
        'category': 'category_19',
        'boost': 0.2,
        'reason': 'mail/inbox is Knowledge & Productivity, not the host',
    },
    {
        'id': 'cloudflare-host',
        'any': {'email', 'inbox', 'mailbox'},
        'also': {'cloudflare', 'workers', 'cloudflare_workers'},
        'category': 'category_19',
        'boost': 0.1,
        'down': {'category_15': 0.12},
        'reason': 'Cloudflare is the host, not the purpose',
    },
    {
        'id': 'mobile-sim',
        'any': {'simulator', 'simulators', 'react_native', 'expo', 'xcode', 'simslim'},
        'category': 'category_12',
        'boost': 0.22,
        'down': {'category_25': 0.08},
        'reason': 'mobile/simulator development environment',
    },
    {
        'id': 'mobile-native',
        'any': {'ios', 'android', 'tvos', 'watchos', 'visionos'},
        'also': {'simulator', 'simulators', 'react_native', 'expo', 'xcode'},
        'category': 'category_12',
        'boost': 0.22,
        'down': {'category_25': 0.08},
        'reason': 'mobile/simulator development environment',
    },
    {
        'id': 'ui-blocks',
        'any': {'ui_components', 'design_system', 'tailwind', 'tailwindcss', 'figma', 'typography'},
        'category': 'category_11',
        'boost': 0.2,
        'down': {'category_12': 0.06},
        'reason': 'UI components/blocks, not an application framework',
    },
    {
        'id': 'ui-react-blocks',
        'any': {'components', 'blocks'},
        'also': {'react', 'motion', 'tailwind', 'tailwindcss'},
        'category': 'category_11',
        'boost': 0.2,
        'down': {'category_12': 0.06},
        'reason': 'copy-source UI blocks rather than an app runtime',
    },
    {
        'id': 'video-studio',
        'any': {'video', 'screen_recording', 'mp4', 'webm', 'recording_studio', 'video_editor'},
        'category': 'category_10',
        'boost': 0.22,
        'down': {'category_09': 0.08},
        'reason': 'primary deliverable is video/image, not voice-only capture',
    },
    {
        'id': 'recording-video',
        'any': {'recording', 'studio', 'podcast'},
        'also': {'video', 'screen', '4k', 'mp4', 'webm'},
        'category': 'category_10',
        'boost': 0.22,
        'down': {'category_09': 0.08},
        'reason': 'recording studio whose output is video',
    },
    {
        'id': 'agent-spec',
        'any': {'specification', 'spec', 'standard', 'standards'},
        'also': {'agent', 'agents'},
        'category': 'category_03',
        'boost': 0.2,
        'down': {'category_02': 0.05, 'category_13': 0.06},
        'reason': 'agent specification/methods, not a runtime',
    },
    {
        'id': 'security-domain',
        'any': {'pentest', 'pentesters', 'hacking', 'privacy', 'vulnerability', 'authn', 'secrets'},
        'category': 'category_18',
        'boost': 0.2,
        'reason': 'security, privacy and identity follow that domain',
    },
    {
        'id': 'image-video-skill',
        'any': {'video', 'image', 'presentation', 'slides'},
        'also': {'skill', 'skills'},
        'category': 'category_10',
        'boost': 0.2,
        'down': {'category_03': 0.08},
        'reason': 'domain-specific video/image skill follows Image, Video & Presentations',
    },
    {
        'id': 'inference-gateway',
        'any': {
            'gateway', 'inference', 'vllm', 'llamacpp', 'llama_cpp', 'model_server',
            'inference_engine', 'llm_gateway', 'agentgateway', 'agentic_proxy',
            'llm_apis', 'geforce',
        },
        'category': 'category_07',
        'boost': 0.3,
        'down': {'category_23': 0.12, 'category_12': 0.08},
        'reason': 'inference runtime, API gateway or model proxy',
    },
    {
        'id': 'linter',
        'any': {'linter', 'lints', 'clippy', 'eslint', 'static_analysis'},
        'category': 'category_14',
        'boost': 0.24,
        'down': {'category_03': 0.1},
        'reason': 'linters and static analysis are Testing, Debugging & Code Quality',
    },
    {
        'id': 'dictation',
        'any': {'dictation', 'wispr', 'speech_to_text', 'voice_dictation', 'superwhisper'},
        'category': 'category_09',
        'boost': 0.24,
        'down': {'category_19': 0.1},
        'reason': 'dictation/speech-to-text follows Voice, Audio & Music',
    },
    {
        'id': 'memory-rag',
        'any': {'memory_layer', 'long_term_memory', 'rag'},
        'also': {'agent', 'agents', 'ai'},
        'category': 'category_05',
        'boost': 0.24,
        'down': {'category_03': 0.08, 'category_10': 0.08},
        'reason': 'memory/RAG for agents follows AI Memory, Context & RAG',
    },
    {
        'id': 'models-on-device',
        'any': {'coreml', 'coreai', 'coreai-models', 'model_export'},
        'category': 'category_06',
        'boost': 0.24,
        'down': {'category_12': 0.12},
        'reason': 'model export/training artifacts, not an app or simulator runtime',
    },
)

# awesome-* lists follow their subject, not the generic software-directory bucket.
AWESOME_SUBJECTS = (
    ({'sysadmin', 'devops', 'scalability'}, 'category_15', 'awesome list subject is Systems, Cloud & DevOps'),
    ({'tailwind', 'tailwindcss', 'react-components', 'android-ui', 'ui'}, 'category_11', 'awesome list subject is UI & Product Design'),
    ({'godot', 'unity', 'unreal', 'blender'}, 'category_23', 'awesome list subject is Games & 3D'),
    ({'hacking', 'pentest', 'pentesters', 'privacy', 'security', 'web-security'}, 'category_18', 'awesome list subject is Security, Privacy & Identity'),
    ({'pytorch', 'tensorflow'}, 'category_06', 'awesome list subject is AI Models & Training'),
    ({'skills', 'subagents', 'claude-skills'}, 'category_03', 'awesome list subject is Agent Methods, Skills & Configuration'),
    ({'creative-coding', 'creative'}, 'category_10', 'awesome list subject is Image, Video & Presentations'),
    ({'generative-ai'}, 'category_26', 'awesome list subject is AI Engineering & Learning'),
    ({'llm', 'llm-apis'}, 'category_07', 'awesome list subject is AI Inference & Gateways'),
    ({'remote-job', 'cv', 'seo'}, 'category_20', 'awesome list subject is Marketing, Sales & Careers'),
    ({'raspberry-pi', 'raspberry', 'flipperzero', 'flipper'}, 'category_24', 'awesome list subject is Robotics, Hardware & CAD'),
    ({'go', 'golang', 'ruby', 'nodejs', 'node', 'swift', 'vite', 'readme', 'guidelines', 'ddd', 'interview', 'patterns', 'competitive', 'system-design'}, 'category_13', 'awesome list subject is Developer Tools & Languages'),
    ({'mac'}, 'category_19', 'awesome list of macOS software is a transversal directory'),
)


def load_stars_module():
    spec = importlib.util.spec_from_file_location('stars', Path(__file__).with_name('sync-github-stars.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stars = load_stars_module()


def fold(text: str) -> str:
    text = unicodedata.normalize('NFKD', text or '')
    return ''.join(ch for ch in text if not unicodedata.combining(ch)).lower()


def strip_markup(text: str) -> str:
    text = text or ''
    text = re.sub(r'```.*?```', ' ', text, flags=re.S)
    text = re.sub(r'`[^`]+`', ' ', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r' \1 ', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'https?://\S+', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text, flags=re.I)
    return text


def tokens(text: str) -> list[str]:
    words = []
    for match in TOKEN.finditer(fold(strip_markup(text))):
        raw = match.group(0)
        parts = raw.split('-')
        pieces = [raw.replace('-', '_'), *parts] if len(parts) > 1 else [raw]
        for word in pieces:
            if len(word) < 2 or word in STOP or word.isdigit():
                continue
            words.append(word)
    out = list(words)
    out.extend(f'{left}_{right}' for left, right in zip(words, words[1:]))
    return out


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) & set(right)
    numerator = sum(left[key] * right[key] for key in keys)
    norm_l = math.sqrt(sum(value * value for value in left.values())) or 1.0
    norm_r = math.sqrt(sum(value * value for value in right.values())) or 1.0
    return numerator / (norm_l * norm_r)


def weighted(bag: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(bag)
    return {token: (1 + math.log(count)) * idf.get(token, 1.0) for token, count in counts.items()}


def category_map(catalog: dict) -> dict[str, dict]:
    return {category['id']: category for category in catalog['categories']}


def repo_document(repo: dict) -> list[str]:
    parts = [
        repo.get('name', '').split('/')[-1],
        repo.get('description') or '',
        repo.get('purpose') or '',
        repo.get('evidence_quote') or '',
        ' '.join(repo.get('keywords') or []),
    ]
    return tokens(' '.join(parts))


def query_document(name: str, features: dict) -> list[str]:
    repo = name.split('/')[-1]
    bag = []
    bag.extend(tokens(repo.replace('-', ' ').replace('_', ' ')) * 4)
    bag.extend(tokens(features.get('description') or '') * 5)
    bag.extend(tokens(' '.join(features.get('topics') or [])) * 6)
    bag.extend(tokens(features.get('language') or ''))
    bag.extend(tokens(strip_markup(features.get('readme') or '')[:README_CHARS]))
    return bag


def title_token_set(name: str, features: dict) -> set[str]:
    """Tokens that may fire domain-rule reasons: name, description, topics, language."""
    repo = name.split('/')[-1].replace('_', '-')
    bag = []
    bag.extend(tokens(repo.replace('-', ' ')))
    bag.extend(tokens(repo))
    bag.extend(tokens(features.get('description') or ''))
    bag.extend(tokens(' '.join(features.get('topics') or [])))
    bag.extend(tokens(features.get('language') or ''))
    return set(bag)


def rule_matches(rule: dict, token_set: set[str]) -> bool:
    if not (rule['any'] & token_set):
        return False
    if 'also' in rule and not (rule['also'] & token_set):
        return False
    if rule.get('forbid') and (rule['forbid'] & token_set):
        return False
    return True


def is_awesome_list(name: str) -> bool:
    repo = fold(name.split('/')[-1]).replace('_', '-')
    return repo.startswith('awesome') or '-awesome' in repo or repo.endswith('awesome')


def expand_needles(needles: set[str]) -> set[str]:
    """Match token() hyphen/underscore forms so awesome-remote-job hits remote_job."""
    expanded = set()
    for needle in needles:
        expanded.add(needle)
        expanded.add(needle.replace('-', '_'))
        expanded.add(needle.replace('_', '-'))
    return expanded


def awesome_subject(name: str, title: set[str]) -> tuple[str, str] | None:
    if not is_awesome_list(name):
        return None
    repo = fold(name.split('/')[-1]).replace('_', '-')
    subject = set(tokens(repo.replace('-', ' '))) | set(tokens(repo)) | title
    for needles, category, reason in AWESOME_SUBJECTS:
        if expand_needles(needles) & subject:
            return category, reason
    return None


class CatalogIndex:
    def __init__(self, catalog: dict, hold_out: set[str] | None = None):
        hold_out = hold_out or set()
        self.categories = category_map(catalog)
        if not self.categories:
            raise ValueError('catalog has no categories')
        members: dict[str, list[dict]] = defaultdict(list)
        for repo in catalog['repositories']:
            if repo['name'] in hold_out or repo['id'] in hold_out:
                continue
            members[repo['category']].append(repo)
        self.members = members
        bags = {cid: self._category_bag(cid) for cid in self.categories}
        document_frequency: Counter[str] = Counter()
        for bag in bags.values():
            document_frequency.update(set(bag))
        n_docs = len(bags)
        self.idf = {
            token: math.log((n_docs + 1) / (count + 1)) + 1
            for token, count in document_frequency.items()
        }
        self.category_vectors = {cid: weighted(bag, self.idf) for cid, bag in bags.items()}
        self.member_vectors = [
            (cid, repo['name'], weighted(repo_document(repo), self.idf))
            for cid, repos in members.items()
            for repo in repos
        ]

    def _category_bag(self, category_id: str) -> list[str]:
        category = self.categories[category_id]
        bag: list[str] = []
        bag.extend(tokens(category['name']) * 6)
        bag.extend(tokens(category['description']) * 4)
        bag.extend(tokens(category['definition']) * 5)
        bag.extend(tokens(category['slug'].replace('-', ' ')) * 3)
        keywords = []
        for repo in self.members.get(category_id, []):
            keywords.extend(repo.get('keywords') or [])
            bag.extend(tokens(repo.get('description') or ''))
            bag.extend(tokens(repo.get('purpose') or ''))
            bag.extend(tokens((repo.get('evidence_quote') or '')[:400]))
            bag.extend(tokens(repo['name'].split('/')[-1]))
        bag.extend(tokens(' '.join(keywords)) * 2)
        return bag

    def score(self, name: str, features: dict) -> list[dict]:
        query = query_document(name, features)
        query_vec = weighted(query, self.idf)
        title = title_token_set(name, features)
        scores = {
            cid: cosine(query_vec, vector)
            for cid, vector in self.category_vectors.items()
        }
        reasons: dict[str, list[str]] = {cid: [] for cid in scores}
        neighbours: dict[str, list[tuple[float, str]]] = defaultdict(list)
        for cid, repo_name, vector in self.member_vectors:
            neighbours[cid].append((cosine(query_vec, vector), repo_name))
        for cid, pairs in neighbours.items():
            pairs.sort(reverse=True)
            top = pairs[:NEIGHBOUR_K]
            if not top:
                continue
            scores[cid] += NEIGHBOUR_WEIGHT * (sum(item[0] for item in top) / len(top))
            reasons[cid].append(f'nearest classified neighbour {top[0][1]}')
        applied = set()
        for rule in DOMAIN_RULES:
            if rule['id'] in applied:
                continue
            if not rule_matches(rule, title):
                continue
            if rule['category'] not in scores:
                continue
            scores[rule['category']] += rule['boost']
            reasons[rule['category']].append(rule['reason'])
            for cid, penalty in (rule.get('down') or {}).items():
                if cid in scores:
                    scores[cid] -= penalty
            applied.add(rule['id'])
            # A more specific skill rule replaces the generic same-domain rule.
            if rule['id'].endswith('-skill'):
                applied.add(rule['id'].removesuffix('-skill'))
        awesome = awesome_subject(name, title)
        if awesome:
            category, reason = awesome
            if category in scores:
                scores[category] += 0.32
                reasons[category].append(reason)
                if category != 'category_19' and 'category_19' in scores:
                    scores['category_19'] -= 0.08
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [
            {
                'category': cid,
                'name': self.categories[cid]['name'],
                'score': score,
                'reasons': reasons[cid],
            }
            for cid, score in ranked
        ]


def classify_repo(index: CatalogIndex, name: str, features: dict) -> dict:
    ranked = index.score(name, features)
    if not ranked:
        raise ValueError(f'no category scores for {name}')
    top, runner_up = ranked[0], ranked[1] if len(ranked) > 1 else ranked[0]
    gap = top['score'] - runner_up['score'] if runner_up is not top else top['score']
    review_required = gap < REVIEW_GAP or top['score'] < REVIEW_MIN_SCORE
    reason_parts = list(top['reasons'][:3])
    if not reason_parts:
        reason_parts.append(f"nearest existing category by catalog text ({top['score']:.3f})")
    if review_required:
        reason_parts.append(f"runner-up {runner_up['name']}")
    return {
        'name': name,
        'category': top['category'],
        'category_name': top['name'],
        'score': top['score'],
        'gap': gap,
        'confidence': 'low' if review_required else 'high',
        'review_required': review_required,
        'review_candidates': [top['category'], runner_up['category']] if review_required else [],
        'review_candidate_names': [top['name'], runner_up['name']] if review_required else [],
        'reason': '; '.join(reason_parts),
        'neighbour_reason': next((part for part in top['reasons'] if part.startswith('nearest')), ''),
        'ranked': [
            {'category': row['category'], 'name': row['name'], 'score': row['score']}
            for row in ranked[:3]
        ],
    }


def category_choice_criteria(categories: list[dict]) -> dict[str, str]:
    """Choice names are the catalog headings; values are the one-line descriptions."""
    return {category['name']: category['description'] for category in categories}


def jev_questions(categories: list[dict]) -> dict:
    return {
        'category': {
            'type': 'choice',
            'instructions': JEV_CATEGORY_INSTRUCTIONS,
            'criteria': category_choice_criteria(categories),
        },
        'confident': {
            'type': 'noul',
            'instructions': JEV_CONFIDENT_INSTRUCTIONS,
        },
    }


def jev_state(name: str, features: dict, decision: dict) -> dict:
    excerpt = re.sub(r'\s+', ' ', strip_markup(features.get('readme') or '')).strip()
    return {
        'name': name,
        'description': features.get('description') or '',
        'topics': list(features.get('topics') or []),
        'readme_excerpt': excerpt[:JEV_README_CHARS],
        'classifier_top3': [
            {'name': row['name'], 'score': round(float(row['score']), 4)}
            for row in decision.get('ranked') or []
        ],
    }


def _as_probability(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        return None
    return number


def _choice_name(answer) -> str | None:
    if isinstance(answer, str):
        name = answer.strip()
        return name or None
    if not isinstance(answer, dict):
        return None
    raw = answer.get('choice', answer.get('value', answer.get('answer')))
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    return name or None


def _noul_value(answer) -> float | None:
    if isinstance(answer, (int, float)) and not isinstance(answer, bool):
        return _as_probability(answer)
    if not isinstance(answer, dict):
        return None
    for key in ('noul', 'value', 'probability', 'confident'):
        parsed = _as_probability(answer.get(key))
        if parsed is not None:
            return parsed
    return None


def parse_jev_response(payload: object) -> dict | None:
    """Return {category_name, noul} or None when the payload cannot be trusted."""
    if not isinstance(payload, dict):
        return None
    answers = payload.get('answers')
    if not isinstance(answers, dict):
        return None
    category_name = _choice_name(answers.get('category'))
    noul = _noul_value(answers.get('confident'))
    if not category_name or noul is None:
        return None
    return {'category_name': category_name, 'noul': noul}


def request_jev(payload: dict, api_key: str, *, timeout: float = JEV_TIMEOUT) -> dict | None:
    """POST one System One question set. Never log the key; errors return None."""
    if not api_key:
        return None
    body = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        JEV_URL,
        data=body,
        method='POST',
        headers={
            'Accept': 'application/json',
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return None
    return data if isinstance(data, dict) else None


def apply_jev_verdict(decision: dict, verdict: dict | None, *, name_to_id: dict[str, str], evidence_date: str) -> None:
    classifier_name = decision['category_name']
    classifier_id = decision['category']
    if not verdict:
        decision['jev'] = 'review'
        return
    jev_name = verdict['category_name']
    noul = verdict['noul']
    jev_id = name_to_id.get(jev_name)
    comparison = f"classifier {classifier_name} vs jev {jev_name} (confident {noul:.2f})"
    if jev_id is None or noul < JEV_CONFIDENT_MIN:
        decision['jev'] = 'review'
        decision['reason'] = f"{decision['reason']}; {comparison}; keeping classifier pick"
        return
    decision['category'] = jev_id
    decision['category_name'] = jev_name
    decision['review_required'] = False
    decision['confidence'] = 'high'
    decision['review_candidates'] = []
    decision['review_candidate_names'] = []
    decision['jev'] = 'decided'
    decision['classification_source'] = f'jev:{evidence_date}'
    if jev_id == classifier_id:
        decision['reason'] = f"jev accepted {jev_name}; {comparison}"
    else:
        decision['reason'] = f"jev chose {jev_name}; {comparison}"


def apply_jev_second_pass(
    rows: list[tuple[dict, dict, dict]],
    *,
    categories: list[dict],
    api_key: str,
    evidence_date: str,
    request=None,
) -> None:
    """Second-pass only low-confidence first-pass rows. Never creates a category."""
    if not api_key:
        for _, _, decision in rows:
            if decision.get('review_required') and not decision.get('skipped'):
                decision['jev'] = 'review'
        return
    pending = [
        (features, decision)
        for _, features, decision in rows
        if decision.get('review_required') and not decision.get('skipped')
    ][:JEV_MAX_CALLS]
    if not pending:
        return
    questions = jev_questions(categories)
    name_to_id = {category['name']: category['id'] for category in categories}
    post = request or request_jev

    def evaluate(item: tuple[dict, dict]) -> tuple[str, dict | None]:
        features, decision = item
        payload = {
            'state': jev_state(decision['name'], features, decision),
            'model': JEV_MODEL,
            'questions': questions,
        }
        try:
            return decision['name'], post(payload, api_key)
        except Exception:
            return decision['name'], None

    replies: dict[str, dict | None] = {}
    workers = max(1, min(JEV_CONCURRENCY, len(pending)))
    if workers == 1:
        for item in pending:
            name, payload = evaluate(item)
            replies[name] = payload
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(evaluate, item) for item in pending]
            for future in as_completed(futures):
                try:
                    name, payload = future.result()
                except Exception:
                    continue
                replies[name] = payload
    sent = {decision['name'] for _, decision in pending}
    for _, _, decision in rows:
        if decision['name'] not in sent:
            if decision.get('review_required') and not decision.get('skipped'):
                decision['jev'] = 'review'
            continue
        payload = replies.get(decision['name'])
        verdict = parse_jev_response(payload)
        apply_jev_verdict(decision, verdict, name_to_id=name_to_id, evidence_date=evidence_date)


def unsorted_rows(snapshot: dict, catalog: dict) -> list[dict]:
    classified = {repo['id'] for repo in catalog['repositories']}
    rows = []
    seen = set()
    for row in snapshot.get('repositories', []):
        category_id = row.get('category_id')
        if category_id != stars.UNSORTED_ID and row.get('id') in classified:
            continue
        key = row.get('id') or row['name']
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    rows.sort(key=lambda row: row['name'].casefold())
    return rows


def request_optional(url: str, token: str):
    try:
        return stars.request_json(url, token)
    except RuntimeError as error:
        if ' 404 ' in str(error) or str(error).endswith('404'):
            return None
        raise


def fetch_features(name: str, token: str, base: dict | None = None) -> dict:
    features = {
        'name': name,
        'description': (base or {}).get('description') or '',
        'language': '',
        'topics': [],
        'readme': '',
        'readme_url': '',
        'archived': bool((base or {}).get('archived')),
        'fork': bool((base or {}).get('fork')),
        'id': (base or {}).get('id') or '',
        'url': (base or {}).get('url') or f'https://github.com/{name}',
    }
    if not token:
        return features
    data = request_optional(f'{stars.API}/repos/{name}', token)
    if data and data.get('private'):
        print(f'Skipping private repository {name}', file=sys.stderr)
        features['private'] = True
        features['description'] = ''
        features['readme'] = ''
        features['topics'] = []
        return features
    if data:
        features['name'] = data.get('full_name') or name
        features['id'] = data.get('node_id') or features['id']
        features['url'] = data.get('html_url') or features['url']
        features['description'] = data.get('description') or features['description']
        features['language'] = data.get('language') or ''
        features['topics'] = data.get('topics') or []
        features['archived'] = bool(data.get('archived'))
        features['fork'] = bool(data.get('fork'))
    readme = request_optional(f'{stars.API}/repos/{name}/readme', token)
    if readme and readme.get('content'):
        features['readme'] = base64.b64decode(readme['content']).decode('utf-8', 'replace')
        features['readme_url'] = readme.get('html_url') or features['url']
    return features


def evidence_quote(features: dict) -> str:
    text = strip_markup(features.get('readme') or '')
    text = re.sub(r'\s+', ' ', text).strip()
    if text:
        sentence = re.split(r'(?<=[.!?])\s+', text, maxsplit=1)[0].strip()
        quote = sentence or text
        return quote[:400]
    description = (features.get('description') or '').strip()
    return description[:400] if description else 'Starred repository with no public description or README excerpt.'


def purpose_text(features: dict, decision: dict) -> str:
    description = re.sub(r'\s+', ' ', (features.get('description') or '').strip())
    if description:
        return description.split('. ', 1)[0].rstrip('.')[:240]
    return f"Auto-classified as {decision['category_name']}."


def keywords_for(features: dict) -> list[str]:
    seen = []
    for item in features.get('topics') or []:
        value = str(item).strip()
        if value and value not in seen:
            seen.append(value)
    language = (features.get('language') or '').strip()
    if language and language.casefold() not in {item.casefold() for item in seen}:
        seen.append(language)
    return seen[:16]


def catalog_record(row: dict, features: dict, decision: dict, *, source: str, evidence_date: str) -> dict:
    name = features.get('name') or row['name']
    record = {
        'id': features.get('id') or row.get('id') or f"{stars.UNSORTED_ID}:{name}",
        'name': name,
        'url': features.get('url') or row.get('url') or f'https://github.com/{name}',
        'description': features.get('description') or row.get('description') or '',
        'category': decision['category'],
        'purpose': purpose_text(features, decision),
        'keywords': keywords_for(features),
        'review_required': decision['review_required'],
        'evidence_quote': evidence_quote(features),
        'evidence_status': 'readme_read_excerpt' if features.get('readme') else 'description_only',
        'archived': bool(features.get('archived', row.get('archived'))),
        'fork': bool(features.get('fork', row.get('fork'))),
        'evidence_url': features.get('readme_url') or features.get('url') or f'https://github.com/{name}',
        'evidence_read_at': evidence_date,
        'classification_source': source,
    }
    if decision['review_required']:
        record['review_candidates'] = decision['review_candidates']
    return record


def insert_records(catalog: dict, records: list[dict]) -> tuple[dict, list[dict]]:
    ids = {category['id'] for category in catalog['categories']}
    by_id = {repo['id']: repo for repo in catalog['repositories']}
    by_name = {repo['name'].casefold(): repo for repo in catalog['repositories']}
    conflicts = []
    for record in records:
        if record['category'] not in ids:
            raise ValueError(f"refusing unknown category {record['category']} for {record['name']}")
        if record['category'] == stars.UNSORTED_ID:
            raise ValueError(f'refusing unsorted category for {record["name"]}')
        if record['id'] in by_id:
            continue
        name_hit = by_name.get(record['name'].casefold())
        if name_hit:
            conflicts.append({
                'name': record['name'],
                'id': record['id'],
                'existing_id': name_hit['id'],
                'reason': (
                    f"{record['name']} is already catalogued as node {name_hit['id']}; "
                    'live star has a different id and needs a human'
                ),
            })
            continue
        catalog['repositories'].append(record)
        by_id[record['id']] = record
        by_name[record['name'].casefold()] = record
    catalog['repositories'].sort(key=lambda repo: repo['name'].casefold())
    stars.validate_catalog(catalog)
    return catalog, conflicts


def jev_cell(decision: dict) -> str:
    if decision.get('skipped'):
        return '—'
    if decision.get('jev') == 'decided':
        return 'decided'
    if decision.get('review_required'):
        return 'review'
    return '—'


def render_pr_body(decisions: list[dict], *, source: str, conflicts: list[dict] | None = None) -> str:
    lines = [
        '## Classify unsorted GitHub stars',
        '',
        'Deterministic nearest-neighbour classifier against existing `catalog.json` rows and documented domain rules. Low-confidence rows may get a TypeSafe System One (Jev) second pass. No new category. Ardjo merges this PR; nothing is auto-merged.',
        '',
        f'Classifier: `{CLASSIFIER_ID}`. Jev model: `{JEV_MODEL}`. Source run: {source}.',
        '',
        '| Repository | Category | Confidence | Jev | Reason |',
        '| --- | --- | --- | --- | --- |',
    ]
    for decision in decisions:
        if decision.get('skipped'):
            reason = decision['reason'].replace('|', '/')
            lines.append(f"| `{decision['name']}` | skipped | — | — | {reason} |")
            continue
        confidence = decision['confidence']
        if decision['review_required']:
            names = ' vs '.join(decision['review_candidate_names'])
            confidence = f"low · review {names}"
        reason = decision['reason'].replace('|', '/')
        lines.append(
            f"| `{decision['name']}` | {decision['category_name']} | {confidence} | {jev_cell(decision)} | {reason} |"
        )
    decided = [row for row in decisions if row.get('jev') == 'decided']
    needs_review = [row for row in decisions if row.get('review_required') and not row.get('skipped')]
    lines.extend([
        '',
        'Low-confidence rows keep a category and set `review_required` with the top two candidates unless Jev accepts an existing category with confident ≥ 0.65.',
        '',
        '## Jev second pass',
        '',
        'Only low-confidence `star-catalog-nn-v2` rows are sent to TypeSafe System One. Jev cannot create a category. A missing `TYPESAFE_API_KEY` or API error keeps the classifier pick.',
        '',
        f'- Jev decided (review cleared): {len(decided)}',
        f'- Still need review: {len(needs_review)}',
        '',
        '| Repository | Jev | Final category |',
        '| --- | --- | --- |',
    ])
    for decision in decisions:
        if decision.get('skipped') or not (decision.get('jev') or decision.get('review_required')):
            continue
        lines.append(
            f"| `{decision['name']}` | {jev_cell(decision)} | {decision['category_name']} |"
        )
    if not decided and not needs_review:
        lines.append('| — | — | no low-confidence rows |')
    lines.extend([
        '',
        '## Loop',
        '',
        '1. `sync-github-stars.yml` exports unknown live stars to `docs/stars/unsorted.md`.',
        '2. This workflow runs after that sync (and when `unsorted.md` changes on `main`).',
        '3. It updates `catalog.json`, regenerates the pages, runs `--check`, and refreshes this rolling PR on `auto/classify-stars`.',
        '4. If `unsorted.md` is empty, the job exits without opening a PR.',
        '',
    ])
    if conflicts:
        lines.extend([
            '## Name conflicts',
            '',
            'These live stars reuse a catalogued `owner/repo` with a new GitHub node id. They stay unsorted until a human decides.',
            '',
        ])
        for conflict in conflicts:
            lines.append(f"- `{conflict['name']}` live `{conflict['id']}` vs catalog `{conflict['existing_id']}`")
        lines.append('')
    return '\n'.join(lines) + '\n'


def classification_source() -> str:
    server = os.environ.get('GITHUB_SERVER_URL', 'https://github.com').rstrip('/')
    repository = os.environ.get('GITHUB_REPOSITORY', 'ardjo-s/ardjo-s')
    run_id = os.environ.get('GITHUB_RUN_ID')
    if run_id:
        return f'{server}/{repository}/actions/runs/{run_id}'
    return CLASSIFIER_ID


def write_catalog(path: Path, catalog: dict) -> None:
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def classify_unsorted(
    catalog: dict,
    snapshot: dict,
    *,
    features_by_name: dict[str, dict] | None = None,
    token: str = '',
    hold_out: set[str] | None = None,
    typesafe_api_key: str | None = None,
    jev_request=None,
) -> tuple[list[dict], list[dict]]:
    rows = unsorted_rows(snapshot, catalog)
    index = CatalogIndex(catalog, hold_out=hold_out)
    decisions = []
    classified: list[tuple[dict, dict, dict]] = []
    source = classification_source()
    evidence_date = os.environ.get('EVIDENCE_DATE') or dt.date.today().isoformat()
    api_key = typesafe_api_key if typesafe_api_key is not None else (os.environ.get('TYPESAFE_API_KEY') or '')
    for row in rows:
        name = row['name']
        features = (features_by_name or {}).get(name)
        if features is None:
            features = fetch_features(name, token, row)
        else:
            merged = fetch_features(name, '', row)
            merged.update({key: value for key, value in features.items() if value not in (None, '', [])})
            if not merged.get('description'):
                merged['description'] = row.get('description') or ''
            features = merged
        if features.get('private'):
            decisions.append({
                'name': name,
                'category': '',
                'category_name': '',
                'score': 0.0,
                'gap': 0.0,
                'confidence': 'low',
                'review_required': True,
                'review_candidates': [],
                'review_candidate_names': [],
                'reason': 'repository is private; not written to the public catalog',
                'skipped': True,
            })
            continue
        decision = classify_repo(index, name, features)
        if decision['category'] not in index.categories:
            raise ValueError(f"classifier invented category {decision['category']}")
        decisions.append(decision)
        classified.append((row, features, decision))
    apply_jev_second_pass(
        classified,
        categories=catalog['categories'],
        api_key=api_key,
        evidence_date=evidence_date,
        request=jev_request,
    )
    records = []
    for row, features, decision in classified:
        if decision['category'] not in index.categories:
            raise ValueError(f"classifier invented category {decision['category']}")
        records.append(catalog_record(
            row,
            features,
            decision,
            source=decision.get('classification_source') or source,
            evidence_date=evidence_date,
        ))
    return decisions, records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--catalog', type=Path, default=Path('docs/stars/catalog.json'))
    parser.add_argument('--output-dir', type=Path, default=Path('docs/stars'))
    parser.add_argument('--readme', type=Path, default=Path('README.md'))
    parser.add_argument('--features-json', type=Path, help='Offline repo features keyed by owner/name')
    parser.add_argument('--pr-body', type=Path, help='Write the rolling PR markdown table')
    parser.add_argument('--apply', action='store_true', help='Write catalog.json and regenerate the export')
    parser.add_argument('--offline', action='store_true', help='Do not call the GitHub API')
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    snapshot = json.loads((args.output_dir / 'stars.json').read_text(encoding='utf-8'))
    rows = unsorted_rows(snapshot, catalog)
    if not rows:
        print('No unsorted public stars.')
        if args.pr_body:
            args.pr_body.write_text('No unsorted public stars.\n', encoding='utf-8')
        return 0
    features_by_name = {}
    if args.features_json:
        features_by_name = json.loads(args.features_json.read_text(encoding='utf-8'))
    token = ''
    if not args.offline:
        token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or ''
        if not token and not features_by_name:
            parser.error('GH_TOKEN or GITHUB_TOKEN is required unless --offline / --features-json is used')
    decisions, records = classify_unsorted(
        catalog,
        snapshot,
        features_by_name=features_by_name,
        token=token,
        typesafe_api_key=os.environ.get('TYPESAFE_API_KEY') or '',
    )
    for decision in decisions:
        if decision.get('skipped'):
            print(f"{decision['name']}: skipped — {decision['reason']}")
            continue
        flag = ' review' if decision['review_required'] else ''
        print(f"{decision['name']}: {decision['category_name']} ({decision['confidence']}{flag}) — {decision['reason']}")
    if not args.apply:
        body = render_pr_body(decisions, source=classification_source())
        if args.pr_body:
            args.pr_body.write_text(body, encoding='utf-8')
        return 0
    _, conflicts = insert_records(catalog, records)
    body = render_pr_body(decisions, source=classification_source(), conflicts=conflicts)
    if args.pr_body:
        args.pr_body.write_text(body, encoding='utf-8')
    write_catalog(args.catalog, catalog)
    live = stars.snapshot_stars(catalog, json.loads((args.output_dir / 'stars.json').read_text(encoding='utf-8')))
    stars.export(live, catalog, args.output_dir, args.readme)
    return 0


if __name__ == '__main__':
    sys.exit(main())
