"""
backend/routers/revit.py — Revit API Endpoints
===============================================

REST API for Revit operations:
- Connection management
- RVT file reading
- Element creation (walls, floors, doors, windows)
- Element modification
- Configuration management

ENDPOINTS:
- GET /api/v1/revit/status — Check Revit connection status
- POST /api/v1/revit/connect — Connect to Revit
- POST /api/v1/revit/disconnect — Disconnect from Revit
- GET /api/v1/revit/read — Read current Revit document
- POST /api/v1/revit/create/wall — Create a wall
- POST /api/v1/revit/create/floor — Create a floor
- POST /api/v1/revit/create/door — Place a door
- POST /api/v1/revit/create/window — Place a window
- POST /api/v1/revit/modify — Modify element
- DELETE /api/v1/revit/element/{element_id} — Delete element
- GET /api/v1/revit/config — Get configuration
- PUT /api/v1/revit/config — Update configuration
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.services.revit_service import (
    RevitConfig,
    RevitConfigManager,
    RevitService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/revit", tags=["Revit"])


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class ConnectionStatus(BaseModel):
    """Revit connection status."""
    connected: bool
    version: Optional[str] = None
    document: Optional[str] = None
    message: str = ""


class ConnectRequest(BaseModel):
    """Request to connect to Revit."""
    pass


class CreateWallRequest(BaseModel):
    """Request to create a wall."""
    start_x: float
    start_y: float
    start_z: float = 0.0
    end_x: float
    end_y: float
    end_z: float = 0.0
    height: float
    level: str = Field(default="Level 1")
    wall_type: str = Field(default="Generic - 200mm")


class CreateFloorRequest(BaseModel):
    """Request to create a floor."""
    boundary_points: List[Tuple[float, float, float]]
    level: str = Field(default="Level 1")
    floor_type: str = Field(default="Generic 150mm")


class PlaceDoorRequest(BaseModel):
    """Request to place a door."""
    wall_id: int
    location_x: float
    location_y: float
    location_z: float
    door_type: str = Field(default="Single-Flush")


class PlaceWindowRequest(BaseModel):
    """Request to place a window."""
    wall_id: int
    location_x: float
    location_y: float
    location_z: float
    window_type: str = Field(default="Fixed")


class ModifyElementRequest(BaseModel):
    """Request to modify an element."""
    element_id: int
    parameters: Dict[str, Any]


class ReadDocumentResponse(BaseModel):
    """Response from reading a Revit document."""
    filename: str
    elements: List[Dict[str, Any]]
    levels: List[Dict[str, Any]]
    views: List[Dict[str, Any]]
    element_count: int


class OperationResponse(BaseModel):
    """Generic operation response."""
    success: bool
    message: str
    element_id: Optional[int] = None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_revit_service: Optional[RevitService] = None
_config_manager = RevitConfigManager()


def get_revit_service() -> RevitService:
    """Get or initialize Revit service singleton."""
    global _revit_service
    if _revit_service is None:
        config = _config_manager.load()
        _revit_service = RevitService(config)
    return _revit_service


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/status", response_model=ConnectionStatus)
async def get_status():
    """
    Check Revit connection status.
    
    Returns:
        ConnectionStatus with connected flag, version, and document info
    """
    try:
        service = get_revit_service()
        
        if service.connection.is_connected:
            return ConnectionStatus(
                connected=True,
                version=service.connection.doc.Application.VersionNumber if service.connection.is_connected else None,
                document=service.connection.doc.Title if service.connection.is_connected else None,
                message="Connected to Revit",
            )
        else:
            return ConnectionStatus(
                connected=False,
                message="Not connected to Revit",
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
    Connect to Revit.
    
    Returns:
        ConnectionStatus with connection details
    """
    try:
        service = get_revit_service()
        
        if not service.initialize():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to connect to Revit. Is Revit installed and running?",
            )
        
        return ConnectionStatus(
            connected=True,
            version=service.connection.doc.Application.VersionNumber,
            document=service.connection.doc.Title,
            message="Successfully connected to Revit",
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
    Disconnect from Revit.
    
    Returns:
        OperationResponse with success status
    """
    try:
        service = get_revit_service()
        service.shutdown()
        
        return OperationResponse(
            success=True,
            message="Successfully disconnected from Revit",
        )
    except Exception as e:
        logger.error(f"Failed to disconnect: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Disconnect failed: {str(e)}",
        )


@router.get("/read", response_model=ReadDocumentResponse)
async def read_document():
    """
    Read current Revit document.
    
    Returns:
        ReadDocumentResponse with elements, levels, and views
    """
    try:
        service = get_revit_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to Revit. Call /connect first.",
            )
        
        data = service.read_current_document()
        
        return ReadDocumentResponse(
            filename=data.get("filename", "Unknown"),
            elements=data.get("elements", []),
            levels=data.get("levels", []),
            views=data.get("views", []),
            element_count=len(data.get("elements", [])),
        )
    except Exception as e:
        logger.error(f"Failed to read document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Read failed: {str(e)}",
        )


@router.post("/create/wall", response_model=OperationResponse)
async def create_wall(request: CreateWallRequest):
    """
    Create a wall in Revit.
    
    Args:
        request: CreateWallRequest with start/end points, height, and type
    
    Returns:
        OperationResponse with element ID
    """
    try:
        service = get_revit_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to Revit. Call /connect first.",
            )
        
        element_id = service.create_wall(
            start=(request.start_x, request.start_y, request.start_z),
            end=(request.end_x, request.end_y, request.end_z),
            height=request.height,
            level=request.level,
            wall_type=request.wall_type,
        )
        
        return OperationResponse(
            success=True,
            message=f"Wall created with ID: {element_id}",
            element_id=element_id,
        )
    except Exception as e:
        logger.error(f"Failed to create wall: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Create failed: {str(e)}",
        )


@router.post("/create/floor", response_model=OperationResponse)
async def create_floor(request: CreateFloorRequest):
    """
    Create a floor in Revit.
    
    Args:
        request: CreateFloorRequest with boundary points, level, and type
    
    Returns:
        OperationResponse with element ID
    """
    try:
        service = get_revit_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to Revit. Call /connect first.",
            )
        
        element_id = service.create_floor(
            boundary=request.boundary_points,
            level=request.level,
            floor_type=request.floor_type,
        )
        
        return OperationResponse(
            success=True,
            message=f"Floor created with ID: {element_id}",
            element_id=element_id,
        )
    except Exception as e:
        logger.error(f"Failed to create floor: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Create failed: {str(e)}",
        )


@router.post("/create/door", response_model=OperationResponse)
async def create_door(request: PlaceDoorRequest):
    """
    Place a door in Revit.
    
    Args:
        request: PlaceDoorRequest with wall ID, location, and door type
    
    Returns:
        OperationResponse with element ID
    """
    try:
        service = get_revit_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to Revit. Call /connect first.",
            )
        
        element_id = service.place_door(
            wall_id=request.wall_id,
            location=(request.location_x, request.location_y, request.location_z),
            door_type=request.door_type,
        )
        
        return OperationResponse(
            success=True,
            message=f"Door placed with ID: {element_id}",
            element_id=element_id,
        )
    except Exception as e:
        logger.error(f"Failed to place door: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Place failed: {str(e)}",
        )


@router.post("/create/window", response_model=OperationResponse)
async def create_window(request: PlaceWindowRequest):
    """
    Place a window in Revit.
    
    Args:
        request: PlaceWindowRequest with wall ID, location, and window type
    
    Returns:
        OperationResponse with element ID
    """
    try:
        service = get_revit_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to Revit. Call /connect first.",
            )
        
        assert service.modeling_engine is not None
        element_id = service.modeling_engine.place_window(
            wall_id=request.wall_id,
            location=(request.location_x, request.location_y, request.location_z),
            window_type=request.window_type,
        )
        
        return OperationResponse(
            success=True,
            message=f"Window placed with ID: {element_id}",
            element_id=element_id,
        )
    except Exception as e:
        logger.error(f"Failed to place window: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Place failed: {str(e)}",
        )


@router.post("/modify", response_model=OperationResponse)
async def modify_element(request: ModifyElementRequest):
    """
    Modify a Revit element.
    
    Args:
        request: ModifyElementRequest with element ID and parameters
    
    Returns:
        OperationResponse with success status
    """
    try:
        service = get_revit_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to Revit. Call /connect first.",
            )
        
        assert service.modeling_engine is not None
        success = service.modeling_engine.modify_element(
            element_id=request.element_id,
            **request.parameters,
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to modify element {request.element_id}",
            )
        
        return OperationResponse(
            success=True,
            message=f"Element {request.element_id} modified successfully",
        )
    except Exception as e:
        logger.error(f"Failed to modify element: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Modify failed: {str(e)}",
        )


@router.delete("/element/{element_id}", response_model=OperationResponse)
async def delete_element(element_id: int):
    """
    Delete a Revit element.
    
    Args:
        element_id: Element ID
    
    Returns:
        OperationResponse with success status
    """
    try:
        service = get_revit_service()
        
        if not service.connection.is_connected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not connected to Revit. Call /connect first.",
            )
        
        assert service.modeling_engine is not None
        success = service.modeling_engine.delete_element(element_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to delete element {element_id}",
            )
        
        return OperationResponse(
            success=True,
            message=f"Element {element_id} deleted successfully",
        )
    except Exception as e:
        logger.error(f"Failed to delete element: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete failed: {str(e)}",
        )


@router.get("/config", response_model=RevitConfig)
async def get_config():
    """
    Get Revit configuration.
    
    Returns:
        RevitConfig with current settings
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
async def update_config(config: RevitConfig):
    """
    Update Revit configuration.
    
    Args:
        config: RevitConfig with new settings
    
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
