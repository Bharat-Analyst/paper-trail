"""
app/sources/arxiv.py — talk to the public arXiv API.

Two jobs:
  1. search_by_title(title): given a seed paper's title, find the REAL paper on
     arXiv, confirm it's a good match, and return its true id / PDF link /
     authors / abstract. This means a wrong `arxiv_id` in seed_papers.py fixes
     itself, and we always get a valid PDF.
  2. fetch_recent(...): pull brand-new papers from the last N days by category
     and keyword — used by the weekly job.

We use only the Python standard library (urllib + xml parsing) so there's no
extra dependency. arXiv returns Atom XML, which we parse with ElementTree.

Politeness: arXiv asks callers to wait ~3 seconds between requests. We do.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

ARXIV_API = "http://export.arxiv.org/api/query"

# XML namespaces used in arXiv's Atom feed.
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# Be a polite API citizen. arXiv recommends ~3s between calls.
_POLITE_DELAY_SECONDS = 3.0
_last_call_time = 0.0


def _throttle() -> None:
    """Sleep just enough to keep at least _POLITE_DELAY_SECONDS between calls."""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < _POLITE_DELAY_SECONDS:
        time.sleep(_POLITE_DELAY_SECONDS - elapsed)
    _last_call_time = time.time()


def _http_get(params: dict) -> str:
    """Perform a throttled GET against the arXiv API and return the XML text."""
    _throttle()
    # Use full percent-encoding (spaces -> +, quotes -> %22). arXiv rejects a
    # raw double-quote in the query string with a 400, so DON'T mark it "safe".
    query = urllib.parse.urlencode(params)
    url = f"{ARXIV_API}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "PaperPilot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _clean_title(title: str) -> str:
    """
    Normalize a title for searching/comparison:
      * drop parenthetical nicknames like "(word2vec)"
      * collapse whitespace, lowercase, strip punctuation
    """
    title = re.sub(r"\(.*?\)", "", title)          # remove (...) chunks
    title = re.sub(r"[^a-zA-Z0-9 ]", " ", title)   # punctuation -> space
    return re.sub(r"\s+", " ", title).strip().lower()


def _similarity(a: str, b: str) -> float:
    """0..1 fuzzy similarity between two cleaned titles."""
    return SequenceMatcher(None, _clean_title(a), _clean_title(b)).ratio()


def _parse_entry(entry: ET.Element) -> dict:
    """Turn one <entry> element into a plain dict of the fields we care about."""
    # <id> looks like: http://arxiv.org/abs/1706.03762v5  -> keep 1706.03762
    raw_id = entry.findtext("atom:id", default="", namespaces=_NS)
    arxiv_id = raw_id.rsplit("/abs/", 1)[-1]
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id)  # strip version suffix

    title = (entry.findtext("atom:title", default="", namespaces=_NS) or "").strip()
    title = re.sub(r"\s+", " ", title)

    abstract = (entry.findtext("atom:summary", default="", namespaces=_NS) or "").strip()
    abstract = re.sub(r"\s+", " ", abstract)

    authors = [
        (a.findtext("atom:name", default="", namespaces=_NS) or "").strip()
        for a in entry.findall("atom:author", _NS)
    ]

    published = entry.findtext("atom:published", default="", namespaces=_NS)

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "authors": [a for a in authors if a],
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "published": published,
    }


def _parse_feed(xml_text: str) -> list[dict]:
    """Parse a full Atom feed into a list of entry dicts."""
    root = ET.fromstring(xml_text)
    return [_parse_entry(e) for e in root.findall("atom:entry", _NS)]


# ---------------------------------------------------------------------------
# 1) Confirm a seed paper by title
# ---------------------------------------------------------------------------
def search_by_title(title: str, min_similarity: float = 0.6) -> dict | None:
    """
    Search arXiv for a paper by title and return the best confirmed match.

    Returns a dict (arxiv_id, title, abstract, authors, abs_url, pdf_url) if a
    close-enough match is found, otherwise None (e.g. classics not on arXiv).
    """
    cleaned = _clean_title(title)
    params = {
        "search_query": f'ti:"{cleaned}"',
        "start": 0,
        "max_results": 5,
    }
    try:
        xml_text = _http_get(params)
        candidates = _parse_feed(xml_text)
    except Exception:
        # Network hiccup or parse error — treat as "no confirmation".
        return None

    if not candidates:
        return None

    # Pick the candidate whose title is most similar to what we asked for.
    best = max(candidates, key=lambda c: _similarity(title, c["title"]))
    if _similarity(title, best["title"]) >= min_similarity:
        return best
    return None


# ---------------------------------------------------------------------------
# 2) Weekly fetch of brand-new papers
# ---------------------------------------------------------------------------
def fetch_recent(
    categories: list[str],
    keywords: list[str],
    days: int = 7,
    max_per_category: int = 40,
) -> list[dict]:
    """
    Fetch papers submitted in the last `days` days across `categories`, keeping
    only those whose title or abstract mentions one of `keywords`.

    Returns a de-duplicated list of entry dicts (newest first).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    lowered_keywords = [k.lower() for k in keywords]

    seen_ids: set[str] = set()
    results: list[dict] = []

    for category in categories:
        params = {
            "search_query": f"cat:{category}",
            "start": 0,
            "max_results": max_per_category,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        try:
            entries = _parse_feed(_http_get(params))
        except Exception:
            continue  # skip a failing category rather than aborting the whole run

        for entry in entries:
            # De-dupe across categories.
            if entry["arxiv_id"] in seen_ids:
                continue

            # Keep only recent papers.
            published = _parse_date(entry.get("published", ""))
            if published and published < cutoff:
                continue

            # Keep only papers matching our interest keywords.
            haystack = f"{entry['title']} {entry['abstract']}".lower()
            if lowered_keywords and not any(k in haystack for k in lowered_keywords):
                continue

            seen_ids.add(entry["arxiv_id"])
            results.append(entry)

    # Newest first.
    results.sort(key=lambda e: e.get("published", ""), reverse=True)
    return results


def fetch_by_id(arxiv_id: str) -> dict | None:
    """
    Fetch a single paper's metadata by its exact arXiv id (e.g. "1706.03762").

    Returns the same dict shape as search_by_title, or None if not found.
    """
    try:
        xml_text = _http_get({"id_list": arxiv_id, "max_results": 1})
        entries = _parse_feed(xml_text)
    except Exception:
        return None
    return entries[0] if entries else None


def extract_arxiv_id(text: str) -> str | None:
    """
    Pull an arXiv id out of a raw string — a bare id, or an abs/pdf URL.
    e.g. "https://arxiv.org/abs/1706.03762v5" -> "1706.03762".
    """
    # URL form: .../abs/<id> or .../pdf/<id>
    url_match = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+)", text, re.IGNORECASE)
    candidate = url_match.group(1) if url_match else text.strip()
    # Bare modern id like 1706.03762 (optionally with a version suffix).
    id_match = re.match(r"^(\d{4}\.\d{4,5})", candidate)
    return id_match.group(1) if id_match else None


def year_from_arxiv_id(arxiv_id: str | None) -> int | None:
    """
    Derive the publication year from a modern arXiv id.

    Modern ids look like "YYMM.number" (e.g. "1706.03762" -> 2017,
    "2401.04088" -> 2024). Returns None for old-style ids or bad input.
    """
    if not arxiv_id:
        return None
    match = re.match(r"^(\d{2})(\d{2})\.\d+", arxiv_id)
    if not match:
        return None
    yy = int(match.group(1))
    # arXiv's YYMM scheme started in 2007; treat everything as 2000-2099.
    return 2000 + yy


def _parse_date(value: str) -> datetime | None:
    """Parse an arXiv ISO timestamp like '2024-01-15T00:00:00Z'."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
