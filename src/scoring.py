"""Deterministic scoring: converts (a) deterministic keyword evidence and
(b) optional LLM structured evidence into the final 100-point score.

The LLM (when available) never returns a number — it returns per-project
`depth` classifications and evidence lists (see models.LLMExtraction). This
module is the ONLY place numeric scores are computed, which is what makes
every score auditable from fields already present in results.json.

Fixed category caps (must match assignment weights):
    ai_agentic_rag   = 40
    python_backend   = 30
    cloud_fullstack  = 15
    github           = 10   (computed in github_enrich.py, not here)
    engineering_depth= 5
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.config import Config
from src.models import LLMExtraction, LLMProjectEvidence, PenaltyRecord, ScoreBreakdown

# Base points awarded per AI/agentic project found, BEFORE penalty deduction.
# A shallow/tutorial project still counts as "an AI project exists" (base
# points), then the required 5-15 point penalty is deducted explicitly and
# separately — this keeps the "why did this score drop" auditable as its own
# line item instead of silently baking it into a lower base score.
_AI_PROJECT_BASE_POINTS = {
    "real_implementation": 16,
    "shallow_wrapper": 16,
    "tutorial_style": 16,
    "skill_mention_only": 5,
}
_MAX_AI_PROJECTS_COUNTED = 3  # avoid unbounded stacking from a long project list

_SHALLOW_WRAPPER_PENALTY = 10  # within PenaltyConfig [5,15]
_TUTORIAL_STYLE_PENALTY = 8    # within PenaltyConfig [5,15]

_PYTHON_BACKEND_SKILL_POINTS = {
    "python": 10, "fastapi": 6, "django": 4, "flask": 4,
    "postgresql": 5, "redis": 4, "async": 3, "sql": 2, "celery": 2,
}
_CLOUD_FULLSTACK_SKILL_POINTS = {
    "gcp": 6, "aws": 6, "azure": 6, "docker": 5, "kubernetes": 3,
    "react": 2, "next.js": 2,
}
_ENGINEERING_DEPTH_SKILL_POINTS = {
    "testing": 2, "async": 1, "docker": 1, "redis": 1, "celery": 1,
}

_LLM_EVIDENCE_BONUS_CAP = {
    "python_backend": 5,
    "cloud_fullstack": 3,
    "engineering_depth": 2,
}

# Fallback ceilings used when the LLM is unavailable/failed for an eligible
# candidate. Deliberately lower than the LLM-informed ceiling for
# ai_agentic_rag because depth (real vs shallow) cannot be judged
# deterministically — we only know AI keywords are present, not how they were
# used, so we intentionally cannot award full marks.
_FALLBACK_AI_SCORE_PER_KEYWORD = 4
_FALLBACK_AI_SCORE_CAP = 24


@dataclass
class ScoringInput:
    matched_skills: list[str]
    ai_evidence_hits: list[str]           # from eligibility (regex hits)
    llm_extraction: LLMExtraction | None  # None if LLM not run / failed
    github_score: int = 0                 # 0-10, computed separately


def _score_ai_agentic_rag(inp: ScoringInput) -> tuple[int, list[PenaltyRecord]]:
    cap = 40
    penalties: list[PenaltyRecord] = []

    if inp.llm_extraction is not None:
        ai_projects: list[LLMProjectEvidence] = [
            p for p in inp.llm_extraction.projects if p.category == "ai_agentic_rag"
        ][:_MAX_AI_PROJECTS_COUNTED]

        if not ai_projects and inp.llm_extraction.ai_agentic_evidence:
            # LLM found AI evidence but didn't structure it as a project entry —
            # treat as a single skill_mention_only project so it isn't scored 0.
            ai_projects = [LLMProjectEvidence(
                name="AI/agentic evidence (unstructured)",
                category="ai_agentic_rag",
                depth="skill_mention_only",
                evidence="; ".join(inp.llm_extraction.ai_agentic_evidence[:3]),
            )]

        base = 0
        for proj in ai_projects:
            base += _AI_PROJECT_BASE_POINTS.get(proj.depth, 5)
            if proj.depth == "shallow_wrapper":
                penalties.append(PenaltyRecord(project=proj.name, reason="shallow_wrapper",
                                                points=_SHALLOW_WRAPPER_PENALTY))
            elif proj.depth == "tutorial_style":
                penalties.append(PenaltyRecord(project=proj.name, reason="tutorial_style",
                                                points=_TUTORIAL_STYLE_PENALTY))
        base = min(base, cap)
        total_penalty = min(sum(p.points for p in penalties), base)  # never go negative
        score = max(0, base - total_penalty)
        return min(score, cap), penalties

    # Fallback: no LLM evidence available — deterministic keyword-count proxy,
    # capped well below max since depth cannot be judged.
    score = min(len(inp.ai_evidence_hits) * _FALLBACK_AI_SCORE_PER_KEYWORD, _FALLBACK_AI_SCORE_CAP)
    return score, penalties


def _score_python_backend(inp: ScoringInput) -> int:
    cap = 30
    base = sum(pts for skill, pts in _PYTHON_BACKEND_SKILL_POINTS.items() if skill in inp.matched_skills)
    base = min(base, cap)
    if inp.llm_extraction is not None:
        bonus = min(len(inp.llm_extraction.python_backend_evidence), _LLM_EVIDENCE_BONUS_CAP["python_backend"])
        base = min(base + bonus, cap)
    return base


def _score_cloud_fullstack(inp: ScoringInput) -> int:
    cap = 15
    base = sum(pts for skill, pts in _CLOUD_FULLSTACK_SKILL_POINTS.items() if skill in inp.matched_skills)
    base = min(base, cap)
    if inp.llm_extraction is not None:
        bonus = min(len(inp.llm_extraction.cloud_fullstack_evidence), _LLM_EVIDENCE_BONUS_CAP["cloud_fullstack"])
        base = min(base + bonus, cap)
    return base


def _score_engineering_depth(inp: ScoringInput) -> int:
    cap = 5
    base = sum(pts for skill, pts in _ENGINEERING_DEPTH_SKILL_POINTS.items() if skill in inp.matched_skills)
    base = min(base, cap)
    if inp.llm_extraction is not None:
        bonus = min(len(inp.llm_extraction.engineering_depth_evidence), _LLM_EVIDENCE_BONUS_CAP["engineering_depth"])
        base = min(base + bonus, cap)
    return base


def compute_score(inp: ScoringInput, config: Config) -> tuple[ScoreBreakdown, list[PenaltyRecord]]:
    ai_score, penalties = _score_ai_agentic_rag(inp)
    breakdown = ScoreBreakdown(
        ai_project_depth=ai_score,
        python_backend=_score_python_backend(inp),
        cloud_fullstack=_score_cloud_fullstack(inp),
        github=max(0, min(inp.github_score, config.weights.github)),
        engineering_depth=_score_engineering_depth(inp),
    )
    return breakdown, penalties
