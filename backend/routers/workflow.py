"""backend/routers/workflow.py — Workflow API endpoints for FireAI.

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

import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from backend.auth import require_permission
from backend.rbac import Permission
from backend.services.workflow_service import (
    get_workflow_service,
)


def _get_fireai_api_key():
    """Read FIREAI_API_KEY at runtime, not import time."""
    return os.getenv("FIREAI_API_KEY", "")


def verify_api_key_dep(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Verify API key from X-API-Key header."""
    _api_key = _get_fireai_api_key()
    if _api_key and (not x_api_key or not hmac.compare_digest(x_api_key, _api_key)):
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing API key")


logger = logging.getLogger(__name__)


# ── Path Traversal Defense-in-Depth (V113) ─────────────────────────────────
# SECURITY: file_path comes from user-controlled query string.
# Without validation, an attacker can read ANY file on the server:
#   ?file_path=../../../../etc/passwd
#   ?file_path=/etc/shadow
# The service layer (workflow_service.py:node_initialize) also validates,
# but defense-in-depth requires BOTH layers reject traversal.
# Per agent.md Priority 1 (Safety): a compromised FireAI system produces
# fake compliance reports = catastrophic loss of life.

ALLOWED_DATA_DIRS = os.environ.get(
    "FIREAI_DATA_DIRS",
    "/tmp/fireai_uploads:/data:/uploads",
).split(":")

ALLOWED_FILE_EXTENSIONS = frozenset({".dxf", ".dwg", ".pdf", ".ifc", ".rvt"})


def _validate_file_path(file_path: str) -> str:
    """Validate file_path against path traversal and extension whitelist.

    SECURITY: This is the FIRST line of defense at the router layer.
    The service layer (node_initialize) provides a SECOND check.
    Both are required — defense-in-depth per agent.md Priority 1 (Safety).

    Raises HTTPException 400 if:
      - Path resolves outside allowed directories
      - File extension is not in allowed set
      - Path contains null bytes
    """
    # Null byte injection (e.g., "file.pdf\x00.sh")
    if "\x00" in file_path:
        raise HTTPException(
            status_code=400,
            detail="Invalid file path: null byte detected",
        )

    # Extension whitelist — only BIM/CAD file types
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File extension '{ext}' not allowed. "
                f"Permitted: {sorted(ALLOWED_FILE_EXTENSIONS)}"
            ),
        )

    # Path traversal check — resolve and verify within allowed dirs
    real_path = os.path.realpath(file_path)
    for allowed_dir in ALLOWED_DATA_DIRS:
        if not allowed_dir:
            continue
        allowed_real = os.path.realpath(allowed_dir)
        if real_path == allowed_real or real_path.startswith(allowed_real + os.sep):
            return file_path  # OK — within allowed directory

    # If file doesn't exist yet (upload pending), check the parent path
    # This handles cases where the path is within an allowed dir but
    # the file hasn't been created yet
    parent_dir = os.path.dirname(real_path)
    for allowed_dir in ALLOWED_DATA_DIRS:
        if not allowed_dir:
            continue
        allowed_real = os.path.realpath(allowed_dir)
        if parent_dir == allowed_real or parent_dir.startswith(allowed_real + os.sep):
            return file_path

    raise HTTPException(
        status_code=400,
        detail=(
            f"Path traversal blocked: '{file_path}' resolves outside "
            f"allowed directories. Per security policy, file access is "
            f"restricted to designated data directories."
        ),
    )


router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/status", dependencies=[Depends(require_permission(Permission.WORKFLOW_READ))])
async def get_workflow_engine_status():
    """Get overall workflow engine status.

    Returns summary counts of workflows by status, plus service health.
    Does not require authentication (read-only monitoring endpoint).
    """
    svc = get_workflow_service()

    # Count workflows by status from the in-memory store
    status_counts = {}
    for _wf_id, wf_data in svc._workflows.items():
        state = wf_data.get("state", {})
        wf_status = state.get("status", "UNKNOWN")
        status_counts[wf_status] = status_counts.get(wf_status, 0) + 1

    langgraph_available = getattr(svc, "_langgraph_available", False)
    initialized = getattr(svc, "is_initialized", False)

    from backend.response import success
    return success({
        "engine": {
            "initialized": initialized,
            "langgraph_available": langgraph_available,
            "status": "operational" if initialized and langgraph_available else "degraded",
        },
        "workflows": {
            "total": len(svc._workflows),
            "by_status": status_counts,
        },
    })


@router.post("/start", dependencies=[Depends(require_permission(Permission.WORKFLOW_MANAGE))])
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
    """Start a new FireAI NFPA 72 analysis workflow.

    The workflow follows this state machine:
      Upload → Parse → Validate → NFPA Analysis → Conflict Detection
        → [Human Review Gate] → Generate Report

    If critical issues are found (unknown rooms, missing detectors),
    the workflow pauses at the Human Review Gate and must be
    explicitly approved or rejected before proceeding.

    LIFE-SAFETY: skip_human_review=True should NEVER be used in production.
    It bypasses the PE review gate required by NFPA 72.
    """
    # V113: Path traversal defense-in-depth — validate at router level
    _validate_file_path(file_path)

    if skip_human_review:
        # V114 FIX: Block skip_human_review in production environments.
        # NFPA 72 requires PE review for all fire alarm designs.
        # Allowing this in production is a direct violation of NFPA 72.
        env = os.getenv("FIREAI_ENV", os.getenv("NODE_ENV", "production")).lower()
        if env not in ("development", "dev", "test", "testing"):
            raise HTTPException(
                status_code=403,
                detail=(
                    "skip_human_review=True is FORBIDDEN in production. "
                    "NFPA 72 requires Professional Engineer review for all "
                    "fire alarm designs. Set FIREAI_ENV=development to enable."
                ),
            )
        logger.warning(
            f"⚠️ DEVELOPMENT ONLY: Human review gate BYPASSED for {file_path}. "
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


@router.get("/{workflow_id}/status", dependencies=[Depends(require_permission(Permission.WORKFLOW_READ))])
async def get_workflow_status(
    workflow_id: str,
):
    """Get the current status of a workflow.

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


@router.post("/{workflow_id}/approve", dependencies=[Depends(require_permission(Permission.WORKFLOW_MANAGE))])
async def approve_workflow(
    workflow_id: str,
    reviewer_comments: Optional[str] = Query(
        None, max_length=2000,
        description="Reviewer comments (optional but recommended)",
    ),
):
    """Approve a workflow at the human review gate.

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


@router.post("/{workflow_id}/reject", dependencies=[Depends(require_permission(Permission.WORKFLOW_MANAGE))])
async def reject_workflow(
    workflow_id: str,
    reviewer_comments: Optional[str] = Query(
        None, max_length=2000,
        description="Reviewer comments (required for rejection — explain why)",
    ),
):
    """Reject a workflow at the human review gate.

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


@router.get("/{workflow_id}/audit", dependencies=[Depends(require_permission(Permission.WORKFLOW_READ))])
async def get_audit_trail(
    workflow_id: str,
):
    """Get the full audit trail for a workflow.

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
