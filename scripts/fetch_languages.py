#!/usr/bin/env python3
"""Collect deterministic GitHub language totals for the profile chart."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Iterable

import requests


API = "https://api.github.com"
PROFILE_REPOSITORY_MARKER = "PROFILE_REPOSITORY"


class CollectionError(RuntimeError):
    pass


def github_request(session: requests.Session, url: str, params: dict | None = None) -> requests.Response:
    for attempt in range(5):
        response = session.get(url, params=params, timeout=30)
        if response.status_code in (403, 429):
            retry_after = response.headers.get("Retry-After")
            reset = response.headers.get("X-RateLimit-Reset")
            try:
                delay = int(retry_after) if retry_after else max(1, int(reset) - int(time.time()) if reset else 60)
            except (TypeError, ValueError):
                delay = 60
            if attempt == 4:
                raise CollectionError("GitHub API rate limit or authorization failure.")
            time.sleep(min(delay, 60))
            continue
        if response.status_code >= 400:
            raise CollectionError(f"GitHub API returned HTTP {response.status_code}.")
        return response
    raise CollectionError("GitHub API request failed.")


def paginate(session: requests.Session, url: str, params: dict) -> list[dict]:
    results: list[dict] = []
    page = 1
    while True:
        page_params = {**params, "page": page, "per_page": 100}
        response = github_request(session, url, page_params)
        batch = response.json()
        if not isinstance(batch, list):
            raise CollectionError("Unexpected GitHub API response.")
        results.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return results


def read_identifier_list(path: Path) -> set[str]:
    if not path.exists():
        return set()
    identifiers: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            identifiers.add(line.lower())
    return identifiers


def normalize_repo(repo: dict) -> tuple[str, str]:
    owner = repo.get("owner", {}).get("login")
    name = repo.get("name")
    if not owner or not name:
        raise CollectionError("Incomplete repository metadata.")
    return str(owner).lower(), str(name).lower()


def get_user_and_owned_repositories(session: requests.Session) -> tuple[str, list[dict]]:
    user_response = github_request(session, f"{API}/user")
    user = user_response.json()
    login = user.get("login")
    if not login:
        raise CollectionError("Authenticated GitHub username is unavailable.")

    repos = paginate(
        session,
        f"{API}/user/repos",
        {"affiliation": "owner", "type": "owner", "sort": "full_name", "direction": "asc"},
    )
    return str(login), repos


def get_repository(session: requests.Session, owner_repo: str) -> dict:
    response = github_request(session, f"{API}/repos/{owner_repo}")
    repo = response.json()
    if not isinstance(repo, dict):
        raise CollectionError("Unexpected repository metadata response.")
    if repo.get("private"):
        raise CollectionError("The public collaboration allowlist contains a private repository.")
    return repo


def aggregate_language_counts(
    username: str,
    owned_repositories: Iterable[dict],
    collaborator_repositories: Iterable[dict],
    exclusions: set[str],
) -> tuple[dict[str, int], int]:
    token = os.environ.get("LANGUAGE_STATS_TOKEN", "").strip()
    if not token:
        raise CollectionError("LANGUAGE_STATS_TOKEN is required.")

    session = requests.Session()
    session.headers.update({
        "Accept": "application/vnd.github+json",
        "Authorization": "token " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "profile-language-territory",
    })

    totals: Counter[str] = Counter()
    included_count = 0
    seen: set[tuple[str, str]] = set()

    for repo in list(owned_repositories) + list(collaborator_repositories):
        owner, name = normalize_repo(repo)
        key = (owner, name)
        if key in seen:
            continue
        if repo.get("fork") or repo.get("archived"):
            continue
        if f"{owner}/{name}" in exclusions or name in exclusions:
            continue
        if owner == username.lower() and name == f"{username.lower()}.github.io":
            continue
        if owner == username.lower() and name == username.lower():
            continue

        seen.add(key)
        response = github_request(session, f"{API}/repos/{owner}/{name}/languages")
        languages = response.json()
        if not isinstance(languages, dict):
            raise CollectionError("Unexpected language statistics response.")
        for language, byte_count in languages.items():
            if isinstance(language, str) and isinstance(byte_count, int) and byte_count > 0:
                totals[language] += byte_count
        included_count += 1

    if not totals:
        raise CollectionError("No language bytes were found across included repositories.")
    return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0]))), included_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collaborations", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, default=Path("config/excluded_repositories.txt"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        token = os.environ.get("LANGUAGE_STATS_TOKEN", "").strip()
        if not token:
            raise CollectionError("LANGUAGE_STATS_TOKEN is required.")
        session = requests.Session()
        session.headers.update({
            "Accept": "application/vnd.github+json",
        "Authorization": "token " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "profile-language-territory",
        })
        username, owned = get_user_and_owned_repositories(session)

        collaborations = read_identifier_list(args.collaborations)
        exclusions = read_identifier_list(args.exclusions)
        collaborators: list[dict] = []
        for owner_repo in sorted(collaborations):
            if "/" not in owner_repo:
                raise CollectionError("A collaboration entry must use owner/repository format.")
            owner, name = owner_repo.split("/", 1)
            owner = owner.strip()
            name = name.strip()
            if not owner or not name:
                raise CollectionError("A collaboration entry must use owner/repository format.")
            collaborators.append(get_repository(session, f"{owner}/{name}"))

        totals, included_count = aggregate_language_counts(
            username,
            owned,
            collaborators,
            exclusions,
        )
        payload = {
            "languages": totals,
            "included_repository_count": included_count,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(args.output)
        print(f"Collected language totals from {included_count} repositories.")
        return 0
    except CollectionError as error:
        print(f"Collection failed safely: {error}", file=sys.stderr)
        return 1
    except requests.RequestException:
        print("Collection failed safely due to a network or GitHub API error.", file=sys.stderr)
        return 1
    except Exception:
        print("Collection failed safely due to an unexpected error.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
