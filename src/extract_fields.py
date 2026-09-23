"""Deterministic field extraction: name, email, GitHub URL(s), matched skills.

No LLM involved here — this runs for every resume (eligible or not), which is
required since rejected candidates must still get name/email/skills/evidence
in the output without paying for an LLM call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.text_normalize import normalize_text

EMAIL_PATTERN = re.compile(r"[\w.\-+]+@[\w\-]+\.[\w.\-]+")
GITHUB_TEXT_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.\-]+)", re.I)

# A curated, deterministic skills catalog. Matched with word boundaries against
# normalized text. This intentionally favors precision (real tech names) over
# an exhaustive NLP skill taxonomy, per the "don't over-engineer" guidance.
SKILL_CATALOG: dict[str, str] = {
    "python": r"\bpython\b",
    "java": r"\bjava\b(?!\s*script)",
    "javascript": r"\bjavascript\b|\bjs\b",
    "typescript": r"\btypescript\b",
    "react": r"\breact(\.js)?\b",
    "next.js": r"\bnext\.?js\b",
    "fastapi": r"\bfastapi\b",
    "django": r"\bdjango\b",
    "flask": r"\bflask\b",
    "postgresql": r"\bpostgres(ql)?\b",
    "redis": r"\bredis\b",
    "docker": r"\bdocker\b",
    "kubernetes": r"\bkubernetes\b|\bk8s\b",
    "gcp": r"\bgcp\b|\bgoogle cloud\b",
    "aws": r"\baws\b|\bamazon web services\b",
    "azure": r"\bazure\b",
    "langchain": r"\blangchain\b",
    "langgraph": r"\blanggraph\b",
    "llamaindex": r"\bllama[\s-]?index\b",
    "rag": r"\brag\b|retrieval[\s-]augmented",
    "vector_db": r"\b(pinecone|chromadb|chroma|faiss|weaviate)\b|vector\s*(db|database|store)",
    "embeddings": r"\bembeddings?\b",
    "openai": r"\bopenai\b",
    "anthropic_claude": r"\banthropic\b|\bclaude\b",
    "huggingface": r"huggingface|\btransformers?\b",
    "agentic": r"\bagentic\b|multi[\s-]?agent|tool[\s-]calling",
    "sql": r"\bsql\b",
    "async": r"\basync(io)?\b",
    "celery": r"\bcelery\b",
    "testing": r"\b(pytest|unit test(ing)?|integration test(ing)?)\b",
}


@dataclass
class ExtractedFields:
    name: str | None
    email: str | None
    github_usernames: list[str] = field(default_factory=list)
    github_urls_raw: list[str] = field(default_factory=list)
    invalid_github_urls: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    normalized_text: str = ""


def _guess_name(text: str) -> str | None:
    """Heuristic: the first non-empty line that looks like a person's name
    (not an email/phone/URL and not too long). Confirmed reliable across the
    sampled dataset — resume builders consistently put the name first."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if EMAIL_PATTERN.search(line):
            continue
        if re.search(r"https?://|github\.com|linkedin\.com|\d{5,}", line):
            continue
        # A plausible name: short, mostly alphabetic words
        words = line.split()
        if 1 <= len(words) <= 5 and all(re.match(r"^[A-Za-z.'\-]+$", w) for w in words):
            return line.title() if line.isupper() else line
        # Names embedded in a longer header line separated by '|' (e.g. "Name | Title | Phone: ...")
        first_segment = line.split("|")[0].strip()
        if first_segment and first_segment != line:
            seg_words = first_segment.split()
            if 1 <= len(seg_words) <= 5 and all(re.match(r"^[A-Za-z.'\-]+$", w) for w in seg_words):
                return first_segment.title() if first_segment.isupper() else first_segment
        break  # only inspect the very first non-empty line
    return None


def _normalize_github_url(raw: str) -> tuple[str | None, str | None]:
    """Returns (username, invalid_reason). username is None if invalid."""
    m = GITHUB_TEXT_PATTERN.search(raw)
    if not m:
        return None, f"unparseable: {raw}"
    username = m.group(1).strip("/").strip()
    # Guard against paths that aren't actually usernames (orgs pages, raw domain)
    if not username or username.lower() in {"settings", "login", "join", "features"}:
        return None, f"empty_or_reserved_username: {raw}"
    if not re.match(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$", username):
        return None, f"invalid_username_format: {raw}"
    return username, None


def extract_fields(text: str, hyperlinks: list[str]) -> ExtractedFields:
    norm = normalize_text(text)

    emails = EMAIL_PATTERN.findall(norm)
    email = emails[0] if emails else None

    name = _guess_name(norm)

    # Combine visible-text GitHub mentions with hyperlink-annotation URIs.
    candidate_urls = list(GITHUB_TEXT_PATTERN.findall(norm))  # returns usernames directly
    raw_text_matches = [f"github.com/{u}" for u in candidate_urls]
    github_like_links = [u for u in hyperlinks if "github.com" in u.lower()]

    all_raw = raw_text_matches + github_like_links
    usernames: list[str] = []
    invalid: list[str] = []
    seen_usernames: set[str] = set()
    for raw in all_raw:
        username, err = _normalize_github_url(raw)
        if username:
            if username.lower() not in seen_usernames:
                seen_usernames.add(username.lower())
                usernames.append(username)
        elif err:
            invalid.append(raw)

    matched_skills = [
        skill for skill, pattern in SKILL_CATALOG.items() if re.search(pattern, norm, re.I)
    ]

    return ExtractedFields(
        name=name,
        email=email,
        github_usernames=usernames,
        github_urls_raw=all_raw,
        invalid_github_urls=invalid,
        matched_skills=matched_skills,
        normalized_text=norm,
    )
