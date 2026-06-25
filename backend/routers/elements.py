"""FireAI Digital Twin - Elements Router
======================================
CRUD endpoints for building elements.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import require_permission
from backend.db_service import DatabaseService, get_db_service
from backend.rbac import Permission
from backend.schemas import (
    ApiResponse,
    ElementCreate,
    ElementResponse,
    ElementUpdate,
    PaginatedData,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/elements", tags=["elements"])


@router.get("", response_model=ApiResponse[PaginatedData[ElementResponse]], dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def list_elements(
    element_type: Optional[str] = Query(None, description="Filter by element type"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    is_deleted: Optional[bool] = Query(None, description="Include deleted elements"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_timestamp", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    db: DatabaseService = Depends(get_db_service),
):
    """List elements with optional filtering and pagination."""
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
        logger.error("list_elements failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("", response_model=ApiResponse[ElementResponse], status_code=201, dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])
async def create_element(
    element_data: ElementCreate,
    db: DatabaseService = Depends(get_db_service),
):
    """Create a new element."""
    try:
        element = db.create_element(element_data)
        return ApiResponse(success=True, data=element, message="Element created successfully")
    except ValueError as e:
        # V113 SECURITY: ValueError messages may contain internal paths
        # or class details. Sanitize before exposing to client.
        safe_msg = str(e)[:200]  # Truncate to prevent overflow
        # Remove common path patterns that leak server structure
        safe_msg = re.sub(r'/[\w./-]+', '[PATH]', safe_msg)
        safe_msg = re.sub(r'<class \w+>', '[CLASS]', safe_msg)
        raise HTTPException(status_code=400, detail=safe_msg)
    except Exception as e:
        logger.error("create_element failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{element_id}", response_model=ApiResponse[ElementResponse], dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def get_element(
    element_id: str,
    db: DatabaseService = Depends(get_db_service),
):
    """Get an element by ID."""
    try:
        element = db.get_element(element_id)
        if element is None:
            raise HTTPException(status_code=404, detail=f"Element {element_id} not found")
        return ApiResponse(success=True, data=element)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_element failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{element_id}", response_model=ApiResponse[ElementResponse], dependencies=[Depends(require_permission(Permission.ELEMENT_UPDATE))])
async def update_element(
    element_id: str,
    element_data: ElementUpdate,
    db: DatabaseService = Depends(get_db_service),
):
    """Update an element."""
    try:
        element = db.update_element(element_id, element_data)
        if element is None:
            raise HTTPException(status_code=404, detail=f"Element {element_id} not found")
        return ApiResponse(success=True, data=element, message="Element updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_element failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{element_id}", response_model=ApiResponse[None], dependencies=[Depends(require_permission(Permission.ELEMENT_DELETE))])
async def delete_element(
    element_id: str,
    db: DatabaseService = Depends(get_db_service),
):
    """Soft delete an element."""
    try:
        success = db.delete_element(element_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Element {element_id} not found")
        return ApiResponse(success=True, message="Element deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_element failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
