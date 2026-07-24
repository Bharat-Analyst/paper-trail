"""
cli/main.py — PaperPilot's command-line data pipeline.

Run it as a module from the project root so imports resolve:

    python -m cli.main --mode init                 # seed + confirm + enrich + rank
    python -m cli.main --mode init --limit 3 --skip-enrich   # fast smoke test
    python -m cli.main --mode weekly               # fetch new papers, append

MODES
  init    Load the curated seed list, confirm each on arXiv (fixing stale ids),
          enrich with the LLM, and compute the reading order. Run this once to
          populate an empty database.
  weekly  Fetch papers from the last N days (config.yaml -> arxiv), skip ones
          already in the DB, enrich the new ones, append, and re-rank.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import select

import seed_papers as seed
from app.config import settings
from app.db import SessionLocal, create_tables
from app.enrich import enrich_paper, placeholder_enrichment
from app.models import Paper
from app.ranker import compute_read_order
from app.sources import arxiv


def _apply_enrichment(paper: Paper, data: dict) -> None:
    """Copy an enrichment dict onto a Paper row."""
    paper.relevance_score = data["relevance_score"]
    paper.difficulty = data["difficulty"]
    paper.prerequisites = data["prerequisites"]
    paper.builds_on = data["builds_on"]
    paper.core_idea = data["core_idea"]
    paper.est_reading_minutes = data["est_reading_minutes"]
    paper.skip_the_math = data["skip_the_math"]
    paper.enriched_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------
def run_init(limit: int | None, skip_enrich: bool) -> None:
    """Seed the database from seed_papers.py."""
    print("→ Creating tables (if they don't exist)...")
    create_tables()

    papers = seed.SEED_PAPERS[:limit] if limit else seed.SEED_PAPERS
    print(f"→ Seeding {len(papers)} papers "
          f"(enrichment: {'SKIPPED (placeholder)' if skip_enrich else 'ON'})\n")

    db = SessionLocal()
    added, skipped = 0, 0
    try:
        for i, sp in enumerate(papers, start=1):
            title = sp["title"]
            print(f"[{i}/{len(papers)}] {title[:70]}")

            # Skip if this paper is already in the DB (by title).
            existing = db.scalar(select(Paper).where(Paper.title == title))
            if existing:
                print("    · already in DB, skipping")
                skipped += 1
                continue

            # 1) Confirm on arXiv (self-correct the id + get real PDF/abstract).
            confirmed = arxiv.search_by_title(title)
            if confirmed:
                arxiv_id = confirmed["arxiv_id"]
                abs_url = confirmed["abs_url"]
                pdf_url = confirmed["pdf_url"]
                authors = confirmed["authors"]
                abstract = confirmed["abstract"]
                print(f"    · arXiv match: {arxiv_id}")
            else:
                # Classic not on arXiv (arxiv_id=None) or no confident match:
                # fall back to whatever the seed provided.
                arxiv_id = sp.get("arxiv_id")
                abs_url = seed.abs_url(arxiv_id)
                pdf_url = seed.pdf_url(arxiv_id) or sp.get("url")
                authors = []
                abstract = None
                print("    · no arXiv confirmation, using seed values")

            paper = Paper(
                arxiv_id=arxiv_id,
                title=title,
                abs_url=abs_url,
                pdf_url=pdf_url,
                authors=authors,
                abstract=abstract,
                topic=sp.get("topic"),
                tier=sp.get("tier"),
                year=arxiv.year_from_arxiv_id(arxiv_id),
                source="seed",
                why=sp.get("why"),
                status="unread",
                is_new=False,
            )

            # 2) Enrich (or use placeholder for the fast smoke test).
            if skip_enrich:
                _apply_enrichment(paper, placeholder_enrichment())
            else:
                print("    · enriching with LLM...")
                _apply_enrichment(paper, enrich_paper({
                    "title": title,
                    "abstract": abstract,
                    "tier": sp.get("tier"),
                }))

            db.add(paper)
            db.commit()
            added += 1

        # 3) Rank everything.
        print("\n→ Computing read order...")
        compute_read_order(db)
    finally:
        db.close()

    print(f"\n✅ Init complete. Added {added}, skipped {skipped}.")
    if skip_enrich:
        print("   (Ran with --skip-enrich: run `--mode init` again without it to "
              "get real analysis. Existing rows are skipped, so delete "
              "paperpilot.db first for a full re-enrich.)")


# ---------------------------------------------------------------------------
# weekly
# ---------------------------------------------------------------------------
def run_weekly(limit: int | None = None, days: int | None = None) -> None:
    """Fetch recent papers, dedupe, enrich, append, re-rank."""
    print("→ Creating tables (if they don't exist)...")
    create_tables()

    cfg = settings.arxiv
    categories = cfg.get("categories", [])
    keywords = cfg.get("keywords", [])
    days = days if days is not None else cfg.get("days", 7)
    max_per = cfg.get("max_per_category", 40)

    print(f"→ Fetching papers from last {days} days across {len(categories)} categories...")
    recent = arxiv.fetch_recent(categories, keywords, days=days, max_per_category=max_per)
    print(f"→ {len(recent)} candidate papers after keyword filtering.")
    if limit:
        recent = recent[:limit]
        print(f"→ Limiting to the first {limit} for this run.")
    print()

    db = SessionLocal()
    added = 0
    try:
        # Clear the previous week's "new" flags so only this run shows as new.
        for old_new in db.scalars(select(Paper).where(Paper.is_new.is_(True))).all():
            old_new.is_new = False
        db.commit()

        for i, entry in enumerate(recent, start=1):
            title = entry["title"]
            arxiv_id = entry["arxiv_id"]

            # Dedupe against the DB by arxiv_id OR title.
            existing = db.scalar(
                select(Paper).where(
                    (Paper.arxiv_id == arxiv_id) | (Paper.title == title)
                )
            )
            if existing:
                continue

            print(f"[{i}/{len(recent)}] NEW: {title[:70]}")
            # Prefer the real published year; fall back to the id-derived year.
            pub_year = None
            published = entry.get("published", "")
            if published[:4].isdigit():
                pub_year = int(published[:4])
            paper = Paper(
                arxiv_id=arxiv_id,
                title=title,
                abs_url=entry["abs_url"],
                pdf_url=entry["pdf_url"],
                authors=entry["authors"],
                abstract=entry["abstract"],
                topic=None,
                tier=None,          # weekly papers have no curated tier
                year=pub_year or arxiv.year_from_arxiv_id(arxiv_id),
                source="weekly",
                why=None,
                status="unread",
                is_new=True,
            )
            print("    · enriching with LLM...")
            _apply_enrichment(paper, enrich_paper({
                "title": title,
                "abstract": entry["abstract"],
                "tier": None,
            }))

            db.add(paper)
            db.commit()
            added += 1

        print("\n→ Recomputing read order...")
        compute_read_order(db)
    finally:
        db.close()

    print(f"\n✅ Weekly complete. Added {added} new papers.")


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="PaperPilot data pipeline.")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["init", "weekly"],
        help="init = seed the DB; weekly = fetch & append new papers.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N papers (works for both init and weekly).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="(weekly only) look back this many days instead of the config default.",
    )
    parser.add_argument(
        "--skip-enrich",
        action="store_true",
        help="(init only) use placeholder analysis instead of calling the LLM (fast, free).",
    )
    args = parser.parse_args()

    if args.mode == "init":
        run_init(limit=args.limit, skip_enrich=args.skip_enrich)
    elif args.mode == "weekly":
        run_weekly(limit=args.limit, days=args.days)


if __name__ == "__main__":
    main()
