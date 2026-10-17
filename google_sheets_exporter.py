"""Google Sheets export using the Google Sheets API.

Requires a Google service-account or OAuth credentials file. If not configured,
the other export formats remain fully functional. This module NEVER pretends a
spreadsheet was created — it reports the actual result.
"""

from __future__ import annotations

import logging
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return get_settings().has_google


def export_to_google_sheets(
    records: list[dict[str, Any]],
    job_name: str,
    spreadsheet_title: str | None = None,
    columns: list[str] | None = None,
) -> dict[str, Any]:
    """Export records to a new Google Sheet. Returns a result dict.

    Requires google-auth and google-api-python-client to be installed, and
    GOOGLE_CLIENT_SECRETS_PATH to point to a valid credentials JSON file.

    Returns:
        {"ok": True, "url": "...", "spreadsheet_id": "..."} on success.
        {"ok": False, "error": "..."} on failure or if not configured.
    """
    settings = get_settings()
    if not is_configured():
        return {
            "ok": False,
            "error": (
                "Google Sheets is not configured. Set GOOGLE_CLIENT_SECRETS_PATH in your .env "
                "to point to a Google service-account JSON key file. See the README for setup instructions."
            ),
        }

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        return {
            "ok": False,
            "error": (
                "Google API libraries not installed. Run: "
                "pip install google-auth google-auth-oauthlib google-api-python-client"
            ),
        }

    try:
        from exports.common import collect_columns

        cols = collect_columns(records, columns)
        if not cols:
            cols = list(records[0].keys()) if records else []

        credentials = service_account.Credentials.from_service_account_file(
            settings.google_client_secrets_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=credentials)

        title = spreadsheet_title or job_name or "Research Export"
        spreadsheet = service.spreadsheets().create(
            body={"properties": {"title": title}}
        ).execute()
        spreadsheet_id = spreadsheet["spreadsheetId"]
        spreadsheet_url = spreadsheet["spreadsheetUrl"]

        # Prepare values: header + data rows.
        values = [[c.replace("_", " ").title() for c in cols]]
        for record in records:
            values.append([str(record.get(c, "") or "") for c in cols])

        # Write in a single batch.
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="A1",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

        return {
            "ok": True,
            "url": spreadsheet_url,
            "spreadsheet_id": spreadsheet_id,
            "rows_written": len(values) - 1,
        }

    except Exception as exc:
        logger.error("Google Sheets export failed: %s", exc, exc_info=True)
        return {"ok": False, "error": str(exc)}
