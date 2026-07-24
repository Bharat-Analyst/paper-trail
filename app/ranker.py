"""
app/ranker.py — decide the "read next" order for unread papers.

The queue should adapt as you read: once you finish a paper, papers that were
waiting on it become better candidates. So we RECOMPUTE the whole order every
time (on init, on weekly append, and right after you mark a paper read).

Scoring intuition (weights live in config.yaml -> ranker):
    high relevance        -> read sooner
    high difficulty       -> read later   (we're a beginner)
    higher tier number    -> read later   (foundations first)
    prerequisites already read -> big boost (it's now "unlocked")
    brand-new this week    -> small nudge toward the top

Lower final `read_order` = surfaces earlier in the feed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Paper, UserSettings


def _tokens(text: str) -> set[str]:
    """Lowercase word set, for loose prerequisite matching."""
    return {w for w in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(w) > 2}


def read_vocabulary(db: Session) -> set[str]:
    """Pooled title+topic word set of every paper you've marked read."""
    vocab: set[str] = set()
    for p in db.scalars(select(Paper).where(Paper.status == "read")).all():
        vocab |= _tokens(p.title or "")
        vocab |= _tokens(p.topic or "")
    return vocab


def _prereqs_satisfied(paper: Paper, read_vocabulary: set[str]) -> bool:
    """
    Rough check: are this paper's prerequisites covered by papers already read?

    We compare the words in each prerequisite against the pooled vocabulary of
    titles + topics of papers you've marked read. It's a heuristic, not exact
    citation tracking — good enough to bubble "unlocked" papers upward.
    """
    prereqs = paper.prerequisites or []
    if not prereqs:
        return True  # nothing required -> considered satisfied
    for prereq in prereqs:
        prereq_tokens = _tokens(prereq)
        # Satisfied if most of the prerequisite's words appear in what you've read.
        if prereq_tokens and len(prereq_tokens & read_vocabulary) >= max(1, len(prereq_tokens) // 2):
            continue
        return False
    return True


def compute_read_order(db: Session) -> None:
    """
    Recompute `read_order` for every UNREAD paper and save it.

    Read papers keep a read_order of 0 (they're filtered out of the feed anyway).
    """
    weights = settings.ranker
    now = datetime.now(timezone.utc)

    # Build the "vocabulary" of everything you've already read.
    read_papers = db.scalars(select(Paper).where(Paper.status == "read")).all()
    vocab: set[str] = set()
    for p in read_papers:
        vocab |= _tokens(p.title or "")
        vocab |= _tokens(p.topic or "")

    # The reader's inferred difficulty level (nudged by "Too hard today").
    user = db.scalar(select(UserSettings).where(UserSettings.id == 1))
    level = user.level if user and user.level else 3.0

    unread = db.scalars(select(Paper).where(Paper.status != "read")).all()

    scored: list[tuple[float, Paper]] = []
    for paper in unread:
        relevance = paper.relevance_score or 5
        difficulty = paper.difficulty or 3

        score = 0.0
        score += weights["relevance_weight"] * relevance
        score -= weights["difficulty_weight"] * difficulty
        if _prereqs_satisfied(paper, vocab):
            score += weights["prereq_bonus"]
        if paper.is_new:
            score += weights["new_bonus"]

        # Papers harder than your inferred level are pushed down (grows as you
        # defer hard papers, so easier ones surface).
        score -= weights.get("level_gap_weight", 1.0) * max(0.0, difficulty - level)

        # Snoozed ("too hard today") papers sink for ~2 weeks.
        if paper.snoozed_until is not None:
            snoozed = paper.snoozed_until
            if snoozed.tzinfo is None:
                snoozed = snoozed.replace(tzinfo=timezone.utc)
            if snoozed > now:
                score -= weights.get("snooze_penalty", 100.0)

        scored.append((score, paper))

    # Highest score first. Assign read_order = 1, 2, 3, ... (lower surfaces first).
    scored.sort(key=lambda t: t[0], reverse=True)
    for position, (_, paper) in enumerate(scored, start=1):
        paper.read_order = float(position)

    # Mark read papers with 0 so they never compete in the feed ordering.
    for p in read_papers:
        p.read_order = 0.0

    db.commit()
