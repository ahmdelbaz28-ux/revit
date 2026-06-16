"""
backend/routers/digital_twin.py — Digital Twin API Endpoints
=============================================================

REST API for Digital Twin operations:
- AutoCAD → Revit conversion
- Revit → AutoCAD conversion
- Version history management
- Conversion settings configuration

ENDPOINTS:
- POST /api/v1/digital-twin/convert/autocad-to-revit — Convert AutoCAD to Revit
- POST /api/v1/digital-twin/convert/revit-to-autocad — Convert Revit to AutoCAD
- GET /api/v1/digital-twin/history — Get conversion history
- POST /api/v1/digital-twin/rollback/{version_id} — Rollback to version
- GET /api/v1/digital-twin/config — Get conversion configuration
- PUT /api/v1/digital-twin/config — Update conversion configuration
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, status, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.rbac import Permission
from backend.auth import require_permission
from backend.services.digital_twin_service import (
    ConversionConfig,
    ConversionConfigManager,
    ConversionResult,
    DigitalTwinService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/digital-twin", tags=["Digital Twin"])


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

UPLOAD_DIR = os.getenv("DIGITAL_TWIN_UPLOAD_DIR", "uploads")


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and special-char issues.
    Keeps only basename and replaces unsafe characters.
    """
    # Ensure basename-only (drops any path segments)
    base = os.path.basename(filename or "")
    # Reject empty / suspicious
    if not base or base in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Reject explicit traversal patterns
    if ".." in base or base.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Replace unsafe characters; keep common safe set
    safe = []
    for ch in base:
        if ch.isalnum() or ch in ("-", "_", ".", " "):
            safe.append(ch)
        else:
            safe.append("_")
    sanitized = "".join(safe).strip()
    if not sanitized:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return sanitized


def _safe_resolve_upload_path(filename: str) -> str:
    """
    Resolve a filename under UPLOAD_DIR only. Prevents path traversal.
    Returns the resolved absolute path if valid.
    """
    sanitized = _sanitize_filename(filename)
    base_dir = os.path.realpath(UPLOAD_DIR)
    target = os.path.realpath(os.path.join(base_dir, sanitized))

    # Must stay inside uploads dir
    if not (target + os.sep).startswith(base_dir + os.sep) and target != base_dir:
        raise HTTPException(status_code=400, detail="Invalid file path")
    return target


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class ConversionResponse(BaseModel):
    """Response from a conversion operation."""
    success: bool
    source_file: str
    target_file: str
    elements_converted: int
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    duration_seconds: float
    timestamp: str
    message: str = ""


class VersionInfo(BaseModel):
    """Version history entry."""
    version_id: str
    timestamp: str
    source_file: str
    target_file: str
    conversion_type: str
    elements_count: int
    status: str


class HistoryResponse(BaseModel):
    """Response with conversion history."""
    versions: List[VersionInfo]
    total: int


class OperationResponse(BaseModel):
    """Generic operation response."""
    success: bool
    message: str


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_digital_twin_service: Optional[DigitalTwinService] = None
_config_manager = ConversionConfigManager()


def get_digital_twin_service() -> DigitalTwinService:
    """Get or initialize Digital Twin service singleton."""
    global _digital_twin_service
    if _digital_twin_service is None:
        config = _config_manager.load()
        _digital_twin_service = DigitalTwinService(config)
    return _digital_twin_service


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/convert/autocad-to-revit",
    response_model=ConversionResponse,
    dependencies=[Depends(require_permission(Permission.EXPORT_EXECUTE))],
)
async def convert_autocad_to_revit(
    file: UploadFile = File(...),
    output_path: Optional[str] = None,
    template_path: Optional[str] = None,
):
    """
    Convert AutoCAD DWG/DXF file to Revit RVT.
    
    Args:
        file: Uploaded DWG/DXF file
        output_path: Optional output path for RVT file
        template_path: Optional Revit template path
    
    Returns:
        ConversionResponse with conversion results
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename is required",
            )

        # Validate file extension
        if not file.filename.lower().endswith(('.dwg', '.dxf')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be .dwg or .dxf",
            )
        
        # Save uploaded file temporarily (sanitized under UPLOAD_DIR only)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        safe_in_name = _sanitize_filename(file.filename)
        input_path = os.path.join(UPLOAD_DIR, safe_in_name)
        
        with open(input_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Determine output path
        if not output_path:
            output_path = input_path.rsplit('.', 1)[0] + '.rvt'
        
        # Perform conversion
        service = get_digital_twin_service()
        result: ConversionResult = service.convert_autocad_to_revit(
            dwg_path=input_path,
            rvt_path=output_path,
            template=template_path,
        )
        
        return ConversionResponse(
            success=result.success,
            source_file=result.source_file,
            target_file=result.target_file,
            elements_converted=result.elements_converted,
            errors=result.errors,
            warnings=result.warnings,
            duration_seconds=result.duration_seconds,
            timestamp=result.timestamp,
            message="Conversion completed successfully" if result.success else "Conversion failed",
        )
    except Exception as e:
        logger.error(f"Failed to convert AutoCAD to Revit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conversion failed: {str(e)}",
        )


@router.post(
    "/convert/revit-to-autocad",
    response_model=ConversionResponse,
    dependencies=[Depends(require_permission(Permission.EXPORT_EXECUTE))],
)
async def convert_revit_to_autocad(
    file: UploadFile = File(...),
    output_path: Optional[str] = None,
):
    """
    Convert Revit RVT file to AutoCAD DWG.
    
    Args:
        file: Uploaded RVT file
        output_path: Optional output path for DWG file
    
    Returns:
        ConversionResponse with conversion results
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename is required",
            )

        # Validate file extension
        if not file.filename.lower().endswith('.rvt'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be .rvt",
            )
        
        # Save uploaded file temporarily (sanitized under UPLOAD_DIR only)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        safe_in_name = _sanitize_filename(file.filename)
        input_path = os.path.join(UPLOAD_DIR, safe_in_name)
        
        with open(input_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Determine output path
        if not output_path:
            output_path = input_path.rsplit('.', 1)[0] + '.dwg'
        
        # Perform conversion
        service = get_digital_twin_service()
        result: ConversionResult = service.convert_revit_to_autocad(
            rvt_path=input_path,
            dwg_path=output_path,
        )
        
        return ConversionResponse(
            success=result.success,
            source_file=result.source_file,
            target_file=result.target_file,
            elements_converted=result.elements_converted,
            errors=result.errors,
            warnings=result.warnings,
            duration_seconds=result.duration_seconds,
            timestamp=result.timestamp,
            message="Conversion completed successfully" if result.success else "Conversion failed",
        )
    except Exception as e:
        logger.error(f"Failed to convert Revit to AutoCAD: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conversion failed: {str(e)}",
        )


@router.get(
    "/history",
    response_model=HistoryResponse,
    dependencies=[Depends(require_permission(Permission.EXPORT_READ))],
)
async def get_history():
    """
    Get conversion version history.
    
    Returns:
        HistoryResponse with list of all conversions
    """
    try:
        service = get_digital_twin_service()
        history = service.get_conversion_history()
        
        versions = [
            VersionInfo(
                version_id=v["version_id"],
                timestamp=v["timestamp"],
                source_file=v["source_file"],
                target_file=v["target_file"],
                conversion_type=v["conversion_type"],
                elements_count=v["elements_count"],
                status=v["status"],
            )
            for v in history
        ]
        
        return HistoryResponse(
            versions=versions,
            total=len(versions),
        )
    except Exception as e:
        logger.error(f"Failed to get history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get history: {str(e)}",
        )


@router.post(
    "/rollback/{version_id}",
    response_model=OperationResponse,
    dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))],
)
async def rollback_to_version(version_id: str):
    """
    Rollback to a specific conversion version.
    
    Args:
        version_id: Version ID to rollback to
    
    Returns:
        OperationResponse with success status
    """
    try:
        service = get_digital_twin_service()
        success = service.rollback_to_version(version_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_id} not found",
            )
        
        return OperationResponse(
            success=True,
            message=f"Successfully rolled back to version {version_id}",
        )
    except Exception as e:
        logger.error(f"Failed to rollback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rollback failed: {str(e)}",
        )


@router.get(
    "/config",
    response_model=ConversionConfig,
    dependencies=[Depends(require_permission(Permission.EXPORT_READ))],
)
async def get_config():
    """
    Get conversion configuration.
    
    Returns:
        ConversionConfig with current settings
    """
    try:
        config = _config_manager.load()
        return config
    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get config: {str(e)}",
        )


@router.put(
    "/config",
    response_model=OperationResponse,
    dependencies=[Depends(require_permission(Permission.SYSTEM_CONFIG))],
)
async def update_config(config: ConversionConfig):
    """
    Update conversion configuration.
    
    Args:
        config: ConversionConfig with new settings
    
    Returns:
        OperationResponse with success status
    """
    try:
        _config_manager.save(config)
        
        return OperationResponse(
            success=True,
            message="Configuration updated successfully",
        )
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update failed: {str(e)}",
        )


@router.get(
    "/download/{filename:path}",
    dependencies=[Depends(require_permission(Permission.EXPORT_READ))],
)
async def download_file(filename: str):
    """
    Download a converted file.
    
    Args:
        filename: Path to file
    
    Returns:
        FileResponse with file content
    """
    try:
        # Restrict downloads to uploads directory only
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
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download failed: {str(e)}",
        )
