# AI Resume Screening & Ranking System

A small, production-minded CLI pipeline that ingests a folder of resume
PDFs, applies deterministic hard-eligibility filters (Python + AI/agentic
evidence), scores eligible candidates against a fixed 100-point rubric using
a single structured LLM call per candidate plus deterministic scoring logic,
enriches scores with public GitHub activity, and writes a ranked
`results.json`.

## Setup

```bash
cd resume_screener
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then fill in ANTHROPIC_API_KEY or OPENAI_API_KEY (optional)
```

## Run

```bash
python main.py --input ./resumes --output ./output/results.json
```

Or against the provided 50-resume dataset:

```bash
python main.py --input "../resume_dataset_50 (1)/resumes" --output ./output/results.json
```

No API key is required to run — see [LLM behavior without a key](#llm-behavior-without-a-key) below.

## Run tests

```bash
python -m pytest tests/ -v
```

17/17 tests pass, covering eligibility (5 cases), GitHub URL extraction (6
cases including annotation-only and malformed URLs), scoring/penalties (4
cases), and reliability (corrupt PDF, LLM failure — 2 cases).

---

## Design Decisions

### Filtering strategy (eligibility)
Eligibility is **100% deterministic** — no LLM in the loop. A candidate is
eligible only if the normalized resume text contains (a) the word `python`
as a real token, and (b) at least one of a curated list of AI/agentic/RAG
patterns (LangChain, LangGraph, RAG, embeddings, vector search, tool-calling,
agentic, LLM/GPT/OpenAI/Anthropic mentions, HuggingFace, etc.). This keeps
the hard gate reproducible, free, and auditable — the same input always
produces the same eligibility decision, which the assignment explicitly
requires ("hard eligibility checks outside the LLM where possible").
JS/React/Java presence never disqualifies a candidate as long as Python + AI
evidence both exist, per spec.

**Dataset-verified problem this design solves**: while inspecting all 50
resumes before writing any code, I found that **24 of 50** candidates only
expose their GitHub profile as a clickable PDF hyperlink annotation — the
visible text just says "GitHub" with no URL printed. A text-only regex
approach would have silently missed GitHub data for nearly half the
dataset. `pdf_extract.py` therefore extracts both the plain text **and**
the raw `/Annots → /A → /URI` hyperlink list, and `extract_fields.py` merges
both sources (deduplicated, http→https normalized, validated) before
eligibility/scoring ever run.

### Scoring strategy
The five category weights (`AI/Agentic/RAG=40, Python/Backend=30,
Cloud/Fullstack=15, GitHub=10, Engineering Depth=5`) are fixed exactly as
specified and enforced as hard caps in `config.py` / `scoring.py`.

Per the corrected architecture: **the LLM never returns a number.** For each
eligible candidate, one structured call (`LLMExtraction` schema) returns
per-project `depth` classifications (`real_implementation` /
`shallow_wrapper` / `tutorial_style` / `skill_mention_only`) with evidence
and reasoning strings, plus category-tagged evidence lists. Python code in
`scoring.py` is the *only* place that turns this into numbers:

- **AI/Agentic/RAG (40)**: each AI-tagged project contributes base points
  (capped at 3 projects counted); `shallow_wrapper` and `tutorial_style`
  projects then have an **explicit, separately-recorded penalty** (8–10
  points, bounded within the assignment's 5–15 range) deducted — visible as
  its own `penalties[]` entry in the output, not silently baked into a lower
  base score. Total is clamped to `[0, 40]`.
- **Python/Backend (30)**, **Cloud/Fullstack (15)**, **Engineering Depth
  (5)**: deterministic keyword-in-normalized-text scoring (python, fastapi,
  django, postgresql, redis, async, gcp/aws/azure, docker, kubernetes,
  testing, etc.), with a small bounded bonus if the LLM's evidence lists for
  that category are non-empty (rewards "used in a project" over "listed as
  a skill"). Everything is capped at the category weight.
- **GitHub (10)**: computed entirely in `github_enrich.py` (0–5 recent
  activity + 0–5 relevant/maintained repos), independent of the LLM.

Every number in `score_breakdown` is reconstructable from `matched_skills`,
`penalties`, and the candidate's `github` block already present in the same
JSON record — nothing is a black box.

### LLM usage
- One call per **eligible** candidate only — ineligible candidates (17/50 in
  this dataset) never reach the LLM at all, which is the main cost/token
  saver requested.
- Structured JSON output validated against a Pydantic schema
  (`models.LLMExtraction`); invalid/unparseable JSON is caught and treated
  as a per-candidate LLM failure, not a crash.
- Provider-specific code is isolated in `llm_adapter.py` behind one function
  `extract_with_llm(text, config)`; swapping Anthropic ↔ OpenAI (or adding a
  third provider) never touches pipeline/scoring code.
- On any LLM failure (network, auth, timeout, bad JSON, no key configured),
  the candidate is still scored — via the deterministic fallback formula in
  `scoring.py` — and `llm_status="failed"` plus `llm_error` are recorded
  directly in `results.json` so the degradation is visible, not hidden.

#### LLM behavior without a key
This evaluation environment has no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` set.
The generated `output/results.json` in this submission was produced with
**no LLM configured**, so every eligible candidate shows `llm_status:
"failed"` with `llm_error: "no_llm_provider_configured..."` and was scored
using the deterministic fallback path (capped lower for the AI-depth
category specifically because depth/shallowness can't be judged without an
LLM — see `_FALLBACK_AI_SCORE_CAP` in `scoring.py`). This is not a bug: it's
the exact "LLM must fail gracefully, per-resume, not batch-fatal" behavior
the assignment requires, demonstrated end-to-end. Add a real key to `.env`
and re-run to get full LLM-informed depth scoring.

### GitHub scoring
`github_enrich.py` calls the public GitHub REST API (`/users/{u}` +
`/users/{u}/repos`), no token required. Handles: 404 (not found), 403/rate
limit headers (stops making further calls for the rest of the run and marks
remaining candidates `rate_limited` rather than hammering the API), timeout,
and generic network errors — all return a typed `GitHubEnrichment.status`,
never an exception. An in-run dict cache keyed by lowercased username avoids
redundant calls (useful since some resumes repeat the same GitHub link
several times via duplicate annotations).

**Observed in this run**: the dataset has ~43 distinct real GitHub
usernames, requiring ~2 calls each (~86 calls) against the unauthenticated
60-req/hr GitHub limit — so most candidates in the committed
`output/results.json` show `github.status: "rate_limited"` after the first
~30 profiles. This is the *expected, documented, graceful-degradation
behavior*, not a failure of the pipeline. Setting `GITHUB_TOKEN` in `.env`
(free, no special scope needed) raises the limit to 5000/hr, comfortably
covering the full batch — re-running with a token produces full GitHub
enrichment for all candidates.

---

## If I Had More Time

1. **Section-aware extraction** — currently eligibility/skills matching runs
   over the whole normalized document. Splitting into Skills/Experience/
   Projects sections (even a lightweight heading-regex split) would let
   scoring weight "used in a project" evidence more precisely than the
   current skills-catalog + LLM-evidence-count heuristic.
2. **Persistent GitHub cache** — an on-disk JSON cache keyed by username
   with a TTL would let re-runs (e.g. while iterating on scoring logic)
   avoid re-hitting the rate limit every time. Deliberately not built now
   per the "no persistent caching until core is done" instruction.
3. **Bounded-concurrency LLM/GitHub calls** — the 33 eligible candidates are
   currently processed sequentially; a bounded `ThreadPoolExecutor` (e.g.
   concurrency=5) for the LLM + GitHub calls would meaningfully cut wall
   time on larger batches without the complexity of full async.
4. **Two-column resume layout handling** — spot-checked one resume
   (`candidate_35.pdf`) where `pdfplumber`'s default text order interleaves
   a two-column header, splitting the candidate's name across two extracted
   lines ("<redacted>" / "<redacted>"). A layout-aware
   extraction pass (e.g. clustering by x-coordinate) would fix this class of
   name-extraction error without needing full NLP.
5. **FastAPI wrapper** (`POST /screen`, `GET /results`) around the existing
   `pipeline.run_pipeline()` — the core logic already returns a clean
   Pydantic model, so this would be a thin adapter layer, explicitly
   deferred as a bonus per the assignment's scope guardrails.

---

## Project Structure

```
resume_screener/
  src/
    ingest.py            # directory walk, SHA-256 dedup
    pdf_extract.py        # deterministic text + hyperlink-annotation extraction
    text_normalize.py     # whitespace/unicode cleanup shared by extraction+eligibility
    extract_fields.py     # deterministic name/email/GitHub/skills extraction
    eligibility.py         # deterministic Python+AI hard gate
    llm_adapter.py         # provider-agnostic structured LLM call (1 per eligible candidate)
    scoring.py              # deterministic scoring formulas + bounded penalties
    github_enrich.py       # public GitHub API, cache, rate-limit handling
    models.py               # Pydantic schemas (LLM contract + output contract)
    config.py               # weights, thresholds, model names, env loading
    pipeline.py              # orchestration
  tests/
    test_eligibility.py
    test_github_extract.py
    test_scoring.py
    test_reliability.py
  main.py                    # CLI entry point
  output/results.json        # generated output for the provided 50-resume dataset
  requirements.txt
  .env.example
```

## Known Limitations

- Name extraction is a first-line heuristic; fails on the rare two-column
  header layout described above (1/50 observed).
- The AI/agentic keyword list is curated, not exhaustive — a framework not
  in the list would need adding to `config.py`.
- Without an LLM key, AI-project-depth scoring is capped lower (fallback
  mode) since shallow-vs-real depth genuinely cannot be judged from keywords
  alone — this is an intentional, documented trade-off, not an oversight.
