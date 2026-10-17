"""Database access layer using the Supabase Postgres REST API (psycopg2 for raw SQL).

Two access modes:
  - supabase_client(): high-level table CRUD via the supabase-py SDK.
  - db_connection(): direct psycopg2 connection for complex queries / batch writes.
"""

from __future__ import annotations

import functools
from typing import Any

from config import get_settings

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None  # type: ignore
    Client = None  # type: ignore

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore


@functools.lru_cache(maxsize=1)
def supabase_client() -> "Client":
    settings = get_settings()
    if not settings.has_supabase:
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY in your environment."
        )
    if create_client is None:
        raise RuntimeError("supabase-py is not installed. Run: pip install supabase")
    return create_client(settings.supabase_url, settings.supabase_key)


@functools.lru_cache(maxsize=1)
def service_client() -> "Client":
    """Service-role client that bypasses RLS. Use sparingly for internal operations."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not configured.")
    if create_client is None:
        raise RuntimeError("supabase-py is not installed.")
    return create_client(settings.supabase_url, settings.supabase_service_key)


def db_connection():
    """Direct psycopg2 connection using the Supabase Postgres connection string."""
    settings = get_settings()
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed. Run: pip install psycopg2-binary")
    # Build connection string from SUPABASE_DB_URL or individual env vars.
    db_url = _get_db_url(settings)
    return psycopg2.connect(db_url)


def _get_db_url(settings) -> str:
    import os

    url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL", "")
    if url:
        return url
    # Fallback: construct from Supabase project URL.
    project = settings.supabase_url.replace("https://", "").replace("http://", "").split(".")[0]
    return f"postgresql://postgres:{_get_secret('SUPABASE_DB_PASSWORD', '')}@db.{project}.supabase.co:5432/postgres"


def _get_secret(key: str, default: str = "") -> str:
    import os

    return os.environ.get(key, default)


# ---------------------------------------------------------------------------
# Repository helpers — thin wrappers around the Supabase REST API.
# ---------------------------------------------------------------------------

def insert_row(table: str, data: dict[str, Any]) -> dict[str, Any]:
    client = supabase_client()
    result = client.table(table).insert(data).execute()
    return result.data[0] if result.data else {}


def update_row(table: str, row_id: str, data: dict[str, Any]) -> dict[str, Any]:
    client = supabase_client()
    result = client.table(table).update(data).eq("id", row_id).execute()
    return result.data[0] if result.data else {}


def fetch_rows(table: str, filters: dict[str, Any] | None = None, order: str = "created_at", limit: int = 1000) -> list[dict[str, Any]]:
    client = supabase_client()
    query = client.table(table).select("*")
    if filters:
        for col, val in filters.items():
            query = query.eq(col, val)
    query = query.order(order, desc=True).limit(limit)
    result = query.execute()
    return result.data or []


def fetch_row_by_id(table: str, row_id: str) -> dict[str, Any] | None:
    client = supabase_client()
    result = client.table(table).select("*").eq("id", row_id).maybeSingle().execute()
    return result.data
