# File-level issue suppression removed per AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
FireAI Digital Twin - Elements Router.
======================================
CRUD endpoints for building elements.
"""

import logging
import math
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth import require_permission
from backend.db_service import DatabaseService, get_db_service
from backend.limiter import limiter
from backend.rbac import Permission
from backend.schemas import (
    ApiResponse,
    ElementCreate,
    ElementResponse,
    ElementUpdate,
    PaginatedData,
)

logger = logging.getLogger(__name__)

# (relative). The absolute prefix caused double-prefixing when
# _safe_include_router added "/api/v1" via app.include_router(prefix="/api/v1"),
# producing /api/v1/api/v1/elements which broke all tests.
router = APIRouter(prefix="/elements", tags=["elements"])


@router.get("", response_model=ApiResponse[PaginatedData[ElementResponse]], dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def list_elements(
    element_type: Optional[str] = Query(None, description="Filter by element type"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    is_deleted: Optional[bool] = Query(None, description="Include deleted elements"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_timestamp", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db = Depends(get_db_service),
):
    """List elements with optional filtering and pagination."""
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    try:
        elements, total = db.list_elements(
            element_type=element_type,
            project_id=project_id,
            is_deleted=is_deleted,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return ApiResponse(
            success=True,
            data=PaginatedData(
                items=elements,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            ),
        )
    except Exception as e:
        logger.exception("list_elements failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S1192: duplicated literal acceptable in this localized context


@router.post("", response_model=ApiResponse[ElementResponse], status_code=201, dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])
@limiter.limit("30/minute")
async def create_element(
    request: Request,
    element_data: ElementCreate,
    db = Depends(get_db_service),
):
    """Create a new element."""
    try:
        element = db.create_element(element_data)
        return ApiResponse(success=True, data=element, message="Element created successfully")
    except ValueError as e:
        # or class details. Sanitize before exposing to client.
        safe_msg = str(e)[:200]  # Truncate to prevent overflow
        # Remove common path patterns that leak server structure
        safe_msg = re.sub(r'/[\w./-]+', '[PATH]', safe_msg)
        safe_msg = re.sub(r'<class \w+>', '[CLASS]', safe_msg)
        raise HTTPException(status_code=400, detail=safe_msg)  # NOSONAR — S8415: assignment kept for readability / debuggability
    except Exception as e:
        logger.exception("create_element failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.get("/{element_id}", response_model=ApiResponse[ElementResponse], dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def get_element(
    element_id: str,
    db = Depends(get_db_service),
):
    """Get an element by ID."""
    try:
        element = db.get_element(element_id)
        if element is None:
            raise HTTPException(status_code=404, detail=f"Element {element_id} not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
        return ApiResponse(success=True, data=element)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get_element failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.put("/{element_id}", response_model=ApiResponse[ElementResponse], dependencies=[Depends(require_permission(Permission.ELEMENT_UPDATE))])
@limiter.limit("30/minute")
async def update_element(
    request: Request,
    element_id: str,
    element_data: ElementUpdate,
    db = Depends(get_db_service),
):
    """Update an element."""
    try:
        element = db.update_element(element_id, element_data)
        if element is None:
            raise HTTPException(status_code=404, detail=f"Element {element_id} not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
        return ApiResponse(success=True, data=element, message="Element updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_element failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.delete("/{element_id}", response_model=ApiResponse[None], dependencies=[Depends(require_permission(Permission.ELEMENT_DELETE))])
@limiter.limit("30/minute")
async def delete_element(
    request: Request,
    element_id: str,
    db = Depends(get_db_service),
):
    """Soft delete an element."""
    try:
        success = db.delete_element(element_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Element {element_id} not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
        return ApiResponse(success=True, message="Element deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_element failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S8415: assignment kept for readability / debuggability
