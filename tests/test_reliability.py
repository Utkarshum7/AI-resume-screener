import os
import shutil
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.llm_adapter import LLMCallError
from src.models import GitHubEnrichment
from src.pipeline import run_pipeline

_REAL_RESUME_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resumes")


def test_corrupted_pdf_does_not_kill_batch():
    with tempfile.TemporaryDirectory() as tmp:
        # A genuinely corrupt "PDF" (not valid PDF bytes at all).
        with open(os.path.join(tmp, "corrupt.pdf"), "wb") as f:
            f.write(b"NOT A REAL PDF FILE %%EOF garbage")

        result = run_pipeline(tmp, Config())

        assert result.batch_summary.total_resumes == 1
        assert result.batch_summary.failed_to_parse == 1
        assert result.candidates[0].parse_status == "failed"
        assert result.candidates[0].parse_error is not None


def test_llm_failure_does_not_kill_batch_and_uses_fallback():
    # Deterministically simulate an LLM failure by mocking the pipeline's
    # reference to extract_with_llm to raise LLMCallError, instead of relying
    # on "no provider configured" (which is no longer true now that a real
    # GEMINI_API_KEY exists in .env, and would otherwise make a real network
    # call here). No network/API call of any kind occurs in this test.
    known_eligible_resume = os.path.join(_REAL_RESUME_DIR, "candidate_30.pdf")
    assert os.path.exists(known_eligible_resume), "fixture resume missing from resumes/"

    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(known_eligible_resume, os.path.join(tmp, "candidate_30.pdf"))

        # candidate_30.pdf also contains a real GitHub link; enrich_github runs
        # for every candidate regardless of eligibility, so it is stubbed too
        # to guarantee this test makes zero network calls of any kind.
        with patch("src.pipeline.extract_with_llm", side_effect=LLMCallError("simulated_failure_for_test")), \
             patch("src.pipeline.enrich_github", return_value=GitHubEnrichment(status="not_provided")):
            result = run_pipeline(tmp, Config())

        assert result.batch_summary.total_resumes == 1
        candidate = result.candidates[0]
        assert candidate.parse_status == "ok"
        assert candidate.eligible is True  # eligibility is deterministic, unaffected by LLM failure
        assert candidate.llm_status == "failed"
        assert candidate.llm_error == "simulated_failure_for_test"
        # Batch continued and deterministic fallback scoring still produced a result.
        assert candidate.total_score is not None
        assert candidate.score_breakdown is not None
