"""
backend/routers/autocad.py — AutoCAD Integration Endpoints
==========================================================

REST API endpoints for AutoCAD integration operations.
Provides connection, file operations, and drawing operations.

ENDPOINTS:
- POST /api/autocad/connect - Connect to AutoCAD application
- POST /api/autocad/read_dwg - Read entities from DWG file
- POST /api/autocad/write_dwg - Write entities to DWG file
- POST /api/autocad/draw_line - Draw line in AutoCAD
- POST /api/autocad/draw_polyline - Draw polyline in AutoCAD
- POST /api/autocad/draw_circle - Draw circle in AutoCAD
- POST /api/autocad/draw_text - Draw text in AutoCAD
- GET /api/autocad/status - Get connection status
- POST /api/autocad/save - Save current document
- POST /api/autocad/upload_dwg - Upload and read DWG file
- DELETE /api/autocad/entity/{handle} - Delete entity by handle
- PUT /api/autocad/entity/{handle} - Update entity properties
"""

import logging
import os
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pydantic import BaseModel

from backend.services.autocad_service import AutoCADService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/autocad", tags=["AutoCAD"])

# Global service instance
_autocad_service: Optional[AutoCADService] = None

def get_autocad_service() -> AutoCADService:
    """Get or initialize AutoCAD service singleton."""
    global _autocad_service
    if _autocad_service is None:
        _autocad_service = AutoCADService()
    return _autocad_service

# Pydantic models
class ConnectRequest(BaseModel):
    """Request model for AutoCAD connection."""
    visible: bool = True
    force_new: bool = False

class ConnectResponse(BaseModel):
    """Response model for AutoCAD connection."""
    success: bool
    message: str
    connected: bool

class ReadDwgRequest(BaseModel):
    """Request model for reading DWG file."""
    filepath: str

class WriteDwgRequest(BaseModel):
    """Request model for writing DWG file."""
    filepath: str
    entities: List[Dict[str, Any]]

class DrawLineRequest(BaseModel):
    """Request model for drawing a line."""
    start_point: List[float]
    end_point: List[float]
    layer: str = "0"
    color: int = 0

class DrawPolylineRequest(BaseModel):
    """Request model for drawing a polyline."""
    vertices: List[List[float]]
    layer: str = "0"
    color: int = 0
    closed: bool = False

class DrawCircleRequest(BaseModel):
    """Request model for drawing a circle."""
    center: List[float]
    radius: float
    layer: str = "0"
    color: int = 0

class DrawTextRequest(BaseModel):
    """Request model for drawing text."""
    text: str
    insertion_point: List[float]
    height: float = 0.2
    layer: str = "0"
    color: int = 0

class StatusResponse(BaseModel):
    """Response model for connection status."""
    connected: bool
    message: str
    document_info: Optional[Dict[str, Any]] = None

class SaveRequest(BaseModel):
    """Request model for saving document."""
    filepath: str

class ModifyEntityRequest(BaseModel):
    """Request model for modifying an entity."""
    handle: str
    properties: Dict[str, Any]

class DeleteEntityResponse(BaseModel):
    """Response model for entity deletion."""
    success: bool
    message: str

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

# Endpoints
@router.post("/connect", response_model=ConnectResponse)
async def connect_to_autocad(request: ConnectRequest) -> ConnectResponse:
    """
    Connect to AutoCAD application.
    
    Args:
        request: Connection parameters
        
    Returns:
        Connection status response
    """
    try:
        service = get_autocad_service()
        
        if not service.connect(visible=request.visible, force_new=request.force_new):
            raise HTTPException(
                status_code=503,
                detail="Failed to connect to AutoCAD. Is AutoCAD installed and running?",
            )
            
        return ConnectResponse(
            success=True,
            message="Successfully connected to AutoCAD",
            connected=service.connected
        )
    except Exception as e:
        logger.error(f"Error connecting to AutoCAD: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to connect to AutoCAD: {str(e)}")

@router.post("/disconnect", response_model=ConnectResponse)
async def disconnect_from_autocad() -> ConnectResponse:
    """
    Disconnect from AutoCAD application.
    
    Returns:
        Disconnection status response
    """
    try:
        service = get_autocad_service()
        success = service.disconnect()
            
        return ConnectResponse(
            success=success,
            message="Successfully disconnected from AutoCAD" if success else "Failed to disconnect from AutoCAD",
            connected=service.connected
        )
    except Exception as e:
        logger.error(f"Error disconnecting from AutoCAD: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disconnect from AutoCAD: {str(e)}")

@router.post("/read_dwg", response_model=ReadFileResponse)
async def read_dwg_file(request: ReadDwgRequest) -> ReadFileResponse:
    """
    Read entities from a DWG file.
    
    Args:
        request: File path to read
        
    Returns:
        Entities data from the DWG file
    """
    try:
        service = get_autocad_service()
        
        if not os.path.exists(request.filepath):
            raise HTTPException(
                status_code=404,
                detail=f"DWG file not found: {request.filepath}"
            )
            
        result = service.read_dwg(request.filepath)
        
        if not result.get("success", False):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Unknown error reading file")
            )
            
        return ReadFileResponse(
            filepath=request.filepath,
            metadata=result.get("metadata", {}),
            layers=result.get("layers", []),
            entities=result.get("entities", []),
            blocks=result.get("blocks", {}),
            entity_count=len(result.get("entities", [])),
        )
    except FileNotFoundError:
        logger.error(f"DWG file not found: {request.filepath}")
        raise HTTPException(status_code=404, detail=f"DWG file not found: {request.filepath}")
    except Exception as e:
        logger.error(f"Error reading DWG file: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading DWG file: {str(e)}")

@router.post("/write_dwg", response_model=OperationResponse)
async def write_dwg_file(request: WriteDwgRequest) -> OperationResponse:
    """
    Write entities to a DWG file.
    
    Args:
        request: File path and entities to write
        
    Returns:
        Success status
    """
    try:
        service = get_autocad_service()
        
        if not service.connected:
            raise HTTPException(
                status_code=503,
                detail="AutoCAD not connected. Call /connect first."
            )
            
        success = service.write_dwg(request.filepath, request.entities)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to write to {request.filepath}"
            )
            
        return OperationResponse(
            success=True,
            message=f"Successfully wrote to {request.filepath}"
        )
    except Exception as e:
        logger.error(f"Error writing DWG file: {e}")
        raise HTTPException(status_code=500, detail=f"Error writing DWG file: {str(e)}")

@router.post("/draw_line", response_model=OperationResponse)
async def draw_line(request: DrawLineRequest) -> OperationResponse:
    """
    Draw a line in AutoCAD.
    
    Args:
        request: Line drawing parameters
        
    Returns:
        Result of the operation
    """
    try:
        service = get_autocad_service()
        
        if not service.connected:
            raise HTTPException(
                status_code=503,
                detail="AutoCAD not connected. Call /connect first."
            )
            
        line_handle = service.draw_line(
            start_point=request.start_point,
            end_point=request.end_point,
            layer=request.layer,
            color=request.color
        )
        
        if not line_handle:
            raise HTTPException(
                status_code=500,
                detail="Failed to draw line"
            )
            
        return OperationResponse(
            success=True, 
            message="Line drawn successfully",
            handle=line_handle
        )
    except Exception as e:
        logger.error(f"Error drawing line: {e}")
        raise HTTPException(status_code=500, detail=f"Error drawing line: {str(e)}")

@router.post("/draw_polyline", response_model=OperationResponse)
async def draw_polyline(request: DrawPolylineRequest) -> OperationResponse:
    """
    Draw a polyline in AutoCAD.
    
    Args:
        request: Polyline drawing parameters
        
    Returns:
        Result of the operation
    """
    try:
        service = get_autocad_service()
        
        if not service.connected:
            raise HTTPException(
                status_code=503,
                detail="AutoCAD not connected. Call /connect first."
            )
            
        polyline_handle = service.draw_polyline(
            vertices=request.vertices,
            layer=request.layer,
            color=request.color,
            closed=request.closed
        )
        
        if not polyline_handle:
            raise HTTPException(
                status_code=500,
                detail="Failed to draw polyline"
            )
            
        return OperationResponse(
            success=True,
            message="Polyline drawn successfully",
            handle=polyline_handle
        )
    except Exception as e:
        logger.error(f"Error drawing polyline: {e}")
        raise HTTPException(status_code=500, detail=f"Error drawing polyline: {str(e)}")

@router.post("/draw_circle", response_model=OperationResponse)
async def draw_circle(request: DrawCircleRequest) -> OperationResponse:
    """
    Draw a circle in AutoCAD.
    
    Args:
        request: Circle drawing parameters
        
    Returns:
        Result of the operation
    """
    try:
        service = get_autocad_service()
        
        if not service.connected:
            raise HTTPException(
                status_code=503,
                detail="AutoCAD not connected. Call /connect first."
            )
            
        circle_handle = service.draw_circle(
            center=request.center,
            radius=request.radius,
            layer=request.layer,
            color=request.color
        )
        
        if not circle_handle:
            raise HTTPException(
                status_code=500,
                detail="Failed to draw circle"
            )
            
        return OperationResponse(
            success=True,
            message="Circle drawn successfully",
            handle=circle_handle
        )
    except Exception as e:
        logger.error(f"Error drawing circle: {e}")
        raise HTTPException(status_code=500, detail=f"Error drawing circle: {str(e)}")

@router.post("/draw_text", response_model=OperationResponse)
async def draw_text(request: DrawTextRequest) -> OperationResponse:
    """
    Draw text in AutoCAD.
    
    Args:
        request: Text drawing parameters
        
    Returns:
        Result of the operation
    """
    try:
        service = get_autocad_service()
        
        if not service.connected:
            raise HTTPException(
                status_code=503,
                detail="AutoCAD not connected. Call /connect first."
            )
            
        text_handle = service.draw_text(
            text=request.text,
            insertion_point=request.insertion_point,
            height=request.height,
            layer=request.layer,
            color=request.color
        )
        
        if not text_handle:
            raise HTTPException(
                status_code=500,
                detail="Failed to draw text"
            )
            
        return OperationResponse(
            success=True,
            message="Text drawn successfully",
            handle=text_handle
        )
    except Exception as e:
        logger.error(f"Error drawing text: {e}")
        raise HTTPException(status_code=500, detail=f"Error drawing text: {str(e)}")

@router.get("/status", response_model=StatusResponse)
async def get_autocad_status() -> StatusResponse:
    """
    Get the current AutoCAD connection status.
    
    Returns:
        Connection status and document info
    """
    try:
        service = get_autocad_service()
        doc_info = {}
        
        if service.connected:
            doc_info = service.get_document_info()
        
        return StatusResponse(
            connected=service.connected,
            message="AutoCAD service status" if service.connected else "AutoCAD not connected",
            document_info=doc_info if doc_info else None
        )
    except Exception as e:
        logger.error(f"Error getting AutoCAD status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting AutoCAD status: {str(e)}")

@router.post("/save", response_model=OperationResponse)
async def save_document(request: SaveRequest) -> OperationResponse:
    """
    Save the current AutoCAD document.
    
    Args:
        request: File path to save to
        
    Returns:
        Success status
    """
    try:
        service = get_autocad_service()
        
        if not service.connected:
            raise HTTPException(
                status_code=503,
                detail="AutoCAD not connected. Call /connect first."
            )
            
        success = service.save(request.filepath)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save document to {request.filepath}"
            )
            
        return OperationResponse(
            success=True,
            message=f"Document saved to {request.filepath}"
        )
    except Exception as e:
        logger.error(f"Error saving document: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving document: {str(e)}")

@router.post("/upload_dwg", response_model=ReadFileResponse)
async def upload_and_read_dwg(file: UploadFile = File(...)) -> ReadFileResponse:
    """
    Upload a DWG file and read its contents.
    
    Args:
        file: DWG file to upload and read
        
    Returns:
        Entities data from the uploaded file
    """
    try:
        service = get_autocad_service()
        
        # Save uploaded file temporarily
        temp_path = f"temp_{file.filename}"
        with open(temp_path, "wb") as buffer:
            buffer.write(await file.read())
        
        # Read the file
        result = service.read_dwg(temp_path)
        
        # Clean up temporary file
        os.remove(temp_path)
        
        if not result.get("success", False):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Unknown error reading file")
            )
            
        return ReadFileResponse(
            filepath=temp_path,
            metadata=result.get("metadata", {}),
            layers=result.get("layers", []),
            entities=result.get("entities", []),
            blocks=result.get("blocks", {}),
            entity_count=len(result.get("entities", [])),
        )
    except FileNotFoundError:
        logger.error(f"Uploaded DWG file not found: {file.filename}")
        raise HTTPException(status_code=404, detail=f"Uploaded DWG file not found: {file.filename}")
    except Exception as e:
        logger.error(f"Error processing uploaded DWG file: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing uploaded DWG file: {str(e)}")

@router.delete("/entity/{handle}", response_model=DeleteEntityResponse)
async def delete_entity(handle: str) -> DeleteEntityResponse:
    """
    Delete an AutoCAD entity by handle.
    
    Args:
        handle: Entity handle
        
    Returns:
        Deletion status
    """
    try:
        service = get_autocad_service()
        
        if not service.connected:
            raise HTTPException(
                status_code=503,
                detail="AutoCAD not connected. Call /connect first."
            )
            
        success = service.delete_entity(handle)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to delete entity {handle}"
            )
            
        return DeleteEntityResponse(
            success=True,
            message=f"Entity {handle} deleted successfully"
        )
    except Exception as e:
        logger.error(f"Error deleting entity: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting entity: {str(e)}")

@router.put("/entity/{handle}", response_model=OperationResponse)
async def update_entity(handle: str, request: ModifyEntityRequest) -> OperationResponse:
    """
    Update an AutoCAD entity's properties.
    
    Args:
        handle: Entity handle
        request: Entity properties to update
        
    Returns:
        Update status
    """
    try:
        service = get_autocad_service()
        
        if not service.connected:
            raise HTTPException(
                status_code=503,
                detail="AutoCAD not connected. Call /connect first."
            )
            
        if handle != request.handle:
            raise HTTPException(
                status_code=400,
                detail="Handle in URL and request body must match"
            )
            
        success = service.modify_entity(
            handle=request.handle,
            properties=request.properties
        )
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to modify entity {handle}"
            )
            
        return OperationResponse(
            success=True,
            message=f"Entity {handle} modified successfully"
        )
    except Exception as e:
        logger.error(f"Error modifying entity: {e}")
        raise HTTPException(status_code=500, detail=f"Error modifying entity: {str(e)}")


def _ensure_file_end():
    """Dummy function to ensure file has proper ending."""
    pass


def _ensure_file_end():
    """Dummy function to ensure file has proper ending."""
    pass
