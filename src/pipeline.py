"""Orchestrates the full pipeline:

PDF -> deterministic extraction -> deterministic fields -> deterministic
eligibility -> (eligible only) single LLM call -> deterministic scoring ->
GitHub enrichment -> CandidateResult -> batch summary.

Every per-resume step is isolated so one bad file/LLM/GitHub call cannot
crash the run.
"""
from __future__ import annotations

import logging

from src.config import Config
from src.docx_extract import extract_docx
from src.eligibility import evaluate_eligibility
from src.extract_fields import extract_fields
from src.github_enrich import enrich_github, new_cache
from src.ingest import ingest_directory
from src.llm_adapter import LLMCallError, extract_with_llm
from src.models import (
    BatchSummary,
    CandidateResult,
    PipelineResult,
    ScoreBreakdown,
)
from src.pdf_extract import extract_pdf
from src.scoring import ScoringInput, compute_score

logger = logging.getLogger("resume_screener")


def run_pipeline(input_dir: str, config: Config | None = None) -> PipelineResult:
    config = config or Config()
    files = ingest_directory(input_dir)

    candidates: list[CandidateResult] = []
    github_cache = new_cache()

    for f in files:
        result = CandidateResult(file=f.filename, is_duplicate=f.is_duplicate, duplicate_of=f.duplicate_of)

        if f.sha256.startswith("UNREADABLE:"):
            result.parse_status = "failed"
            result.parse_error = f.sha256
            candidates.append(result)
            continue

        if f.filename.lower().endswith(".docx"):
            file_result = extract_docx(f.path)
        else:
            file_result = extract_pdf(f.path)
        if not file_result.ok:
            result.parse_status = "failed"
            result.parse_error = file_result.error
            candidates.append(result)
            continue

        try:
            fields = extract_fields(file_result.text, file_result.hyperlinks)
        except Exception as e:  # noqa: BLE001 - extraction bug must not kill the batch
            result.parse_status = "failed"
            result.parse_error = f"field_extraction_failed: {e}"
            candidates.append(result)
            continue

        result.candidate_name = fields.name
        result.email = fields.email
        result.matched_skills = fields.matched_skills

        try:
            elig = evaluate_eligibility(fields.normalized_text, config)
        except Exception as e:  # noqa: BLE001
            result.parse_status = "failed"
            result.parse_error = f"eligibility_check_failed: {e}"
            candidates.append(result)
            continue

        result.eligible = elig.eligible
        result.rejection_reasons = elig.rejection_reasons

        # GitHub enrichment runs for every candidate (eligible or not) since
        # the requirement lists it as part of the standard output, not
        # conditional on eligibility.
        result.github = enrich_github(fields.github_usernames, fields.invalid_github_urls, config, github_cache)

        if not result.eligible:
            result.llm_status = "skipped_ineligible"
            candidates.append(result)
            continue

        llm_extraction = None
        try:
            llm_extraction = extract_with_llm(fields.normalized_text, config)
            result.llm_status = "ok"
        except LLMCallError as e:
            result.llm_status = "failed"
            result.llm_error = str(e)
        except Exception as e:  # noqa: BLE001 - absolute last-resort guard
            result.llm_status = "failed"
            result.llm_error = f"unexpected_llm_error: {e}"

        scoring_input = ScoringInput(
            matched_skills=fields.matched_skills,
            ai_evidence_hits=elig.ai_evidence_hits,
            llm_extraction=llm_extraction,
            github_score=result.github.recent_activity_score + result.github.relevant_repos_score,
        )
        breakdown, penalties = compute_score(scoring_input, config)
        result.score_breakdown = breakdown
        result.penalties = penalties
        result.total_score = breakdown.total()

        if llm_extraction is not None:
            result.project_summary = "; ".join(llm_extraction.project_summaries[:2]) or None
            result.strengths = [
                p.name for p in llm_extraction.projects if p.depth == "real_implementation"
            ][:3]
            result.concerns = [
                f"{p.name}: {p.reasoning}" for p in llm_extraction.projects
                if p.depth in ("shallow_wrapper", "tutorial_style")
            ][:3]
        else:
            result.project_summary = (
                "LLM unavailable/failed for this candidate; scored from deterministic "
                "keyword evidence only (see matched_skills, score_breakdown)."
            )
            result.concerns = ["LLM assessment unavailable — score based on deterministic evidence only"]

        candidates.append(result)

    # Rank eligible candidates by score, descending; ties broken by filename for determinism.
    eligible_candidates = [c for c in candidates if c.eligible and c.total_score is not None]
    eligible_candidates.sort(key=lambda c: (-c.total_score, c.file))
    for i, c in enumerate(eligible_candidates, start=1):
        c.rank = i

    summary = BatchSummary(
        total_resumes=len(candidates),
        successfully_parsed=sum(1 for c in candidates if c.parse_status == "ok"),
        failed_to_parse=sum(1 for c in candidates if c.parse_status == "failed"),
        duplicates_found=sum(1 for c in candidates if c.is_duplicate),
        eligible=sum(1 for c in candidates if c.eligible),
        rejected=sum(1 for c in candidates if c.parse_status == "ok" and not c.eligible),
    )

    # Final ordering: ranked eligible first, then rejected, then failed — for readability.
    ordered = (
        sorted([c for c in candidates if c.eligible], key=lambda c: c.rank or 999999)
        + [c for c in candidates if c.parse_status == "ok" and not c.eligible]
        + [c for c in candidates if c.parse_status == "failed"]
    )

    return PipelineResult(batch_summary=summary, candidates=ordered)
