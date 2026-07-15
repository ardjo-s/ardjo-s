#!/usr/bin/env python3
"""Export the authenticated user's GitHub stars and star lists to Markdown."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


API = "https://api.github.com"
GRAPHQL = f"{API}/graphql"


def request_json(url: str, token: str, *, method: str = "GET", payload: dict | None = None) -> dict | list:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            if error.code in {502, 503, 504} and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"GitHub API {error.code} for {url}: {detail}") from error


def fetch_stars(token: str) -> list[dict]:
    stars: list[dict] = []
    page = 1
    while True:
        rows = request_json(f"{API}/user/starred?per_page=100&page={page}", token)
        if not rows:
            return stars
        for row in rows:
            repo = row.get("repo", row)
            stars.append(
                {
                    "name": repo["full_name"],
                    "url": repo["html_url"],
                    "description": repo.get("description") or "",
                    "language": repo.get("language") or "—",
                    "stars": repo.get("stargazers_count", 0),
                    "archived": bool(repo.get("archived")),
                    "fork": bool(repo.get("fork")),
                    "pushed_at": repo.get("pushed_at") or "—",
                    "starred_at": row.get("starred_at") or "—",
                }
            )
        page += 1


def fetch_lists(token: str) -> dict[str, list[str]]:
    list_query = "query { viewer { lists(first: 100) { nodes { id name } pageInfo { hasNextPage } } } }"
    result = request_json(GRAPHQL, token, method="POST", payload={"query": list_query})
    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL: " + "; ".join(e["message"] for e in result["errors"]))
    lists = result["data"]["viewer"]["lists"]
    if lists["pageInfo"]["hasNextPage"]:
        raise RuntimeError("More than 100 GitHub star lists are not supported by this export yet")
    memberships: dict[str, list[str]] = {}
    for item in lists["nodes"]:
        item_query = f'''query {{ node(id: "{item["id"]}") {{ ... on UserList {{ items(first: 100) {{ pageInfo {{ hasNextPage }} nodes {{ ... on Repository {{ nameWithOwner }} }} }} }} }} }}'''
        item_result = request_json(GRAPHQL, token, method="POST", payload={"query": item_query})
        if item_result.get("errors"):
            raise RuntimeError("GitHub GraphQL: " + "; ".join(e["message"] for e in item_result["errors"]))
        items = item_result["data"]["node"]["items"]
        if items["pageInfo"]["hasNextPage"]:
            raise RuntimeError(f"Star list {item['name']!r} contains more than 100 repositories")
        for repo in items["nodes"]:
            memberships.setdefault(repo["nameWithOwner"], []).append(item["name"])
    return memberships


def md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def render(stars: list[dict], memberships: dict[str, list[str]]) -> str:
    by_list: defaultdict[str, list[dict]] = defaultdict(list)
    for repo in stars:
        for list_name in memberships.get(repo["name"], []):
            by_list[list_name].append(repo)
    listed = set(memberships)
    unlisted = [repo for repo in stars if repo["name"] not in listed]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# GitHub stars — ardjo-s",
        "",
        "> Généré automatiquement depuis les stars et Star Lists du compte GitHub `ardjo-s`. Ne pas modifier à la main.",
        "",
        "Synchronisation : [`.github/workflows/sync-github-stars.yml`](../.github/workflows/sync-github-stars.yml) toutes les 15 minutes ou via `workflow_dispatch`, avec le secret GitHub `GH_STARS_TOKEN`.",
        "",
        f"Dernière synchronisation : **{generated}** · **{len(stars)}** stars · **{len(by_list)}** listes · **{len(unlisted)}** sans liste.",
        "",
        "## Listes",
        "",
    ]
    for list_name in sorted(by_list, key=str.casefold):
        repos = sorted(by_list[list_name], key=lambda repo: repo["name"].casefold())
        lines += [f"### {list_name} ({len(repos)})", ""]
        for repo in repos:
            flags = "".join([" · archived" if repo["archived"] else "", " · fork" if repo["fork"] else ""])
            detail = f" — {md_escape(repo['description'])}" if repo["description"] else ""
            lines.append(f"- [{repo['name']}]({repo['url']}){flags}{detail}")
        lines.append("")
    if unlisted:
        lines += [f"### Sans liste ({len(unlisted)})", ""]
        for repo in sorted(unlisted, key=lambda item: item["name"].casefold()):
            lines.append(f"- [{repo['name']}]({repo['url']})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GH_TOKEN or GITHUB_TOKEN is required", file=sys.stderr)
        return 2
    document = render(fetch_stars(token), fetch_lists(token))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
