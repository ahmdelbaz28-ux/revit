# File-level suppression comment removed per audit guide (V143 hardening).
# Per-line justified suppressions are preserved.
"""
backend/routers/etap.py — ETAP Integration REST API.
=====================================================

Endpoints:
    POST /api/v1/integrations/etap/connect          — Test ETAP connection
    POST /api/v1/integrations/etap/disconnect       — Disconnect from ETAP
    GET  /api/v1/integrations/etap/status           — Get integration status
    GET  /api/v1/integrations/etap/projects         — List ETAP projects
    POST /api/v1/integrations/etap/export           — Export to ETAP
    POST /api/v1/integrations/etap/import           — Import from ETAP
    GET  /api/v1/integrations/etap/logs             — Get sync logs
    POST /api/v1/integrations/etap/settings         — Create/update settings
    GET  /api/v1/integrations/etap/settings         — Get settings
    DELETE /api/v1/integrations/etap/settings       — Delete settings
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth import require_permission
from backend.integrations.etap_schemas import (
    EtapConnectionSettings,
    EtapConnectionTestResponse,
    EtapExportRequest,
    EtapImportRequest,
    EtapProjectInfo,
    EtapSettingsResponse,
    EtapSettingsUpdate,
    EtapSyncLogResponse,
)
from backend.integrations.etap_service import EtapService
from backend.rbac import Permission

router = APIRouter(prefix="/api/v1/integrations/etap", tags=["ETAP Integration"])


def get_etap_service(request: Request) -> EtapService:
    """Dependency to get ETAP service instance."""
    db = request.app.state.db
    return EtapService(db)


# ─── Connection Endpoints ────────────────────────────────────────────────────


@router.post("/connect")
async def test_connection(
    request: Request,
    settings: EtapConnectionSettings,
    service: EtapService = Depends(get_etap_service),
) -> EtapConnectionTestResponse:
    """
    Test connection to ETAP server.

    Requires INTEGRATION_MANAGE permission.
    """
    require_permission(Permission.INTEGRATION_MANAGE)

    project_id = request.query_params.get("project_id", "default")
    result = service.test_connection(project_id)
    return EtapConnectionTestResponse(**result)


@router.post(
    "/disconnect",
    responses={
        404: {"description": "ETAP integration not configured"},
    },
)
async def disconnect(
    request: Request,
    service: EtapService = Depends(get_etap_service),
) -> dict:
    """Disconnect from ETAP (disable integration)."""
    require_permission(Permission.INTEGRATION_MANAGE)

    project_id = request.query_params.get("project_id", "default")
    existing = service.get_settings(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="ETAP integration not configured")

    service.update_settings(project_id, EtapSettingsUpdate(enabled=False))
    return {"message": "Disconnected successfully", "enabled": False}


@router.get("/status")
async def get_status(
    request: Request,
    project_id: str = Query(..., description="Project ID"),
    service: EtapService = Depends(get_etap_service),
) -> dict:
    """Get ETAP integration status for a project."""
    require_permission(Permission.INTEGRATION_READ)
    return service.get_status(project_id)


# ─── Projects Endpoints ──────────────────────────────────────────────────────


@router.get("/projects")
async def list_etap_projects(
    request: Request,
    project_id: str = Query(..., description="Project ID"),
    service: EtapService = Depends(get_etap_service),
) -> List[EtapProjectInfo]:
    """List available ETAP projects."""
    require_permission(Permission.INTEGRATION_READ)
    projects = service.list_etap_projects(project_id)
    return [EtapProjectInfo(**p) for p in projects]


@router.get("/projects/local")
async def list_local_projects(
    request: Request,
    service: EtapService = Depends(get_etap_service),
) -> List[dict]:
    """List local BAZSPARK projects."""
    require_permission(Permission.INTEGRATION_READ)
    return service.list_local_projects()


# ─── Export/Import Endpoints ─────────────────────────────────────────────────


@router.post(
    "/export",
    responses={
        400: {"description": "Bad request — invalid export parameters"},
        500: {"description": "Export failed"},
    },
)
async def export_to_etap(
    request: Request,
    export_request: EtapExportRequest,
    service: EtapService = Depends(get_etap_service),
) -> dict:
    """
    Export local project data to ETAP.

    Requires INTEGRATION_MANAGE permission.
    """
    require_permission(Permission.INTEGRATION_MANAGE)
    try:
        return service.export_to_etap(export_request.project_id, export_request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc


@router.post(
    "/import",
    responses={
        400: {"description": "Bad request — invalid import parameters"},
        500: {"description": "Import failed"},
    },
)
async def import_from_etap(
    request: Request,
    import_request: EtapImportRequest,
    service: Annotated[EtapService, Depends(get_etap_service)],
) -> dict:
    """
    Import data from ETAP to local project.

    Requires INTEGRATION_MANAGE permission.
    """
    require_permission(Permission.INTEGRATION_MANAGE)
    try:
        return service.import_from_etap(import_request.project_id, import_request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Import failed: {exc}") from exc


# ─── Logs Endpoint ───────────────────────────────────────────────────────────


@router.get("/logs")
async def get_logs(
    request: Request,
    service: Annotated[EtapService, Depends(get_etap_service)],
    project_id: str = Query(..., description="Project ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
) -> EtapSyncLogResponse:
    """Get sync logs for a project."""
    require_permission(Permission.INTEGRATION_READ)
    result = service.get_logs(project_id, page, page_size)
    return EtapSyncLogResponse(**result)


# ─── Settings Endpoints ──────────────────────────────────────────────────────


@router.post("/settings")
async def create_settings(
    request: Request,
    service: Annotated[EtapService, Depends(get_etap_service)],
    settings: EtapConnectionSettings,
    project_id: str = Query(..., description="Project ID"),
) -> EtapSettingsResponse:
    """
    Create ETAP integration settings for a project.

    Requires INTEGRATION_MANAGE permission.
    """
    require_permission(Permission.INTEGRATION_MANAGE)
    result = service.create_settings(project_id, settings)
    return EtapSettingsResponse(**result)


@router.get("/settings")
async def get_settings(
    request: Request,
    service: Annotated[EtapService, Depends(get_etap_service)],
    project_id: str = Query(..., description="Project ID"),
) -> Optional[EtapSettingsResponse]:
    """Get ETAP settings for a project (no secrets returned)."""
    require_permission(Permission.INTEGRATION_READ)
    settings = service.get_settings(project_id)
    if not settings:
        return None
    # Return only non-sensitive fields
    safe_settings = {
        "id": settings["id"],
        "project_id": settings["project_id"],
        "host": settings["host"],
        "port": settings["port"],
        "username": settings["username"],
        "enabled": settings["enabled"],
        "last_sync": settings["last_sync"],
        "created_at": settings["created_at"],
        "updated_at": settings["updated_at"],
    }
    return EtapSettingsResponse(**safe_settings)


@router.put(
    "/settings",
    responses={
        404: {"description": "ETAP integration not configured"},
    },
)
async def update_settings(
    request: Request,
    service: Annotated[EtapService, Depends(get_etap_service)],
    update: EtapSettingsUpdate,
    project_id: str = Query(..., description="Project ID"),
) -> EtapSettingsResponse:
    """
    Update ETAP integration settings.

    Requires INTEGRATION_MANAGE permission.
    Password is optional — only update if provided.
    """
    require_permission(Permission.INTEGRATION_MANAGE)
    updated = service.update_settings(project_id, update)
    if not updated:
        raise HTTPException(status_code=404, detail="ETAP integration not configured")
    # Return only non-sensitive fields
    safe_settings = {
        "id": updated["id"],
        "project_id": updated["project_id"],
        "host": updated["host"],
        "port": updated["port"],
        "username": updated["username"],
        "enabled": updated["enabled"],
        "last_sync": updated["last_sync"],
        "created_at": updated["created_at"],
        "updated_at": updated["updated_at"],
    }
    return EtapSettingsResponse(**safe_settings)


@router.delete(
    "/settings",
    responses={
        404: {"description": "ETAP integration not configured"},
    },
)
async def delete_settings(
    request: Request,
    service: Annotated[EtapService, Depends(get_etap_service)],
    project_id: str = Query(..., description="Project ID"),
) -> dict:
    """Delete ETAP integration settings."""
    require_permission(Permission.INTEGRATION_MANAGE)
    deleted = service.delete_settings(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="ETAP integration not configured")
    return {"message": "Settings deleted successfully"}
