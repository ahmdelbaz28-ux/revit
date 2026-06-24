"""backend/routers/projects.py — Projects CRUD endpoints.

LIFE-SAFETY NOTE: Projects are the top-level container for all fire alarm
engineering data. Deletion cascades to all child devices, connections,
and reports.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import require_permission
from backend.contract import validate_paginated, validate_project
from backend.database import get_db
from backend.models import (
    CreateProjectInput,
    UpdateProjectInput,
)
from backend.project_bridge import (
    sync_project_delete_to_udm,
    sync_project_to_udm,
    sync_project_update_to_udm,
)
from backend.rbac import Permission
from backend.response import success

router = APIRouter(prefix="/projects", tags=["projects"])
_SORT_MAP = {
    "createdAt": "created_at",
    "updatedAt": "updated_at",
    "name": "name",
    "status": "status",
    "author": "author",
}


def _normalize_sort(sort: str) -> str:
    """Convert camelCase sort fields to snake_case for database.

    SECURITY FIX (BUG-32): Strict whitelist — if the sort field isn't
    in _SORT_MAP, default to 'created_at'. Previously, raw user input
    with underscores passed through, creating an SQL injection vector
    if the database whitelist was ever bypassed.
    """
    return _SORT_MAP.get(sort, "created_at")


@router.get("", dependencies=[Depends(require_permission(Permission.PROJECT_READ))])
async def list_projects(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort: str = Query("createdAt", description="Sort field"),
    order: str = Query("desc", description="Sort order (asc/desc)"),
):
    """List all projects with pagination."""
    db = get_db()
    result = db.list_projects(page=page, limit=limit, sort=_normalize_sort(sort), order=order)
    validate_paginated(result, item_validator=validate_project)
    return success(result)


@router.post("", status_code=201, dependencies=[Depends(require_permission(Permission.PROJECT_CREATE))])
async def create_project(input_data: CreateProjectInput):
    """Create a new project."""
    db = get_db()
    project_data = {
        "id": str(uuid.uuid4()),
        "name": input_data.name,
        "description": input_data.description or "",
        "author": input_data.author or "",
    }
    project = db.create_project(project_data)
    validate_project(project)

    # Sync to UDM (System B) — non-blocking, never raises
    try:
        sync_project_to_udm(project)
    except Exception:
        pass  # Bridge failures are logged internally, must not block

    return success(project)


@router.get("/{project_id}", dependencies=[Depends(require_permission(Permission.PROJECT_READ))])
async def get_project(project_id: str):
    """Get a project by ID."""
    db = get_db()
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    validate_project(project)
    return success(project)


@router.put("/{project_id}", dependencies=[Depends(require_permission(Permission.PROJECT_UPDATE))])
async def update_project(project_id: str, input_data: UpdateProjectInput):
    """Update an existing project."""
    db = get_db()
    updates = input_data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    project = db.update_project(project_id, updates)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    validate_project(project)

    # Sync update to UDM (System B) — non-blocking, never raises
    try:
        sync_project_update_to_udm(project_id, updates)
    except Exception:
        pass  # Bridge failures are logged internally, must not block

    return success(project)


@router.delete("/{project_id}", dependencies=[Depends(require_permission(Permission.PROJECT_DELETE))])
async def delete_project(project_id: str):
    """Delete a project and all its children."""
    db = get_db()
    deleted = db.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")

    # Sync deletion to UDM (System B) — non-blocking, never raises
    try:
        sync_project_delete_to_udm(project_id)
    except Exception:
        pass  # Bridge failures are logged internally, must not block

    return success(None, "Project deleted")
