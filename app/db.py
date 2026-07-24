"""
app/db.py — database engine, session factory, and table creation.

We use SQLAlchemy (a popular Python ORM) so the SAME code works with SQLite
locally and Postgres in production — only the DATABASE_URL changes.

Key idea for beginners:
  * An "engine" is the connection to the database.
  * A "session" is a short-lived workspace for reading/writing rows.
  * We open a fresh session per web request and close it when done.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, settings


def _normalize_database_url(url: str) -> str:
    """
    Make the DATABASE_URL work with our installed drivers.

    Neon/Heroku-style URLs sometimes start with "postgres://", but SQLAlchemy
    wants "postgresql://". We also ensure Postgres uses SSL (Neon requires it).
    For a RELATIVE SQLite path we anchor it to the project root, so the same
    database file is used no matter which folder you launch the server from.
    """
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # For Postgres, make sure SSL is requested (Neon rejects non-SSL connects).
    if url.startswith("postgresql://") and "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"

    # Anchor a relative SQLite file (sqlite:///./paperpilot.db) to the project
    # root so cwd doesn't matter. Absolute paths (sqlite:////...) are untouched.
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        rel = url[len("sqlite:///"):]
        if rel.startswith("./"):
            rel = rel[2:]
        url = f"sqlite:///{(BASE_DIR / rel).as_posix()}"

    return url


DATABASE_URL = _normalize_database_url(settings.DATABASE_URL)

# SQLite needs a special flag when used from multiple threads (FastAPI does).
# Postgres does not, so we only add it for SQLite.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # transparently reconnect if a pooled connection died
    future=True,
)

# Session factory. Call SessionLocal() to get a new session.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Base class all ORM models inherit from."""
    pass


def create_tables() -> None:
    """
    Create every table defined by our models if it doesn't already exist.

    This is our lightweight "migration" step — safe to run repeatedly. It's
    called by `--mode init` and again on app startup.
    """
    # Importing models here (not at top) avoids a circular import, and ensures
    # every model class is registered on Base.metadata before create_all runs.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_add_columns()


def _migrate_add_columns() -> None:
    """
    Tiny hand-rolled migration: add any new columns that create_all() can't add
    to a table that already exists (create_all only creates *new* tables).

    Currently: adds papers.year and backfills it from each paper's arXiv id.
    Safe to run every startup — it checks first and does nothing if up to date.
    """
    from sqlalchemy import inspect, text

    from app.sources.arxiv import year_from_arxiv_id

    inspector = inspect(engine)
    if "papers" not in inspector.get_table_names():
        return  # fresh DB; create_all already made the column

    existing_cols = {c["name"] for c in inspector.get_columns("papers")}

    with engine.begin() as conn:
        if "year" not in existing_cols:
            # ADD COLUMN works the same on SQLite and Postgres for a simple type.
            conn.execute(text("ALTER TABLE papers ADD COLUMN year INTEGER"))
            # Backfill year from each paper's arXiv id.
            rows = conn.execute(text("SELECT id, arxiv_id FROM papers")).fetchall()
            for row in rows:
                yr = year_from_arxiv_id(row[1])
                if yr is not None:
                    conn.execute(
                        text("UPDATE papers SET year = :y WHERE id = :i"),
                        {"y": yr, "i": row[0]},
                    )

        # Notes + spaced-repetition columns (added in a later version).
        if "notes" not in existing_cols:
            conn.execute(text("ALTER TABLE papers ADD COLUMN notes TEXT DEFAULT ''"))
        if "next_review" not in existing_cols:
            conn.execute(text("ALTER TABLE papers ADD COLUMN next_review TIMESTAMP"))
        if "review_count" not in existing_cols:
            conn.execute(text("ALTER TABLE papers ADD COLUMN review_count INTEGER DEFAULT 0"))
        # "Too hard today" snooze column.
        if "snoozed_until" not in existing_cols:
            conn.execute(text("ALTER TABLE papers ADD COLUMN snoozed_until TIMESTAMP"))

    # user_settings.level (inferred difficulty level).
    if "user_settings" in inspector.get_table_names():
        settings_cols = {c["name"] for c in inspector.get_columns("user_settings")}
        if "level" not in settings_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE user_settings ADD COLUMN level FLOAT DEFAULT 3.0"))


def get_db():
    """
    FastAPI dependency: yields a database session and guarantees it's closed.

    Usage in a route:  def endpoint(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
