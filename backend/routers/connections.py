"""
backend/routers/connections.py — Connections CRUD endpoints.

LIFE-SAFETY NOTE: Connections represent cable wiring between fire alarm
devices. The cable size and length parameters are used in voltage drop
calculations per NFPA 72-2022 §27.4.1.2.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

from backend.database import get_db
from backend.models import CreateConnectionInput
from backend.contract import validate_connection, validate_paginated

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


@router.get("")
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
    return {"success": True, "data": result}


@router.post("", status_code=201)
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
    return {"data": connection, "success": True}


@router.delete("/{connection_id}")
async def delete_connection(project_id: str, connection_id: str):
    """Delete a connection from a project."""
    _verify_project(project_id)
    db = get_db()
    deleted = db.delete_connection(project_id, connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"data": None, "success": True, "message": "Connection deleted"}
