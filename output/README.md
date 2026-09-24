# output/

Generated files are written here when you run the pipeline:

| File | Produced by | Contents |
|---|---|---|
| `results.json` | `python main.py --input <dir> --output ./output/results.json` | Batch summary plus one record per input file: parse status, extracted fields, eligibility and rejection reasons, LLM status, score breakdown, penalties, and GitHub enrichment |
| `report.html` | the same command with `--report`, or `python -m src.report --input output/results.json --output output/report.html` | Static HTML report: batch summary, LLM/GitHub status counts, top 10 candidates with score breakdowns, rejected candidates with reasons, scoring categories |

Open `report.html` directly in a browser.

**Generated outputs are intentionally not committed.** They contain candidate names, email addresses, and GitHub usernames taken from the input resumes. Everything in this folder except this README is ignored by Git (see `.gitignore`). Aggregate figures from the original production run are documented in the main [README](../README.md#example-run-production-dataset), without candidate identities.
