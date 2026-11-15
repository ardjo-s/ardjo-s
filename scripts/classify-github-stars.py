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
JEV_AGREE_MIN = 0.65
JEV_OVERRIDE_MIN = 0.8
JEV_DUEL_MIN = 0.7
JEV_README_CHARS = 800
JEV_DUEL_README_CHARS = 4000
JEV_FEW_SHOT = 3
HUMAN_MEMBER_WEIGHT = 3.0
HUMAN_CORRECTION_WEIGHT = 4.0
BOT_MEMBER_WEIGHT = 1.0
JEV_CATEGORY_INSTRUCTIONS = (
    'Which existing catalog category is the primary useful outcome of this repository?'
)
JEV_CONFIDENT_INSTRUCTIONS = 'the chosen category clearly fits this repository'
JEV_DUEL_INSTRUCTIONS = (
    'Choose only between these two classifier finalists. Which one is the primary useful outcome?'
)

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
            (cid, repo['name'], weighted(repo_document(repo), self.idf), member_weight(repo), repo)
            for cid, repos in members.items()
            for repo in repos
        ]
        self.human_members = [
            item for item in self.member_vectors if is_human_label(item[4])
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
            repeat = max(1, int(round(member_weight(repo))))
            bag.extend(tokens(repo.get('description') or '') * repeat)
            bag.extend(tokens(repo.get('purpose') or '') * repeat)
            bag.extend(tokens((repo.get('evidence_quote') or '')[:400]) * repeat)
            bag.extend(tokens(repo['name'].split('/')[-1]) * repeat)
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
        neighbours: dict[str, list[tuple[float, str, float]]] = defaultdict(list)
        for cid, repo_name, vector, weight, _repo in self.member_vectors:
            neighbours[cid].append((cosine(query_vec, vector), repo_name, weight))
        for cid, pairs in neighbours.items():
            pairs.sort(key=lambda item: item[0], reverse=True)
            top = pairs[:NEIGHBOUR_K]
            if not top:
                continue
            total_w = sum(item[2] for item in top) or 1.0
            scores[cid] += NEIGHBOUR_WEIGHT * (sum(item[0] * item[2] for item in top) / total_w)
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

    def human_examples(self, name: str, features: dict, k: int = JEV_FEW_SHOT) -> list[dict]:
        """Closest human-labelled rows, preferring human corrections when they are near."""
        if not self.human_members:
            return []
        query_vec = weighted(query_document(name, features), self.idf)
        ranked = []
        for cid, repo_name, vector, _weight, repo in self.human_members:
            ranked.append((cosine(query_vec, vector), repo_name, cid, repo))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        corrections = [item for item in ranked if is_human_correction(item[3])]
        others = [item for item in ranked if not is_human_correction(item[3])]
        out = []
        seen = set()
        for _sim, repo_name, cid, repo in corrections + others:
            if repo_name in seen:
                continue
            seen.add(repo_name)
            out.append({
                'name': repo['name'],
                'category': self.categories[cid]['name'],
                'description': (repo.get('description') or '')[:240],
                'corrected': is_human_correction(repo),
            })
            if len(out) >= k:
                break
        return out


def is_human_label(repo: dict) -> bool:
    source = repo.get('classification_source') or ''
    return source.startswith('human:')


def is_human_correction(repo: dict) -> bool:
    if not is_human_label(repo):
        return False
    candidates = repo.get('review_candidates') or []
    return bool(candidates) and candidates[0] != repo.get('category')


def member_weight(repo: dict) -> float:
    if is_human_correction(repo):
        return HUMAN_CORRECTION_WEIGHT
    if is_human_label(repo):
        return HUMAN_MEMBER_WEIGHT
    return BOT_MEMBER_WEIGHT


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


def jev_questions(categories: list[dict], *, instructions: str | None = None) -> dict:
    return {
        'category': {
            'type': 'choice',
            'instructions': instructions or JEV_CATEGORY_INSTRUCTIONS,
            'criteria': category_choice_criteria(categories),
        },
    }


def jev_confident_questions(category_name: str, description: str) -> dict:
    """Noul about one already-chosen category. Questions are independent, so this is a follow-up call."""
    return {
        'confident': {
            'type': 'noul',
            'instructions': JEV_CONFIDENT_INSTRUCTIONS,
            'criteria': {
                'true': f'{category_name} clearly fits this repository. {description}',
                'false': f'{category_name} is not a clear fit for this repository.',
            },
        },
    }


def readme_excerpt(features: dict, limit: int) -> str:
    return re.sub(r'\s+', ' ', strip_markup(features.get('readme') or '')).strip()[:limit]


def jev_state(
    name: str,
    features: dict,
    decision: dict,
    *,
    readme_limit: int = JEV_README_CHARS,
    examples: list[dict] | None = None,
    chosen: dict | None = None,
) -> dict:
    state = {
        'name': name,
        'description': features.get('description') or '',
        'topics': list(features.get('topics') or []),
        'readme_excerpt': readme_excerpt(features, readme_limit),
        'classifier_top3': [
            {'name': row['name'], 'score': round(float(row['score']), 4)}
            for row in decision.get('ranked') or []
        ],
        'human_examples': examples or [],
    }
    if chosen:
        state['chosen_category'] = chosen['name']
        state['chosen_category_description'] = chosen.get('description') or ''
    return state


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


def _jev_answers(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None
    answers = payload.get('answers')
    return answers if isinstance(answers, dict) else None


def parse_jev_choice(payload: object) -> str | None:
    answers = _jev_answers(payload)
    if answers is None:
        return None
    return _choice_name(answers.get('category'))


def parse_jev_noul(payload: object) -> float | None:
    answers = _jev_answers(payload)
    if answers is None:
        return None
    return _noul_value(answers.get('confident'))


def parse_jev_response(payload: object) -> dict | None:
    """Return {category_name, noul} or None when a combined payload cannot be trusted."""
    category_name = parse_jev_choice(payload)
    noul = parse_jev_noul(payload)
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


def accept_jev_pick(decision: dict, jev_id: str, jev_name: str, noul: float, *, evidence_date: str, how: str) -> None:
    classifier_name = decision['category_name']
    comparison = f"classifier {classifier_name} vs jev {jev_name} (confident {noul:.2f})"
    decision['category'] = jev_id
    decision['category_name'] = jev_name
    decision['review_required'] = False
    decision['confidence'] = 'high'
    decision['review_candidates'] = []
    decision['review_candidate_names'] = []
    decision['jev'] = 'decided'
    decision['classification_source'] = f'jev:{evidence_date}'
    decision['reason'] = f"{how}; {comparison}"


def mark_trancher(decision: dict, extra: str = '') -> None:
    decision['jev'] = 'review'
    decision['review_required'] = True
    decision['confidence'] = 'low'
    if extra:
        decision['reason'] = f"{decision['reason']}; {extra}"


def jev_agreement_accepts(decision: dict, verdict: dict | None, name_to_id: dict[str, str]) -> bool:
    if not verdict or verdict.get('noul') is None:
        return False
    jev_id = name_to_id.get(verdict['category_name'])
    if jev_id is None:
        return False
    noul = verdict['noul']
    if jev_id == decision['category'] and noul >= JEV_AGREE_MIN:
        return True
    if noul >= JEV_OVERRIDE_MIN:
        return True
    return False


def jev_duel_accepts(decision: dict, verdict: dict | None, name_to_id: dict[str, str]) -> bool:
    if not verdict or verdict.get('noul') is None:
        return False
    jev_id = name_to_id.get(verdict['category_name'])
    allowed = set(decision.get('review_candidates') or [])
    if jev_id is None or jev_id not in allowed:
        return False
    return verdict['noul'] >= JEV_DUEL_MIN


def _run_jev_calls(jobs: list[tuple[str, dict]], *, api_key: str, post) -> dict[str, dict | None]:
    replies: dict[str, dict | None] = {}
    if not jobs:
        return replies

    def evaluate(job: tuple[str, dict]) -> tuple[str, dict | None]:
        name, payload = job
        try:
            return name, post(payload, api_key)
        except Exception:
            return name, None

    workers = max(1, min(JEV_CONCURRENCY, len(jobs)))
    if workers == 1:
        for job in jobs:
            name, payload = evaluate(job)
            replies[name] = payload
        return replies
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(evaluate, job) for job in jobs]
        for future in as_completed(futures):
            try:
                name, payload = future.result()
            except Exception:
                continue
            replies[name] = payload
    return replies


def run_choice_then_noul(
    items: list[tuple[dict, dict]],
    *,
    choice_categories: list[dict] | None,
    instructions: str,
    readme_limit: int,
    budget: int,
    api_key: str,
    post,
    index: CatalogIndex | None,
    name_to_id: dict[str, str],
    id_to_category: dict[str, dict],
    allowed_ids: set[str] | None = None,
) -> tuple[dict[str, dict | None], int, set[str]]:
    """Choice call first, then a Noul that names that pick. TypeSafe questions are independent."""
    verdicts: dict[str, dict | None] = {decision['name']: None for _features, decision in items}
    ran: set[str] = set()
    if not items or budget < 1:
        return verdicts, budget, ran

    def categories_for(decision: dict) -> list[dict]:
        if choice_categories is not None:
            return choice_categories
        return [
            id_to_category[cid]
            for cid in decision.get('review_candidates') or []
            if cid in id_to_category
        ]

    pair_slots = max(0, budget // 2)
    choice_jobs = []
    for features, decision in items:
        if len(choice_jobs) >= pair_slots:
            break
        cats = categories_for(decision)
        if len(cats) < 1:
            continue
        examples = index.human_examples(decision['name'], features) if index else []
        choice_jobs.append((decision['name'], {
            'state': jev_state(
                decision['name'], features, decision,
                readme_limit=readme_limit, examples=examples,
            ),
            'model': JEV_MODEL,
            'questions': jev_questions(cats, instructions=instructions),
        }))
    choice_replies = _run_jev_calls(choice_jobs, api_key=api_key, post=post)
    budget -= len(choice_jobs)
    ran = {name for name, _payload in choice_jobs}

    noul_jobs = []
    picked: dict[str, str] = {}
    for features, decision in items:
        if decision['name'] not in ran:
            continue
        jev_name = parse_jev_choice(choice_replies.get(decision['name']))
        if not jev_name:
            continue
        jev_id = name_to_id.get(jev_name)
        if jev_id is None or (allowed_ids is not None and jev_id not in allowed_ids):
            verdicts[decision['name']] = {'category_name': jev_name, 'noul': None}
            continue
        cat = id_to_category[jev_id]
        picked[decision['name']] = jev_name
        examples = index.human_examples(decision['name'], features) if index else []
        noul_jobs.append((decision['name'], {
            'state': jev_state(
                decision['name'], features, decision,
                readme_limit=readme_limit, examples=examples,
                chosen={'name': cat['name'], 'description': cat['description']},
            ),
            'model': JEV_MODEL,
            'questions': jev_confident_questions(cat['name'], cat['description']),
        }))
    noul_jobs = noul_jobs[: max(0, budget)]
    noul_replies = _run_jev_calls(noul_jobs, api_key=api_key, post=post)
    budget -= len(noul_jobs)
    sent_noul = {name for name, _payload in noul_jobs}
    for name, jev_name in picked.items():
        if name not in sent_noul:
            verdicts[name] = {'category_name': jev_name, 'noul': None}
            continue
        noul = parse_jev_noul(noul_replies.get(name))
        verdicts[name] = {'category_name': jev_name, 'noul': noul}
    return verdicts, budget, ran


def apply_jev_second_pass(
    rows: list[tuple[dict, dict, dict]],
    *,
    categories: list[dict],
    api_key: str,
    evidence_date: str,
    request=None,
    index: CatalogIndex | None = None,
) -> None:
    """Second-pass only low-confidence first-pass rows. Never creates a category."""
    low = [
        (features, decision)
        for _, features, decision in rows
        if decision.get('review_required') and not decision.get('skipped')
    ]
    if not api_key:
        for _, decision in low:
            mark_trancher(decision)
        return
    pending = low
    if not pending:
        return
    name_to_id = {category['name']: category['id'] for category in categories}
    id_to_category = {category['id']: category for category in categories}
    post = request or request_jev
    budget = JEV_MAX_CALLS
    first_verdicts, budget, ran = run_choice_then_noul(
        pending,
        choice_categories=categories,
        instructions=JEV_CATEGORY_INSTRUCTIONS,
        readme_limit=JEV_README_CHARS,
        budget=budget,
        api_key=api_key,
        post=post,
        index=index,
        name_to_id=name_to_id,
        id_to_category=id_to_category,
    )
    duels: list[tuple[dict, dict]] = []
    for features, decision in pending:
        if decision['name'] not in ran:
            mark_trancher(decision, 'Jev call cap reached; à trancher')
            continue
        verdict = first_verdicts.get(decision['name'])
        if jev_agreement_accepts(decision, verdict, name_to_id):
            jev_name = verdict['category_name']
            how = (
                'jev agreed with classifier top-1'
                if name_to_id[jev_name] == decision['category']
                else 'jev override'
            )
            accept_jev_pick(
                decision, name_to_id[jev_name], jev_name, verdict['noul'],
                evidence_date=evidence_date, how=how,
            )
            continue
        extra = 'first Jev pass did not meet agreement'
        if verdict and verdict.get('category_name'):
            noul_txt = 'n/a' if verdict.get('noul') is None else f"{verdict['noul']:.2f}"
            extra = (
                f"classifier {decision['category_name']} vs jev {verdict['category_name']} "
                f"(confident {noul_txt}); first pass not accepted"
            )
        decision['reason'] = f"{decision['reason']}; {extra}"
        duels.append((features, decision))

    if not duels or budget < 2:
        for _, decision in duels:
            mark_trancher(decision, 'à trancher')
        return
    ready = []
    for features, decision in duels:
        finalists = [
            cid for cid in decision.get('review_candidates') or [] if cid in id_to_category
        ]
        if len(finalists) < 2:
            mark_trancher(decision, 'à trancher')
            continue
        ready.append((features, decision))
    finalist_ids = {
        cid
        for _, decision in ready
        for cid in decision.get('review_candidates') or []
        if cid in id_to_category
    }
    duel_verdicts, _budget, duel_ran = run_choice_then_noul(
        ready,
        choice_categories=None,
        instructions=JEV_DUEL_INSTRUCTIONS,
        readme_limit=JEV_DUEL_README_CHARS,
        budget=budget,
        api_key=api_key,
        post=post,
        index=index,
        name_to_id=name_to_id,
        id_to_category=id_to_category,
        allowed_ids=finalist_ids or None,
    )
    for features, decision in ready:
        if decision['name'] not in duel_ran:
            mark_trancher(decision, 'Jev call cap reached; à trancher')
            continue
        verdict = duel_verdicts.get(decision['name'])
        if jev_duel_accepts(decision, verdict, name_to_id):
            accept_jev_pick(
                decision,
                name_to_id[verdict['category_name']],
                verdict['category_name'],
                verdict['noul'],
                evidence_date=evidence_date,
                how='jev finalists duel',
            )
            continue
        extra = 'finalists duel not accepted; à trancher'
        if verdict and verdict.get('category_name'):
            noul_txt = 'n/a' if verdict.get('noul') is None else f"{verdict['noul']:.2f}"
            extra = f"duel jev {verdict['category_name']} (confident {noul_txt}); à trancher"
        mark_trancher(decision, extra)


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
        return 'à trancher'
    return '—'


def unsorted_notes(decisions: list[dict]) -> dict[str, list[str]]:
    notes = {}
    for decision in decisions:
        if decision.get('skipped') or not decision.get('review_required'):
            continue
        names = list(decision.get('review_candidate_names') or [])
        if names:
            notes[decision['name']] = names
    return notes


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
            confidence = f"low · à trancher {names}"
        reason = decision['reason'].replace('|', '/')
        category = '—' if decision['review_required'] else decision['category_name']
        lines.append(
            f"| `{decision['name']}` | {category} | {confidence} | {jev_cell(decision)} | {reason} |"
        )
    decided = [row for row in decisions if row.get('jev') == 'decided']
    needs_review = [row for row in decisions if row.get('review_required') and not row.get('skipped')]
    lines.extend([
        '',
        'Jev auto-accepts a low-confidence row only on classifier agreement (`confident >= 0.65`) or a high override (`>= 0.8`). Otherwise a top-2 finalists duel runs (`>= 0.7`). Remaining doubtful rows stay in `docs/stars/unsorted.md` and are not published in a category.',
        '',
        '## Jev second pass',
        '',
        'Only low-confidence `star-catalog-nn-v2` rows are sent to TypeSafe System One. Jev cannot create a category. A missing `TYPESAFE_API_KEY` or API error leaves the row unpublished.',
        '',
        f'- Jev decided (review cleared): {len(decided)}',
        f'- À trancher (not published): {len(needs_review)}',
        '',
        '| Repository | Jev | Final category |',
        '| --- | --- | --- |',
    ])
    for decision in decisions:
        if decision.get('skipped') or not (decision.get('jev') or decision.get('review_required')):
            continue
        final = '—' if decision.get('review_required') else decision['category_name']
        lines.append(
            f"| `{decision['name']}` | {jev_cell(decision)} | {final} |"
        )
    if not decided and not needs_review:
        lines.append('| — | — | no low-confidence rows |')
    if needs_review:
        lines.extend([
            '',
            '## À trancher',
            '',
            'These rows stay in Unsorted / to classify until a human chooses. They are not written into a category page or the profile README.',
            '',
            '| Repository | Candidates |',
            '| --- | --- |',
        ])
        for decision in needs_review:
            names = ' vs '.join(decision.get('review_candidate_names') or [])
            lines.append(f"| `{decision['name']}` | {names or '—'} |")
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
        index=index,
    )
    records = []
    for row, features, decision in classified:
        if decision['category'] not in index.categories:
            raise ValueError(f"classifier invented category {decision['category']}")
        if decision['review_required']:
            continue
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
    stars.export(
        live,
        catalog,
        args.output_dir,
        args.readme,
        unsorted_notes=unsorted_notes(decisions),
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
