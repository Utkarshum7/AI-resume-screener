#!/usr/bin/env python3
"""CLI entry point.

Usage:
    python main.py --input ./resumes --output ./output/results.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import Config  # noqa: E402
from src.models import PipelineResult  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402


def _print_summary(result: PipelineResult, output_path: str) -> None:
    """Concise terminal summary printed after a successful run. Purely a
    presentation layer over the already-computed PipelineResult — reads
    fields only, no new computation, no effect on results.json."""
    s = result.batch_summary
    eligible = [c for c in result.candidates if c.eligible]
    llm_ok = sum(1 for c in eligible if c.llm_status == "ok")
    llm_failed = sum(1 for c in eligible if c.llm_status == "failed")

    gh_status_counts: dict[str, int] = {}
    for c in result.candidates:
        gh_status_counts[c.github.status] = gh_status_counts.get(c.github.status, 0) + 1

    top5 = sorted(eligible, key=lambda c: c.rank or 999999)[:5]

    print()
    print("=" * 60)
    print("RESUME SCREENING SUMMARY")
    print("=" * 60)
    print(f"Total resumes   : {s.total_resumes}")
    print(f"Parsed          : {s.successfully_parsed}")
    print(f"Failed          : {s.failed_to_parse}")
    print(f"Duplicates      : {s.duplicates_found}")
    print(f"Eligible        : {s.eligible}")
    print(f"Rejected        : {s.rejected}")
    print(f"LLM successes   : {llm_ok}")
    print(f"LLM failures    : {llm_failed}")
    print("GitHub statuses :", ", ".join(f"{k}={v}" for k, v in sorted(gh_status_counts.items())))
    print()
    print("Top 5 eligible candidates:")
    for c in top5:
        print(f"  {c.rank}. {c.candidate_name or c.file} - {c.total_score}/100")
    print()
    print(f"Full results written to: {output_path}")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Resume Screening & Ranking System")
    parser.add_argument("--input", required=True, help="Directory containing candidate resume PDFs")
    parser.add_argument("--output", required=True, help="Path to write results.json")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("resume_screener.cli")

    config = Config()
    if config.llm.provider == "none":
        logger.warning(
            "No LLM provider configured (ANTHROPIC_API_KEY / OPENAI_API_KEY not set). "
            "Eligible candidates will be scored using deterministic fallback only."
        )

    logger.info("Running pipeline on input dir: %s", args.input)
    result = run_pipeline(args.input, config)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, indent=2)

    s = result.batch_summary
    logger.info(
        "Done. total=%d parsed=%d failed=%d duplicates=%d eligible=%d rejected=%d -> %s",
        s.total_resumes, s.successfully_parsed, s.failed_to_parse, s.duplicates_found,
        s.eligible, s.rejected, args.output,
    )
    _print_summary(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
