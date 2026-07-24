"""
app/models.py — the database tables, described as Python classes.

Each class is one table. Each attribute is one column. SQLAlchemy's `JSON`
column type stores Python lists/dicts and works on both SQLite and Postgres.

This is a SINGLE-USER app (it's your personal reading habit), so there's no
users/auth table — just the papers, your study sessions, your settings, and
push subscriptions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    """Timezone-aware 'now' in UTC (avoids the deprecated utcnow())."""
    return datetime.now(timezone.utc)


class Paper(Base):
    """One research paper — either a seed paper or a weekly-fetched new one."""

    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Identity / links ---
    arxiv_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abs_url: Mapped[str | None] = mapped_column(Text, nullable=True)   # arXiv abstract page
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)   # direct PDF link
    authors: Mapped[list] = mapped_column(JSON, default=list)         # list[str]
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Curation metadata (from seed_papers.py) ---
    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tier: Mapped[int | None] = mapped_column(Integer, nullable=True)   # None for weekly papers
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # publication year
    source: Mapped[str] = mapped_column(String(16), default="seed")    # "seed" | "weekly"
    why: Mapped[str | None] = mapped_column(Text, nullable=True)       # seed rationale

    # --- Enrichment (filled by one LLM call in enrich.py) ---
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 1..10
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)        # 1..5 (beginner)
    prerequisites: Mapped[list] = mapped_column(JSON, default=list)               # list[str]
    builds_on: Mapped[list] = mapped_column(JSON, default=list)                   # list[str]
    core_idea: Mapped[str | None] = mapped_column(Text, nullable=True)            # one sentence
    est_reading_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skip_the_math: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Reading state ---
    # status: "unread" -> "studying" -> "read"
    status: Mapped[str] = mapped_column(String(16), default="unread", index=True)
    read_order: Mapped[float] = mapped_column(Float, default=0.0, index=True)  # lower = read sooner
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)  # show under "New this week"

    # --- Personal notes ---
    notes: Mapped[str] = mapped_column(Text, default="")  # free-text notes you jot down

    # --- Spaced repetition ---
    # After you study a paper, it's scheduled to resurface for a quick review.
    next_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0)  # how many reviews done

    # --- "Too hard today" snooze ---
    # When you defer a paper, we push it down the queue for ~2 weeks.
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # A paper can have many study sessions (you can re-study it).
    sessions: Mapped[list["StudySession"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON API responses."""
        return {
            "id": self.id,
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "abs_url": self.abs_url,
            "pdf_url": self.pdf_url,
            "authors": self.authors or [],
            "abstract": self.abstract,
            "topic": self.topic,
            "tier": self.tier,
            "year": self.year,
            "source": self.source,
            "why": self.why,
            "relevance_score": self.relevance_score,
            "difficulty": self.difficulty,
            "prerequisites": self.prerequisites or [],
            "builds_on": self.builds_on or [],
            "core_idea": self.core_idea,
            "est_reading_minutes": self.est_reading_minutes,
            "skip_the_math": self.skip_the_math,
            "status": self.status,
            "read_order": self.read_order,
            "is_new": self.is_new,
            "notes": self.notes or "",
            "next_review": self.next_review.isoformat() if self.next_review else None,
            "review_count": self.review_count or 0,
        }


class StudySession(Base):
    """A completed Tutor Mode session for a paper: score + recap + full transcript."""

    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), index=True)

    score: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 1..5 understanding
    recap: Mapped[list] = mapped_column(JSON, default=list)             # 3 bullet strings
    transcript: Mapped[list] = mapped_column(JSON, default=list)        # list[{role, text}]

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    paper: Mapped["Paper"] = relationship(back_populates="sessions")


class UserSettings(Base):
    """Single-row table holding your app preferences (there's only one 'you')."""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    theme: Mapped[str] = mapped_column(String(8), default="dark")   # "dark" | "light"

    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    notif_frequency: Mapped[int] = mapped_column(Integer, default=3)  # nudges per day
    quiet_start: Mapped[int] = mapped_column(Integer, default=22)     # 24h clock
    quiet_end: Mapped[int] = mapped_column(Integer, default=8)

    # Inferred difficulty level (1-5). "Too hard today" nudges this down so the
    # ranker surfaces easier papers. Starts in the middle.
    level: Mapped[float] = mapped_column(Float, default=3.0)

    def to_dict(self) -> dict:
        return {
            "theme": self.theme,
            "notifications_enabled": self.notifications_enabled,
            "notif_frequency": self.notif_frequency,
            "quiet_start": self.quiet_start,
            "quiet_end": self.quiet_end,
            "level": self.level,
        }


class PushSubscription(Base):
    """A browser's Web Push subscription (endpoint + keys). One per device."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)  # public key from the browser
    auth: Mapped[str] = mapped_column(Text)    # auth secret from the browser
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def to_subscription_info(self) -> dict:
        """Shape pywebpush expects."""
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }
