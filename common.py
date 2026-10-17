"""Export utilities shared across all export formats."""

from __future__ import annotations

import os
import tempfile
import time
from typing import Any

from config import get_settings

# Retention: temp files older than this are cleaned up on export.
TEMP_RETENTION_SECONDS = 3600


def ensure_temp_dir() -> str:
    settings = get_settings()
    os.makedirs(settings.temp_dir, exist_ok=True)
    return settings.temp_dir


def generate_filename(job_name: str, ext: str, include_ts: bool = True) -> str:
    safe_name = "".join(c for c in (job_name or "research") if c.isalnum() or c in ("-", "_")).strip() or "research"
    if include_ts:
        ts = time.strftime("%Y%m%d_%H%M%S")
        return f"{safe_name}_{ts}.{ext}"
    return f"{safe_name}.{ext}"


def get_records_for_export(job_id: str, record_ids: list[str] | None = None, include_metadata: bool = True) -> list[dict[str, Any]]:
    """Fetch records from the database, optionally filtered by record_ids."""
    from database.connection import fetch_rows, supabase_client

    client = supabase_client()
    if record_ids:
        result = client.table("research_records").select("*").in_("id", record_ids).order("created_at").execute()
    else:
        result = (
            client.table("research_records")
            .select("*")
            .eq("job_id", job_id)
            .eq("is_duplicate", False)
            .order("created_at")
            .execute()
        )

    records = result.data or []
    rows: list[dict[str, Any]] = []
    for rec in records:
        fields = rec.get("fields", {})
        row = dict(fields)
        if include_metadata:
            row["_validation_status"] = rec.get("validation_status", "")
            row["_source_page_id"] = rec.get("source_page_id", "")
        row["_record_id"] = rec.get("id", "")
        rows.append(row)
    return rows


def cleanup_old_temp_files():
    """Remove temp files older than the retention period."""
    import os
    import time as _time

    temp_dir = ensure_temp_dir()
    now = _time.time()
    for fname in os.listdir(temp_dir):
        fpath = os.path.join(temp_dir, fname)
        try:
            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > TEMP_RETENTION_SECONDS:
                os.remove(fpath)
        except OSError:
            pass


def collect_columns(records: list[dict[str, Any]], selected_columns: list[str] | None = None) -> list[str]:
    """Determine the column order for export."""
    if selected_columns:
        return selected_columns
    # Auto-detect from records, excluding internal metadata keys.
    all_keys: list[str] = []
    for rec in records:
        for key in rec:
            if key.startswith("_"):
                continue
            if key not in all_keys:
                all_keys.append(key)
    return all_keys
