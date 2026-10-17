"""Unified export service — dispatches to the correct format-specific exporter."""

from __future__ import annotations

import os
from typing import Any

from exports.csv_exporter import export_to_csv
from exports.excel_exporter import export_to_xlsx
from exports.google_sheets_exporter import export_to_google_sheets, is_configured as google_is_configured
from exports.pdf_exporter import export_to_pdf
from exports.word_exporter import export_to_docx

EXPORT_FORMATS = ["xlsx", "csv", "docx", "pdf", "google_sheets"]


def export_records(
    records: list[dict[str, Any]],
    fmt: str,
    job_name: str = "research",
    objective: str = "",
    columns: list[str] | None = None,
    include_sources: bool = True,
) -> dict[str, Any]:
    """Export records in the specified format.

    Returns:
        {"ok": True, "path": "...", "format": "..."} for file exports.
        {"ok": True, "url": "...", "spreadsheet_id": "..."} for Google Sheets.
        {"ok": False, "error": "..."} on failure.
    """
    if not records:
        return {"ok": False, "error": "No records to export."}

    fmt = fmt.lower().strip()

    try:
        if fmt == "xlsx":
            path = export_to_xlsx(records, job_name, columns, include_sources)
            return {"ok": True, "path": path, "format": "xlsx", "size": os.path.getsize(path)}
        elif fmt == "csv":
            path = export_to_csv(records, job_name, columns, include_sources)
            return {"ok": True, "path": path, "format": "csv", "size": os.path.getsize(path)}
        elif fmt == "docx":
            path = export_to_docx(records, job_name, objective, columns, include_sources)
            return {"ok": True, "path": path, "format": "docx", "size": os.path.getsize(path)}
        elif fmt == "pdf":
            path = export_to_pdf(records, job_name, objective, columns, include_sources)
            return {"ok": True, "path": path, "format": "pdf", "size": os.path.getsize(path)}
        elif fmt in ("google_sheets", "google sheets", "gsheets"):
            result = export_to_google_sheets(records, job_name, None, columns)
            return result
        else:
            return {"ok": False, "error": f"Unknown export format: {fmt}"}
    except Exception as exc:
        return {"ok": False, "error": f"Export failed: {exc}"}
