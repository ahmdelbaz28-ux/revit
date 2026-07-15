"""
backend/routers/fds_webhook.py
================================
FDS Simulation Webhook Router.

Handles:
  POST /api/v2/fds/submit   — Submit a new FDS simulation job
  GET  /api/v2/fds/status/{job_id} — Check job status
  GET  /api/v2/fds/jobs     — List all jobs for the authenticated user
  POST /api/v2/fds/webhook  — Internal webhook (Modal → BAZspark result callback)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.services.fds_queue_service import (
    FDSJobStatus,
    get_fds_job_status,
    handle_fds_webhook,
    list_fds_jobs,
    submit_fds_job,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/fds", tags=["FDS Simulation Queue"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class FDSSubmitRequest(BaseModel):
    """Request body for submitting an FDS simulation."""
    fds_input:  str             = Field(..., min_length=10,
                                        description="Raw FDS input file content")
    project_id: str             = Field(default="",
                                        description="BAZspark project ID")
    metadata:   Dict[str, Any]  = Field(default_factory=dict)


class FDSWebhookPayload(BaseModel):
    """Payload sent by Modal worker when a job completes."""
    job_id:  str
    status:  str
    secret:  str
    result:  Optional[Dict[str, Any]] = None
    error:   Optional[str]            = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/submit", summary="Submit an FDS simulation job")
async def submit_simulation(
    body: FDSSubmitRequest,
    request: Request,
) -> Dict[str, Any]:
    """
    Submit an FDS input file for cloud simulation.

    - If Modal credentials are configured → job runs on Modal cloud (8 CPU, 16 GB).
    - Otherwise → instant local simulation stub (demo mode).

    Results are delivered via the `/fds/webhook` endpoint and can also be
    polled via `/fds/status/{job_id}`.
    """
    # Build the webhook URL so Modal knows where to POST results
    base_url = str(request.base_url).rstrip("/")
    webhook_url = f"{base_url}/api/v2/fds/webhook"

    # Attempt to get user ID from request state (set by auth middleware)
    user_id = getattr(request.state, "user_id", "") or ""

    return submit_fds_job(
        fds_input=body.fds_input,
        project_id=body.project_id,
        user_id=user_id,
        webhook_url=webhook_url,
        metadata=body.metadata,
    )


@router.get("/status/{job_id}", summary="Get FDS job status")
async def get_job_status(job_id: str) -> Dict[str, Any]:
    """Poll the status and result of an FDS simulation job."""
    result = get_fds_job_status(job_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/jobs", summary="List FDS simulation jobs")
async def list_jobs(
    request: Request,
    limit: int = 20,
) -> Dict[str, Any]:
    """List recent FDS jobs for the authenticated user."""
    user_id = getattr(request.state, "user_id", "") or ""
    return list_fds_jobs(user_id=user_id, limit=limit)


@router.post("/webhook", summary="FDS simulation result webhook (internal)")
async def fds_result_webhook(
    payload: FDSWebhookPayload,
    request: Request,
) -> Dict[str, Any]:
    """
    Internal webhook called by Modal worker when an FDS simulation completes.
    Validates the HMAC secret, updates the job record, and broadcasts to
    subscribed WebSocket clients.

    This endpoint should NOT be exposed to unauthenticated users in production.
    Add IP allowlisting for Modal's egress IPs if needed.
    """
    result = handle_fds_webhook(payload.model_dump())

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
