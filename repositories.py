"""Repository layer — job and record CRUD operations via Supabase."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from database.connection import fetch_row_by_id, fetch_rows, insert_row, supabase_client, update_row


def create_job(plan_dict: dict[str, Any]) -> dict[str, Any]:
    """Create a new research job from a plan dict."""
    data = {
        "prompt": plan_dict["prompt"],
        "objective": plan_dict.get("objective", ""),
        "search_queries": plan_dict.get("search_queries", []),
        "target_count": plan_dict.get("target_count", 100),
        "batch_size": plan_dict.get("batch_size", 20),
        "max_concurrency": plan_dict.get("max_concurrency", 3),
        "fields": plan_dict.get("fields", []),
        "inclusion_rules": plan_dict.get("inclusion_rules", []),
        "exclusion_rules": plan_dict.get("exclusion_rules", []),
        "dedup_keys": plan_dict.get("dedup_keys", ["name"]),
        "geography": plan_dict.get("geography", ""),
        "export_format": plan_dict.get("export_format", "xlsx"),
        "status": "draft",
    }
    return insert_row("research_jobs", data)


def get_job(job_id: str) -> dict[str, Any] | None:
    return fetch_row_by_id("research_jobs", job_id)


def list_jobs(limit: int = 100) -> list[dict[str, Any]]:
    return fetch_rows("research_jobs", order="created_at", limit=limit)


def update_job_status(job_id: str, status: str, error_message: str | None = None):
    data: dict[str, Any] = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if error_message is not None:
        data["error_message"] = error_message
    update_row("research_jobs", job_id, data)


def delete_job(job_id: str):
    client = supabase_client()
    client.table("research_jobs").delete().eq("id", job_id).execute()


def get_job_records(job_id: str, include_duplicates: bool = False) -> list[dict[str, Any]]:
    client = supabase_client()
    query = client.table("research_records").select("*").eq("job_id", job_id).order("created_at")
    if not include_duplicates:
        query = query.eq("is_duplicate", False)
    result = query.execute()
    return result.data or []


def get_job_search_queries(job_id: str) -> list[dict[str, Any]]:
    return fetch_rows("search_queries", {"job_id": job_id}, order="created_at")


def get_job_source_pages(job_id: str) -> list[dict[str, Any]]:
    return fetch_rows("source_pages", {"job_id": job_id}, order="created_at")


def update_record_fields(record_id: str, fields: dict[str, Any]):
    update_row("research_records", record_id, {
        "fields": fields,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def delete_record(record_id: str):
    client = supabase_client()
    client.table("research_records").delete().eq("id", record_id).execute()


def re_extract_record(record_id: str, new_fields: dict[str, Any]):
    update_row("research_records", record_id, {
        "fields": new_fields,
        "validation_status": "validated",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def list_exports(job_id: str | None = None) -> list[dict[str, Any]]:
    if job_id:
        return fetch_rows("export_jobs", {"job_id": job_id}, order="created_at")
    return fetch_rows("export_jobs", order="created_at")


def create_export_job(job_id: str, fmt: str, record_count: int, columns: list[str], file_path: str = "", destination: str = "") -> dict[str, Any]:
    data = {
        "job_id": job_id,
        "format": fmt,
        "status": "completed" if file_path else "pending",
        "file_path": file_path,
        "record_count": record_count,
        "columns": columns,
        "destination": destination,
        "completed_at": datetime.now(timezone.utc).isoformat() if file_path else None,
    }
    if file_path:
        import os
        data["file_size"] = os.path.getsize(file_path) if os.path.exists(file_path) else None
    return insert_row("export_jobs", data)
