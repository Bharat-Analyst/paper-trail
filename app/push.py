"""
app/push.py — send Web Push notifications.

Web Push lets the server deliver a notification to a browser even when the app
isn't open (once the user has installed the PWA and granted permission).

It works via VAPID keys (a public/private pair identifying our server). Generate
them once with `python scripts/gen_vapid.py` and put them in .env.

If the keys aren't configured, every function here degrades to a safe no-op so
the rest of the app keeps working without push.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PushSubscription

try:
    # pywebpush does the actual encryption + HTTP delivery.
    from pywebpush import WebPushException, webpush
    _PYWEBPUSH_AVAILABLE = True
except Exception:  # library not installed
    _PYWEBPUSH_AVAILABLE = False


def push_available() -> bool:
    """True only if the library is installed AND both VAPID keys are set."""
    return _PYWEBPUSH_AVAILABLE and settings.has_push_keys()


def send_to_subscription(subscription_info: dict, title: str, body: str, url: str = "/") -> bool:
    """
    Send one notification to one browser subscription.

    Returns True on success, False on failure (e.g. expired subscription).
    """
    if not push_available():
        return False

    import json

    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
        )
        return True
    except WebPushException as exc:
        print(f"Web push failed: {exc}")
        return False


def broadcast(db: Session, title: str, body: str, url: str = "/") -> int:
    """
    Send a notification to EVERY stored subscription. Prunes dead ones.

    Returns the number of notifications successfully delivered.
    """
    if not push_available():
        return 0

    subs = db.scalars(select(PushSubscription)).all()
    delivered = 0
    for sub in subs:
        ok = send_to_subscription(sub.to_subscription_info(), title, body, url)
        if ok:
            delivered += 1
        else:
            # A failed send usually means the subscription is stale — remove it.
            db.delete(sub)
    db.commit()
    return delivered
