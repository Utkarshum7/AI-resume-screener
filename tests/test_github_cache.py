"""Tests for the in-run GitHub enrichment cache (src.github_enrich._RunCache).

All GitHub API calls are mocked via unittest.mock — no real network requests
occur in this file.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from src.config import Config
from src.github_enrich import enrich_github, new_cache

config = Config()


def _mock_response(status_code=200, json_data=None, headers=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.headers = headers or {}
    return resp


def _profile_and_repos(username, public_repos=3):
    profile = _mock_response(200, {"public_repos": public_repos})
    repos = _mock_response(200, [])
    return [profile, repos]


def test_first_lookup_calls_the_mocked_api():
    cache = new_cache()
    with patch("requests.Session.get", side_effect=_profile_and_repos("alice")) as mock_get:
        result = enrich_github(["alice"], [], config, cache)

    assert result.status == "ok"
    assert mock_get.call_count == 2  # profile + repos, exactly once


def test_second_lookup_for_same_username_reuses_cache():
    cache = new_cache()
    with patch("requests.Session.get", side_effect=_profile_and_repos("bob")) as mock_get:
        first = enrich_github(["bob"], [], config, cache)
        second = enrich_github(["bob"], [], config, cache)

    # API must have been called only ONCE (2 requests: profile+repos), not twice.
    assert mock_get.call_count == 2
    assert first.status == "ok" and second.status == "ok"
    assert first.public_repos == second.public_repos
    assert second.username == "bob"


def test_different_usernames_do_not_share_cached_results():
    cache = new_cache()
    call_count = {"n": 0}

    def side_effect(url, **kwargs):
        call_count["n"] += 1
        if "/repos" in url:
            return _mock_response(200, [])
        if "carol" in url:
            return _mock_response(200, {"public_repos": 5})
        return _mock_response(200, {"public_repos": 50})

    with patch("requests.Session.get", side_effect=side_effect) as mock_get:
        carol_result = enrich_github(["carol"], [], config, cache)
        dave_result = enrich_github(["dave"], [], config, cache)

    assert carol_result.public_repos == 5
    assert dave_result.public_repos == 50
    assert mock_get.call_count == 4  # 2 distinct usernames x (profile + repos), no cache reuse across them


def test_github_failure_is_cached_and_isolated_from_other_usernames():
    cache = new_cache()

    def side_effect(url, **kwargs):
        if "erin" in url:
            raise requests.Timeout("simulated timeout")
        if "/repos" in url:
            return _mock_response(200, [])
        return _mock_response(200, {"public_repos": 7})

    with patch("requests.Session.get", side_effect=side_effect):
        erin_result = enrich_github(["erin"], [], config, cache)
        frank_result = enrich_github(["frank"], [], config, cache)

    assert erin_result.status == "timeout"
    assert frank_result.status == "ok"  # one candidate's failure does not affect another
    assert frank_result.public_repos == 7

    # A repeated lookup for the failed username reuses the cached failure
    # rather than retrying the network.
    with patch("requests.Session.get", side_effect=AssertionError("should not be called")):
        erin_again = enrich_github(["erin"], [], config, cache)
    assert erin_again.status == "timeout"
