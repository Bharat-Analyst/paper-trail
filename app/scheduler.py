"""
app/scheduler.py — decide WHEN to send notification nudges, and drive them.

Two ways nudges can fire:
  1. LOCAL / always-on server: an in-process hourly job (APScheduler) calls
     `run_tick()` every hour.
  2. PRODUCTION on Render's FREE tier: the web service SLEEPS when idle, so an
     in-process timer can't be trusted. Instead an EXTERNAL cron (GitHub Actions
     or a free service like cron-job.org) hits `POST /api/push/tick` hourly,
     which also calls `run_tick()`. This is the honest, reliable path in prod.

Scheduling rules (from the DB UserSettings, editable in the app):
  * notifications_enabled must be True.
  * We never send during quiet hours.
  * `notif_frequency` nudges are spread evenly across the non-quiet hours.
"""

from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.config import settings as app_settings
from app.db import SessionLocal
from app.models import UserSettings
from app.push import broadcast, push_available


def is_quiet_hour(hour: int, quiet_start: int, quiet_end: int) -> bool:
    """
    True if `hour` (0-23) falls inside the quiet window.

    Handles windows that wrap midnight, e.g. quiet_start=22, quiet_end=8 means
    "quiet from 22:00 through 07:59".
    """
    if quiet_start == quiet_end:
        return False  # no quiet window
    if quiet_start < quiet_end:
        return quiet_start <= hour < quiet_end
    # Wraps past midnight.
    return hour >= quiet_start or hour < quiet_end


def compute_send_hours(frequency: int, quiet_start: int, quiet_end: int) -> list[int]:
    """
    Pick which hours of the day a nudge should fire.

    We take all non-quiet hours and choose `frequency` of them, evenly spaced,
    so the nudges are spread across your active day rather than bunched up.
    """
    active = [h for h in range(24) if not is_quiet_hour(h, quiet_start, quiet_end)]
    if not active or frequency <= 0:
        return []
    frequency = min(frequency, len(active))

    # Evenly sample `frequency` hours from the active list.
    step = len(active) / frequency
    chosen = sorted({active[int(i * step)] for i in range(frequency)})
    return chosen


def run_tick(now: datetime | None = None) -> dict:
    """
    Called once per hour (by APScheduler locally, or external cron in prod).

    Decides whether THIS hour is a send hour and, if so, broadcasts the nudge.
    Returns a small status dict for logging / the API response.
    """
    now = now or datetime.now()
    hour = now.hour

    db = SessionLocal()
    try:
        row = db.scalar(select(UserSettings).where(UserSettings.id == 1))
        if row is None or not row.notifications_enabled:
            return {"sent": 0, "reason": "notifications disabled"}

        if is_quiet_hour(hour, row.quiet_start, row.quiet_end):
            return {"sent": 0, "reason": "quiet hours"}

        send_hours = compute_send_hours(row.notif_frequency, row.quiet_start, row.quiet_end)
        if hour not in send_hours:
            return {"sent": 0, "reason": f"not a send hour (send at {send_hours})"}

        if not push_available():
            return {"sent": 0, "reason": "push not configured (no VAPID keys)"}

        message = app_settings.notifications.get("message", "📄 2-min paper break?")
        delivered = broadcast(db, title="PaperPilot", body=message, url="/")
        return {"sent": delivered, "reason": "ok"}
    finally:
        db.close()


# A module-level scheduler so we can start/stop it once.
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    """
    Start the in-process hourly job. Safe to call once on app startup.

    On Render free tier this pauses whenever the service sleeps — that's why the
    external-cron `/api/push/tick` path exists. Locally (server always running)
    this is all you need.
    """
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(daemon=True)
    # Run at minute 0 of every hour.
    _scheduler.add_job(run_tick, "cron", minute=0, id="hourly_nudge")
    _scheduler.start()


def shutdown_scheduler() -> None:
    """Stop the scheduler cleanly on app shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
