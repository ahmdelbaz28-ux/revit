"""
FireAI Digital Twin - Connections V2 Router
============================================
Relationship-based connections for the UniversalDataModel.
Separate from the project-scoped cable connections router.

This router handles the /api/connections endpoints used by the
frontend api.ts client for element relationships.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.db_service import DatabaseService
from backend.schemas import (
    ApiResponse,
    ConnectionCreate,
    ConnectionResponse,
    PaginatedData,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connections", tags=["connections-v2"])


@router.get("", response_model=ApiResponse[PaginatedData[ConnectionResponse]])
async def list_connections(
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    element_id: Optional[str] = Query(None, description="Filter by element ID"),
    relationship_type: Optional[str] = Query(None, description="Filter by relationship type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """List connections (relationships) with optional filtering and pagination."""
    try:
        db = DatabaseService()
        connections, total = db.list_connections(
            project_id=project_id,
            element_id=element_id,
            relationship_type=relationship_type,
            page=page,
            page_size=page_size,
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return ApiResponse(
            success=True,
            data=PaginatedData(
                items=connections,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            ),
        )
    except Exception as e:
        logger.error(f"list_connections failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("", response_model=ApiResponse[ConnectionResponse], status_code=201)
async def create_connection(connection_data: ConnectionCreate):
    """Create a new connection (relationship) between elements."""
    try:
        db = DatabaseService()
        connection = db.create_connection(connection_data)
        return ApiResponse(success=True, data=connection, message="Connection created successfully")
    except ValueError as e:
        # H-4 FIX: Never expose str(e) from ValueError to the client.
        # Shapely/geometry ValueError messages include internal coordinates,
        # variable names, and algorithm details that aid attackers.
        # Log the full error server-side; return generic message to client.
        logger.warning("Connection creation ValueError: %s", e)
        raise HTTPException(status_code=400, detail="Invalid connection data. Please check the input parameters.")
    except Exception as e:
        logger.error(f"create_connection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{connection_id}", response_model=ApiResponse[None])
async def delete_connection(connection_id: str):
    """Delete a connection by ID."""
    try:
        db = DatabaseService()
        success = db.delete_connection(connection_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")
        return ApiResponse(success=True, message="Connection deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"delete_connection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
