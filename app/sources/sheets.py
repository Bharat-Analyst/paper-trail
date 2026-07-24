"""
app/sources/sheets.py — OPTIONAL Google Sheets export (disabled by default).

PaperPilot works fully without Google. This module is a STUB so you can deploy
today with no Google credentials, and switch on a spreadsheet mirror later.

TO ENABLE LATER (summary — full steps in the README):
  1. pip install gspread google-auth
  2. In Google Cloud, create a Service Account, download its JSON key.
  3. Share your Google Sheet with the service account's email.
  4. In .env set:
        GOOGLE_SHEETS_ENABLED=true
        GOOGLE_SHEETS_CREDENTIALS_FILE=/path/to/service-account.json
        GOOGLE_SHEETS_ID=<the long id from your sheet's URL>
  5. Replace the body of `export_to_sheet` below with the gspread calls shown
     in the comments.

Until then, calling export_to_sheet() is a safe no-op that just logs a hint.
"""

from __future__ import annotations

from app.config import settings


def is_enabled() -> bool:
    """True only if the user has explicitly turned Sheets export on."""
    return settings.GOOGLE_SHEETS_ENABLED


def export_to_sheet(rows: list[dict]) -> bool:
    """
    Export a list of paper rows to a Google Sheet.

    Returns True if something was exported, False if the feature is off (the
    normal case). Never raises for the disabled path, so callers can call it
    unconditionally.
    """
    if not is_enabled():
        # Feature intentionally off — do nothing.
        return False

    # --- Reference implementation (uncomment after installing gspread) ---------
    #
    # import gspread
    # from google.oauth2.service_account import Credentials
    #
    # scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    # creds = Credentials.from_service_account_file(
    #     settings.GOOGLE_SHEETS_CREDENTIALS_FILE, scopes=scopes
    # )
    # client = gspread.authorize(creds)
    # sheet = client.open_by_key(settings.GOOGLE_SHEETS_ID).sheet1
    #
    # # Write a header row once, then append each paper.
    # header = ["title", "tier", "topic", "difficulty", "relevance_score", "pdf_url"]
    # existing = sheet.get_all_values()
    # if not existing:
    #     sheet.append_row(header)
    # for r in rows:
    #     sheet.append_row([str(r.get(col, "")) for col in header])
    # return True
    # ---------------------------------------------------------------------------

    print(
        "Google Sheets export is enabled in config but the gspread code is still "
        "commented out. See app/sources/sheets.py to finish wiring it up."
    )
    return False
