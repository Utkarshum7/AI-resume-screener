# samples/

**Everything in this folder is synthetic.** The people, email addresses (`@example.com`), and projects are fictional and were written for demonstration. They are not part of, and do not represent, the resume dataset used for the documented production run.

| File | Intended profile |
|---|---|
| `resumes/sample_01_strong_ai_backend.docx` | Python backend engineer with a multi-agent / retrieval project — expected to be **eligible** and score well |
| `resumes/sample_02_shallow_ai_project.docx` | Python developer whose only AI project is a single API call — expected to be **eligible** but with a low AI-depth score (the LLM may classify the project as a shallow wrapper) |
| `resumes/sample_03_frontend_only.docx` | JavaScript/React developer with no Python or AI evidence — expected to be **rejected** |

None of the samples include a GitHub link, so running them never queries a real GitHub account (GitHub status will be `not_provided`).

Run the pipeline on them:

```bash
python main.py --input ./samples/resumes --output ./output/results.json --report
```

Without an LLM key configured, eligible samples are scored with the deterministic fallback; with a key, they receive LLM-based project analysis. Outputs are written to `output/`, which is ignored by Git.
