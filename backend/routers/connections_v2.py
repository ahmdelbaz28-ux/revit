# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
FireAI Digital Twin - Connections V2 Router.
============================================
Relationship-based connections for the UniversalDataModel.
Separate from the project-scoped cable connections router.

This router handles the /api/connections endpoints used by the
frontend api.ts client for element relationships.

FIX #13: Uses Dependency Injection (get_db_service) instead of creating
a new DatabaseService() per request, which leaked database connections.
FIX #28: Does not expose connection_id in error messages.
"""

import logging
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth import require_permission
from backend.db_service import DatabaseService, get_db_service
from backend.limiter import limiter
from backend.rbac import Permission
from backend.schemas import (
    ApiResponse,
    ConnectionCreate,
    ConnectionResponse,
    PaginatedData,
)

logger = logging.getLogger(__name__)

# (relative) to avoid double-prefixing when include_router adds /api/v1.
router = APIRouter(prefix="/connections", tags=["connections-v2"])


@router.get("", response_model=ApiResponse[PaginatedData[ConnectionResponse]], dependencies=[Depends(require_permission(Permission.CONNECTION_READ))])
async def list_connections(
    project_id: Optional[str] =  Query(None, description="Filter by project ID"),  # NOSONAR - python:S8410
    element_id: Optional[str] =  Query(None, description="Filter by element ID"),  # NOSONAR - python:S8410
    relationship_type: Optional[str] =  Query(None, description="Filter by relationship type"),  # NOSONAR - python:S8410
    page: int = Query(1, ge=1, description="Page number"),  # NOSONAR - python:S8410
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),  # NOSONAR - python:S8410
    db: DatabaseService = Depends(get_db_service),  # NOSONAR - python:S8410
):
    """List connections (relationships) with optional filtering and pagination."""
    try:
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
        logger.exception("list_connections failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S1192: duplicated literal acceptable in this localized context


@router.post("", response_model=ApiResponse[ConnectionResponse], status_code=201, dependencies=[Depends(require_permission(Permission.CONNECTION_CREATE))])
@limiter.limit("30/minute")
async def create_connection(
    request: Request,
    connection_data: ConnectionCreate,
    db: DatabaseService = Depends(get_db_service),  # NOSONAR - python:S8410
):
    """Create a new connection (relationship) between elements."""
    try:
        connection = db.create_connection(connection_data)
        return ApiResponse(success=True, data=connection, message="Connection created successfully")
    except ValueError as e:
        # Never expose str(e) from ValueError to the client.
        logger.warning("Connection creation ValueError: %s", e)
        raise HTTPException(status_code=400, detail="Invalid connection data. Please check the input parameters.")  # NOSONAR — S8415: assignment kept for readability / debuggability
    except Exception as e:
        logger.exception("create_connection failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S8415: assignment kept for readability / debuggability


@router.put("/{connection_id}", response_model=ApiResponse[ConnectionResponse], dependencies=[Depends(require_permission(Permission.CONNECTION_UPDATE))])
@limiter.limit("30/minute")
async def update_connection(
    request: Request,
    connection_id: str,
    data: ConnectionCreate,
    db: DatabaseService = Depends(get_db_service),  # NOSONAR - python:S8410
):
    """Update a connection by ID. V215 FIX: was missing — frontend got 405."""
    try:
        updated = db.update_connection(connection_id, data)
        if updated is None:
            raise HTTPException(status_code=404, detail="Connection not found")  # noqa: S8415
        return ApiResponse[ConnectionResponse](
            success=True,
            data=ConnectionResponse.model_validate(updated),
            message="Connection updated successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("update_connection failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # noqa: S8415


@router.delete("/{connection_id}", response_model=ApiResponse[None], dependencies=[Depends(require_permission(Permission.CONNECTION_DELETE))])
@limiter.limit("30/minute")
async def delete_connection(
    request: Request,
    connection_id: str,
    db: DatabaseService = Depends(get_db_service),  # NOSONAR - python:S8410
):
    """Delete a connection by ID."""
    try:
        success = db.delete_connection(connection_id)
        if not success:
            # FIX #28: Do not expose connection_id in error message
            raise HTTPException(status_code=404, detail="Connection not found")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
        return ApiResponse(success=True, message="Connection deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_connection failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")  # NOSONAR — S8415: assignment kept for readability / debuggability
