"""
Central configuration: scoring weights, thresholds, model name, env loading.

Keeping all tunables here (instead of scattered through business logic) is what
lets the scoring formula, LLM model, and GitHub behavior be changed without
touching pipeline code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no external dependency). Does not override
    variables already set in the real environment."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class ScoringWeights:
    """Fixed category weights from the assignment. Total = 100."""
    ai_agentic_rag: int = 40
    python_backend: int = 30
    cloud_fullstack: int = 15
    github: int = 10
    engineering_depth: int = 5

    def total(self) -> int:
        return (
            self.ai_agentic_rag
            + self.python_backend
            + self.cloud_fullstack
            + self.github
            + self.engineering_depth
        )


@dataclass(frozen=True)
class PenaltyConfig:
    """Bounded penalty range for shallow/tutorial AI projects, applied inside
    the ai_agentic_rag category only. Never pushes a category below 0."""
    shallow_wrapper_min: int = 5
    shallow_wrapper_max: int = 15
    tutorial_style_min: int = 5
    tutorial_style_max: int = 15


@dataclass(frozen=True)
class GitHubConfig:
    api_base: str = "https://api.github.com"
    token: str | None = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN") or None)
    request_timeout_seconds: float = 6.0
    recent_activity_days: int = 180  # "recent" window for pushed_at scoring
    max_repos_checked: int = 10
    rate_limit_floor: int = 2  # stop calling once remaining requests <= this


@dataclass(frozen=True)
class LLMConfig:
    # Explicit LLM_PROVIDER always wins if set; otherwise auto-detect from
    # whichever API key is present, checked in this order: Anthropic, OpenAI,
    # Gemini. Preserves existing behavior for Anthropic/OpenAI unchanged.
    provider: str = field(
        default_factory=lambda: os.environ.get("LLM_PROVIDER", "").lower()
        or ("anthropic" if os.environ.get("ANTHROPIC_API_KEY") else
            "openai" if os.environ.get("OPENAI_API_KEY") else
            "gemini" if os.environ.get("GEMINI_API_KEY") else "none")
    )
    anthropic_model: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    )
    openai_model: str = field(
        default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )
    gemini_model: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    )
    anthropic_api_key: str | None = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY"))
    openai_api_key: str | None = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY"))
    gemini_api_key: str | None = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY"))
    request_timeout_seconds: float = 30.0
    max_output_tokens: int = 1500


@dataclass(frozen=True)
class Config:
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    penalties: PenaltyConfig = field(default_factory=PenaltyConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    # Eligibility keyword sets — deterministic, curated (not exhaustive NLP).
    python_evidence_patterns: tuple = (r"\bpython\b",)
    ai_evidence_patterns: tuple = (
        r"\blangchain\b", r"\blanggraph\b", r"\bllama[\s-]?index\b", r"\brag\b",
        r"retrieval[\s-]augmented", r"vector\s*(db|database|store|search|embedding)",
        r"\bembeddings?\b", r"tool[\s-]calling", r"multi[\s-]?agent", r"\bagentic\b",
        r"\bagents?\b", r"\bopenai\b", r"\bgpt[\s-]?\d", r"\bllm[s]?\b", r"\banthropic\b",
        r"\bclaude\b", r"huggingface", r"\btransformers?\b", r"fine[\s-]?tun",
        r"prompt engineering", r"\bchatbots?\b", r"\bautogen\b", r"\bcrewai\b",
        r"semantic kernel", r"\bpinecone\b", r"\bchroma(db)?\b", r"\bfaiss\b",
        r"\bweaviate\b", r"\brag pipelines?\b", r"google adk", r"\bnlp\b",
        r"generative ai", r"\bgenai\b",
    )
