"""
backend/routers/revit_integration.py — Revit Integration API Router
=================================================================

REST API endpoints for comprehensive Revit integration with AI support.

ENDPOINTS:
- POST /api/revit-integration/connect - Connect to Revit
- POST /api/revit-integration/disconnect - Disconnect from Revit
- GET /api/revit-integration/status - Get connection status
- POST /api/revit-integration/document/open - Open RVT document
- POST /api/revit-integration/document/save - Save document
- POST /api/revit-integration/document/close - Close document
- GET /api/revit-integration/elements - Get elements
- GET /api/revit-integration/elements/{id} - Get element by ID
- GET /api/revit-integration/elements/selected - Get selected elements
- POST /api/revit-integration/elements/create/wall - Create wall
- POST /api/revit-integration/elements/create/floor - Create floor
- POST /api/revit-integration/elements/create/door - Create door
- POST /api/revit-integration/elements/create/window - Create window
- POST /api/revit-integration/elements/create/column - Create column
- POST /api/revit-integration/elements/create/beam - Create beam
- POST /api/revit-integration/elements/create/family - Create family instance
- PUT /api/revit-integration/elements/{id}/parameters - Update element parameters
- DELETE /api/revit-integration/elements/{id} - Delete element
- GET /api/revit-integration/views - Get all views
- POST /api/revit-integration/views - Create a view
- GET /api/revit-integration/levels - Get all levels
- POST /api/revit-integration/levels - Create a level
- GET /api/revit-integration/grids - Get all grids
- GET /api/revit-integration/worksets - Get all worksets
- GET /api/revit-integration/families/{category}/symbols - Get family symbols
- POST /api/revit-integration/families/load - Load a family
- POST /api/revit-integration/search/api - Search API data locally
- GET /api/revit-integration/search/online - Search RevitAPIDocs.com
- POST /api/revit-integration/execute - Execute AI command
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services.revit_integration import (
    RevitIntegration,
    get_revit_integration,
    RevitAPIInfo,
    SearchResult,
    ConnectionMethod,
    ElementCategory
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Get singleton instance
revit = get_revit_integration()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class ConnectRequest(BaseModel):
    """Request to connect to Revit."""
    method: str = Field(default="auto", description="Connection method: api, macro, simulation, auto")


class ConnectResponse(BaseModel):
    """Response from connection attempt."""
    success: bool
    message: str
    connection_method: Optional[str] = None
    is_connected: bool


class Point3D(BaseModel):
    """3D Point coordinates."""
    x: float
    y: float
    z: float


class WallCreateRequest(BaseModel):
    """Request to create a wall."""
    start_point: List[float]
    end_point: List[float]
    height: float = 3000.0
    level: str = "Level 1"
    wall_type: str = "Basic Wall"


class FloorCreateRequest(BaseModel):
    """Request to create a floor."""
    boundary_points: List[List[float]]
    level: str = "Level 1"
    floor_type: str = "Floor"


class DoorCreateRequest(BaseModel):
    """Request to create a door."""
    host_wall_id: str
    location_point: List[float]
    family_type: str = "M_Single-Flush"
    level: str = "Level 1"


class WindowCreateRequest(BaseModel):
    """Request to create a window."""
    host_wall_id: str
    location_point: List[float]
    family_type: str = "M_Single-Flush"
    level: str = "Level 1"


class ColumnCreateRequest(BaseModel):
    """Request to create a column."""
    location_point: List[float]
    height: float = 3000.0
    level: str = "Level 1"
    column_type: str = "M_Columns"


class BeamCreateRequest(BaseModel):
    """Request to create a beam."""
    start_point: List[float]
    end_point: List[float]
    level: str = "Level 1"
    beam_type: str = "W-Wide Flange"


class FamilyInstanceCreateRequest(BaseModel):
    """Request to create a generic family instance."""
    family_name: str
    category: str
    location_point: List[float]
    level: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class DocumentOpenRequest(BaseModel):
    """Request to open a document."""
    filepath: str


class DocumentSaveRequest(BaseModel):
    """Request to save a document."""
    filepath: Optional[str] = None


class DocumentCloseRequest(BaseModel):
    """Request to close a document."""
    save_changes: bool = True


class ParameterUpdateRequest(BaseModel):
    """Request to update element parameters."""
    parameters: Dict[str, Any]


class APISearchRequest(BaseModel):
    """Request to search API data."""
    keyword: Optional[str] = None
    api_name: Optional[str] = None
    namespace: Optional[str] = None
    api_type: Optional[str] = None


class OnlineSearchRequest(BaseModel):
    """Request to search online."""
    query: str
    engine: str = "revitapidocs"


class AICommandRequest(BaseModel):
    """Request to execute AI command."""
    command: str
    context: Optional[Dict[str, Any]] = None


class ElementResponse(BaseModel):
    """Response containing element data."""
    success: bool
    message: str
    element_id: Optional[str] = None
    element: Optional[Dict[str, Any]] = None


class ElementsResponse(BaseModel):
    """Response containing multiple elements."""
    success: bool
    elements: List[Dict[str, Any]]
    count: int


class APIResultResponse(BaseModel):
    """Response from API search."""
    success: bool
    results: List[Dict[str, Any]]
    count: int


class ViewCreateRequest(BaseModel):
    """Request to create a view."""
    view_name: str
    view_type: str = "Floor Plan"
    level: str = "Level 1"


class LevelCreateRequest(BaseModel):
    """Request to create a level."""
    name: str
    elevation: float


class FamilyLoadRequest(BaseModel):
    """Request to load a family."""
    family_path: str
    category: Optional[str] = None


# ============================================================================
# CONNECTION ENDPOINTS
# ============================================================================

@router.post("/connect", response_model=ConnectResponse, tags=["revit-integration"])
async def connect_to_revit(request: ConnectRequest = None) -> ConnectResponse:
    """
    Connect to Revit using specified method.
    
    Methods:
    - api: Direct Revit API (requires Revit installed, best performance)
    - macro: Revit Macro API (runs inside Revit)
    - simulation: Development mode (no Revit needed)
    - auto: Automatically choose best method
    """
    try:
        method = request.method if request else "auto"
        success = revit.connect(method=method)
        
        return ConnectResponse(
            success=success,
            message=f"Connected via {revit.connection_method}" if success else "Connection failed",
            connection_method=revit.connection_method,
            is_connected=revit.is_connected
        )
    except Exception as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disconnect", response_model=ConnectResponse, tags=["revit-integration"])
async def disconnect_from_revit() -> ConnectResponse:
    """Disconnect from Revit."""
    try:
        success = revit.disconnect()
        
        return ConnectResponse(
            success=success,
            message="Disconnected from Revit" if success else "Disconnect failed",
            is_connected=revit.is_connected
        )
    except Exception as e:
        logger.error(f"Disconnect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", tags=["revit-integration"])
async def get_status():
    """Get current connection status and capabilities."""
    return {
        "is_connected": revit.is_connected,
        "connection_method": revit.connection_method,
        "platform": "Windows" if revit._is_windows else "Other",
        "has_revit_api": revit._has_revit_api,
        "has_pythonnet": revit._has_pythonnet,
        "api_data_loaded": revit._api_data_loaded,
        "api_data_count": len(revit._api_data_cache)
    }


# ============================================================================
# DOCUMENT ENDPOINTS
# ============================================================================

@router.post("/document/open", tags=["revit-integration"])
async def open_document(request: DocumentOpenRequest) -> Dict[str, Any]:
    """Open an RVT file."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    success = revit.open_document(request.filepath)
    if success:
        return {"success": True, "message": f"Opened: {request.filepath}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to open document")


@router.post("/document/save", tags=["revit-integration"])
async def save_document(request: DocumentSaveRequest = None) -> Dict[str, Any]:
    """Save the current document."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    filepath = request.filepath if request else None
    success = revit.save_document(filepath)
    
    if success:
        return {"success": True, "message": "Document saved"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save document")


@router.post("/document/close", tags=["revit-integration"])
async def close_document(request: DocumentCloseRequest) -> Dict[str, Any]:
    """Close the current document."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    success = revit.close_document(request.save_changes)
    
    if success:
        return {"success": True, "message": "Document closed"}
    else:
        raise HTTPException(status_code=500, detail="Failed to close document")


# ============================================================================
# ELEMENT READ ENDPOINTS
# ============================================================================

@router.get("/elements", response_model=ElementsResponse, tags=["revit-integration"])
async def get_elements(
    category: Optional[str] = Query(None, description="Filter by category"),
    element_class: Optional[str] = Query(None, description="Filter by class"),
    level_id: Optional[str] = Query(None, description="Filter by level"),
    workset_id: Optional[str] = Query(None, description="Filter by workset")
) -> ElementsResponse:
    """
    Get elements using FilteredElementCollector pattern.
    
    This is the main method for reading elements from Revit.
    """
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        elements = revit.get_elements(
            category=category,
            element_class=element_class,
            level_id=level_id,
            workset_id=workset_id
        )
        
        return ElementsResponse(
            success=True,
            elements=elements,
            count=len(elements)
        )
    except Exception as e:
        logger.error(f"Error getting elements: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/elements/selected", response_model=ElementsResponse, tags=["revit-integration"])
async def get_selected_elements() -> ElementsResponse:
    """Get currently selected elements in Revit UI."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        elements = revit.get_selected_elements()
        
        return ElementsResponse(
            success=True,
            elements=elements,
            count=len(elements)
        )
    except Exception as e:
        logger.error(f"Error getting selected: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/elements/{element_id}", tags=["revit-integration"])
async def get_element(element_id: str) -> Dict[str, Any]:
    """Get a single element by ID."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    element = revit.get_element_by_id(element_id)
    if element:
        return {"success": True, "element": element}
    else:
        raise HTTPException(status_code=404, detail="Element not found")


@router.get("/elements/{element_id}/parameters", tags=["revit-integration"])
async def get_element_parameters(element_id: str) -> Dict[str, Any]:
    """Get all parameters of an element."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        params = revit.get_element_parameters(element_id)
        return {"success": True, "parameters": params}
    except Exception as e:
        logger.error(f"Error getting parameters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ELEMENT CREATE ENDPOINTS
# ============================================================================

@router.post("/elements/create/wall", response_model=ElementResponse, tags=["revit-integration"])
async def create_wall(request: WallCreateRequest) -> ElementResponse:
    """Create a wall in Revit."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        element_id = revit.create_wall(
            start_point=request.start_point,
            end_point=request.end_point,
            height=request.height,
            level=request.level,
            wall_type=request.wall_type
        )
        
        return ElementResponse(
            success=element_id is not None,
            message=f"Wall created: {element_id}" if element_id else "Failed to create wall",
            element_id=element_id
        )
    except Exception as e:
        logger.error(f"Error creating wall: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/elements/create/floor", response_model=ElementResponse, tags=["revit-integration"])
async def create_floor(request: FloorCreateRequest) -> ElementResponse:
    """Create a floor in Revit."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        element_id = revit.create_floor(
            boundary_points=request.boundary_points,
            level=request.level,
            floor_type=request.floor_type
        )
        
        return ElementResponse(
            success=element_id is not None,
            message=f"Floor created: {element_id}" if element_id else "Failed to create floor",
            element_id=element_id
        )
    except Exception as e:
        logger.error(f"Error creating floor: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/elements/create/door", response_model=ElementResponse, tags=["revit-integration"])
async def create_door(request: DoorCreateRequest) -> ElementResponse:
    """Create a door in a wall."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        element_id = revit.create_door(
            host_wall_id=request.host_wall_id,
            location_point=request.location_point,
            family_type=request.family_type,
            level=request.level
        )
        
        return ElementResponse(
            success=element_id is not None,
            message=f"Door created: {element_id}" if element_id else "Failed to create door",
            element_id=element_id
        )
    except Exception as e:
        logger.error(f"Error creating door: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/elements/create/window", response_model=ElementResponse, tags=["revit-integration"])
async def create_window(request: WindowCreateRequest) -> ElementResponse:
    """Create a window in a wall."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        element_id = revit.create_window(
            host_wall_id=request.host_wall_id,
            location_point=request.location_point,
            family_type=request.family_type,
            level=request.level
        )
        
        return ElementResponse(
            success=element_id is not None,
            message=f"Window created: {element_id}" if element_id else "Failed to create window",
            element_id=element_id
        )
    except Exception as e:
        logger.error(f"Error creating window: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/elements/create/column", response_model=ElementResponse, tags=["revit-integration"])
async def create_column(request: ColumnCreateRequest) -> ElementResponse:
    """Create a structural column."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        element_id = revit.create_column(
            location_point=request.location_point,
            height=request.height,
            level=request.level,
            column_type=request.column_type
        )
        
        return ElementResponse(
            success=element_id is not None,
            message=f"Column created: {element_id}" if element_id else "Failed to create column",
            element_id=element_id
        )
    except Exception as e:
        logger.error(f"Error creating column: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/elements/create/beam", response_model=ElementResponse, tags=["revit-integration"])
async def create_beam(request: BeamCreateRequest) -> ElementResponse:
    """Create a structural beam."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        element_id = revit.create_beam(
            start_point=request.start_point,
            end_point=request.end_point,
            level=request.level,
            beam_type=request.beam_type
        )
        
        return ElementResponse(
            success=element_id is not None,
            message=f"Beam created: {element_id}" if element_id else "Failed to create beam",
            element_id=element_id
        )
    except Exception as e:
        logger.error(f"Error creating beam: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/elements/create/family", response_model=ElementResponse, tags=["revit-integration"])
async def create_family_instance(request: FamilyInstanceCreateRequest) -> ElementResponse:
    """Create a generic family instance."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        element_id = revit.create_family_instance(
            family_name=request.family_name,
            category=request.category,
            location_point=request.location_point,
            level=request.level,
            parameters=request.parameters
        )
        
        return ElementResponse(
            success=element_id is not None,
            message=f"Family instance created: {element_id}" if element_id else "Failed to create",
            element_id=element_id
        )
    except Exception as e:
        logger.error(f"Error creating family: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ELEMENT UPDATE/DELETE ENDPOINTS
# ============================================================================

@router.put("/elements/{element_id}/parameters", tags=["revit-integration"])
async def update_element_parameters(
    element_id: str,
    request: ParameterUpdateRequest
) -> Dict[str, Any]:
    """Update element parameters."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        success = True
        for param_name, value in request.parameters.items():
            if not revit.set_element_parameter(element_id, param_name, value):
                success = False
        
        return {
            "success": success,
            "message": "Parameters updated" if success else "Some parameters failed"
        }
    except Exception as e:
        logger.error(f"Error updating parameters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/elements/{element_id}", tags=["revit-integration"])
async def delete_element(element_id: str) -> Dict[str, Any]:
    """Delete an element."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        success = revit.delete_element(element_id)
        
        if success:
            return {"success": True, "message": f"Element {element_id} deleted"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete element")
    except Exception as e:
        logger.error(f"Error deleting element: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VIEW ENDPOINTS
# ============================================================================

@router.get("/views", response_model=ElementsResponse, tags=["revit-integration"])
async def get_views() -> ElementsResponse:
    """Get all views in the project."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        views = revit.get_views()
        return ElementsResponse(success=True, elements=views, count=len(views))
    except Exception as e:
        logger.error(f"Error getting views: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/views", response_model=ElementResponse, tags=["revit-integration"])
async def create_view(request: ViewCreateRequest) -> ElementResponse:
    """Create a new view."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        view_id = revit.create_view(
            view_name=request.view_name,
            view_type=request.view_type,
            level=request.level
        )
        
        return ElementResponse(
            success=view_id is not None,
            message=f"View created: {view_id}" if view_id else "Failed to create view",
            element_id=view_id
        )
    except Exception as e:
        logger.error(f"Error creating view: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LEVEL ENDPOINTS
# ============================================================================

@router.get("/levels", response_model=ElementsResponse, tags=["revit-integration"])
async def get_levels() -> ElementsResponse:
    """Get all levels in the project."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        levels = revit.get_levels()
        return ElementsResponse(success=True, elements=levels, count=len(levels))
    except Exception as e:
        logger.error(f"Error getting levels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/levels", response_model=ElementResponse, tags=["revit-integration"])
async def create_level(request: LevelCreateRequest) -> ElementResponse:
    """Create a new level."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        level_id = revit.create_level(
            name=request.name,
            elevation=request.elevation
        )
        
        return ElementResponse(
            success=level_id is not None,
            message=f"Level created: {level_id}" if level_id else "Failed to create level",
            element_id=level_id
        )
    except Exception as e:
        logger.error(f"Error creating level: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# GRID ENDPOINTS
# ============================================================================

@router.get("/grids", response_model=ElementsResponse, tags=["revit-integration"])
async def get_grids() -> ElementsResponse:
    """Get all grids in the project."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        grids = revit.get_grids()
        return ElementsResponse(success=True, elements=grids, count=len(grids))
    except Exception as e:
        logger.error(f"Error getting grids: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WORKSET ENDPOINTS
# ============================================================================

@router.get("/worksets", response_model=ElementsResponse, tags=["revit-integration"])
async def get_worksets() -> ElementsResponse:
    """Get all worksets in the project."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        worksets = revit.get_worksets()
        return ElementsResponse(success=True, elements=worksets, count=len(worksets))
    except Exception as e:
        logger.error(f"Error getting worksets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FAMILY ENDPOINTS
# ============================================================================

@router.get("/families/{category}/symbols", response_model=ElementsResponse, tags=["revit-integration"])
async def get_family_symbols(category: str) -> ElementsResponse:
    """
    Get all family symbols (types) for a category.
    
    Category examples: Doors, Windows, Furniture, Columns, etc.
    """
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        symbols = revit.get_family_symbols(category)
        return ElementsResponse(success=True, elements=symbols, count=len(symbols))
    except Exception as e:
        logger.error(f"Error getting family symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/families/load", tags=["revit-integration"])
async def load_family(request: FamilyLoadRequest) -> Dict[str, Any]:
    """Load a family (.rfa) into the project."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        success = revit.load_family(
            family_path=request.family_path,
            category=request.category
        )
        
        if success:
            return {"success": True, "message": f"Family loaded: {request.family_path}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to load family")
    except Exception as e:
        logger.error(f"Error loading family: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# API SEARCH ENDPOINTS
# ============================================================================

@router.post("/search/api", response_model=APIResultResponse, tags=["revit-integration"])
async def search_api_data(request: APISearchRequest) -> APIResultResponse:
    """
    Search loaded API data locally.
    
    Requires API data to be loaded first via /api/revit-integration/data/load
    """
    try:
        results = revit.search_api_data(
            keyword=request.keyword,
            api_name=request.api_name,
            namespace=request.namespace,
            api_type=request.api_type
        )
        
        # Convert to dict
        result_dicts = [
            {
                "title": r.title,
                "keywords": r.keywords,
                "api_name": r.api_name,
                "description": r.description,
                "namespace": r.namespace,
                "guid": r.guid,
                "type": r.type,
                "url": revit.get_api_url(r)
            }
            for r in results
        ]
        
        return APIResultResponse(
            success=True,
            results=result_dicts,
            count=len(result_dicts)
        )
    except Exception as e:
        logger.error(f"Error searching API data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/online", response_model=APIResultResponse, tags=["revit-integration"])
async def search_online(
    query: str = Query(..., description="Search query"),
    engine: str = Query("revitapidocs", description="Search engine: revitapidocs, revitapiforum")
) -> APIResultResponse:
    """
    Search Revit API documentation online.
    
    Uses Autodesk's autocomplete API (same as RevitJumper).
    """
    try:
        results = await revit.search_revit_api(query, engine)
        
        result_dicts = [
            {
                "related_key": r.related_key,
                "description": r.description,
                "url": r.url
            }
            for r in results
        ]
        
        return APIResultResponse(
            success=True,
            results=result_dicts,
            count=len(result_dicts)
        )
    except Exception as e:
        logger.error(f"Error searching online: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/load", tags=["revit-integration"])
async def load_api_data(filepath: str = Query(..., description="Path to RevitAPI.json")) -> Dict[str, Any]:
    """
    Load Revit API data from JSON file.
    
    Download from: https://github.com/chuongmep/RevitAPIDocGen
    """
    try:
        success = revit.load_revit_api_data(filepath)
        
        if success:
            return {
                "success": True,
                "message": f"Loaded {len(revit._api_data_cache)} API entries",
                "count": len(revit._api_data_cache)
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to load API data")
    except Exception as e:
        logger.error(f"Error loading API data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AI COMMAND EXECUTION
# ============================================================================

@router.post("/execute", tags=["revit-integration"])
async def execute_ai_command(request: AICommandRequest) -> Dict[str, Any]:
    """
    Execute an AI command from the agent.
    
    This interprets natural language commands and converts them to Revit operations.
    
    Example commands:
    - "Create a wall from 0,0,0 to 5000,0,0 on Level 1"
    - "Create a door in the selected wall"
    - "Get all walls in the project"
    - "Delete element with id 12345"
    - "Search api for Wall.Create"
    """
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        result = revit.execute_ai_command(
            command=request.command,
            context=request.context
        )
        
        return result
    except Exception as e:
        logger.error(f"Error executing AI command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TRANSACTION MANAGEMENT
# ============================================================================

@router.post("/transaction/start", tags=["revit-integration"])
async def start_transaction(name: str = Query("Modify", description="Transaction name")) -> Dict[str, Any]:
    """Start a named transaction for grouping operations."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        revit.start_transaction(name)
        return {"success": True, "message": f"Transaction '{name}' started"}
    except Exception as e:
        logger.error(f"Error starting transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transaction/commit", tags=["revit-integration"])
async def commit_transaction() -> Dict[str, Any]:
    """Commit the current transaction."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        revit.commit_transaction()
        return {"success": True, "message": "Transaction committed"}
    except Exception as e:
        logger.error(f"Error committing transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transaction/rollback", tags=["revit-integration"])
async def rollback_transaction() -> Dict[str, Any]:
    """Rollback the current transaction."""
    if not revit.is_connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")
    
    try:
        revit.rollback_transaction()
        return {"success": True, "message": "Transaction rolled back"}
    except Exception as e:
        logger.error(f"Error rolling back transaction: {e}")
        raise HTTPException(status_code=500, detail=str(e))
