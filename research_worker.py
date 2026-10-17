"""Background research worker — runs jobs in a background thread.

Uses a simple in-memory job registry (threading.Thread per job) with progress
persisted to PostgreSQL. For production-scale workloads, swap in a proper task
queue (Celery, RQ). The interface stays the same.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from services.research_pipeline import ResearchPipeline
from services.research_planner import ResearchPlan

logger = logging.getLogger(__name__)

# In-memory registry of running job threads.
_jobs: dict[str, threading.Thread] = {}
_cancel_events: dict[str, threading.Event] = {}
_lock = threading.Lock()


def start_job(job_id: str, plan: ResearchPlan) -> str:
    """Start a research job in a background thread. Returns the job_id."""
    with _lock:
        if job_id in _jobs and _jobs[job_id].is_alive():
            logger.warning("Job %s is already running.", job_id)
            return job_id

        cancel_event = threading.Event()
        _cancel_events[job_id] = cancel_event

        thread = threading.Thread(
            target=_run_job,
            args=(job_id, plan, cancel_event),
            daemon=True,
            name=f"research-{job_id}",
        )
        _jobs[job_id] = thread
        thread.start()
        logger.info("Started background job %s", job_id)
        return job_id


def cancel_job(job_id: str) -> bool:
    """Signal a running job to cancel. Returns True if the signal was sent."""
    with _lock:
        event = _cancel_events.get(job_id)
        if event:
            event.set()
            return True
    return False


def is_job_running(job_id: str) -> bool:
    with _lock:
        thread = _jobs.get(job_id)
        return thread is not None and thread.is_alive()


def get_job_status(job_id: str) -> dict[str, Any]:
    """Check whether a job thread is alive."""
    return {
        "job_id": job_id,
        "running": is_job_running(job_id),
        "cancelled": _cancel_events.get(job_id, threading.Event()).is_set(),
    }


def _run_job(job_id: str, plan: ResearchPlan, cancel_event: threading.Event):
    """Thread target — runs the pipeline and cleans up."""
    pipeline = ResearchPipeline()
    try:
        pipeline.run_job(job_id, plan, cancel_event)
    except Exception as exc:
        logger.error("Job %s crashed: %s", job_id, exc, exc_info=True)
    finally:
        with _lock:
            _cancel_events.pop(job_id, None)
            _jobs.pop(job_id, None)
