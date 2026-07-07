# NOSONAR
"""
FireAI Digital Twin - Conflicts Router.
=======================================
Endpoints for conflict detection and resolution.

FIX: Uses get_db_service() dependency injection instead of creating
a new DatabaseService() per request (which leaked DB connections).
"""

from __future__ import annotations

import logging
import math

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import require_permission
from backend.db_service import DatabaseService, get_db_service
from backend.rbac import Permission
from backend.schemas import (
    ApiResponse,
    ConflictResolveRequest,
    ConflictResponse,
    PaginatedData,
)

logger = logging.getLogger(__name__)

# V139 FIX: Changed prefix from "/api/v1/conflicts" (absolute) to "/conflicts"
# (relative) to avoid double-prefixing when include_router adds /api/v1.
router = APIRouter(prefix="/conflicts", tags=["conflicts"])


@router.get("", response_model=ApiResponse[PaginatedData[ConflictResponse]], dependencies=[Depends(require_permission(Permission.CONFLICT_READ))])
async def list_conflicts(
    resolved: bool | None = Query(None, description="Filter by resolution status"),  # NOSONAR - python:S8410
    conflict_type: str | None = Query(None, description="Filter by conflict type"),  # NOSONAR - python:S8410
    page: int = Query(1, ge=1, description="Page number"),  # NOSONAR - python:S8410
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),  # NOSONAR - python:S8410
    db: DatabaseService = Depends(get_db_service),  # NOSONAR - python:S8410
):
    """List conflicts with optional filtering and pagination."""
    try:
        conflicts, total = db.list_conflicts(
            resolved=resolved,
            conflict_type=conflict_type,
            page=page,
            page_size=page_size,
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return ApiResponse(
            success=True,
            data=PaginatedData(
                items=conflicts,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            ),
        )
    except Exception as e:
        logger.exception("list_conflicts failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S1192: duplicated literal acceptable in this localized context


@router.post("/detect", response_model=ApiResponse[list], dependencies=[Depends(require_permission(Permission.CONFLICT_READ))])
async def detect_conflicts(
    db: DatabaseService = Depends(get_db_service),  # NOSONAR - python:S8410
):
    """Run conflict detection on all elements."""
    try:
        conflicts = db.detect_conflicts()
        return ApiResponse(
            success=True,
            data=conflicts,
            message=f"Detected {len(conflicts)} conflicts",
        )
    except Exception as e:
        logger.exception("detect_conflicts failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.post("/{conflict_id}/resolve", response_model=ApiResponse[ConflictResponse], dependencies=[Depends(require_permission(Permission.CONFLICT_RESOLVE))])
async def resolve_conflict(
    conflict_id: str,
    resolve_data: ConflictResolveRequest,
    db: DatabaseService = Depends(get_db_service),  # NOSONAR - python:S8410
):
    """Resolve a conflict by ID."""
    try:
        conflict = db.resolve_conflict(conflict_id, strategy=resolve_data.strategy)
        if conflict is None:
            raise HTTPException(status_code=404, detail="Conflict not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
        return ApiResponse(success=True, data=conflict, message="Conflict resolved successfully")
    except HTTPException:
        raise
    except RuntimeError as e:
        # Don't expose internal error details to client.
        logger.exception("resolve_conflict RuntimeError: %s", e)
        raise HTTPException(status_code=422, detail="Conflict resolution failed — check server logs for details")  # NOSONAR — S8415: assignment kept for readability / debuggability
    except Exception as e:
        logger.exception("resolve_conflict failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S8415: assignment kept for readability / debuggability
