"""Deterministic hard eligibility gate. No LLM involved by design — the
assignment requires eligibility to stay outside the LLM where possible, and a
binary Python+AI gate is exactly the case where a regex/keyword check is more
reliable and reproducible than an LLM call.

A candidate is eligible only if BOTH:
  1. Python evidence: "python" appears as a real token (word boundary).
  2. AI/agentic evidence: at least one curated AI/LLM/RAG/agentic pattern.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.config import Config


@dataclass
class EligibilityResult:
    eligible: bool
    rejection_reasons: list[str] = field(default_factory=list)
    python_evidence_hits: list[str] = field(default_factory=list)
    ai_evidence_hits: list[str] = field(default_factory=list)


def evaluate_eligibility(normalized_text: str, config: Config) -> EligibilityResult:
    python_hits = [
        p for p in config.python_evidence_patterns if re.search(p, normalized_text, re.I)
    ]
    ai_hits = [
        p for p in config.ai_evidence_patterns if re.search(p, normalized_text, re.I)
    ]

    has_python = bool(python_hits)
    has_ai = bool(ai_hits)

    reasons: list[str] = []
    if not has_python:
        reasons.append("No evidence of Python stack")
    if not has_ai:
        reasons.append("No AI/agentic project evidence")

    return EligibilityResult(
        eligible=has_python and has_ai,
        rejection_reasons=reasons,
        python_evidence_hits=python_hits,
        ai_evidence_hits=ai_hits,
    )
