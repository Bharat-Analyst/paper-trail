"""
app/config.py — one place that loads ALL configuration.

Two sources of settings:
  1. .env file  -> secrets & environment-specific values (API keys, DB URL).
  2. config.yaml -> non-secret knobs (topics, arXiv categories, ranker weights).

Everything else in the app imports from here, so there's a single source of
truth and no scattered os.getenv() calls.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

# The project root is the folder that contains this app/ package.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from a .env file (if present) into os.environ.
# On Render there is no .env file — the variables come from the dashboard —
# and load_dotenv() simply does nothing in that case. Either way works.
load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    """Read an environment variable, trimming whitespace, with a default."""
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


@lru_cache(maxsize=1)
def get_yaml_config() -> dict:
    """Load and cache config.yaml. Cached so we only read the file once."""
    config_path = BASE_DIR / "config.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Convenience accessors. Grouped by area so imports read nicely, e.g.:
#   from app.config import settings
#   settings.GROQ_API_KEY
# ---------------------------------------------------------------------------
class Settings:
    """Typed-ish view over env vars + config.yaml. Import the `settings` singleton."""

    # --- LLM provider selection ---
    LLM_PROVIDER: str = _get("LLM_PROVIDER", "groq").lower()

    GROQ_API_KEY: str = _get("GROQ_API_KEY")
    GROQ_MODEL: str = _get("GROQ_MODEL", "llama-3.3-70b-versatile")

    GEMINI_API_KEY: str = _get("GEMINI_API_KEY")
    GEMINI_MODEL: str = _get("GEMINI_MODEL", "gemini-1.5-flash")

    OLLAMA_HOST: str = _get("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = _get("OLLAMA_MODEL", "llama3.1")

    # --- Database ---
    DATABASE_URL: str = _get("DATABASE_URL", "sqlite:///./paperpilot.db")

    # --- Web Push (Phase 2) ---
    VAPID_PUBLIC_KEY: str = _get("VAPID_PUBLIC_KEY")
    VAPID_PRIVATE_KEY: str = _get("VAPID_PRIVATE_KEY")
    VAPID_SUBJECT: str = _get("VAPID_SUBJECT", "mailto:example@example.com")

    # --- Optional Google Sheets export ---
    GOOGLE_SHEETS_ENABLED: bool = _get("GOOGLE_SHEETS_ENABLED", "false").lower() == "true"
    GOOGLE_SHEETS_CREDENTIALS_FILE: str = _get("GOOGLE_SHEETS_CREDENTIALS_FILE")
    GOOGLE_SHEETS_ID: str = _get("GOOGLE_SHEETS_ID")

    # --- config.yaml sections (with sensible fallbacks) ---
    @property
    def yaml(self) -> dict:
        return get_yaml_config()

    @property
    def topics(self) -> list[str]:
        return self.yaml.get("topics", [])

    @property
    def arxiv(self) -> dict:
        return self.yaml.get("arxiv", {})

    @property
    def ranker(self) -> dict:
        # Defaults mirror config.yaml so the app still ranks if the file is missing.
        defaults = {
            "relevance_weight": 1.0,
            "difficulty_weight": 1.2,
            "prereq_bonus": 2.0,
            "new_bonus": 1.0,
            "level_gap_weight": 1.0,   # penalty for difficulty above your inferred level
            "snooze_penalty": 100.0,   # "too hard today" sinks a paper while snoozed
            "snooze_days": 14,         # how long a snooze lasts
        }
        defaults.update(self.yaml.get("ranker", {}))
        return defaults

    @property
    def notifications(self) -> dict:
        defaults = {
            "frequency": 3,
            "quiet_start": 22,
            "quiet_end": 8,
            "message": "📄 2-min paper break? Your next paper is waiting.",
        }
        defaults.update(self.yaml.get("notifications", {}))
        return defaults

    def has_push_keys(self) -> bool:
        """True only if both VAPID keys are configured."""
        return bool(self.VAPID_PUBLIC_KEY and self.VAPID_PRIVATE_KEY)


# The single shared instance the rest of the app imports.
settings = Settings()
