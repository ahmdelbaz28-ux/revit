"""
backend/routers/workflow.py — Workflow API endpoints for FireAI.

Provides REST API for the LangGraph-based workflow engine:
  - POST /api/workflow/start     — Start a new analysis workflow
  - GET  /api/workflow/{id}/status — Get workflow status
  - POST /api/workflow/{id}/approve — Approve at human review gate
  - POST /api/workflow/{id}/reject  — Reject at human review gate
  - GET  /api/workflow/{id}/audit   — Get full audit trail

LIFE-SAFETY NOTE:
  - Approval endpoints require X-API-Key (same as all mutating endpoints)
  - Every action is logged with timestamp and reviewer identity
  - Rejected workflows do NOT generate reports (fail-safe)
  - Audit trails are append-only (no deletion or modification)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.services.workflow_service import (
    get_workflow_service,
    close_workflow_service,
    WorkflowService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/start")
async def start_workflow(
    file_path: str = Query(
        ..., min_length=1, max_length=1000,
        description="Path to DWG/PDF/DXF file to analyze",
    ),
    latitude: Optional[float] = Query(
        None, ge=-90, le=90,
        description="Building latitude for environmental context",
    ),
    longitude: Optional[float] = Query(
        None, ge=-180, le=180,
        description="Building longitude for environmental context",
    ),
    skip_human_review: bool = Query(
        False,
        description="Skip human review gate (DEVELOPMENT ONLY — never use in production)",
    ),
):
    """
    Start a new FireAI NFPA 72 analysis workflow.

    The workflow follows this state machine:
      Upload → Parse → Validate → NFPA Analysis → Conflict Detection
        → [Human Review Gate] → Generate Report

    If critical issues are found (unknown rooms, missing detectors),
    the workflow pauses at the Human Review Gate and must be
    explicitly approved or rejected before proceeding.

    LIFE-SAFETY: skip_human_review=True should NEVER be used in production.
    It bypasses the PE review gate required by NFPA 72.
    """
    if skip_human_review:
        logger.warning(
            f"⚠️ PRODUCTION WARNING: Human review gate BYPASSED for {file_path}. "
            f"This is acceptable for development/testing ONLY. "
            f"NFPA 72 requires PE review for all fire alarm designs."
        )

    svc = get_workflow_service()
    result = await svc.start_workflow(
        file_path=file_path,
        latitude=latitude,
        longitude=longitude,
        skip_human_review=skip_human_review,
    )

    return {
        "success": True,
        "data": result,
    }


@router.get("/{workflow_id}/status")
async def get_workflow_status(
    workflow_id: str,
):
    """
    Get the current status of a workflow.

    Returns workflow status, review requirements, and summary statistics.
    Does NOT include the full report (use /audit for full details).
    """
    svc = get_workflow_service()
    result = await svc.get_workflow_status(workflow_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow not found: {workflow_id}",
        )

    return {
        "success": True,
        "data": result,
    }


@router.post("/{workflow_id}/approve")
async def approve_workflow(
    workflow_id: str,
    reviewer_comments: Optional[str] = Query(
        None, max_length=2000,
        description="Reviewer comments (optional but recommended)",
    ),
):
    """
    Approve a workflow at the human review gate.

    After approval, the workflow resumes and generates the final report.
    The approval is logged with timestamp and comments in the audit trail.

    LIFE-SAFETY: Only a qualified Fire Protection Engineer (FPE) should
    approve a fire alarm design. This endpoint requires X-API-Key.
    """
    svc = get_workflow_service()
    result = await svc.approve_workflow(
        workflow_id=workflow_id,
        reviewer_comments=reviewer_comments,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow not found: {workflow_id}",
        )

    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result["error"],
        )

    return {
        "success": True,
        "data": result,
    }


@router.post("/{workflow_id}/reject")
async def reject_workflow(
    workflow_id: str,
    reviewer_comments: Optional[str] = Query(
        None, max_length=2000,
        description="Reviewer comments (required for rejection — explain why)",
    ),
):
    """
    Reject a workflow at the human review gate.

    Rejected workflows do NOT generate reports (fail-safe).
    The rejection is logged with timestamp and comments in the audit trail.

    The workflow must be restarted with corrected data.
    """
    svc = get_workflow_service()
    result = await svc.reject_workflow(
        workflow_id=workflow_id,
        reviewer_comments=reviewer_comments,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow not found: {workflow_id}",
        )

    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result["error"],
        )

    return {
        "success": True,
        "data": result,
    }


@router.get("/{workflow_id}/audit")
async def get_audit_trail(
    workflow_id: str,
):
    """
    Get the full audit trail for a workflow.

    Returns every state transition with:
    - Timestamp (ISO 8601 UTC)
    - From/to nodes
    - Evidence (what was verified at each step)
    - Status at time of transition

    This satisfies agent.md traceability requirements and
    provides the evidence chain for PE sign-off.
    """
    svc = get_workflow_service()
    result = await svc.get_audit_trail(workflow_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow not found: {workflow_id}",
        )

    return {
        "success": True,
        "data": {
            "workflow_id": workflow_id,
            "transition_count": len(result),
            "transitions": result,
        },
    }
