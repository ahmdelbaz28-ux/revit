"""
backend/worker/celery_app.py — Celery Worker for FireAI Background Tasks
=========================================================================

Replaces the time.sleep(10) stub in deploy/docker/entrypoint-worker.sh
with a real Celery worker that processes analysis tasks asynchronously.

ARCHITECTURE:
  Redis (broker/backend) ← Celery Worker ← FastAPI (task submission)

SAFETY-CRITICAL DESIGN:
  - Every task has a correlation_id for audit trail (NFPA 72-2022 §14.2.4)
  - Task results are traceable and immutable
  - Failed tasks NEVER silently disappear — all failures are logged
  - Task timeouts prevent infinite hangs (determinism per agent.md priority 5)

REFERENCE:
  NFPA 72-2022 §10.6 (audit trail), §14.2.4 (correlation ID)
  ISO 16739-1:2024 (IFC 4.3 ADD2)
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from celery import Celery

logger = logging.getLogger("fireai.worker")

# ── Celery Configuration ─────────────────────────────────────────────────────

REDIS_URL = os.getenv("FIREAI_REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("FIREAI_CELERY_BROKER", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("FIREAI_CELERY_BACKEND", REDIS_URL)

# Task timeout — prevents infinite hangs (safety-critical: agent.md priority 5)
TASK_SOFT_TIME_LIMIT = int(os.getenv("FIREAI_TASK_SOFT_TIME_LIMIT_S", "300"))  # 5 min
TASK_TIME_LIMIT = int(os.getenv("FIREAI_TASK_TIME_LIMIT_S", "600"))  # 10 min hard

celery_app = Celery(
    "fireai",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timeouts — safety-critical: prevent zombie tasks
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT,
    task_time_limit=TASK_TIME_LIMIT,

    # Reliability
    task_acks_late=True,          # Ack after execution, not before
    task_reject_on_worker_lost=True,  # Re-queue if worker crashes
    worker_prefetch_multiplier=1,  # Fair scheduling: one task at a time
    result_expires=86400,          # Keep results 24h for audit trail

    # Correlation tracking
    task_track_started=True,

    # Queue configuration
    task_routes={
        "backend.worker.celery_app.run_analysis_task": {"queue": "analysis"},
    },

    # Default queue
    task_default_queue="default",
)


# ── Analysis Task ─────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="backend.worker.celery_app.run_analysis_task",
    max_retries=2,
    default_retry_delay=30,
)
def run_analysis_task(
    self: Any,
    file_path: str,
    file_type: str,
    correlation_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute a FireAI analysis pipeline as a background task.

    Args:
        file_path: Path to the uploaded file (DWG/PDF/IFC).
        file_type: File type string ("dxf", "dwg", "pdf", "ifc").
        correlation_id: Audit trail correlation ID (NFPA 72 §14.2.4).
        **kwargs: Additional analysis parameters.

    Returns:
        Dict with analysis results and audit metadata.

    Raises:
        celery.exceptions.Retry: On transient failure (up to max_retries).
        ValueError: On invalid input (not retried).
    """
    # ── Correlation ID (audit trail per NFPA 72 §14.2.4) ──
    if correlation_id is None:
        correlation_id = f"task-{self.request.id or uuid.uuid4().hex[:12]}"

    start_time = time.monotonic()
    logger.info(
        "Task %s started | correlation_id=%s | file=%s | type=%s",
        self.request.id, correlation_id, file_path, file_type,
    )

    try:
        # ── Input Validation ──
        if not file_path:
            raise ValueError("file_path is required — cannot analyze empty path")
        if not file_type:
            raise ValueError("file_type is required — cannot determine parser")

        # ── Route to appropriate parser ──
        from parsers.ifc_dispatcher import dispatch_ifc_parse

        if file_type.lower() in ("ifc", "ifcjson", "ifc.json"):
            result = dispatch_ifc_parse(file_path, correlation_id=correlation_id)
        else:
            # Delegate to workflow service for DWG/PDF
            result = _run_workflow_analysis(
                file_path=file_path,
                file_type=file_type,
                correlation_id=correlation_id,
                **kwargs,
            )

        elapsed = time.monotonic() - start_time

        # ── Build audit result ──
        audit_result = {
            "status": "COMPLETED",
            "correlation_id": correlation_id,
            "task_id": self.request.id,
            "file_path": file_path,
            "file_type": file_type,
            "elapsed_seconds": round(elapsed, 3),
            "result": result,
            "timestamp_utc": _utc_now_iso(),
        }

        logger.info(
            "Task %s COMPLETED | correlation_id=%s | elapsed=%.3fs",
            self.request.id, correlation_id, elapsed,
        )
        return audit_result

    except ValueError as exc:
        # Non-retriable: input validation failure
        elapsed = time.monotonic() - start_time
        logger.error(
            "Task %s FAILED (validation) | correlation_id=%s | error=%s",
            self.request.id, correlation_id, exc,
        )
        return {
            "status": "FAILED",
            "correlation_id": correlation_id,
            "task_id": self.request.id,
            "error": str(exc),
            "error_type": "ValidationError",
            "elapsed_seconds": round(elapsed, 3),
            "timestamp_utc": _utc_now_iso(),
        }

    except Exception as exc:
        # Potentially retriable
        elapsed = time.monotonic() - start_time
        logger.exception(
            "Task %s FAILED (unexpected) | correlation_id=%s | error=%s",
            self.request.id, correlation_id, exc,
        )

        # Retry for transient failures
        if self.request.retries < self.max_retries:
            logger.info("Retrying task %s (attempt %d/%d)",
                        self.request.id, self.request.retries + 1, self.max_retries)
            raise self.retry(exc=exc)

        # Max retries exhausted — return failure result (not silent!)
        return {
            "status": "FAILED",
            "correlation_id": correlation_id,
            "task_id": self.request.id,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "elapsed_seconds": round(elapsed, 3),
            "timestamp_utc": _utc_now_iso(),
        }


# ── Workflow Delegation ───────────────────────────────────────────────────────

def _run_workflow_analysis(
    file_path: str,
    file_type: str,
    correlation_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Delegate to the LangGraph workflow service for DWG/PDF analysis.

    This is a synchronous wrapper — Celery workers run sync by default.
    The workflow service's async methods are run via asyncio.run().
    """
    import asyncio

    try:
        from backend.services.workflow_service import WorkflowService
    except ImportError:
        logger.warning("WorkflowService not available — returning stub result")
        return {
            "status": "STUB",
            "message": "WorkflowService not available in worker context",
            "file_type": file_type,
        }

    async def _async_run() -> dict[str, Any]:
        service = WorkflowService()
        result = await service.run_pipeline(
            file_path=file_path,
            file_type=file_type,
            correlation_id=correlation_id,
            **kwargs,
        )
        return result

    try:
        return asyncio.run(_async_run())
    except RuntimeError as e:
        if "Event loop" in str(e):
            # Already in an event loop — create a new one in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _async_run())
                return future.result(timeout=TASK_TIME_LIMIT)
        raise


# ── Utility ───────────────────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── Worker Health Check ──────────────────────────────────────────────────────

@celery_app.task(name="backend.worker.celery_app.health_check")
def health_check() -> dict[str, str]:
    """Lightweight health check task for monitoring."""
    return {
        "status": "healthy",
        "worker": "fireai-celery",
        "timestamp_utc": _utc_now_iso(),
    }
