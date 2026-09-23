"""Pydantic schemas shared across the pipeline.

Two groups:
  - LLM-facing schemas (structured output contract for the single eligible-
    candidate call): LLMProjectAssessment / LLMExtraction.
  - Output schemas (what goes into results.json): ScoreBreakdown / CandidateResult.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# LLM structured-output contract (eligible candidates only)
# --------------------------------------------------------------------------

class LLMProjectEvidence(BaseModel):
    name: str = Field(description="Short project/experience name")
    category: Literal["ai_agentic_rag", "python_backend", "cloud_fullstack", "other"] = "other"
    depth: Literal["real_implementation", "shallow_wrapper", "tutorial_style", "skill_mention_only"] = (
        "skill_mention_only"
    )
    evidence: str = Field(default="", description="Quote or paraphrase from the resume supporting this classification")
    reasoning: str = Field(default="", description="One sentence on why this depth label was chosen")


class LLMExtraction(BaseModel):
    """The single structured response requested per eligible candidate."""
    normalized_skills: list[str] = Field(default_factory=list)
    project_summaries: list[str] = Field(default_factory=list)
    projects: list[LLMProjectEvidence] = Field(default_factory=list)
    ai_agentic_evidence: list[str] = Field(default_factory=list)
    python_backend_evidence: list[str] = Field(default_factory=list)
    cloud_fullstack_evidence: list[str] = Field(default_factory=list)
    engineering_depth_evidence: list[str] = Field(default_factory=list)
    overall_reasoning: str = Field(default="")


# --------------------------------------------------------------------------
# Output schemas
# --------------------------------------------------------------------------

class ScoreBreakdown(BaseModel):
    ai_project_depth: int = 0
    python_backend: int = 0
    cloud_fullstack: int = 0
    github: int = 0
    engineering_depth: int = 0

    def total(self) -> int:
        return (
            self.ai_project_depth
            + self.python_backend
            + self.cloud_fullstack
            + self.github
            + self.engineering_depth
        )


class PenaltyRecord(BaseModel):
    project: str
    reason: Literal["shallow_wrapper", "tutorial_style"]
    points: int


class GitHubEnrichment(BaseModel):
    status: Literal[
        "not_provided", "invalid_url", "ok", "not_found", "rate_limited",
        "timeout", "error",
    ] = "not_provided"
    username: str | None = None
    profile_urls_found: list[str] = Field(default_factory=list)
    public_repos: int | None = None
    recent_activity_score: int = 0
    relevant_repos_score: int = 0
    summary: str = ""


class CandidateResult(BaseModel):
    rank: int | None = None
    file: str
    candidate_name: str | None = None
    email: str | None = None
    parse_status: Literal["ok", "failed"] = "ok"
    parse_error: str | None = None
    duplicate_of: str | None = None
    is_duplicate: bool = False

    eligible: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)

    llm_status: Literal["not_applicable", "ok", "failed", "skipped_ineligible"] = "not_applicable"
    llm_error: str | None = None

    total_score: int | None = None
    score_breakdown: ScoreBreakdown | None = None
    penalties: list[PenaltyRecord] = Field(default_factory=list)

    project_summary: str | None = None
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)

    github: GitHubEnrichment = Field(default_factory=GitHubEnrichment)


class BatchSummary(BaseModel):
    total_resumes: int
    successfully_parsed: int
    failed_to_parse: int
    duplicates_found: int
    eligible: int
    rejected: int


class PipelineResult(BaseModel):
    batch_summary: BatchSummary
    candidates: list[CandidateResult]
