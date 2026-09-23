"""Lightweight public GitHub enrichment.

Handles, per the requirements: visible URLs, annotation URLs (already merged
upstream in extract_fields), duplicate links, http/https normalization
(handled in extract_fields via regex), invalid `github.com/` URLs, missing
GitHub, 404, rate limiting, and timeout/network failure. GitHub must never
fail the batch — every branch below returns a GitHubEnrichment with a status
instead of raising.

In-run cache: a plain dict keyed by lowercased username, since the same
username often appears multiple times within one resume (e.g. repeated link
annotations) and could in principle repeat across the batch.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

from src.config import Config
from src.models import GitHubEnrichment


class _RunCache:
    def __init__(self) -> None:
        self.store: dict[str, GitHubEnrichment] = {}
        self.rate_limited = False  # once tripped, skip all further API calls this run


def new_cache() -> _RunCache:
    return _RunCache()


def _get(session: requests.Session, url: str, config: Config) -> requests.Response:
    headers = {"Accept": "application/vnd.github+json"}
    if config.github.token:
        headers["Authorization"] = f"Bearer {config.github.token}"
    return session.get(url, headers=headers, timeout=config.github.request_timeout_seconds)


def _check_rate_limit_headers(resp: requests.Response, cache: _RunCache, config: Config) -> None:
    remaining = resp.headers.get("X-RateLimit-Remaining")
    if remaining is not None:
        try:
            if int(remaining) <= config.github.rate_limit_floor:
                cache.rate_limited = True
        except ValueError:
            pass


def enrich_github(usernames: list[str], invalid_urls: list[str], config: Config,
                   cache: _RunCache) -> GitHubEnrichment:
    if not usernames:
        if invalid_urls:
            return GitHubEnrichment(status="invalid_url", profile_urls_found=invalid_urls,
                                     summary="GitHub link present but URL was malformed/unusable.")
        return GitHubEnrichment(status="not_provided", summary="No GitHub profile found in resume.")

    username = usernames[0]  # first valid, deduped username found
    key = username.lower()
    if key in cache.store:
        cached = cache.store[key]
        # Return a copy so profile_urls_found reflects this candidate's own list
        return cached.model_copy(update={"profile_urls_found": usernames})

    if cache.rate_limited:
        result = GitHubEnrichment(
            status="rate_limited", username=username, profile_urls_found=usernames,
            summary="Skipped: GitHub API rate limit was reached earlier in this run.",
        )
        cache.store[key] = result
        return result

    session = requests.Session()
    try:
        profile_resp = _get(session, f"{config.github.api_base}/users/{username}", config)
        _check_rate_limit_headers(profile_resp, cache, config)

        if profile_resp.status_code == 404:
            result = GitHubEnrichment(status="not_found", username=username, profile_urls_found=usernames,
                                       summary="GitHub profile not found (404).")
            cache.store[key] = result
            return result
        if profile_resp.status_code == 403:
            cache.rate_limited = True
            result = GitHubEnrichment(status="rate_limited", username=username, profile_urls_found=usernames,
                                       summary="GitHub API rate limit or access forbidden (403).")
            cache.store[key] = result
            return result
        if profile_resp.status_code != 200:
            result = GitHubEnrichment(status="error", username=username, profile_urls_found=usernames,
                                       summary=f"GitHub API returned HTTP {profile_resp.status_code}.")
            cache.store[key] = result
            return result

        profile = profile_resp.json()
        public_repos = profile.get("public_repos", 0)

        repos_resp = _get(
            session,
            f"{config.github.api_base}/users/{username}/repos"
            f"?sort=pushed&per_page={config.github.max_repos_checked}",
            config,
        )
        _check_rate_limit_headers(repos_resp, cache, config)
        repos = repos_resp.json() if repos_resp.status_code == 200 else []
        if not isinstance(repos, list):
            repos = []

        recent_score = _score_recent_activity(repos, config)
        relevant_score = _score_relevant_repos(repos)

        result = GitHubEnrichment(
            status="ok",
            username=username,
            profile_urls_found=usernames,
            public_repos=public_repos,
            recent_activity_score=recent_score,
            relevant_repos_score=relevant_score,
            summary=_summary_text(public_repos, recent_score, relevant_score),
        )
        cache.store[key] = result
        return result

    except requests.Timeout:
        result = GitHubEnrichment(status="timeout", username=username, profile_urls_found=usernames,
                                   summary="GitHub API request timed out.")
        cache.store[key] = result
        return result
    except requests.RequestException as e:
        result = GitHubEnrichment(status="error", username=username, profile_urls_found=usernames,
                                   summary=f"GitHub API network error: {e}")
        cache.store[key] = result
        return result


def _score_recent_activity(repos: list[dict], config: Config) -> int:
    if not repos:
        return 0
    now = datetime.now(timezone.utc)
    most_recent_days = None
    for repo in repos:
        pushed_at = repo.get("pushed_at")
        if not pushed_at:
            continue
        try:
            dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        days = (now - dt).days
        if most_recent_days is None or days < most_recent_days:
            most_recent_days = days

    if most_recent_days is None:
        return 0
    window = config.github.recent_activity_days
    if most_recent_days <= window // 6:      # very recent (~1 month)
        return 5
    if most_recent_days <= window // 2:      # within ~3 months
        return 4
    if most_recent_days <= window:           # within window (~6 months)
        return 2
    return 0


def _score_relevant_repos(repos: list[dict]) -> int:
    if not repos:
        return 0
    relevant_keywords = ("ai", "llm", "agent", "rag", "gpt", "ml", "bot", "langchain", "nlp")
    count = 0
    for repo in repos:
        if repo.get("fork"):
            continue
        language = (repo.get("language") or "").lower()
        name = (repo.get("name") or "").lower()
        desc = (repo.get("description") or "").lower()
        if language == "python" or any(k in name or k in desc for k in relevant_keywords):
            count += 1
    return min(count, 5)


def _summary_text(public_repos: int, recent: int, relevant: int) -> str:
    activity = "Recently active" if recent >= 4 else "Limited recent activity" if recent > 0 else "No recent activity detected"
    return f"{activity}; {public_repos} public repos; {relevant}/5 relevant/maintained repos scored."
