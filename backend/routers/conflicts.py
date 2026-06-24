"""FireAI Digital Twin - Conflicts Router
=======================================
Endpoints for conflict detection and resolution.

FIX: Uses get_db_service() dependency injection instead of creating
a new DatabaseService() per request (which leaked DB connections).
"""

from __future__ import annotations

import logging
import math
from typing import Optional

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

router = APIRouter(prefix="/api/v1/conflicts", tags=["conflicts"])


@router.get("", response_model=ApiResponse[PaginatedData[ConflictResponse]], dependencies=[Depends(require_permission(Permission.CONFLICT_READ))])
async def list_conflicts(
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    conflict_type: Optional[str] = Query(None, description="Filter by conflict type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: DatabaseService = Depends(get_db_service),
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
        logger.error("list_conflicts failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/detect", response_model=ApiResponse[list], dependencies=[Depends(require_permission(Permission.CONFLICT_READ))])
async def detect_conflicts(
    db: DatabaseService = Depends(get_db_service),
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
        logger.error("detect_conflicts failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{conflict_id}/resolve", response_model=ApiResponse[ConflictResponse], dependencies=[Depends(require_permission(Permission.CONFLICT_RESOLVE))])
async def resolve_conflict(
    conflict_id: str,
    resolve_data: ConflictResolveRequest,
    db: DatabaseService = Depends(get_db_service),
):
    """Resolve a conflict by ID."""
    try:
        conflict = db.resolve_conflict(conflict_id, strategy=resolve_data.strategy)
        if conflict is None:
            raise HTTPException(status_code=404, detail="Conflict not found")
        return ApiResponse(success=True, data=conflict, message="Conflict resolved successfully")
    except HTTPException:
        raise
    except RuntimeError as e:
        # Don't expose internal error details to client.
        logger.error("resolve_conflict RuntimeError: %s", e, exc_info=True)
        raise HTTPException(status_code=422, detail="Conflict resolution failed — check server logs for details")
    except Exception as e:
        logger.error("resolve_conflict failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
