"""
backend/services/fds_queue_service.py
======================================
FDS (Fire Dynamics Simulator) Cloud Job Queue.

Routes heavy smoke/fire simulation workloads to an external compute worker
(Modal.io) instead of running them in-process on the constrained HF Space container.

Architecture:
  [BAZspark API] --submit--> [Modal Worker] --webhook--> [BAZspark /fds/webhook]
                                                              |
                                                         [DB update]
                                                              |
                                                         [WS notify]

Without MODAL_TOKEN_ID / MODAL_TOKEN_SECRET in the environment, all jobs run
in LOCAL_SIMULATION mode so the system stays fully functional for demo purposes.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Modal SDK (optional) ──────────────────────────────────────────────────────
try:
    import modal  # type: ignore
    _MODAL_AVAILABLE = bool(
        os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET")
    )
except ImportError:
    modal = None  # type: ignore
    _MODAL_AVAILABLE = False

if not _MODAL_AVAILABLE:
    logger.info(
        "FDS Queue: MODAL_TOKEN_ID/MODAL_TOKEN_SECRET not set — "
        "running in LOCAL_SIMULATION mode. "
        "Set these env vars to enable real cloud FDS runs."
    )


# ── Job status enum ───────────────────────────────────────────────────────────
class FDSJobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SIMULATED = "simulated"  # Completed locally (demo mode)


# ── In-memory job store (replace with DB calls when Supabase migration done) ──
# Keys: job_id (str) → job dict
# IMPORTANT: defined at module level so it is a true singleton across all
# FastAPI routes and test clients that import this module. Never reassign the
# dict itself — only mutate it (add/update keys) so all references stay live.
_JOB_STORE: Dict[str, Dict[str, Any]] = {}


def _get_job_store() -> Dict[str, Dict[str, Any]]:
    """Return the singleton job store. Always use this instead of _JOB_STORE directly."""
    return _JOB_STORE


# ════════════════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════════════════

def submit_fds_job(
    fds_input: str,
    project_id: str = "",
    user_id: str = "",
    webhook_url: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Submit an FDS simulation job.

    Args:
        fds_input:   Raw FDS input file content (*.fds text).
        project_id:  BAZspark project ID for result association.
        user_id:     Requesting user ID.
        webhook_url: URL BAZspark will POST results to (auto-filled by router).
        metadata:    Optional extra metadata stored with the job.

    Returns:
        Dict with job_id, status, estimated_runtime_sec.
    """
    job_id = str(uuid.uuid4())
    # V294 SECURITY FIX (Bandit B324): MD5 used for non-security checksum
    # (deduplication of FDS input files). Marked usedforsecurity=False to
    # satisfy Bandit and document intent. If this checksum is ever used for
    # security purposes (auth, integrity verification against adversarial
    # input), switch to hashlib.sha256().
    checksum = hashlib.md5(fds_input.encode(), usedforsecurity=False).hexdigest()

    job: Dict[str, Any] = {
        "job_id":          job_id,
        "project_id":      project_id,
        "user_id":         user_id,
        "status":          FDSJobStatus.PENDING,
        "submitted_at":    datetime.now(timezone.utc).isoformat(),
        "completed_at":    None,
        "fds_checksum":    checksum,
        "webhook_url":     webhook_url,
        "result":          None,
        "error":           None,
        "metadata":        metadata or {},
        "modal_call_id":   None,
    }
    _get_job_store()[job_id] = job

    if _MODAL_AVAILABLE:
        _submit_to_modal(job_id, fds_input, webhook_url)
    else:
        _run_local_simulation(job_id, fds_input)

    logger.info(
        "FDS Job %s submitted (modal=%s, project=%s)",
        job_id, _MODAL_AVAILABLE, project_id
    )
    return {
        "job_id":               job_id,
        "status":               job["status"],
        "modal_enabled":        _MODAL_AVAILABLE,
        "estimated_runtime_sec": 180 if _MODAL_AVAILABLE else 5,
        "checksum":             checksum,
    }


def get_fds_job_status(job_id: str) -> Dict[str, Any]:
    """Return the current status and result of a job."""
    job = _get_job_store().get(job_id)
    if not job:
        return {"error": f"Job {job_id} not found"}

    return {
        "job_id":       job["job_id"],
        "status":       job["status"],
        "submitted_at": job["submitted_at"],
        "completed_at": job["completed_at"],
        "project_id":   job["project_id"],
        "result":       job["result"],
        "error":        job["error"],
    }


def list_fds_jobs(user_id: str = "", limit: int = 20) -> Dict[str, Any]:
    """List recent FDS jobs for a user."""
    jobs = [
        {k: v for k, v in j.items() if k != "fds_checksum"}
        for j in _get_job_store().values()
        if not user_id or j.get("user_id") == user_id
    ]
    jobs_sorted = sorted(jobs, key=lambda x: x["submitted_at"], reverse=True)
    return {"jobs": jobs_sorted[:limit], "total": len(jobs_sorted)}


def handle_fds_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle an incoming webhook from Modal (or internal simulation).
    Updates the job record and notifies connected WebSocket clients.

    Expected payload:
        {
            "job_id": "...",
            "status": "completed" | "failed",
            "result": { ... },   # on success
            "error":  "...",     # on failure
            "secret": "..."      # HMAC validation token
        }
    """
    job_id = payload.get("job_id", "")
    status = payload.get("status", "")

    # Validate the webhook secret
    expected_secret = _compute_webhook_secret(job_id)
    received_secret = payload.get("secret", "")
    if received_secret != expected_secret:
        logger.warning("FDS Webhook: invalid secret for job %s", job_id)
        return {"error": "Invalid webhook secret"}

    job = _get_job_store().get(job_id)
    if not job:
        return {"error": f"Job {job_id} not found"}

    job["status"]       = status
    job["completed_at"] = datetime.now(timezone.utc).isoformat()
    job["result"]       = payload.get("result")
    job["error"]        = payload.get("error")

    logger.info("FDS Job %s → %s", job_id, status)

    # WebSocket notification is handled at the router level
    # (backend/routers/fds_webhook.py:fds_result_webhook) after this
    # function returns, so the project_id is available in the response.

    return {"received": True, "job_id": job_id, "status": status}


# ════════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════════════════════════

def _compute_webhook_secret(job_id: str) -> str:
    """Deterministic HMAC-like secret tied to the job_id and a server secret."""
    server_secret = os.getenv("FDS_WEBHOOK_SECRET")
    if not server_secret:
        raise ValueError(
            "FDS_WEBHOOK_SECRET environment variable is not set. "
            "Webhook authentication requires a configured server secret."
        )
    raw = f"{job_id}:{server_secret}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _submit_to_modal(job_id: str, fds_input: str, webhook_url: str) -> None:
    """Submit the FDS job to Modal.io (real cloud compute)."""
    try:
        # Import the Modal app defined in modal_runner/fds_worker.py
        # modal_runner must be importable (ensure it's in the Python path)
        import importlib
        fds_worker = importlib.import_module("modal_runner.fds_worker")

        # Call the Modal function asynchronously (spawns a cloud container)
        call = fds_worker.run_fds_simulation.spawn(  # type: ignore
            job_id=job_id,
            fds_input=fds_input,
            webhook_url=webhook_url,
            webhook_secret=_compute_webhook_secret(job_id),
        )
        _get_job_store()[job_id]["modal_call_id"] = call.object_id
        _get_job_store()[job_id]["status"] = FDSJobStatus.RUNNING
        logger.info("FDS Job %s dispatched to Modal, call_id=%s", job_id, call.object_id)

    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to submit FDS job %s to Modal: %s", job_id, exc)
        _get_job_store()[job_id]["status"] = FDSJobStatus.FAILED
        _get_job_store()[job_id]["error"] = str(exc)


def _run_local_simulation(job_id: str, fds_input: str) -> None:
    """
    Fast local simulation stub — produces plausible results instantly.
    Used when Modal credentials are absent (demo/dev mode).
    """
    lines = fds_input.strip().split("\n")
    duration = 0.0
    mesh_count = sum(1 for l in lines if l.strip().startswith("&MESH"))
    for line in lines:
        if "T_END" in line:
            try:
                duration = float(line.split("T_END=")[1].split(",")[0].strip().rstrip("/"))
            except (IndexError, ValueError):
                pass

    simulated_result = {
        "simulation_type":  "LOCAL_SIMULATION",
        "duration_s":       duration or 60.0,
        "mesh_count":       mesh_count or 1,
        "max_temperature_c": 320.5,
        "smoke_layer_height_m": 2.1,
        "visibility_m": 8.4,
        "co_ppm_max": 145.0,
        "hrr_peak_kw": 1850.0,
        "evacuation_time_s": 210,
        "note": (
            "Simulated locally (no Modal credentials). "
            "Set MODAL_TOKEN_ID + MODAL_TOKEN_SECRET for real FDS runs."
        ),
    }

    _get_job_store()[job_id]["status"]       = FDSJobStatus.SIMULATED
    _get_job_store()[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
    _get_job_store()[job_id]["result"]       = simulated_result
