"""
app/schemas.py — Pydantic request/response models.

FastAPI uses these to validate incoming JSON and to document the API. They are
separate from the SQLAlchemy models in models.py (which describe the database).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Tutor Mode
# ---------------------------------------------------------------------------
class TutorStartRequest(BaseModel):
    paper_id: int


class TutorGradeRequest(BaseModel):
    paper_id: int
    summary: str = Field(..., min_length=1, description="The user's own-words summary")


class TutorTurn(BaseModel):
    """One line of the conversation. role is who spoke, text is what was said."""
    role: Literal["tutor", "user"]
    text: str


class TutorTurnRequest(BaseModel):
    paper_id: int
    # The full conversation so far (client holds the state; server is stateless).
    transcript: list[TutorTurn]


class TutorFinishRequest(BaseModel):
    paper_id: int
    transcript: list[TutorTurn]
    score: int | None = None  # the grade from the grading step (1..5)


# ---------------------------------------------------------------------------
# Notes + requesting a paper
# ---------------------------------------------------------------------------
class NotesUpdate(BaseModel):
    notes: str = ""


class RequestPaper(BaseModel):
    """Add a specific paper: an arXiv id, an arXiv URL, or a paper title."""
    query: str = Field(..., min_length=2, description="arXiv id / URL / title")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
class SettingsUpdate(BaseModel):
    theme: str | None = None
    notifications_enabled: bool | None = None
    notif_frequency: int | None = Field(default=None, ge=1, le=12)
    quiet_start: int | None = Field(default=None, ge=0, le=23)
    quiet_end: int | None = Field(default=None, ge=0, le=23)


# ---------------------------------------------------------------------------
# Push notifications (Phase 2)
# ---------------------------------------------------------------------------
class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    """Matches the JSON a browser's PushSubscription serializes to."""
    endpoint: str
    keys: PushKeys


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------
class OkResponse(BaseModel):
    ok: bool = True
    detail: Any | None = None
