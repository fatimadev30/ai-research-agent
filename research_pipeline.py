"""Research pipeline — orchestrates search, fetch, extraction, dedup, and persistence.

This is the core engine. It is designed to run synchronously in a worker thread
(not blocking the Streamlit main thread). Progress is persisted to PostgreSQL
so the UI can poll real job state.
"""

from __future__ import annotations

import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from database.connection import (
    fetch_row_by_id,
    insert_row,
    supabase_client,
    update_row,
)
from services.deduplication import compute_dedup_key, is_duplicate
from services.extraction_service import extract_fields
from services.research_planner import ResearchPlan
from services.tinyfish_client import (
    TinyFishClient,
    TinyFishError,
    TinyFishNotConfiguredError,
)
from utils.security import validate_url

logger = logging.getLogger(__name__)

MAX_FETCH_URLS = 200


class ResearchPipeline:
    """Runs a research job: search → fetch → extract → dedup → persist."""

    def __init__(self, client: TinyFishClient | None = None):
        self.client = client or TinyFishClient()

    def run_job(self, job_id: str, plan: ResearchPlan, cancel_event=None) -> dict[str, Any]:
        """Execute a full research job. Returns a summary dict.

        Args:
            job_id: The UUID of the research_jobs row.
            plan: The structured ResearchPlan.
            cancel_event: Optional threading.Event to signal cancellation.
        """
        if not self.client.is_configured:
            _update_job(job_id, status="failed", error_message="TinyFish API key not configured.")
            return {"job_id": job_id, "status": "failed", "error": "TinyFish not configured."}

        _update_job(job_id, status="running", error_message=None)
        seen_urls: set[str] = set()
        seen_dedup_keys: set[str] = set()
        counters = {
            "queries_executed": 0,
            "urls_discovered": 0,
            "pages_fetched": 0,
            "records_extracted": 0,
            "records_validated": 0,
            "duplicates_removed": 0,
            "failed_records": 0,
        }

        try:
            # Phase 1: Execute search queries and collect URLs.
            all_results: list[tuple[str, str, str]] = []  # (url, title, snippet)
            for query in plan.search_queries:
                if _is_cancelled(cancel_event):
                    _update_job(job_id, status="cancelled")
                    return _summary(job_id, "cancelled", counters)

                _insert_search_query(job_id, query, status="running")
                try:
                    results = self.client.search(query, num_results=10)
                    for r in results:
                        if r.url and r.url not in seen_urls:
                            validation = validate_url(r.url)
                            if validation.is_valid:
                                seen_urls.add(r.url)
                                all_results.append((r.url, r.title, r.snippet))
                except TinyFishError as exc:
                    logger.warning("Search query '%s' failed: %s", query, exc)
                    _update_search_query(job_id, query, status="failed", error=str(exc))
                    continue

                _update_search_query(job_id, query, status="completed", result_count=len(results))
                counters["queries_executed"] += 1
                _sync_counters(job_id, counters)

            counters["urls_discovered"] = len(all_results)
            _sync_counters(job_id, counters)

            if not all_results:
                _update_job(job_id, status="completed", error_message="No URLs found from search queries.")
                return _summary(job_id, "completed", counters)

            # Phase 2: Fetch pages and extract records.
            urls_to_fetch = all_results[:MAX_FETCH_URLS]
            records_saved = 0

            with ThreadPoolExecutor(max_workers=plan.max_concurrency) as executor:
                future_to_url = {
                    executor.submit(self._fetch_and_extract, job_id, url_info, plan): url_info
                    for url_info in urls_to_fetch
                }

                for future in as_completed(future_to_url):
                    if _is_cancelled(cancel_event):
                        executor.shutdown(wait=False, cancel_futures=True)
                        _update_job(job_id, status="cancelled")
                        return _summary(job_id, "cancelled", counters)

                    url_info = future_to_url[future]
                    try:
                        result = future.result()
                        counters["pages_fetched"] += 1
                        if result and result.get("record"):
                            counters["records_extracted"] += 1
                            record = result["record"]
                            dedup_key = compute_dedup_key(record, plan.dedup_keys)
                            if is_duplicate(dedup_key, seen_dedup_keys):
                                counters["duplicates_removed"] += 1
                            else:
                                seen_dedup_keys.add(dedup_key)
                                _save_record(job_id, result.get("source_page_id"), record, dedup_key)
                                counters["records_validated"] += 1
                                records_saved += 1
                        elif result and result.get("error"):
                            counters["failed_records"] += 1
                    except Exception as exc:
                        logger.warning("Fetch/extract failed for %s: %s", url_info[0], exc)
                        counters["failed_records"] += 1

                    _sync_counters(job_id, counters)

                    # Stop if we've reached the target.
                    if records_saved >= plan.target_count:
                        break

            final_status = "completed"
            if records_saved < plan.target_count:
                logger.info(
                    "Job %s: found %d/%d requested records. Partial results saved.",
                    job_id,
                    records_saved,
                    plan.target_count,
                )

            _update_job(job_id, status=final_status)
            return _summary(job_id, final_status, counters)

        except Exception as exc:
            logger.error("Job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
            _update_job(job_id, status="failed", error_message=str(exc))
            return _summary(job_id, "failed", counters, str(exc))

    def _fetch_and_extract(
        self, job_id: str, url_info: tuple[str, str, str], plan: ResearchPlan
    ) -> dict[str, Any]:
        """Fetch a single page and extract fields. Returns a result dict."""
        url, title_hint, snippet = url_info
        try:
            # Insert source page row.
            page_row = _insert_source_page(job_id, url, title=title_hint)
            page_id = page_row.get("id")

            # Fetch.
            fetch_result = self.client.fetch(url)
            _update_source_page(
                page_id,
                fetch_status="fetched",
                http_status=fetch_result.status,
                title=fetch_result.title or title_hint,
                content_length=len(fetch_result.content),
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                raw_content=fetch_result.content[:50000],  # Truncate large content.
            )

            if fetch_result.error or not fetch_result.content:
                _update_source_page(page_id, fetch_status="failed", error=fetch_result.error or "Empty content")
                return {"error": fetch_result.error or "Empty content"}

            # Extract.
            record = extract_fields(fetch_result.content, url, plan.fields)
            if not record or _record_is_empty(record):
                return {"error": "No fields could be extracted from this page."}

            return {"record": record, "source_page_id": page_id}

        except TinyFishError as exc:
            _update_source_page_by_url(job_id, url, fetch_status="failed", error=str(exc))
            return {"error": str(exc)}
        except Exception as exc:
            logger.warning("Unexpected error processing %s: %s", url, exc)
            return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record_is_empty(record: dict[str, Any]) -> bool:
    non_null = [v for v in record.values() if v and str(v).strip()]
    return len(non_null) <= 1  # Only source_url.


def _is_cancelled(cancel_event) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def _update_job(job_id: str, **kwargs):
    update_row("research_jobs", job_id, {**kwargs, "updated_at": datetime.now(timezone.utc).isoformat()})


def _sync_counters(job_id: str, counters: dict[str, int]):
    update_row("research_jobs", job_id, {**counters, "updated_at": datetime.now(timezone.utc).isoformat()})


def _insert_search_query(job_id: str, query: str, status: str = "pending"):
    try:
        insert_row("search_queries", {"job_id": job_id, "query": query, "status": status})
    except Exception:
        pass  # May be a duplicate — search_queries has no unique constraint on (job_id, query).


def _update_search_query(job_id: str, query: str, **kwargs):
    try:
        client = supabase_client()
        client.table("search_queries").update(kwargs).eq("job_id", job_id).eq("query", query).limit(1).execute()
    except Exception as exc:
        logger.debug("Failed to update search query: %s", exc)


def _insert_source_page(job_id: str, url: str, title: str = "") -> dict[str, Any]:
    try:
        return insert_row("source_pages", {"job_id": job_id, "url": url, "title": title, "fetch_status": "pending"})
    except Exception:
        # URL already exists for this job — fetch existing.
        client = supabase_client()
        result = client.table("source_pages").select("*").eq("job_id", job_id).eq("url", url).maybeSingle().execute()
        return result.data or {}


def _update_source_page(page_id: str | None, **kwargs):
    if not page_id:
        return
    try:
        update_row("source_pages", page_id, kwargs)
    except Exception as exc:
        logger.debug("Failed to update source page: %s", exc)


def _update_source_page_by_url(job_id: str, url: str, **kwargs):
    try:
        client = supabase_client()
        client.table("source_pages").update(kwargs).eq("job_id", job_id).eq("url", url).execute()
    except Exception as exc:
        logger.debug("Failed to update source page by URL: %s", exc)


def _save_record(job_id: str, source_page_id: str | None, record: dict[str, Any], dedup_key: str):
    try:
        insert_row(
            "research_records",
            {
                "job_id": job_id,
                "source_page_id": source_page_id,
                "fields": record,
                "validation_status": "validated",
                "dedup_key": dedup_key,
                "is_duplicate": False,
            },
        )
    except Exception as exc:
        logger.warning("Failed to save record: %s", exc)


def _summary(job_id: str, status: str, counters: dict[str, int], error: str = "") -> dict[str, Any]:
    return {"job_id": job_id, "status": status, "error": error, **counters}
