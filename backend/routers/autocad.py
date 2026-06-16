"""
backend/routers/autocad.py — AutoCAD API Endpoints
===================================================

REST API for AutoCAD operations:
- Connection management
- DWG/DXF file reading
- Drawing commands
- Configuration management

ENDPOINTS:
- GET /api/v1/autocad/status — Check AutoCAD connection status
- POST /api/v1/autocad/connect — Connect to AutoCAD
- POST /api/v1/autocad/disconnect — Disconnect from AutoCAD
- GET /api/v1/autocad/read/{filepath} — Read DWG/DXF file
- POST /api/v1/autocad/draw/line — Draw a line
- POST /api/v1/autocad/draw/circle — Draw a circle
- POST /api/v1/autocad/draw/text — Draw text
- POST /api/v1/autocad/modify — Modify entity
- DELETE /api/v1/autocad/entity/{handle} — Delete entity
- GET /api/v1/autocad/config — Get configuration
- PUT /api/v1/autocad/config — Update configuration
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.services.autocad_service import (
    AutoCADConfig,
    AutoCADConfigManager,
    AutoCADService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/autocad", tags=["AutoCAD"])


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class ConnectionStatus(BaseModel):
    """AutoCAD connection status."""
    connected: bool
    version: Optional[str] = None
    document: Optional[str] = None
    message: str = ""


class ConnectRequest(BaseModel):
    """Request to connect to AutoCAD."""
    force_new: bool = Field(default=False, description="Force new AutoCAD instance")


class DrawLineRequest(BaseModel):
    """Request to draw a line."""
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    layer: str = Field(default="0")
    color: int = Field(default=256)


class DrawCircleRequest(BaseModel):
    """Request to draw a circle."""
    center_x: float
    center_y: float
    radius: float
    layer: str = Field(default="0")
    color: int = Field(default=256)


class DrawTextRequest(BaseModel):
    """Request to draw text."""
    text: str
    insert_x: float
    insert_y: float
    height: float = Field(default=2.5)
    rotation: float = Field(default=0.0)
    layer: str = Field(default="0")
    color: int = Field(default=256)


class ModifyEntityRequest(BaseModel):
    """Request to modify an entity."""
    handle: str
    properties: Dict[str, Any]


class ReadFileResponse(BaseModel):
    """Response from reading a DWG/DXF file."""
    filepath: str
    metadata: Dict[str, Any]
    layers: List[Dict[str, Any]]
    entities: List[Dict[str, Any]]
    blocks: Dict[str, List[Dict[str, Any]]]
    entity_count: int


class OperationResponse(BaseModel):
    """Generic operation response."""
    success: bool
    message: str
    handle: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_autocad_service: Optional[AutoCADService] = None
_config_manager = AutoCADConfigManager()


def get_autocad_service() -> AutoCADService:
    """Get or initialize AutoCAD service singleton."""
    global _autocad_service
    if _autocad_service is None:
        config = _config_manager.load()
        _autocad_service = AutoCADService(config)
    return _autocad_service


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/status", response_model=ConnectionStatus)
async def get_status():
    """
    Check AutoCAD connection status.
    
    Returns:
        ConnectionStatus with connected flag, version, and document info
    """
    try:
        service = get_autocad_service()
        
        if service.connection.is_connected:
            return ConnectionStatus(
                connected=True,
                version=service.connection.acad_app.Version if service.connection.is_connected else None,
                document=service.connection.doc.Name if service.connection.is_connected else None,
                message="Connected to AutoCAD",
            )
        else:
            return ConnectionStatus(
                connected=False,
                message="Not connected to AutoCAD",
            )
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        return ConnectionStatus(
            connected=False,
            message=f"Error: {str(e)}",
        )


@router.post("/connect", response_model=ConnectionStatus)
async def connect(request: ConnectRequest):
    """
    Connect to AutoCAD.
    
    Args:
        request: ConnectRequest with force_new flag
    
    Returns:
        ConnectionStatus with connection details
    """
    try:
        service = get_autocad_service()
        
        if not service.initialize():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to connect to AutoCAD. Is AutoCAD installed and running?",
            )
        
        return ConnectionStatus(
            connected=True,
            version=service.connection.acad_app.Version,
            document=service.connection.doc.Name,
            message="Successfully connected to AutoCAD",
        )
    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection failed: {str(e)}",
        )


@router.post("/disconnect", response_model=OperationResponse)
async def disconnect():
    """
    Disconnect from AutoCAD.
    
    Returns:
        OperationResponse with success status
    """
    try:
        service = get_autocad_service()
        service.shutdown()
        
        return OperationResponse(
            success=True,
            message="Successfully disconnected from AutoCAD",
        )
    except Exception as e:
        logger.error(f"Failed to disconnect: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Disconnect failed: {str(e)}",
        )


@router.get("/read/{filepath:path}", response_model=ReadFileResponse)
async def read_file(filepath: str):
    """
    Read a DWG/DXF file and extract entities.
    
    Args:
        filepath: Path to DWG/DXF file
    
    Returns:
        ReadFileResponse with extracted data
    """
    try:
        service = get_autocad_service()
        
        if not os.path.exists(filepath):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {filepath}",
            )
        
        data = service.read_dwg(filepath)
        
        return ReadFileResponse(
            filepath=filepath,
            metadata=data.get("metadata", {}),
            layers=data.get("layers", []),
            entities=data.get("entities", []),
            blocks=data.get("blocks", {}),
            entity_count=len(data.get("entities", [])),
        )
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Read failed: {str(e)}",
        )


@router.post("/draw/line", response_model=OperationResponse)
async def draw_line(request: DrawLineRequest):
    """
    Draw a line in AutoCAD.
    
    Args:
        request: DrawLineRequest with start/end points and properties
    
    Returns:
        OperationResponse with entity handle
    """
    try:
        service = get_autocad_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to AutoCAD. Call /connect first.",
            )
        
        handle = service.draw_line(
            start=(request.start_x, request.start_y),
            end=(request.end_x, request.end_y),
            layer=request.layer,
            color=request.color,
        )
        
        return OperationResponse(
            success=True,
            message=f"Line drawn with handle: {handle}",
            handle=handle,
        )
    except Exception as e:
        logger.error(f"Failed to draw line: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Draw failed: {str(e)}",
        )


@router.post("/draw/circle", response_model=OperationResponse)
async def draw_circle(request: DrawCircleRequest):
    """
    Draw a circle in AutoCAD.
    
    Args:
        request: DrawCircleRequest with center, radius, and properties
    
    Returns:
        OperationResponse with entity handle
    """
    try:
        service = get_autocad_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to AutoCAD. Call /connect first.",
            )
        
        handle = service.draw_circle(
            center=(request.center_x, request.center_y),
            radius=request.radius,
            layer=request.layer,
            color=request.color,
        )
        
        return OperationResponse(
            success=True,
            message=f"Circle drawn with handle: {handle}",
            handle=handle,
        )
    except Exception as e:
        logger.error(f"Failed to draw circle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Draw failed: {str(e)}",
        )


@router.post("/draw/text", response_model=OperationResponse)
async def draw_text(request: DrawTextRequest):
    """
    Draw text in AutoCAD.
    
    Args:
        request: DrawTextRequest with text, position, and properties
    
    Returns:
        OperationResponse with entity handle
    """
    try:
        service = get_autocad_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to AutoCAD. Call /connect first.",
            )
        
        handle = service.draw_text(
            text=request.text,
            insert=(request.insert_x, request.insert_y),
            height=request.height,
            rotation=request.rotation,
            layer=request.layer,
            color=request.color,
        )
        
        return OperationResponse(
            success=True,
            message=f"Text drawn with handle: {handle}",
            handle=handle,
        )
    except Exception as e:
        logger.error(f"Failed to draw text: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Draw failed: {str(e)}",
        )


@router.post("/modify", response_model=OperationResponse)
async def modify_entity(request: ModifyEntityRequest):
    """
    Modify an AutoCAD entity.
    
    Args:
        request: ModifyEntityRequest with handle and properties
    
    Returns:
        OperationResponse with success status
    """
    try:
        service = get_autocad_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to AutoCAD. Call /connect first.",
            )
        
        assert service.drawing_engine is not None
        success = service.drawing_engine.modify_entity(
            handle=request.handle,
            **request.properties,
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to modify entity {request.handle}",
            )
        
        return OperationResponse(
            success=True,
            message=f"Entity {request.handle} modified successfully",
        )
    except Exception as e:
        logger.error(f"Failed to modify entity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Modify failed: {str(e)}",
        )


@router.delete("/entity/{handle}", response_model=OperationResponse)
async def delete_entity(handle: str):
    """
    Delete an AutoCAD entity.
    
    Args:
        handle: Entity handle
    
    Returns:
        OperationResponse with success status
    """
    try:
        service = get_autocad_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to AutoCAD. Call /connect first.",
            )
        
        assert service.drawing_engine is not None
        success = service.drawing_engine.delete_entity(handle)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete entity {handle}",
            )
        
        return OperationResponse(
            success=True,
            message=f"Entity {handle} deleted successfully",
        )
    except Exception as e:
        logger.error(f"Failed to delete entity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete failed: {str(e)}",
        )


@router.get("/config", response_model=AutoCADConfig)
async def get_config():
    """
    Get AutoCAD configuration.
    
    Returns:
        AutoCADConfig with current settings
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


@router.put("/config", response_model=OperationResponse)
async def update_config(config: AutoCADConfig):
    """
    Update AutoCAD configuration.
    
    Args:
        config: AutoCADConfig with new settings
    
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
