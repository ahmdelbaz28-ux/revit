"""backend/routers/health.py — Health check endpoint.

Provides system health information including:
  - API status
  - Version
  - Uptime
  - Database connectivity

LIFE-SAFETY NOTE: Honest health reporting is critical. A false-green
health endpoint misleads deployment probes and operators.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from backend.auth import require_permission
from backend.contract import validate_health
from backend.database import get_db
from backend.db_service import DatabaseService, get_db_service
from backend.rbac import Permission
from fireai.version import __package_version__

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Track application start time
_start_time = time.time()

# Track core module availability (set from app.py)
_core_modules_loaded = False


def set_core_modules_loaded(loaded: bool) -> None:
    """Set whether core NFPA 72 modules are loaded. Called from app.py."""
    global _core_modules_loaded
    _core_modules_loaded = loaded


@router.get("/health", dependencies=[Depends(require_permission(Permission.HEALTH_READ))])
async def health_check():
    """Health check endpoint.

    Returns honest system status including database connectivity.
    """
    db_connected = True
    try:
        db = get_db()
        # Simple query to verify database is responsive
        result = db.list_projects(page=1, limit=1)
        db_connected = result is not None
    except Exception as e:
        logger.debug("Health check: main database connection failed: %s", e)
        db_connected = False

    # Check UDM (UniversalDataModel) database connectivity
    udm_connected = True
    try:
        udm: DatabaseService = get_db_service()
        udm_stats = udm.get_statistics()
        udm_connected = udm_stats is not None
    except Exception as e:
        logger.debug("Health check: UDM database connection failed: %s", e)
        udm_connected = False

    uptime = time.time() - _start_time
    status = "ok" if (db_connected and udm_connected) else "degraded"

    # Check if core NFPA 72 modules are loaded
    core_modules = "loaded" if _core_modules_loaded else "unavailable"

    health_data = {
        "status": status,
        "api_version": "v1",
        "version": __package_version__,
        "uptime": round(uptime, 2),
        "uptime_seconds": round(uptime, 2),
        "database": "connected" if db_connected else "disconnected",
        "udm_database": "connected" if udm_connected else "disconnected",
        "core_modules": core_modules,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Validate contract — logs CRITICAL on violation but does not block response.
    # A failing health endpoint must still return data so operators can diagnose.
    validated = validate_health(health_data)
    from backend.response import success
    return success(validated)


@router.get("/health/statistics", dependencies=[Depends(require_permission(Permission.HEALTH_READ))])
async def get_health_statistics():
    """Health statistics endpoint.

    Provides counts of projects, devices, and connections across all projects.
    Also includes UDM element counts when core modules are available.
    This endpoint is used by the frontend Dashboard and Statistics API client.
    """
    try:
        db = get_db()
        projects_result = db.list_projects(page=1, limit=1)
        total_projects = projects_result.get("total", 0)

        # Use efficient SQL COUNT instead of loading all projects into memory
        counts = db.get_global_counts()
        total_devices = counts["total_devices"]
        total_connections = counts["total_connections"]
        active_projects = counts["active_projects"]

        # Try to include UDM element counts if core modules are available
        udm_total_elements = 0
        udm_active_elements = 0
        udm_deleted_elements = 0
        udm_total_connections_udm = 0
        udm_total_conflicts = 0
        udm_unresolved_conflicts = 0
        try:
            udm_db: DatabaseService = get_db_service()
            udm_stats = udm_db.get_statistics()
            udm_total_elements = udm_stats.total_elements
            udm_active_elements = udm_stats.active_elements
            udm_deleted_elements = udm_stats.deleted_elements
            udm_total_connections_udm = udm_stats.total_connections
            udm_total_conflicts = udm_stats.total_conflicts
            udm_unresolved_conflicts = udm_stats.unresolved_conflicts
        except Exception:
            pass  # UDM not available — counts remain 0

        from backend.response import success
        return success({
            "total_elements": total_devices + udm_total_elements,
            "deleted_elements": udm_deleted_elements,
            "active_elements": total_devices + udm_active_elements,
            "total_projects": total_projects,
            "active_projects": active_projects,
            "total_connections": total_connections + udm_total_connections_udm,
            "total_conflicts": udm_total_conflicts,
            "unresolved_conflicts": udm_unresolved_conflicts,
            "pending_autocad_to_revit": 0,
            "pending_revit_to_autocad": 0,
            "database_version": 1,
            "last_sync": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    except Exception as e:
        # H-3 FIX: Never expose str(e) to the client — Python exceptions can
        # include file paths, DB connection strings, and internal variable names.
        # In a fire protection system, this information could help attackers.
        logger.error("Statistics endpoint error: %s", e, exc_info=True)
        from backend.response import error
        return error("Statistics unavailable — check server logs", {
            "total_elements": 0,
            "deleted_elements": 0,
            "active_elements": 0,
            "total_projects": 0,
            "active_projects": 0,
            "total_connections": 0,
            "total_conflicts": 0,
            "unresolved_conflicts": 0,
            "pending_autocad_to_revit": 0,
            "pending_revit_to_autocad": 0,
            "database_version": 0,
            "last_sync": None,
        })


# Keep legacy /reports/statistics path working (frontwards-compat)
@router.get("/reports/statistics", dependencies=[Depends(require_permission(Permission.HEALTH_READ))])
async def get_statistics():
    """Legacy alias for /health/statistics."""
    return await get_health_statistics()
