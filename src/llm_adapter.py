"""Provider-agnostic LLM adapter.

Single entry point: `extract_with_llm(resume_text, config) -> LLMExtraction`.
Provider-specific code (Anthropic vs OpenAI SDK calls, prompt formatting,
JSON-mode wiring) is isolated in this one file so swapping providers/models
never touches pipeline or scoring code.

Design choices:
  - One call per eligible candidate (not per category) — the requested
    structured schema (LLMExtraction) already covers all categories in one
    response, minimizing token spend.
  - Ineligible candidates never reach this module at all (enforced by the
    pipeline, not here) — this is the main token/cost saver.
  - Any failure (network, auth, malformed JSON, timeout) raises
    `LLMCallError`; the pipeline catches it, marks `llm_status="failed"`,
    and falls back to deterministic-only scoring for that one candidate.
"""
from __future__ import annotations

import json

from src.config import Config
from src.models import LLMExtraction

SYSTEM_PROMPT = (
    "You are an expert technical resume reviewer for an SDE internship "
    "requiring strong Python and practical AI/agentic project experience. "
    "You will be given the raw text of one resume that has ALREADY passed a "
    "hard eligibility filter (it contains both Python and AI/agentic "
    "evidence). Your job is ONLY to produce structured evidence and "
    "qualitative classifications — you must NOT compute or return any "
    "numeric score. A downstream deterministic program converts your "
    "evidence into the final score.\n\n"
    "For every project or experience entry you find, classify its `depth` "
    "honestly:\n"
    "- real_implementation: clear evidence of workflow/orchestration, "
    "retrieval, state management, backend logic, evaluation, or non-trivial "
    "product logic (not just an API call).\n"
    "- shallow_wrapper: the project is essentially one LLM/API call with no "
    "meaningful workflow, retrieval, state, or backend logic around it.\n"
    "- tutorial_style: listed without implementation detail or evidence of "
    "real ownership (reads like a copied tutorial/course project).\n"
    "- skill_mention_only: a framework/tool name appears in a skills list "
    "with no project describing how it was used.\n\n"
    "Be skeptical: do not award real_implementation just because a framework "
    "name appears. Look for concrete implementation details."
)

USER_PROMPT_TEMPLATE = (
    "Resume text:\n---\n{resume_text}\n---\n\n"
    "Return a JSON object matching exactly this schema (no extra keys, no "
    "prose outside the JSON):\n{schema}\n"
)


class LLMCallError(Exception):
    pass


def _schema_hint() -> str:
    return json.dumps(LLMExtraction.model_json_schema(), indent=None)


def _build_prompt(resume_text: str) -> str:
    # Trim to keep token usage bounded — evidence-relevant content is almost
    # always within the first ~6000 characters of a 1-3 page resume.
    trimmed = resume_text[:6000]
    return USER_PROMPT_TEMPLATE.format(resume_text=trimmed, schema=_schema_hint())


def _parse_response_json(raw: str) -> LLMExtraction:
    raw = raw.strip()
    # Some models wrap JSON in ```json fences despite instructions — strip defensively.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMCallError(f"invalid_json_response: {e}") from e
    try:
        return LLMExtraction.model_validate(data)
    except Exception as e:  # noqa: BLE001 - pydantic ValidationError etc.
        raise LLMCallError(f"schema_validation_failed: {e}") from e


def _call_anthropic(resume_text: str, config: Config) -> LLMExtraction:
    try:
        import anthropic
    except ImportError as e:
        raise LLMCallError(f"anthropic_sdk_not_installed: {e}") from e

    client = anthropic.Anthropic(api_key=config.llm.anthropic_api_key)
    try:
        response = client.messages.create(
            model=config.llm.anthropic_model,
            max_tokens=config.llm.max_output_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(resume_text)}],
            timeout=config.llm.request_timeout_seconds,
        )
    except Exception as e:  # noqa: BLE001 - network/auth/rate-limit, all per-candidate
        raise LLMCallError(f"anthropic_request_failed: {e}") from e

    text_parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return _parse_response_json("".join(text_parts))


def _call_openai(resume_text: str, config: Config) -> LLMExtraction:
    try:
        import openai
    except ImportError as e:
        raise LLMCallError(f"openai_sdk_not_installed: {e}") from e

    client = openai.OpenAI(api_key=config.llm.openai_api_key)
    try:
        response = client.chat.completions.create(
            model=config.llm.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(resume_text)},
            ],
            response_format={"type": "json_object"},
            max_tokens=config.llm.max_output_tokens,
            timeout=config.llm.request_timeout_seconds,
        )
    except Exception as e:  # noqa: BLE001
        raise LLMCallError(f"openai_request_failed: {e}") from e

    content = response.choices[0].message.content or ""
    return _parse_response_json(content)


def _call_gemini(resume_text: str, config: Config) -> LLMExtraction:
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise LLMCallError(f"gemini_sdk_not_installed: {e}") from e

    client = genai.Client(api_key=config.llm.gemini_api_key)
    try:
        response = client.models.generate_content(
            model=config.llm.gemini_model,
            contents=_build_prompt(resume_text),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=LLMExtraction,
                max_output_tokens=config.llm.max_output_tokens,
                http_options=types.HttpOptions(timeout=int(config.llm.request_timeout_seconds * 1000)),
            ),
        )
    except Exception as e:  # noqa: BLE001 - network/auth/rate-limit, all per-candidate
        raise LLMCallError(f"gemini_request_failed: {e}") from e

    text = getattr(response, "text", None) or ""
    return _parse_response_json(text)


def extract_with_llm(resume_text: str, config: Config) -> LLMExtraction:
    provider = config.llm.provider
    if provider == "anthropic":
        return _call_anthropic(resume_text, config)
    if provider == "openai":
        return _call_openai(resume_text, config)
    if provider == "gemini":
        return _call_gemini(resume_text, config)
    raise LLMCallError(
        "no_llm_provider_configured: set ANTHROPIC_API_KEY, OPENAI_API_KEY, "
        "or GEMINI_API_KEY in the environment (see .env.example)"
    )
