import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.report import build_report_html, generate_report

SYNTHETIC_DATA = {
    "batch_summary": {
        "total_resumes": 3, "successfully_parsed": 3, "failed_to_parse": 0,
        "duplicates_found": 0, "eligible": 2, "rejected": 1,
    },
    "candidates": [
        {
            "rank": 1, "file": "c1.pdf", "candidate_name": "Alice Example", "eligible": True,
            "total_score": 88, "llm_status": "ok",
            "score_breakdown": {"ai_project_depth": 32, "python_backend": 28, "cloud_fullstack": 12,
                                 "github": 10, "engineering_depth": 6},
            "github": {"status": "ok"}, "rejection_reasons": [],
        },
        {
            "rank": 2, "file": "c2.pdf", "candidate_name": "Bob <Example>", "eligible": True,
            "total_score": 70, "llm_status": "failed",
            "score_breakdown": {"ai_project_depth": 20, "python_backend": 25, "cloud_fullstack": 10,
                                 "github": 0, "engineering_depth": 5},
            "github": {"status": "not_provided"}, "rejection_reasons": [],
        },
        {
            "rank": None, "file": "c3.pdf", "candidate_name": "Carl Example", "eligible": False,
            "total_score": None, "llm_status": "skipped_ineligible",
            "score_breakdown": None, "github": {"status": "not_provided"},
            "rejection_reasons": ["No evidence of Python stack"], "parse_status": "ok",
        },
    ],
}
# fill in parse_status for the two eligible ones too (real schema requires it)
SYNTHETIC_DATA["candidates"][0]["parse_status"] = "ok"
SYNTHETIC_DATA["candidates"][1]["parse_status"] = "ok"


def test_build_report_html_contains_expected_sections():
    html_out = build_report_html(SYNTHETIC_DATA, "output/results.json")

    assert "<html" in html_out
    assert "Batch Summary" in html_out
    assert "Top 10 Eligible Candidates" in html_out
    assert "Rejected Candidates" in html_out
    assert "Scoring Categories" in html_out
    assert "results.json" in html_out  # visible note about source file


def test_report_reflects_batch_summary_numbers():
    html_out = build_report_html(SYNTHETIC_DATA, "output/results.json")
    assert ">3<" in html_out  # total_resumes
    assert ">2<" in html_out  # eligible
    assert ">1<" in html_out  # rejected


def test_report_includes_top_candidate_scores():
    html_out = build_report_html(SYNTHETIC_DATA, "output/results.json")
    assert "Alice Example" in html_out
    assert ">88<" in html_out


def test_report_escapes_html_in_candidate_name():
    html_out = build_report_html(SYNTHETIC_DATA, "output/results.json")
    assert "<Example>" not in html_out  # raw HTML must not leak into the page
    assert "&lt;Example&gt;" in html_out


def test_report_includes_rejection_reason():
    html_out = build_report_html(SYNTHETIC_DATA, "output/results.json")
    assert "No evidence of Python stack" in html_out


def test_generate_report_writes_file_from_json_input():
    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "results.json")
        output_path = os.path.join(tmp, "report.html")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(SYNTHETIC_DATA, f)

        returned_path = generate_report(input_path, output_path)

        assert returned_path == output_path
        assert os.path.exists(output_path)
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "<html" in content
