"""
backend/routers/revit.py — Revit Integration Endpoints
=====================================================

REST API endpoints for Revit integration operations.
Provides connection, file operations, and element operations.

ENDPOINTS:
- POST /api/revit/connect - Connect to Revit application
- POST /api/revit/read_rvt - Read elements from RVT file
- POST /api/revit/write_rvt - Write elements to RVT file
- POST /api/revit/create_wall - Create wall in Revit
- POST /api/revit/create_floor - Create floor in Revit
- GET /api/revit/status - Get connection status
- POST /api/revit/save - Save current document
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from backend.services.revit_service import RevitService

logger = logging.getLogger(__name__)
router = APIRouter()
service = RevitService()

# Pydantic models
class ConnectRequest(BaseModel):
    """Request model for Revit connection."""
    pass  # Revit connection doesn't typically require parameters

class ConnectResponse(BaseModel):
    """Response model for Revit connection."""
    success: bool
    message: str
    connected: bool

class ReadRvtRequest(BaseModel):
    """Request model for reading RVT file."""
    filepath: str

class WriteRvtRequest(BaseModel):
    """Request model for writing RVT file."""
    filepath: str
    elements: List[Dict[str, Any]]

class CreateWallRequest(BaseModel):
    """Request model for creating a wall."""
    start_point: List[float]
    end_point: List[float]
    height: float = 3000.0
    level: str = "Level 1"

class CreateFloorRequest(BaseModel):
    """Request model for creating a floor."""
    boundary: List[List[float]]
    level: str = "Level 1"

class CreateColumnRequest(BaseModel):
    """Request model for creating a column."""
    location: List[float]
    height: float = 3000.0
    level: str = "Level 1"

class StatusResponse(BaseModel):
    """Response model for connection status."""
    connected: bool
    message: str
    document_info: Optional[Dict[str, Any]] = None

class SaveRequest(BaseModel):
    """Request model for saving document."""
    filepath: str

class GetElementsRequest(BaseModel):
    """Request model for getting elements."""
    category_filter: Optional[str] = None

# Endpoints
@router.post("/connect", response_model=ConnectResponse, tags=["revit"])
async def connect_to_revit(request: ConnectRequest = None) -> ConnectResponse:
    """
    Connect to Revit application.
    
    Args:
        request: Connection parameters (currently unused)
        
    Returns:
        Connection status response
    """
    try:
        success = service.connect()
        if success:
            message = "Successfully connected to Revit environment"
        else:
            message = "Failed to connect to Revit environment"
            
        return ConnectResponse(
            success=success,
            message=message,
            connected=service.connected
        )
    except Exception as e:
        logger.error(f"Error connecting to Revit: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to connect to Revit: {str(e)}")

@router.post("/disconnect", response_model=ConnectResponse, tags=["revit"])
async def disconnect_from_revit() -> ConnectResponse:
    """
    Disconnect from Revit application.
    
    Returns:
        Disconnection status response
    """
    try:
        success = service.disconnect()
        if success:
            message = "Successfully disconnected from Revit"
        else:
            message = "Failed to disconnect from Revit"
            
        return ConnectResponse(
            success=success,
            message=message,
            connected=service.connected
        )
    except Exception as e:
        logger.error(f"Error disconnecting from Revit: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disconnect from Revit: {str(e)}")

@router.post("/read_rvt", tags=["revit"])
async def read_rvt_file(request: ReadRvtRequest) -> Dict[str, Any]:
    """
    Read elements from an RVT file.
    
    Args:
        request: File path to read
        
    Returns:
        Elements data from the RVT file
    """
    try:
        result = service.read_rvt(request.filepath)
        if not result.get("success", False):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error reading file"))
        return result
    except FileNotFoundError:
        logger.error(f"RVT file not found: {request.filepath}")
        raise HTTPException(status_code=404, detail=f"RVT file not found: {request.filepath}")
    except Exception as e:
        logger.error(f"Error reading RVT file: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading RVT file: {str(e)}")

@router.post("/write_rvt", tags=["revit"])
async def write_rvt_file(request: WriteRvtRequest) -> Dict[str, Any]:
    """
    Write elements to an RVT file.
    
    Args:
        request: File path and elements to write
        
    Returns:
        Success status
    """
    try:
        success = service.write_rvt(request.filepath, request.elements)
        if success:
            return {"success": True, "message": f"Successfully wrote to {request.filepath}"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to write to {request.filepath}")
    except Exception as e:
        logger.error(f"Error writing RVT file: {e}")
        raise HTTPException(status_code=500, detail=f"Error writing RVT file: {str(e)}")

@router.post("/create_wall", tags=["revit"])
async def create_wall(request: CreateWallRequest) -> Dict[str, Any]:
    """
    Create a wall in Revit.
    
    Args:
        request: Wall creation parameters
        
    Returns:
        Result of the operation
    """
    try:
        if not service.connected:
            raise HTTPException(status_code=503, detail="Revit not connected")
            
        wall_id = service.create_wall(
            start_point=request.start_point,
            end_point=request.end_point,
            height=request.height,
            level=request.level
        )
        
        if wall_id:
            return {
                "success": True, 
                "message": "Wall created successfully",
                "element_id": wall_id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create wall")
    except Exception as e:
        logger.error(f"Error creating wall: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating wall: {str(e)}")

@router.post("/create_floor", tags=["revit"])
async def create_floor(request: CreateFloorRequest) -> Dict[str, Any]:
    """
    Create a floor in Revit.
    
    Args:
        request: Floor creation parameters
        
    Returns:
        Result of the operation
    """
    try:
        if not service.connected:
            raise HTTPException(status_code=503, detail="Revit not connected")
            
        floor_id = service.create_floor(
            boundary=request.boundary,
            level=request.level
        )
        
        if floor_id:
            return {
                "success": True,
                "message": "Floor created successfully",
                "element_id": floor_id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create floor")
    except Exception as e:
        logger.error(f"Error creating floor: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating floor: {str(e)}")

@router.post("/create_column", tags=["revit"])
async def create_column(request: CreateColumnRequest) -> Dict[str, Any]:
    """
    Create a column in Revit.
    
    Args:
        request: Column creation parameters
        
    Returns:
        Result of the operation
    """
    try:
        if not service.connected:
            raise HTTPException(status_code=503, detail="Revit not connected")
            
        column_id = service.create_column(
            location=request.location,
            height=request.height,
            level=request.level
        )
        
        if column_id:
            return {
                "success": True,
                "message": "Column created successfully",
                "element_id": column_id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create column")
    except Exception as e:
        logger.error(f"Error creating column: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating column: {str(e)}")

@router.get("/status", response_model=StatusResponse, tags=["revit"])
async def get_revit_status() -> StatusResponse:
    """
    Get the current Revit connection status.
    
    Returns:
        Connection status and document info
    """
    try:
        doc_info = {}
        if service.connected:
            doc_info = service.get_document_info()
        
        return StatusResponse(
            connected=service.connected,
            message="Revit service status" if service.connected else "Revit not connected",
            document_info=doc_info if doc_info else None
        )
    except Exception as e:
        logger.error(f"Error getting Revit status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting Revit status: {str(e)}")

@router.post("/save", tags=["revit"])
async def save_document(request: SaveRequest) -> Dict[str, Any]:
    """
    Save the current Revit document.
    
    Args:
        request: File path to save to
        
    Returns:
        Success status
    """
    try:
        if not service.connected:
            raise HTTPException(status_code=503, detail="Revit not connected")
            
        success = service.save(request.filepath)
        if success:
            return {"success": True, "message": f"Document saved to {request.filepath}"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to save document to {request.filepath}")
    except Exception as e:
        logger.error(f"Error saving document: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving document: {str(e)}")

@router.post("/get_elements", tags=["revit"])
async def get_elements(request: GetElementsRequest) -> Dict[str, Any]:
    """
    Get all elements in the document, optionally filtered by category.
    
    Args:
        request: Category filter parameters
        
    Returns:
        List of elements
    """
    try:
        if not service.connected:
            raise HTTPException(status_code=503, detail="Revit not connected")
            
        elements = service.get_all_elements(request.category_filter)
        return {
            "success": True,
            "elements": elements,
            "count": len(elements)
        }
    except Exception as e:
        logger.error(f"Error getting elements: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting elements: {str(e)}")

@router.post("/upload_rvt", tags=["revit"])
async def upload_and_read_rvt(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload an RVT file and read its contents.
    
    Args:
        file: RVT file to upload and read
        
    Returns:
        Elements data from the uploaded file
    """
    try:
        # Save uploaded file temporarily
        temp_path = f"temp_{file.filename}"
        with open(temp_path, "wb") as buffer:
            buffer.write(await file.read())
        
        # Read the file
        result = service.read_rvt(temp_path)
        
        # Clean up temporary file
        import os
        os.remove(temp_path)
        
        if not result.get("success", False):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error reading file"))
        return result
    except FileNotFoundError:
        logger.error(f"Uploaded RVT file not found: {file.filename}")
        raise HTTPException(status_code=404, detail=f"Uploaded RVT file not found: {file.filename}")
    except Exception as e:
        logger.error(f"Error processing uploaded RVT file: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing uploaded RVT file: {str(e)}")