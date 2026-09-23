import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.extract_fields import extract_fields


def test_github_visible_url_in_text():
    text = "John Doe\njohn@example.com\nGitHub: github.com/johndoe123\nPython developer."
    fields = extract_fields(text, hyperlinks=[])
    assert "johndoe123" in fields.github_usernames


def test_github_annotation_only_no_visible_url():
    # Text only says the word "GitHub" (as in ~24/50 real resumes); the actual
    # URL lives in the PDF's hyperlink annotations instead.
    text = "Jane Smith\njane@example.com\nLinkedIn | GitHub\nPython developer."
    hyperlinks = ["https://github.com/janesmith"]
    fields = extract_fields(text, hyperlinks=hyperlinks)
    assert "janesmith" in fields.github_usernames


def test_malformed_github_url_is_flagged_invalid_not_crash():
    text = "Someone\nsomeone@example.com"
    hyperlinks = ["https://github.com/"]  # empty username, seen in real dataset (candidate_43)
    fields = extract_fields(text, hyperlinks=hyperlinks)
    assert fields.github_usernames == []
    assert fields.invalid_github_urls  # recorded, not silently dropped


def test_duplicate_github_urls_are_deduplicated():
    text = "Someone\nsomeone@example.com"
    hyperlinks = [
        "https://github.com/repeatuser",
        "https://github.com/repeatuser/project-one",
        "https://github.com/repeatuser/project-two",
        "http://github.com/repeatuser",
    ]
    fields = extract_fields(text, hyperlinks=hyperlinks)
    assert fields.github_usernames == ["repeatuser"]  # one entry, not four


def test_http_and_https_normalize_to_same_username():
    text = "Someone\nsomeone@example.com"
    hyperlinks = ["http://github.com/mixeduser"]
    fields = extract_fields(text, hyperlinks=hyperlinks)
    assert fields.github_usernames == ["mixeduser"]


def test_no_github_present():
    text = "Someone\nsomeone@example.com\nPython developer with LangChain projects."
    fields = extract_fields(text, hyperlinks=[])
    assert fields.github_usernames == []
    assert fields.invalid_github_urls == []
