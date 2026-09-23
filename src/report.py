"""Lightweight static HTML report generator.

Reads an already-generated results.json (produced by main.py / pipeline.py)
and renders a single dependency-free HTML file summarizing the batch. Pure
presentation over existing data — no scoring, eligibility, LLM, or GitHub
logic lives here, and nothing in this module makes a network call.

Usage:
    python -m src.report --input ./output/results.json --output ./output/report.html
"""
from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone


def _esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _render_top_candidates_rows(candidates: list[dict]) -> str:
    eligible = [c for c in candidates if c.get("eligible")]
    ranked = sorted(eligible, key=lambda c: c.get("rank") or 999999)[:10]
    if not ranked:
        return "<tr><td colspan='7'>No eligible candidates.</td></tr>"

    rows = []
    for c in ranked:
        bd = c.get("score_breakdown") or {}
        rows.append(
            "<tr>"
            f"<td>{_esc(c.get('rank'))}</td>"
            f"<td>{_esc(c.get('candidate_name') or c.get('file'))}</td>"
            f"<td class='score-total'>{_esc(c.get('total_score'))}</td>"
            f"<td>{_esc(bd.get('ai_project_depth'))}</td>"
            f"<td>{_esc(bd.get('python_backend'))}</td>"
            f"<td>{_esc(bd.get('cloud_fullstack'))}</td>"
            f"<td>{_esc(bd.get('github'))}</td>"
            f"<td>{_esc(bd.get('engineering_depth'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _render_rejected_rows(candidates: list[dict]) -> str:
    rejected = [c for c in candidates if c.get("parse_status") == "ok" and not c.get("eligible")]
    if not rejected:
        return "<tr><td colspan='3'>No rejected candidates.</td></tr>"
    rows = []
    for c in rejected:
        reasons = ", ".join(c.get("rejection_reasons") or []) or "-"
        rows.append(
            "<tr>"
            f"<td>{_esc(c.get('file'))}</td>"
            f"<td>{_esc(c.get('candidate_name'))}</td>"
            f"<td>{_esc(reasons)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _count_by(candidates: list[dict], getter) -> dict:
    counts: dict[str, int] = {}
    for c in candidates:
        key = getter(c)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _render_status_list(counts: dict) -> str:
    if not counts:
        return "-"
    return ", ".join(f"{_esc(k)}: {v}" for k, v in counts.items())


def build_report_html(data: dict, source_path: str) -> str:
    summary = data.get("batch_summary", {})
    candidates = data.get("candidates", [])

    eligible_candidates = [c for c in candidates if c.get("eligible")]
    llm_counts = _count_by(eligible_candidates, lambda c: c.get("llm_status", "unknown"))
    github_counts = _count_by(candidates, lambda c: (c.get("github") or {}).get("status", "unknown"))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Resume Screening Report</title>
<style>
  :root {{
    --bg: #ffffff; --fg: #1a1a1a; --muted: #6b7280; --border: #e5e7eb;
    --accent: #2563eb; --good: #16a34a; --bad: #dc2626; --panel: #f9fafb;
  }}
  body {{
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    background: var(--bg); color: var(--fg); margin: 0; padding: 24px;
    line-height: 1.5;
  }}
  h1 {{ margin-bottom: 4px; }}
  .note {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
    padding: 10px 14px; font-size: 0.9em; color: var(--muted); margin: 12px 0 24px;
  }}
  h2 {{ border-bottom: 2px solid var(--border); padding-bottom: 6px; margin-top: 36px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
  th, td {{ border: 1px solid var(--border); padding: 8px 10px; text-align: left; font-size: 0.92em; }}
  th {{ background: var(--panel); }}
  .score-total {{ font-weight: bold; color: var(--accent); }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 12px 0 24px; }}
  .stat-box {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; }}
  .stat-box .label {{ font-size: 0.8em; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }}
  .stat-box .value {{ font-size: 1.6em; font-weight: bold; }}
  .cat-list {{ padding-left: 20px; }}
  footer {{ color: var(--muted); font-size: 0.85em; margin-top: 40px; border-top: 1px solid var(--border); padding-top: 12px; }}
</style>
</head>
<body>
<h1>AI Resume Screening &amp; Ranking Report</h1>
<div class="note">
  This report is auto-generated from <code>{_esc(source_path)}</code>
  ({_esc(len(candidates))} candidate records). Generated at {_esc(generated_at)}.
  It is a read-only presentation of existing results — no scoring or screening
  logic is executed here.
</div>

<h2>Batch Summary</h2>
<div class="stat-grid">
  <div class="stat-box"><div class="label">Total Resumes</div><div class="value">{_esc(summary.get('total_resumes'))}</div></div>
  <div class="stat-box"><div class="label">Parsed</div><div class="value">{_esc(summary.get('successfully_parsed'))}</div></div>
  <div class="stat-box"><div class="label">Failed</div><div class="value">{_esc(summary.get('failed_to_parse'))}</div></div>
  <div class="stat-box"><div class="label">Duplicates</div><div class="value">{_esc(summary.get('duplicates_found'))}</div></div>
  <div class="stat-box"><div class="label">Eligible</div><div class="value" style="color: var(--good)">{_esc(summary.get('eligible'))}</div></div>
  <div class="stat-box"><div class="label">Rejected</div><div class="value" style="color: var(--bad)">{_esc(summary.get('rejected'))}</div></div>
</div>

<h2>LLM &amp; GitHub Enrichment</h2>
<div class="stat-grid">
  <div class="stat-box"><div class="label">LLM Status (eligible candidates)</div><div>{_render_status_list(llm_counts)}</div></div>
  <div class="stat-box"><div class="label">GitHub Status (all candidates)</div><div>{_render_status_list(github_counts)}</div></div>
</div>

<h2>Top 10 Eligible Candidates</h2>
<table>
  <thead>
    <tr>
      <th>Rank</th><th>Name</th><th>Total</th>
      <th>AI/Agentic/RAG (40)</th><th>Python/Backend (30)</th>
      <th>Cloud/Full-Stack (15)</th><th>GitHub (10)</th><th>Engineering Depth (5)</th>
    </tr>
  </thead>
  <tbody>
    {_render_top_candidates_rows(candidates)}
  </tbody>
</table>

<h2>Rejected Candidates</h2>
<table>
  <thead><tr><th>File</th><th>Name</th><th>Rejection Reasons</th></tr></thead>
  <tbody>
    {_render_rejected_rows(candidates)}
  </tbody>
</table>

<h2>Scoring Categories (100 points total)</h2>
<ul class="cat-list">
  <li><strong>AI/Agentic/RAG Project Depth (40)</strong> — real agentic/RAG/LLM implementation evidence, penalized for shallow API-wrapper or tutorial-style projects.</li>
  <li><strong>Python &amp; Backend Engineering (30)</strong> — Python, FastAPI, async, PostgreSQL, Redis, favoring evidence used in real projects over skill-list mentions.</li>
  <li><strong>Cloud / Deployment / Full-Stack (15)</strong> — GCP/AWS/Azure, Docker, deployment; React/Next.js as supporting signals only.</li>
  <li><strong>GitHub Activity (10)</strong> — recent public activity and relevant/maintained repositories, from live GitHub data.</li>
  <li><strong>Engineering Depth (5)</strong> — testing, architecture, caching, concurrency, failure handling.</li>
</ul>

<footer>Static report — regenerate with <code>python -m src.report --input output/results.json --output output/report.html</code></footer>
</body>
</html>
"""


def generate_report(input_path: str, output_path: str) -> str:
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    html_content = build_report_html(data, input_path)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a static HTML report from results.json")
    parser.add_argument("--input", default="output/results.json", help="Path to results.json")
    parser.add_argument("--output", default="output/report.html", help="Path to write report.html")
    args = parser.parse_args()
    path = generate_report(args.input, args.output)
    print(f"Report written to: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
