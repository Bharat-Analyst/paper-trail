"""
app/main_api.py — the FastAPI application.

This single service does two things:
  1. Serves the JSON API under /api/...
  2. Serves the PWA (HTML/CSS/JS/manifest/service worker) as static files.

So one Render web service hosts the whole app.

Run locally:
    uvicorn app.main_api:app --reload
Then open http://localhost:8000
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, create_tables, get_db
from app.enrich import enrich_paper
from app.models import Paper, PushSubscription, StudySession, UserSettings
from app.ranker import _tokens, compute_read_order
from app.sources import arxiv
from app import push as push_module
from app import scheduler as scheduler_module
from app import tutor
from app.schemas import (
    NotesUpdate,
    OkResponse,
    PushSubscriptionIn,
    RequestPaper,
    SettingsUpdate,
    TutorFinishRequest,
    TutorGradeRequest,
    TutorStartRequest,
    TutorTurnRequest,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# ---------------------------------------------------------------------------
# App lifespan: run once at startup, once at shutdown.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Make sure tables exist (idempotent) and there's a settings row.
    create_tables()
    _ensure_settings_row()
    # Start the local hourly nudge scheduler (harmless if push isn't configured).
    try:
        scheduler_module.start_scheduler()
    except Exception as exc:
        print(f"Scheduler did not start: {exc}")
    yield
    scheduler_module.shutdown_scheduler()


app = FastAPI(title="PaperPilot", lifespan=lifespan)


def _ensure_settings_row() -> None:
    """Create the single UserSettings row (id=1) if it doesn't exist yet."""
    db = SessionLocal()
    try:
        row = db.scalar(select(UserSettings).where(UserSettings.id == 1))
        if row is None:
            notif = settings.notifications
            row = UserSettings(
                id=1,
                theme="light",
                notifications_enabled=False,
                notif_frequency=int(notif.get("frequency", 3)),
                quiet_start=int(notif.get("quiet_start", 22)),
                quiet_end=int(notif.get("quiet_end", 8)),
            )
            db.add(row)
            db.commit()
    finally:
        db.close()


def _get_paper_or_404(db: Session, paper_id: int) -> Paper:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


# ===========================================================================
# FEED
# ===========================================================================
@app.get("/api/feed")
def get_feed(
    q: str | None = Query(default=None, description="Free-text search"),
    topic: str | None = Query(default=None, description="Exact topic"),
    year: int | None = Query(default=None, description="Exact publication year"),
    max_difficulty: int | None = Query(default=None, ge=1, le=5, description="Difficulty ≤ this"),
    status: str = Query(default="unread", description="unread | read | all"),
    recency: str | None = Query(default=None, description="week | month (by date added)"),
    sort: str = Query(default="recommended", description="recommended|difficulty|reading_time|year|relevance"),
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=10, ge=1, le=50, description="cards per page"),
    db: Session = Depends(get_db),
):
    """
    Return the ranked reading feed, optionally filtered/searched.

    Query params (all optional):
      q              free-text match across title, core idea, topic, authors
      tier           keep only this tier
      topic          keep only this topic
      max_difficulty keep only papers at or below this difficulty (1-5)
      status         "unread" (default), "read", or "all"

    Response:
      { "new_this_week": [...], "queue": [...], "count": N }
    """
    stmt = select(Paper)

    # --- status ---
    if status == "unread":
        stmt = stmt.where(Paper.status != "read")
    elif status == "read":
        stmt = stmt.where(Paper.status == "read")
    # "all" -> no status filter

    # --- structured filters ---
    if topic:
        stmt = stmt.where(Paper.topic == topic)
    if year is not None:
        stmt = stmt.where(Paper.year == year)
    if max_difficulty is not None:
        stmt = stmt.where(Paper.difficulty <= max_difficulty)

    # --- recency (based on when the paper was ADDED to your list) ---
    if recency in ("week", "month"):
        cutoff = datetime.now(timezone.utc) - timedelta(days=7 if recency == "week" else 30)
        stmt = stmt.where(Paper.created_at >= cutoff)

    papers = db.scalars(stmt).all()

    # --- free-text search (done in Python so it can span authors JSON too) ---
    if q:
        needle = q.lower().strip()
        def matches(p: Paper) -> bool:
            haystack = " ".join([
                p.title or "",
                p.core_idea or "",
                p.topic or "",
                " ".join(p.authors or []),
            ]).lower()
            return needle in haystack
        papers = [p for p in papers if matches(p)]

    # One combined list — every matching paper (no locked/new split).
    queue_papers = list(papers)

    # --- sort ---
    queue_papers.sort(key=_sort_key(sort))

    # --- paginate ---
    total = len(queue_papers)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    start = (page - 1) * page_size
    page_slice = queue_papers[start:start + page_size]

    # Attach paper relations (builds_on / unlocks) to the returned rows only.
    all_papers = db.scalars(select(Paper)).all()
    read_papers = [p for p in all_papers if p.status == "read"]

    def serialize(p: Paper) -> dict:
        d = p.to_dict()
        builds_on, unlocks = _relations(p, read_papers, all_papers)
        d["builds_on_papers"] = builds_on
        d["unlocks"] = unlocks
        return d

    return {
        "new_this_week": [],  # no separate section anymore; everything is in queue
        "queue": [serialize(p) for p in page_slice],
        "count": total,
        "total": total,
        "new_count": sum(1 for p in queue_papers if p.is_new),
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


def _sort_key(sort: str):
    """Return a sort-key function for the queue based on the `sort` param."""
    # Read papers always sink to the bottom regardless of the chosen sort.
    if sort == "difficulty":       # easiest first
        return lambda p: (p.status == "read", p.difficulty or 99, p.read_order)
    if sort == "reading_time":     # shortest first
        return lambda p: (p.status == "read", p.est_reading_minutes or 9999, p.read_order)
    if sort == "year":             # newest first
        return lambda p: (p.status == "read", -(p.year or 0), p.read_order)
    if sort == "relevance":        # most relevant first
        return lambda p: (p.status == "read", -(p.relevance_score or 0), p.read_order)
    # default "recommended": the adaptive read_order
    return lambda p: (p.status == "read", p.read_order)


@app.get("/api/filters")
def get_filters(db: Session = Depends(get_db)):
    """Distinct topics and years present in the DB, for the dropdowns."""
    papers = db.scalars(select(Paper)).all()
    topics = sorted({p.topic for p in papers if p.topic})
    years = sorted({p.year for p in papers if p.year is not None}, reverse=True)
    return {"topics": topics, "years": years}


@app.get("/api/history")
def get_history(db: Session = Depends(get_db)):
    """Past study sessions (newest first) + your average score."""
    sessions = db.scalars(
        select(StudySession).order_by(StudySession.created_at.desc())
    ).all()

    items = []
    scores = []
    for s in sessions:
        paper = db.get(Paper, s.paper_id)
        if s.score:
            scores.append(s.score)
        items.append({
            "id": s.id,
            "paper_id": s.paper_id,
            "title": paper.title if paper else "(deleted paper)",
            "score": s.score,
            "recap": s.recap or [],
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })

    average = round(sum(scores) / len(scores), 1) if scores else None
    return {"sessions": items, "average_score": average, "total_sessions": len(items)}


@app.get("/api/reviews/due")
def get_reviews_due(db: Session = Depends(get_db)):
    """Papers whose spaced-repetition review is due (soonest first)."""
    now = datetime.now(timezone.utc)
    due = db.scalars(
        select(Paper)
        .where(Paper.next_review.is_not(None))
        .where(Paper.next_review <= now)
        .order_by(Paper.next_review.asc())
    ).all()
    return {"due": [p.to_dict() for p in due], "count": len(due)}


# Common words to ignore when relating papers by prerequisite concepts.
_STOPWORDS = {
    "the", "and", "for", "with", "using", "via", "from", "into", "your", "you",
    "are", "all", "need", "learning", "models", "model", "language", "neural",
    "networks", "network", "deep", "large", "efficient", "based", "toward",
    "towards", "generative", "understanding", "method", "methods", "approach",
}


def _significant(tokens: set[str]) -> set[str]:
    """Drop noise words so relatedness matching is meaningful."""
    return {t for t in tokens if t not in _STOPWORDS}


def _relations(paper: Paper, read_papers: list[Paper], all_papers: list[Paper]) -> tuple[list[str], list[str]]:
    """
    Compute (builds_on, unlocks) title lists for a paper.

    builds_on = read papers whose title/topic satisfy this paper's prerequisites.
    unlocks   = papers that list THIS paper (its title/topic words) as a prereq.
    Matching is fuzzy (concept words), which is the honest shape of the data.
    """
    prereq_tokens = set()
    for pr in (paper.prerequisites or []):
        prereq_tokens |= _tokens(pr)
    prereq_tokens = _significant(prereq_tokens)

    builds_on: list[str] = []
    for r in read_papers:
        rt = _significant(_tokens(r.title or "") | _tokens(r.topic or ""))
        if prereq_tokens & rt:
            builds_on.append(r.title)

    self_tokens = _significant(_tokens(paper.title or "") | _tokens(paper.topic or ""))
    unlocks: list[str] = []
    for q in all_papers:
        if q.id == paper.id:
            continue
        qpt = set()
        for pr in (q.prerequisites or []):
            qpt |= _tokens(pr)
        if self_tokens & _significant(qpt):
            unlocks.append(q.title)

    return builds_on[:4], unlocks[:4]




def _today_payload(db: Session) -> dict:
    """
    Build the 'Today' screen data: the single recommended paper + its relations,
    plus context (weekday, day number, streak, overall position, progress).
    """
    all_papers = db.scalars(select(Paper)).all()
    read_papers = [p for p in all_papers if p.status == "read"]

    unread = [p for p in all_papers if p.status != "read"]
    unread.sort(key=lambda p: p.read_order)
    paper = unread[0] if unread else None

    paper_dict = None
    if paper is not None:
        builds_on, unlocks = _relations(paper, read_papers, all_papers)
        paper_dict = paper.to_dict()
        paper_dict["builds_on_papers"] = builds_on
        paper_dict["unlocks"] = unlocks

    # Day number = days since your first study session (habit start), else 1.
    first_session = db.scalar(select(StudySession).order_by(StudySession.created_at.asc()))
    day_number = 1
    if first_session and first_session.created_at:
        from datetime import date
        start = first_session.created_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        day_number = (date.today() - start.astimezone().date()).days + 1

    total = len(all_papers)
    read_count = len(read_papers)
    queued_this_week = sum(1 for p in unread if p.is_new)

    return {
        "paper": paper_dict,
        "weekday": datetime.now().strftime("%A"),
        "day_number": day_number,
        "streak": _compute_streak(db),
        # Overall position: which paper number you're on out of all of them.
        "position": read_count + 1 if paper else read_count,
        "queued_this_week": queued_this_week,
        "read": read_count,
        "total": total,
        "percent": round(read_count / total * 100) if total else 0,
    }


@app.get("/api/today")
def get_today(db: Session = Depends(get_db)):
    """The single recommended paper for today + context (the home screen)."""
    return _today_payload(db)


@app.post("/api/papers/{paper_id}/too-hard")
def too_hard(paper_id: int, db: Session = Depends(get_db)):
    """
    Defer a paper as too hard today: snooze it ~2 weeks, nudge the inferred level
    down, re-rank, and return the next (easier) recommended paper.
    """
    paper = _get_paper_or_404(db, paper_id)
    snooze_days = int(settings.ranker.get("snooze_days", 14))
    paper.snoozed_until = datetime.now(timezone.utc) + timedelta(days=snooze_days)

    row = db.scalar(select(UserSettings).where(UserSettings.id == 1))
    if row is not None:
        row.level = max(1.0, (row.level or 3.0) - 0.3)

    db.commit()
    compute_read_order(db)  # feeds the deferral back into the ranker
    return _today_payload(db)


def _apply_enrichment(paper: Paper, data: dict) -> None:
    """Copy an enrichment dict onto a Paper row (shared with the CLI)."""
    paper.relevance_score = data["relevance_score"]
    paper.difficulty = data["difficulty"]
    paper.prerequisites = data["prerequisites"]
    paper.builds_on = data["builds_on"]
    paper.core_idea = data["core_idea"]
    paper.est_reading_minutes = data["est_reading_minutes"]
    paper.skip_the_math = data["skip_the_math"]
    paper.enriched_at = datetime.now(timezone.utc)


@app.post("/api/papers/request")
def request_paper(req: RequestPaper, db: Session = Depends(get_db)):
    """
    Add a specific paper on demand — paste an arXiv id, an arXiv URL, or a title.
    Fetches metadata from arXiv, enriches it with the LLM, and adds it to your list.
    """
    query = req.query.strip()

    # Try to resolve it: first as an arXiv id/URL, then as a title search.
    arxiv_id = arxiv.extract_arxiv_id(query)
    entry = arxiv.fetch_by_id(arxiv_id) if arxiv_id else None
    if entry is None:
        entry = arxiv.search_by_title(query)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Couldn't find that on arXiv. Try the exact title or an arXiv link.",
        )

    # Skip if we already have it.
    existing = db.scalar(
        select(Paper).where(
            (Paper.arxiv_id == entry["arxiv_id"]) | (Paper.title == entry["title"])
        )
    )
    if existing:
        return {"added": False, "detail": "Already in your list.", "paper": existing.to_dict()}

    published = entry.get("published", "")
    pub_year = int(published[:4]) if published[:4].isdigit() else None

    paper = Paper(
        arxiv_id=entry["arxiv_id"],
        title=entry["title"],
        abs_url=entry["abs_url"],
        pdf_url=entry["pdf_url"],
        authors=entry["authors"],
        abstract=entry["abstract"],
        topic=None,
        tier=None,
        year=pub_year or arxiv.year_from_arxiv_id(entry["arxiv_id"]),
        source="requested",
        why=None,
        status="unread",
        is_new=True,
    )
    _apply_enrichment(paper, enrich_paper({
        "title": entry["title"], "abstract": entry["abstract"], "tier": None,
    }))
    db.add(paper)
    db.commit()
    compute_read_order(db)
    return {"added": True, "paper": paper.to_dict()}


# --- Background "fetch new papers" (runs the weekly arXiv ingest) ---
_ingest_state = {"running": False, "message": "", "added": 0}


def _run_ingest(days: int, limit: int) -> None:
    """Background worker: run the weekly fetch and record a result summary."""
    from cli.main import run_weekly  # imported lazily to avoid import cycles

    _ingest_state.update(running=True, message="Fetching new papers…", added=0)
    try:
        before = SessionLocal().scalar(select(func.count()).select_from(Paper))
        run_weekly(limit=limit, days=days)
        after = SessionLocal().scalar(select(func.count()).select_from(Paper))
        added = (after or 0) - (before or 0)
        _ingest_state.update(message=f"Added {added} new paper(s).", added=added)
    except Exception as exc:  # keep the server alive; surface the error
        _ingest_state.update(message=f"Fetch failed: {exc}")
    finally:
        _ingest_state["running"] = False


@app.post("/api/ingest/run")
def ingest_run(days: int = Query(default=30, ge=1, le=90), limit: int = Query(default=15, ge=1, le=60)):
    """Kick off a background fetch of new arXiv papers."""
    if _ingest_state["running"]:
        return {"started": False, "detail": "A fetch is already running."}
    threading.Thread(target=_run_ingest, args=(days, limit), daemon=True).start()
    return {"started": True}


@app.get("/api/ingest/status")
def ingest_status():
    """Poll the background fetch's status (for the button's progress feedback)."""
    return _ingest_state


@app.post("/api/papers/{paper_id}/read", response_model=OkResponse)
def mark_read(paper_id: int, db: Session = Depends(get_db)):
    """Manually mark a paper as read (done) and re-rank the queue."""
    paper = _get_paper_or_404(db, paper_id)
    paper.status = "read"
    db.commit()
    compute_read_order(db)
    return OkResponse(detail={"id": paper_id, "status": "read"})


@app.get("/api/papers/{paper_id}/pdf")
def proxy_pdf(paper_id: int, db: Session = Depends(get_db)):
    """
    Stream a paper's PDF THROUGH our server so it can be shown inside the app.

    arXiv (like most sites) blocks being embedded in an <iframe> from another
    origin. By fetching the PDF here and serving it from our own domain, the
    in-app reader can display it inline. Falls back with a clear error if the
    PDF can't be fetched (the UI still offers "Open in browser").
    """
    paper = _get_paper_or_404(db, paper_id)
    url = paper.pdf_url or paper.abs_url
    if not url:
        raise HTTPException(status_code=404, detail="No PDF link for this paper.")
    try:
        resp = requests.get(
            url, timeout=30, allow_redirects=True,
            headers={"User-Agent": "PaperTrail/1.0 (research reading app)"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't fetch the PDF: {exc}")

    return Response(
        content=resp.content,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@app.post("/api/papers/{paper_id}/notes", response_model=OkResponse)
def save_notes(paper_id: int, payload: NotesUpdate, db: Session = Depends(get_db)):
    """Save (or clear) your personal notes for a paper."""
    paper = _get_paper_or_404(db, paper_id)
    paper.notes = payload.notes or ""
    db.commit()
    return OkResponse(detail={"id": paper_id, "notes": paper.notes})


@app.post("/api/papers/{paper_id}/unread", response_model=OkResponse)
def mark_unread(paper_id: int, db: Session = Depends(get_db)):
    """Undo 'done' — put a paper back into the unread queue and re-rank."""
    paper = _get_paper_or_404(db, paper_id)
    paper.status = "unread"
    db.commit()
    compute_read_order(db)
    return OkResponse(detail={"id": paper_id, "status": "unread"})


# ===========================================================================
# TUTOR MODE
# ===========================================================================
@app.post("/api/tutor/start")
def tutor_start(req: TutorStartRequest, db: Session = Depends(get_db)):
    """Begin a session: return the paper + the opening 'summarize it' prompt."""
    paper = _get_paper_or_404(db, req.paper_id)
    # Mark as "studying" so Progress can reflect in-progress work.
    if paper.status == "unread":
        paper.status = "studying"
        db.commit()
    return {
        "paper": paper.to_dict(),
        "message": tutor.start_prompt_message(),
    }


@app.post("/api/tutor/grade")
def tutor_grade(req: TutorGradeRequest, db: Session = Depends(get_db)):
    """Grade the learner's own-words summary."""
    paper = _get_paper_or_404(db, req.paper_id)
    result = tutor.grade_summary(paper.title, paper.abstract, req.summary)
    return result


@app.post("/api/tutor/turn")
def tutor_turn(req: TutorTurnRequest, db: Session = Depends(get_db)):
    """Return the next Socratic follow-up, or signal that it's time to recap."""
    paper = _get_paper_or_404(db, req.paper_id)
    transcript = [t.model_dump() for t in req.transcript]
    return tutor.next_turn(paper.title, paper.abstract, transcript)


@app.post("/api/tutor/finish")
def tutor_finish(req: TutorFinishRequest, db: Session = Depends(get_db)):
    """Make the recap, save the session, mark the paper read, and re-rank."""
    paper = _get_paper_or_404(db, req.paper_id)
    transcript = [t.model_dump() for t in req.transcript]

    recap = tutor.make_recap(paper.title, paper.abstract, transcript)

    # Persist the study session.
    session = StudySession(
        paper_id=paper.id,
        score=req.score,
        recap=recap["recap"],
        transcript=transcript,
    )
    db.add(session)

    # Mark the paper read, schedule its spaced-repetition review, and re-rank.
    paper.status = "read"
    _schedule_next_review(paper, req.score)
    db.commit()
    compute_read_order(db)

    return {"recap": recap["recap"], "message": recap["message"]}


# Spaced-repetition intervals (days) by understanding score. Lower score = sooner.
_REVIEW_BASE_DAYS = {1: 1, 2: 2, 3: 4, 4: 7, 5: 14}


def _schedule_next_review(paper: Paper, score: int | None) -> None:
    """
    Set when a paper should resurface for review.

    First review uses a base interval from the score; each subsequent review
    roughly doubles the wait (a simple spaced-repetition curve), capped at 60d.
    """
    base = _REVIEW_BASE_DAYS.get(score or 3, 4)
    interval = min(base * (2 ** (paper.review_count or 0)), 60)
    paper.next_review = datetime.now(timezone.utc) + timedelta(days=interval)
    paper.review_count = (paper.review_count or 0) + 1


# ===========================================================================
# PROGRESS
# ===========================================================================
@app.get("/api/progress")
def get_progress(db: Session = Depends(get_db)):
    """Papers read, streak, and overall progress numbers."""
    all_papers = db.scalars(select(Paper)).all()
    total = len(all_papers)
    read_count = sum(1 for p in all_papers if p.status == "read")

    return {
        "papers_read": read_count,
        "papers_total": total,
        "percent": round(read_count / total * 100) if total else 0,
        "streak": _compute_streak(db),
    }


def _compute_streak(db: Session) -> int:
    """
    Count consecutive days (ending today or yesterday) with >=1 study session.

    A streak survives if you studied today OR yesterday; it breaks on the first
    day with no session.
    """
    sessions = db.scalars(select(StudySession)).all()
    if not sessions:
        return 0

    # Collect the set of local dates you studied on.
    study_dates = set()
    for s in sessions:
        dt = s.created_at
        if dt is None:
            continue
        # Stored as UTC; convert to local date for a human-friendly streak.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        study_dates.add(dt.astimezone().date())

    if not study_dates:
        return 0

    from datetime import date, timedelta

    today = date.today()
    # Start from today if studied today, else yesterday (grace day), else 0.
    if today in study_dates:
        cursor = today
    elif (today - timedelta(days=1)) in study_dates:
        cursor = today - timedelta(days=1)
    else:
        return 0

    streak = 0
    while cursor in study_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# ===========================================================================
# SETTINGS
# ===========================================================================
@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    row = db.scalar(select(UserSettings).where(UserSettings.id == 1))
    data = row.to_dict() if row else {}
    # Tell the client whether push is even possible on the server side.
    data["push_available"] = push_module.push_available()
    return data


@app.post("/api/settings")
def update_settings(update: SettingsUpdate, db: Session = Depends(get_db)):
    row = db.scalar(select(UserSettings).where(UserSettings.id == 1))
    if row is None:
        _ensure_settings_row()
        row = db.scalar(select(UserSettings).where(UserSettings.id == 1))

    # Apply only the fields that were provided.
    for field, value in update.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    db.commit()
    return row.to_dict()


# ===========================================================================
# PUSH NOTIFICATIONS (Phase 2)
# ===========================================================================
@app.get("/api/push/vapid-public-key")
def vapid_public_key():
    """The browser needs this public key to create a push subscription."""
    return {"public_key": settings.VAPID_PUBLIC_KEY, "available": push_module.push_available()}


@app.post("/api/push/subscribe", response_model=OkResponse)
def push_subscribe(sub: PushSubscriptionIn, db: Session = Depends(get_db)):
    """Store (or refresh) a browser's push subscription."""
    existing = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == sub.endpoint)
    )
    if existing:
        existing.p256dh = sub.keys.p256dh
        existing.auth = sub.keys.auth
    else:
        db.add(PushSubscription(endpoint=sub.endpoint, p256dh=sub.keys.p256dh, auth=sub.keys.auth))
    db.commit()
    return OkResponse(detail="subscribed")


@app.post("/api/push/test")
def push_test(db: Session = Depends(get_db)):
    """Send a one-off test notification to all subscribed devices."""
    if not push_module.push_available():
        raise HTTPException(
            status_code=400,
            detail="Push is not configured. Generate VAPID keys and set them in .env.",
        )
    delivered = push_module.broadcast(
        db, title="Paper Trail", body="Notifications are working.", url="/"
    )
    return {"delivered": delivered}


@app.post("/api/push/tick")
def push_tick():
    """
    Endpoint for an EXTERNAL cron (GitHub Actions / cron-job.org) to hit hourly
    in production, since Render's free service sleeps and can't run its own timer.
    """
    return scheduler_module.run_tick()


# ===========================================================================
# STATIC PWA  (mounted LAST so it doesn't shadow the /api routes above)
# ===========================================================================
if STATIC_DIR.exists():
    # html=True makes "/" serve index.html and unknown paths fall back to files.
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:
    @app.get("/")
    def _no_static():
        return JSONResponse(
            {"error": "static/ folder not found — the frontend hasn't been built yet."},
            status_code=500,
        )
