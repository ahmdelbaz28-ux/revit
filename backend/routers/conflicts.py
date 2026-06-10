"""
FireAI Digital Twin - Conflicts Router
=======================================
Endpoints for conflict detection and resolution.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.db_service import DatabaseService
from backend.schemas import (
    ApiResponse,
    ConflictResolveRequest,
    ConflictResponse,
    PaginatedData,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conflicts", tags=["conflicts"])


@router.get("", response_model=ApiResponse[PaginatedData[ConflictResponse]])
async def list_conflicts(
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    conflict_type: Optional[str] = Query(None, description="Filter by conflict type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """List conflicts with optional filtering and pagination."""
    try:
        db = DatabaseService()
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
        logger.error(f"list_conflicts failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/detect", response_model=ApiResponse[list])
async def detect_conflicts():
    """Run conflict detection on all elements."""
    try:
        db = DatabaseService()
        conflicts = db.detect_conflicts()
        return ApiResponse(
            success=True,
            data=conflicts,
            message=f"Detected {len(conflicts)} conflicts",
        )
    except Exception as e:
        logger.error(f"detect_conflicts failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{conflict_id}/resolve", response_model=ApiResponse[ConflictResponse])
async def resolve_conflict(conflict_id: str, resolve_data: ConflictResolveRequest):
    """Resolve a conflict by ID."""
    try:
        db = DatabaseService()
        conflict = db.resolve_conflict(conflict_id, strategy=resolve_data.strategy)
        if conflict is None:
            raise HTTPException(status_code=404, detail=f"Conflict {conflict_id} not found")
        return ApiResponse(success=True, data=conflict, message="Conflict resolved successfully")
    except HTTPException:
        raise
    except RuntimeError as e:
        # V113 SECURITY: Don't expose internal error details to client.
        # RuntimeError may contain server paths, class names, or internal
        # state that helps attackers. Log internally, return generic message.
        logger.error(f"resolve_conflict RuntimeError: {e}", exc_info=True)
        raise HTTPException(status_code=422, detail="Conflict resolution failed — check server logs for details")
    except Exception as e:
        logger.error(f"resolve_conflict failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
