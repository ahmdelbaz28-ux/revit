"""
backend/routers/ifc_service_router.py — API Endpoints for IFC Service
======================================================================

REST API for IFC-native operations: load, extract, convert.
All endpoints enforce path traversal protection and audit trail.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from backend.services.ifc_service import IFCService

logger = logging.getLogger("fireai.routers.ifc_service")

router = APIRouter(prefix="/ifc-service", tags=["ifc-service"])


@router.post("/extract")
async def extract_ifc(request: Request) -> dict:
    """
    Extract building data from an IFC file.

    Request body: {"file_path": "/path/to/file.ifc", "correlation_id": "optional"}
    """
    body = await request.json()
    file_path = body.get("file_path")
    correlation_id = body.get("correlation_id") or request.headers.get("X-Correlation-ID")

    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required")

    svc = IFCService()
    try:
        result = svc.extract_all(file_path, correlation_id=correlation_id)
        standard = svc.to_standard_format(result)
        return {"status": "ok", "data": standard}
    except ValueError as e:
        if "SECURITY" in str(e):
            raise HTTPException(status_code=403, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("IFC extraction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")


@router.post("/load")
async def load_ifc(request: Request) -> dict:
    """
    Load an IFC file and return basic metadata.

    Request body: {"file_path": "/path/to/file.ifc"}
    """
    body = await request.json()
    file_path = body.get("file_path")

    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required")

    svc = IFCService()
    try:
        result = svc.load(file_path)
        svc.close()
        return {"status": "ok", "data": result}
    except ValueError as e:
        if "SECURITY" in str(e):
            raise HTTPException(status_code=403, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health")
async def health() -> dict:
    """Health check for IFC service."""
    try:
        import ifcopenshell  # noqa: F401
        ifc_available = True
        ifc_version = ifcopenshell.version
    except ImportError:
        ifc_available = False
        ifc_version = None

    return {
        "status": "healthy",
        "ifcopenshell_available": ifc_available,
        "ifcopenshell_version": ifc_version,
    }
