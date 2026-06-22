"""
backend/routers/connections.py — Connections CRUD endpoints.

LIFE-SAFETY NOTE: Connections represent cable wiring between fire alarm
devices. The cable size and length parameters are used in voltage drop
calculations per NFPA 72-2022 §27.4.1.2.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import require_permission
from backend.contract import validate_connection, validate_paginated
from backend.database import get_db
from backend.models import CreateConnectionInput
from backend.rbac import Permission
from backend.response import success

router = APIRouter(prefix="/projects/{project_id}/connections", tags=["connections"])


def _verify_project(project_id: str) -> None:
    """Ensure the project exists before operating on its connections."""
    db = get_db()
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")


# camelCase → snake_case sort field mapping
_SORT_MAP = {
    "createdAt": "created_at",
    "cableSize": "cable_size",
    "length": "length",
    "type": "type",
}


def _normalize_sort(sort: str) -> str:
    """Convert camelCase sort fields to snake_case for database.

    SECURITY FIX (BUG-32): Strict whitelist — rejects unknown sort fields.
    """
    return _SORT_MAP.get(sort, "created_at")


@router.get("", dependencies=[Depends(require_permission(Permission.CONNECTION_READ))])
async def list_connections(
    project_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("createdAt"),
    order: str = Query("desc"),
):
    """List all connections in a project with pagination."""
    _verify_project(project_id)
    db = get_db()
    result = db.list_connections(project_id, page=page, limit=limit, sort=_normalize_sort(sort), order=order)
    validate_paginated(result, item_validator=validate_connection)
    return success(result)


@router.post("", status_code=201, dependencies=[Depends(require_permission(Permission.CONNECTION_CREATE))])
async def create_connection(project_id: str, input_data: CreateConnectionInput):
    """Create a new connection in a project."""
    _verify_project(project_id)
    db = get_db()

    # Verify both devices exist
    from_dev = db.get_device(project_id, input_data.fromId)
    if not from_dev:
        raise HTTPException(
            status_code=400,
            detail=f"Source device '{input_data.fromId}' not found",
        )
    to_dev = db.get_device(project_id, input_data.toId)
    if not to_dev:
        raise HTTPException(
            status_code=400,
            detail=f"Target device '{input_data.toId}' not found",
        )

    conn_data = {
        "id": str(uuid.uuid4()),
        "fromId": input_data.fromId,
        "toId": input_data.toId,
        "cableSize": input_data.cableSize or "1.5mm²",
        "length": input_data.length if input_data.length is not None else 0.0,
        "type": input_data.type or "power",
    }
    connection = db.create_connection(project_id, conn_data)
    validate_connection(connection)

    # Sync connection to UDM for conflict detection
    from backend.project_bridge import sync_connection_to_udm
    sync_connection_to_udm(project_id, conn_data)

    return success(connection)


@router.put("/{connection_id}", dependencies=[Depends(require_permission(Permission.CONNECTION_UPDATE))])
async def update_connection(
    project_id: str,
    connection_id: str,
    cableSize: str | None = None,
    length: float | None = None,
    connection_type: str | None = None,  # FIX #14: Renamed 'type' to 'connection_type' — 'type' shadows built-in
):
    """Update an existing connection in a project.

    Allows updating cable size, length, and connection type.
    These parameters affect voltage drop calculations per NFPA 72.
    """
    _verify_project(project_id)
    db = get_db()

    # Check connection exists via indexed lookup
    connection = db.get_connection(project_id, connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Build updates dict with only provided fields
    updates = {}
    if cableSize is not None:
        updates["cableSize"] = cableSize
    if length is not None:
        updates["length"] = length
    if connection_type is not None:
        updates["type"] = connection_type

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Apply updates via database method
    updated = db.update_connection(project_id, connection_id, updates)
    if not updated:
        updated = connection

    return success(updated)


@router.delete("/{connection_id}", dependencies=[Depends(require_permission(Permission.CONNECTION_DELETE))])
async def delete_connection(project_id: str, connection_id: str):
    """Delete a connection from a project."""
    _verify_project(project_id)
    db = get_db()
    deleted = db.delete_connection(project_id, connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Sync connection deletion to UDM (soft-delete for audit trail)
    from backend.project_bridge import sync_connection_delete_to_udm
    sync_connection_delete_to_udm(project_id, connection_id)

    return success(None, "Connection deleted")
