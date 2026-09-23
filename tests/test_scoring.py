import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.models import LLMExtraction, LLMProjectEvidence
from src.scoring import ScoringInput, compute_score

config = Config()


def _make_extraction(depth: str, category: str = "ai_agentic_rag") -> LLMExtraction:
    return LLMExtraction(
        projects=[
            LLMProjectEvidence(
                name="Test Project", category=category, depth=depth,
                evidence="Calls an LLM API once with no retrieval or state.",
                reasoning="Single API call, no workflow.",
            )
        ]
    )


def test_shallow_wrapper_penalty_lowers_score_vs_real_implementation():
    real_input = ScoringInput(matched_skills=["python"], ai_evidence_hits=["rag"],
                               llm_extraction=_make_extraction("real_implementation"))
    shallow_input = ScoringInput(matched_skills=["python"], ai_evidence_hits=["rag"],
                                  llm_extraction=_make_extraction("shallow_wrapper"))

    real_breakdown, real_penalties = compute_score(real_input, config)
    shallow_breakdown, shallow_penalties = compute_score(shallow_input, config)

    assert real_penalties == []
    assert len(shallow_penalties) == 1
    assert 5 <= shallow_penalties[0].points <= 15
    assert shallow_breakdown.ai_project_depth < real_breakdown.ai_project_depth


def test_penalties_never_push_category_below_zero():
    # Even a candidate with only shallow/tutorial projects and no other AI
    # evidence should never score negative.
    inp = ScoringInput(matched_skills=[], ai_evidence_hits=[], llm_extraction=_make_extraction("tutorial_style"))
    breakdown, penalties = compute_score(inp, config)
    assert breakdown.ai_project_depth >= 0
    assert breakdown.total() >= 0


def test_category_scores_never_exceed_configured_caps():
    rich_extraction = LLMExtraction(
        projects=[
            LLMProjectEvidence(name=f"Proj{i}", category="ai_agentic_rag", depth="real_implementation")
            for i in range(10)
        ],
        python_backend_evidence=["a"] * 10,
        cloud_fullstack_evidence=["b"] * 10,
        engineering_depth_evidence=["c"] * 10,
    )
    inp = ScoringInput(
        matched_skills=list({"python", "fastapi", "django", "flask", "postgresql", "redis", "async",
                              "sql", "celery", "gcp", "aws", "azure", "docker", "kubernetes",
                              "testing"}),
        ai_evidence_hits=["rag"],
        llm_extraction=rich_extraction,
        github_score=999,
    )
    breakdown, _ = compute_score(inp, config)
    assert breakdown.ai_project_depth <= config.weights.ai_agentic_rag
    assert breakdown.python_backend <= config.weights.python_backend
    assert breakdown.cloud_fullstack <= config.weights.cloud_fullstack
    assert breakdown.github <= config.weights.github
    assert breakdown.engineering_depth <= config.weights.engineering_depth


def test_no_llm_fallback_still_produces_bounded_score():
    inp = ScoringInput(matched_skills=["python"], ai_evidence_hits=["rag", "langchain", "embeddings"],
                        llm_extraction=None)
    breakdown, penalties = compute_score(inp, config)
    assert penalties == []
    assert 0 <= breakdown.ai_project_depth <= config.weights.ai_agentic_rag
