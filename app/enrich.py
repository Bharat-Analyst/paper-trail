"""
app/enrich.py — turn a raw paper into structured metadata using ONE LLM call.

For each paper we ask the model to read the title + abstract and return a small
JSON object scoring it *for a beginner*: how relevant, how hard, what you should
know first, the single-sentence core idea, etc.

Robustness: models occasionally wrap JSON in prose or add a stray comma. We ask
for JSON mode, then parse defensively, and RETRY up to 3 times with a stricter
instruction if parsing fails.
"""

from __future__ import annotations

import json
import re

from app.llm import ask

# How many times to re-ask if the model returns something we can't parse.
_MAX_RETRIES = 3

_SYSTEM = (
    "You are a kind, precise research mentor helping a motivated BEGINNER build "
    "a reading habit in AI/ML. You always answer in strict JSON when asked."
)


def _build_prompt(paper: dict, stricter: bool = False) -> str:
    """Construct the enrichment prompt for one paper."""
    tier = paper.get("tier")
    tier_hint = (
        f"This paper was hand-curated at tier {tier} (0 = foundational/easy, "
        f"4 = advanced). Let that inform difficulty, but judge from the abstract."
        if tier is not None
        else "This paper was auto-fetched (no curated tier)."
    )

    base = f"""Analyze this research paper FOR A COMPLETE BEGINNER and return JSON.

TITLE: {paper.get('title', '')}

ABSTRACT: {paper.get('abstract') or '(abstract unavailable — infer from the title)'}

CONTEXT: {tier_hint}

Return a JSON object with EXACTLY these keys:
{{
  "relevance_score": <integer 1-10, how important this is for understanding modern LLMs/AI>,
  "difficulty": <integer 1-5, how hard for a BEGINNER: 1=very approachable, 5=very hard>,
  "prerequisites": [<short strings: concepts to understand FIRST, e.g. "neural networks", "attention">],
  "builds_on": [<short strings: earlier ideas/papers this extends>],
  "core_idea": "<ONE plain-English sentence a beginner can understand>",
  "est_reading_minutes": <integer, realistic first-pass reading time in minutes>,
  "skip_the_math": <true if a beginner can safely skim the equations, else false>
}}

Rules:
- core_idea MUST be a single clear sentence, no jargon dumps.
- Keep prerequisites and builds_on short (max 4 items each).
- Output ONLY the JSON object. No markdown, no commentary."""

    if stricter:
        base += (
            "\n\nIMPORTANT: Your previous answer was not valid JSON. Respond with "
            "ONLY the raw JSON object — no code fences, no text before or after."
        )
    return base


def _extract_json(text: str) -> dict:
    """
    Best-effort extraction of a JSON object from the model's reply.

    Handles the common cases: clean JSON, JSON inside ```json fences, or JSON
    with surrounding prose. Raises ValueError if nothing parseable is found.
    """
    text = text.strip()

    # Strip Markdown code fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    # Fast path: the whole thing is JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: grab the first {...} block and try that.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError("No JSON object found in model output.")


def _coerce(raw: dict) -> dict:
    """Clamp/normalize the model's values so the DB always gets sane types."""

    def _int(value, lo, hi, default):
        try:
            return max(lo, min(hi, int(value)))
        except (TypeError, ValueError):
            return default

    def _list(value):
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()][:4]
        return []

    return {
        "relevance_score": _int(raw.get("relevance_score"), 1, 10, 5),
        "difficulty": _int(raw.get("difficulty"), 1, 5, 3),
        "prerequisites": _list(raw.get("prerequisites")),
        "builds_on": _list(raw.get("builds_on")),
        "core_idea": (str(raw.get("core_idea", "")).strip() or "Core idea unavailable."),
        "est_reading_minutes": _int(raw.get("est_reading_minutes"), 5, 240, 30),
        "skip_the_math": bool(raw.get("skip_the_math", False)),
    }


def enrich_paper(paper: dict) -> dict:
    """
    Run one enrichment call for `paper` (a dict with at least title + abstract).

    Returns the normalized enrichment dict. If every retry fails, returns a
    safe fallback so the pipeline never crashes on a single bad paper.
    """
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        prompt = _build_prompt(paper, stricter=(attempt > 0))
        try:
            reply = ask(prompt, system=_SYSTEM, json_mode=True, temperature=0.2)
            return _coerce(_extract_json(reply))
        except Exception as exc:  # JSON parse error, API error, etc.
            last_error = exc
            continue

    # All retries exhausted — return neutral defaults and let the caller log it.
    print(f"  ⚠️  Enrichment failed for '{paper.get('title')}': {last_error}")
    return placeholder_enrichment()


def placeholder_enrichment() -> dict:
    """
    Neutral enrichment used by `--mode init --skip-enrich` (fast smoke test) and
    as the fallback when the LLM is unavailable. No API call is made.
    """
    return {
        "relevance_score": 5,
        "difficulty": 3,
        "prerequisites": [],
        "builds_on": [],
        "core_idea": "(Not yet analyzed — run init without --skip-enrich to fill this in.)",
        "est_reading_minutes": 30,
        "skip_the_math": False,
    }
