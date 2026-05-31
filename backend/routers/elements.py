"""
FireAI Digital Twin - Elements Router
======================================
CRUD endpoints for building elements.
"""

from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.db_service import DatabaseService
from backend.schemas import (
    ApiResponse,
    ElementCreate,
    ElementResponse,
    ElementUpdate,
    PaginatedData,
)

router = APIRouter(prefix="/api/elements", tags=["elements"])


@router.get("", response_model=ApiResponse[PaginatedData[ElementResponse]])
async def list_elements(
    element_type: Optional[str] = Query(None, description="Filter by element type"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    is_deleted: Optional[bool] = Query(None, description="Include deleted elements"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_timestamp", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
):
    """List elements with optional filtering and pagination."""
    try:
        db = DatabaseService()
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
        import logging
        logging.getLogger(__name__).error(f"list_elements failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("", response_model=ApiResponse[ElementResponse], status_code=201)
async def create_element(element_data: ElementCreate):
    """Create a new element."""
    try:
        db = DatabaseService()
        element = db.create_element(element_data)
        return ApiResponse(success=True, data=element, message="Element created successfully")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"create_element failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{element_id}", response_model=ApiResponse[ElementResponse])
async def get_element(element_id: str):
    """Get an element by ID."""
    try:
        db = DatabaseService()
        element = db.get_element(element_id)
        if element is None:
            raise HTTPException(status_code=404, detail=f"Element {element_id} not found")
        return ApiResponse(success=True, data=element)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"get_element failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{element_id}", response_model=ApiResponse[ElementResponse])
async def update_element(element_id: str, element_data: ElementUpdate):
    """Update an element."""
    try:
        db = DatabaseService()
        element = db.update_element(element_id, element_data)
        if element is None:
            raise HTTPException(status_code=404, detail=f"Element {element_id} not found")
        return ApiResponse(success=True, data=element, message="Element updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"update_element failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{element_id}", response_model=ApiResponse[None])
async def delete_element(element_id: str):
    """Soft delete an element."""
    try:
        db = DatabaseService()
        success = db.delete_element(element_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Element {element_id} not found")
        return ApiResponse(success=True, message="Element deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"delete_element failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
