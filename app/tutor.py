"""
app/tutor.py — the brain of Tutor Mode.

Tutor Mode is a guided, chat-like study loop for one paper:
  1. START   — show title + abstract, ask you to summarize the core idea.
  2. GRADE   — score your summary 1-5, say what you got RIGHT, what you MISSED,
               and correct you gently (from scratch if you're badly off).
  3. TURN    — 2-3 progressively deeper Socratic follow-up questions, each one
               reacting to your previous answer and going a layer deeper.
  4. RECAP   — a 3-bullet "what to remember" summary; the paper is marked read.

The server is STATELESS: the browser holds the running transcript and sends it
back each turn. This module just builds prompts and parses the model's replies.

Tone rule threaded through every prompt: warm, encouraging, never harsh — the
reader is a motivated beginner.
"""

from __future__ import annotations

import json
import re

from app.llm import ask

# How many Socratic follow-up questions to ask after grading the summary.
FOLLOWUP_TARGET = 3

_SYSTEM = (
    "You are PaperPilot's tutor: a warm, encouraging mentor teaching a motivated "
    "BEGINNER to understand AI/ML research papers. You are never condescending or "
    "harsh. You explain in plain language, use tiny analogies when helpful, and "
    "celebrate what the learner got right before correcting what they missed."
)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of the model reply (tolerant of fences/prose)."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _transcript_to_text(transcript: list[dict]) -> str:
    """Render the conversation as a readable script for the model's context."""
    lines = []
    for turn in transcript:
        who = "TUTOR" if turn.get("role") == "tutor" else "LEARNER"
        lines.append(f"{who}: {turn.get('text', '')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 1 — START
# ---------------------------------------------------------------------------
def start_prompt_message() -> str:
    """The fixed opening instruction shown to the learner (no LLM call needed)."""
    return (
        "Take a moment to read the abstract above. When you're ready, **summarize "
        "the paper's core idea in your own words** — a few sentences is perfect. "
        "Don't worry about getting it perfect; this is how we find out what to "
        "focus on together."
    )


# ---------------------------------------------------------------------------
# Step 2 — GRADE the learner's summary
# ---------------------------------------------------------------------------
def grade_summary(title: str, abstract: str | None, summary: str) -> dict:
    """
    Score the learner's summary and return structured feedback.

    Returns a dict:
      score (1-5), right, wrong_missed, correction, from_scratch, message
    `message` is a ready-to-display, friendly write-up built from the parts.
    """
    prompt = f"""A beginner is studying this paper and wrote a summary of its core idea.
Grade their understanding kindly and helpfully.

PAPER TITLE: {title}

ABSTRACT: {abstract or '(abstract unavailable)'}

THE LEARNER'S SUMMARY: "{summary}"

Return ONLY a JSON object with these keys:
{{
  "score": <integer 1-5, how well they understood the core idea>,
  "right": "<specific things they got RIGHT — quote/point to their actual words>",
  "wrong_missed": "<what they got WRONG or MISSED, specific and concrete>",
  "correction": "<plain-language correction that fills the gaps>",
  "from_scratch": "<IF their score is 1 or 2, a short from-scratch explanation of the core idea for a beginner; otherwise an empty string>"
}}

Be warm and encouraging. Even a low score should feel like a helpful nudge, not a judgment."""

    reply = ask(prompt, system=_SYSTEM, json_mode=True, temperature=0.3)
    data = _extract_json(reply)

    score = int(data.get("score", 3))
    score = max(1, min(5, score))
    right = str(data.get("right", "")).strip()
    wrong_missed = str(data.get("wrong_missed", "")).strip()
    correction = str(data.get("correction", "")).strip()
    from_scratch = str(data.get("from_scratch", "")).strip()

    # Build a clean, readable message from the parts. Score shown as dots.
    dots = "●" * score + "○" * (5 - score)
    parts = [f"**Understanding** {dots}"]
    if right:
        parts.append(f"**What you got right:** {right}")
    if wrong_missed:
        parts.append(f"**What to sharpen:** {wrong_missed}")
    if correction:
        parts.append(f"**The fuller picture:** {correction}")
    if from_scratch:
        parts.append(f"**From scratch:** {from_scratch}")
    message = "\n\n".join(parts)

    return {
        "score": score,
        "right": right,
        "wrong_missed": wrong_missed,
        "correction": correction,
        "from_scratch": from_scratch,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Step 3 — TURN (Socratic follow-up)
# ---------------------------------------------------------------------------
def next_turn(title: str, abstract: str | None, transcript: list[dict]) -> dict:
    """
    Decide the next tutor move given the conversation so far.

    Returns:
      {"done": False, "question": "..."}  -> ask another, deeper question
      {"done": True}                      -> enough questions; time to recap
    """
    # The learner's first message is the summary; each later one answers a
    # follow-up. Count how many follow-ups they've already answered.
    learner_turns = sum(1 for t in transcript if t.get("role") == "user")
    followups_answered = max(0, learner_turns - 1)

    if followups_answered >= FOLLOWUP_TARGET:
        return {"done": True}

    depth = followups_answered + 1  # this will be follow-up #1, #2, or #3
    script = _transcript_to_text(transcript)

    prompt = f"""You are tutoring a beginner through this paper via Socratic questioning.

PAPER TITLE: {title}
ABSTRACT: {abstract or '(abstract unavailable)'}

CONVERSATION SO FAR:
{script}

Ask ONE follow-up question — this is follow-up #{depth} of {FOLLOWUP_TARGET}.
Requirements:
- React briefly to the learner's LAST answer (a warm one-liner acknowledging it).
- Then ask a single question that goes ONE LAYER DEEPER than the last one.
- Deeper means: from "what" toward "why/how/when it breaks/how it connects".
- Keep it answerable by a beginner who has only read the abstract. No trick questions.
- Output ONLY the question text (your one-line reaction may precede it). No JSON, no preamble labels."""

    question = ask(prompt, system=_SYSTEM, temperature=0.5).strip()
    return {"done": False, "question": question}


# ---------------------------------------------------------------------------
# Step 4 — RECAP
# ---------------------------------------------------------------------------
def make_recap(title: str, abstract: str | None, transcript: list[dict]) -> dict:
    """
    Produce a 3-bullet 'what to remember' recap of the whole session.

    Returns {"recap": [b1, b2, b3], "message": "..."} where message is the
    formatted closing bubble.
    """
    script = _transcript_to_text(transcript)
    prompt = f"""The study session for this paper is ending.

PAPER TITLE: {title}
ABSTRACT: {abstract or '(abstract unavailable)'}

FULL CONVERSATION:
{script}

Write a short "What to remember" recap as EXACTLY 3 bullet points that capture the
most important, beginner-friendly takeaways from this paper and conversation.

Return ONLY a JSON object:
{{ "recap": ["<bullet 1>", "<bullet 2>", "<bullet 3>"] }}

Each bullet: one sentence, plain language, genuinely memorable."""

    try:
        reply = ask(prompt, system=_SYSTEM, json_mode=True, temperature=0.3)
        data = _extract_json(reply)
        bullets = [str(b).strip() for b in data.get("recap", []) if str(b).strip()]
    except Exception:
        bullets = []

    # Safety net so the UI always shows three bullets.
    while len(bullets) < 3:
        bullets.append("Revisit this paper's abstract in a week to reinforce it.")
    bullets = bullets[:3]

    message = "**Nice work — you studied this one.**\n\n**What to remember:**\n" + \
        "\n".join(f"- {b}" for b in bullets)

    return {"recap": bullets, "message": message}
