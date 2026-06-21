"""
backend/routers/digital_twin.py — Digital Twin Conversion Endpoints
===================================================================

Provides endpoints for bidirectional CAD/BIM conversion,
configuration management, version control, and mapping operations.

FIXES APPLIED:
- FIX #8:  Added duration_seconds to ConvertResponse
- FIX #9:  Removed duplicate /rollback/{version_id} route (kept RBAC-protected version)
- FIX #10: Removed duplicate /config route (kept RBAC-protected version)
- FIX #11: Replaced __import__('datetime') with proper import + UTC timezone
- FIX #12: Added missing imports (os, status, FileResponse, etc.)
- FIX #20: Never expose str(e) to client — safe error messages
- FIX #24: Dependency injection instead of module-level service instances
- FIX #25: Update mapping uses request body instead of query params
- FIX #31: Added module docstring
- FIX #33: Proper multi-line imports
"""

import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.rbac import Permission
from backend.auth import require_permission
from backend.services.digital_twin_service import (
    ConversionConfig,
    ConversionConfigManager,
    DigitalTwinService,
)
from parsers._path_security import validate_input_path, UnsafePathError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/digital-twin", tags=["digital-twin"])


# ── Dependency injection (FIX #24) ─────────────────────────────────────────
# Previously, service and config_manager were created at module level,
# making testing difficult and causing import-order issues.

def get_digital_twin_service() -> DigitalTwinService:
    """Provide DigitalTwinService instance via dependency injection."""
    return DigitalTwinService()


def get_config_manager() -> ConversionConfigManager:
    """Provide ConversionConfigManager instance via dependency injection."""
    return ConversionConfigManager()


def _safe_resolve_upload_path(filename: str) -> str:
    """Resolve a filename to a safe path within the uploads directory.

    P0.2 FIX (2026-06-20): The previous implementation used
    `os.path.normpath + startswith(abs_upload)` which is bypassable
    in several ways:
      - Case-insensitive filesystems (e.g. "Uploads/../etc" vs "uploads")
        where startswith() compares strings, not canonical paths.
      - Symlink chases: normpath does not resolve symlinks, so a symlink
        inside upload_dir pointing outside would pass the check.
      - Trailing-separator confusion: "uploads/" vs "uploads" prefix
        match can be tricked with siblings like "uploads_evil/...".

    Root-cause fix: reuse the centralised parsers._path_security.validate_input_path()
    helper — the same security contract used by backend/routers/revit.py.

    The function applies TWO security passes:
      PASS 1 (string-level, on the user-supplied filename):
        - Null-byte rejection (C-string truncation guard)
        - Argument-injection guard (rejects filenames starting with "-")
        These checks MUST run on the raw filename BEFORE joining to
        upload_dir, because joining turns "-foo" into "uploads/-foo"
        which no longer starts with "-" and bypasses the guard.

      PASS 2 (path-level, on the joined path):
        - Path.resolve() — follows symlinks, canonicalises case
        - relative_to(allowed_base) check — true path-containment, not
          string-prefix matching
        - Existence check (FileNotFoundError on missing)

    The function is intentionally stricter than the old one: it REQUIRES
    the file to exist (404 on missing) and to live under
    $FIREAI_ALLOWED_UPLOAD_DIRS (400 on escape attempt).
    """
    # ── PASS 1: raw-string security checks on the user filename ───────
    # We call validate_input_path() on the bare filename to invoke the
    # null-byte and leading-dash guards. These run BEFORE the existence
    # check, so they fire even when the path doesn't exist.
    # FileNotFoundError is expected here (the bare filename won't exist
    # as a relative path) — we swallow it and proceed to PASS 2.
    try:
        validate_input_path(filename, parser_name="digital_twin_router::filename")
    except UnsafePathError as exc:
        # Hard security rejection — log details, return generic 400.
        logger.warning(
            "Path traversal blocked in digital_twin (filename guard): %s", exc
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename. Contact administrator.",
        ) from exc
    except FileNotFoundError:
        # Expected — the bare filename doesn't exist as a relative path.
        # PASS 2 will check existence of the joined path.
        pass

    # ── PASS 2: path-containment check on the joined path ────────────
    upload_dir = os.getenv("FIREAI_UPLOAD_DIR", "uploads")
    candidate = Path(upload_dir) / filename
    try:
        safe_path = validate_input_path(
            str(candidate),
            parser_name="digital_twin_router::joined",
        )
    except FileNotFoundError as exc:
        # Benign missing-file case — let the caller return 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found.",
        ) from exc
    except UnsafePathError as exc:
        # Hard security rejection — log details, return generic 400.
        logger.warning(
            "Path traversal blocked in digital_twin (joined path): %s", exc
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File path is outside allowed directories. Contact administrator.",
        ) from exc
    return str(safe_path)


# ── Pydantic models ────────────────────────────────────────────────────────

class ConvertRequest(BaseModel):
    """Request model for conversion operation."""
    source_filepath: str = Field(min_length=1, max_length=500)
    target_filepath: str = Field(min_length=1, max_length=500)
    conversion_type: str = Field(
        pattern=r"^(autocad_to_revit|revit_to_autocad)$",
        description="Conversion direction: autocad_to_revit or revit_to_autocad",
    )
    template_path: Optional[str] = None


class ConvertResponse(BaseModel):
    """Response model for conversion operation.

    FIX #8: Added duration_seconds field which was previously missing,
    causing Pydantic ValidationError at runtime.
    """
    success: bool
    source_file: str
    target_file: str
    elements_converted: int
    duration_seconds: Optional[float] = None
    errors: List[str] = []
    warnings: List[str] = []


class OperationResponse(BaseModel):
    """Generic operation response."""
    success: bool
    message: str
    handle: Optional[str] = None


class HistoryResponse(BaseModel):
    """Response model for conversion history."""
    history: List[Dict[str, Any]]


class ConfigureRequest(BaseModel):
    """Request model for configuration update."""
    config: Dict[str, Any]


class ConfigureResponse(BaseModel):
    """Response model for configuration update."""
    success: bool
    message: str


class RollbackRequest(BaseModel):
    """Request model for rollback operation."""
    target_file: str = Field(min_length=1, max_length=500)


class UpdateMappingRequest(BaseModel):
    """Request model for updating a single mapping rule (FIX #25).

    Uses request body instead of query parameters for a POST operation.
    """
    layer: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=255)
    direction: str = Field(
        default="autocad_to_revit",
        pattern=r"^(autocad_to_revit|revit_to_autocad)$",
    )


class MappingsResponse(BaseModel):
    """Response model for available mappings."""
    layer_to_category: Dict[str, str]
    category_to_layer: Dict[str, str]
    linetype_to_element: Dict[str, str]
    block_to_family: Dict[str, str]
    units: Dict[str, Any]
    levels: Dict[str, Any]


# ── Safe error helper (FIX #20) ────────────────────────────────────────────
def _safe_error(status_code: int, log_msg: str, exc: Exception) -> HTTPException:
    """Log full exception detail, return safe message to client."""
    logger.error("%s: %s", log_msg, exc, exc_info=True)
    return HTTPException(status_code=status_code, detail=log_msg)


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/convert", response_model=ConvertResponse)
async def convert_files(
    request: ConvertRequest,
    service: DigitalTwinService = Depends(get_digital_twin_service),
) -> ConvertResponse:
    """Perform bidirectional CAD/BIM conversion."""
    try:
        if request.conversion_type == "autocad_to_revit":
            result = service.convert_autocad_to_revit(
                request.source_filepath,
                request.target_filepath,
                request.template_path,
            )
        elif request.conversion_type == "revit_to_autocad":
            result = service.convert_revit_to_autocad(
                request.source_filepath,
                request.target_filepath,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid conversion type: {request.conversion_type}",
            )

        return ConvertResponse(
            success=result.success,
            source_file=result.source_file,
            target_file=result.target_file,
            elements_converted=result.elements_converted,
            duration_seconds=getattr(result, "duration_seconds", None),
            errors=result.errors,
            warnings=result.warnings,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error during conversion", e)


@router.get("/history", response_model=HistoryResponse)
async def get_conversion_history(
    service: DigitalTwinService = Depends(get_digital_twin_service),
) -> HistoryResponse:
    """Get conversion history."""
    try:
        history = service.get_conversion_history()
        return HistoryResponse(history=history)
    except Exception as e:
        raise _safe_error(500, "Error getting conversion history", e)


@router.post("/configure", response_model=ConfigureResponse)
async def configure_conversion(
    request: ConfigureRequest,
    config_mgr: ConversionConfigManager = Depends(get_config_manager),
) -> ConfigureResponse:
    """Update conversion configuration."""
    try:
        config = ConversionConfig.from_dict(request.config)
        success = config_mgr.save_config(config)

        if success:
            return ConfigureResponse(
                success=True,
                message="Configuration updated successfully",
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error updating configuration", e)


@router.post(
    "/rollback/{version_id}",
    response_model=OperationResponse,
    dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))],
)
async def rollback_to_version(
    version_id: str,
    request: RollbackRequest,
    service: DigitalTwinService = Depends(get_digital_twin_service),
) -> OperationResponse:
    """Rollback to a specific conversion version.

    FIX #9: Removed the duplicate /rollback/{version_id} route that lacked
    RBAC protection. This is now the single canonical rollback endpoint.
    """
    try:
        success = service.rollback_to_version(version_id, request.target_file)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Version not found or rollback failed",
            )

        return OperationResponse(
            success=True,
            message=f"Successfully rolled back to version {version_id}",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Rollback failed", e)


@router.get("/mappings", response_model=MappingsResponse)
async def get_available_mappings(
    config_mgr: ConversionConfigManager = Depends(get_config_manager),
) -> MappingsResponse:
    """Get available mapping configurations."""
    try:
        mappings = config_mgr.get_available_mappings()
        return MappingsResponse(
            layer_to_category=mappings["layer_to_category"],
            category_to_layer=mappings["category_to_layer"],
            linetype_to_element=mappings["linetype_to_element"],
            block_to_family=mappings["block_to_family"],
            units=mappings["units"],
            levels=mappings["levels"],
        )
    except Exception as e:
        raise _safe_error(500, "Error getting mappings", e)


@router.get("/status")
async def get_digital_twin_status(
    service: DigitalTwinService = Depends(get_digital_twin_service),
) -> Dict[str, Any]:
    """Get Digital Twin service status.

    FIX #11: Replaced __import__('datetime').datetime.now() with proper
    import using UTC timezone for consistent timestamps.
    """
    try:
        history = service.get_conversion_history()
        return {
            "status": "ready",
            "total_conversions": len(history),
            "last_conversion": history[-1] if history else None,
            "config_loaded": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise _safe_error(500, "Error getting Digital Twin status", e)


@router.post("/update_mapping")
async def update_single_mapping(
    request: UpdateMappingRequest,
    config_mgr: ConversionConfigManager = Depends(get_config_manager),
) -> Dict[str, Any]:
    """Update a single mapping rule.

    FIX #25: Uses request body (UpdateMappingRequest) instead of query
    parameters, enabling proper validation and API documentation.
    """
    try:
        success = config_mgr.update_mapping(request.layer, request.category, request.direction)
        if success:
            return {
                "success": True,
                "message": f"Mapping updated: {request.layer} -> {request.category} ({request.direction})",
                "mapping": {request.layer: request.category},
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update mapping")
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error updating mapping", e)


@router.get(
    "/config",
    dependencies=[Depends(require_permission(Permission.EXPORT_READ))],
)
async def get_config(
    config_mgr: ConversionConfigManager = Depends(get_config_manager),
) -> Dict[str, Any]:
    """Get current conversion configuration.

    FIX #10: Removed the duplicate /config GET route that lacked RBAC
    protection. This is now the single canonical config endpoint.
    """
    try:
        config = config_mgr.load_config()
        return {
            "config": config.to_dict(),
            "loaded_from": str(config_mgr.config_file) if hasattr(config_mgr, "config_file") and config_mgr.config_file.exists() else "default",
        }
    except Exception as e:
        raise _safe_error(500, "Error getting configuration", e)


@router.put(
    "/config",
    response_model=OperationResponse,
    dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))],
)
async def update_config(
    config: ConversionConfig,
    config_mgr: ConversionConfigManager = Depends(get_config_manager),
) -> OperationResponse:
    """Update conversion configuration."""
    try:
        config_mgr.save(config)

        return OperationResponse(
            success=True,
            message="Configuration updated successfully",
        )
    except Exception as e:
        raise _safe_error(500, "Configuration update failed", e)


@router.get(
    "/download/{filename:path}",
    dependencies=[Depends(require_permission(Permission.EXPORT_READ))],
)
async def download_file(filename: str) -> FileResponse:
    """Download a converted file.

    FIX #12: Added missing imports for os, status, FileResponse, and
    _safe_resolve_upload_path that were previously undefined.
    """
    try:
        resolved_path = _safe_resolve_upload_path(filename)

        if not os.path.exists(resolved_path) or not os.path.isfile(resolved_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        return FileResponse(
            path=resolved_path,
            filename=os.path.basename(resolved_path),
            media_type="application/octet-stream",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Download failed", e)
