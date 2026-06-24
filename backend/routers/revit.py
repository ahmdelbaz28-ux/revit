"""backend/routers/revit.py — Revit Integration Endpoints
=====================================================

REST API endpoints for Revit integration with full AI agent support.

CONNECTION METHODS:
- API: Direct Revit API (requires Revit + pythonnet)
- MACRO: Revit Macro API (free, runs inside Revit)
- SIMULATION: Development mode (no Revit needed)

ELEMENT OPERATIONS:
- Walls, Floors, Doors, Windows, Columns, Beams, Family Instances
- Element CRUD (Create, Read, Update, Delete)
- Parameter manipulation
- View/Level/Grid operations

AI FEATURES:
- Natural language command execution
- RevitAPIDocs.com search (local and online)
- Family/Symbol management

ENDPOINTS:
- POST /api/revit/connect - Connect to Revit (method: api, macro, simulation)
- GET /api/revit/status - Get connection status
- POST /api/revit/document/open - Open RVT file
- POST /api/revit/document/save - Save document
- POST /api/revit/document/close - Close document
- GET /api/revit/elements - Get elements (filter by category)
- GET /api/revit/elements/{id} - Get element by ID
- GET /api/revit/elements/selected - Get selected elements
- POST /api/revit/elements/create/wall - Create wall
- POST /api/revit/elements/create/floor - Create floor
- POST /api/revit/elements/create/door - Create door
- POST /api/revit/elements/create/window - Create window
- POST /api/revit/elements/create/column - Create column
- POST /api/revit/elements/create/beam - Create beam
- POST /api/revit/elements/create/family - Create family instance
- PUT /api/revit/elements/{id}/parameters - Update parameters
- DELETE /api/revit/elements/{id} - Delete element
- GET /api/revit/views - Get all views
- GET /api/revit/levels - Get all levels
- GET /api/revit/grids - Get all grids
- GET /api/revit/worksets - Get all worksets
- GET /api/revit/families/{category}/symbols - Get family symbols
- POST /api/revit/search/api - Search local API data
- GET /api/revit/search/online - Search RevitAPIDocs.com
- POST /api/revit/execute - Execute AI command
"""

import logging
import os
import re
import tempfile
import threading
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from backend.services.revit_service import RevitService

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Thread-safe service singleton ────────────────────────────────────────
_service: Optional[RevitService] = None
_service_lock = threading.Lock()


def get_revit_service() -> RevitService:
    """Provide RevitService instance via thread-safe singleton."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = RevitService()
    return _service


# ── Path validation helper (FIX V130: Path Traversal prevention) ────────
# V130 SECURITY FIX (2026-06-18 audit): Replaced broken str.startswith()
# check (bypassable: "/tmp/fireai-data-evil/payload.rvt" matched "/tmp/fireai-data")
# with the centralised parsers._path_security.validate_input_path() helper.
# This is the same hardened implementation already used by every parser in
# parsers/ and qomn_fire/parsers/ — single source of truth, no drift.
#
# Hardening:
#   - TOCTOU-safe Path.resolve() (follows symlinks)
#   - Path.relative_to() check (true containment, not prefix match)
#   - Null-byte rejection (defends C-string truncation in downstream libs)
#   - Leading-"-" rejection (defends argument injection)
#   - Optional extension allow-list
# V130 SECURITY FIX: Auth + rate-limiter dependencies.
# The /execute endpoint runs arbitrary natural-language commands against the
# live Revit session (create walls, delete elements, search API, etc.).
# Leaving it unauthenticated meant ANY network caller could execute AI-driven
# mutations against the building model. Now requires ENGINEER+ permission.
# Upload endpoints are also rate-limited to prevent DoS via cadenced uploads.
from backend.auth import require_permission
from backend.limiter import limiter
from backend.rbac import Permission
from parsers._path_security import UnsafePathError, validate_input_path

# Re-export the validated path as a string for legacy callers.
_ALLOWED_EXTENSIONS = frozenset({".rvt", ".rfa", ".ifc", ".dwg", ".dxf"})


def _validate_file_path(filepath: str) -> str:
    """Validate that a file path is within allowed directories.

    Prevents path traversal attacks (e.g., ../../etc/passwd) and
    argument-injection attacks (e.g. leading "-"). Uses the shared
    parsers._path_security.validate_input_path() helper so the security
    contract is identical across routers and parsers.

    Raises HTTPException(400) if the path is outside allowed directories,
    contains a null byte, starts with "-", or has a disallowed extension.
    """
    try:
        safe_path = validate_input_path(
            filepath,
            allowed_extensions=_ALLOWED_EXTENSIONS,
            parser_name="revit_router",
        )
    except FileNotFoundError as exc:
        # Benign missing-file case — return 404.
        raise HTTPException(status_code=404, detail="File not found.") from exc
    except UnsafePathError as exc:
        # Hard security rejection — log details, return generic 400.
        logger.warning("Path traversal blocked: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="File path is outside allowed directories. Contact administrator.",
        ) from exc
    return str(safe_path)


# ── Safe error helper ────────────────────────────────────────────────────
def _safe_error(status_code: int, log_msg: str, exc: Exception) -> HTTPException:
    """Log full exception detail, return safe message to client."""
    logger.error("%s: %s", log_msg, exc, exc_info=True)
    return HTTPException(status_code=status_code, detail=log_msg)


# Maximum upload size (50 MB)
_MAX_UPLOAD_SIZE = 50 * 1024 * 1024


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ConnectRequest(BaseModel):
    """Request model for Revit connection.
    
    Attributes:
        method: Connection method - 'api' (Revit API), 'macro' (Revit Macro), 
                'simulation' (development), or 'auto' (automatic detection)

    """

    method: str = Field(
        default="auto",
        description="Connection method: 'api', 'macro', 'simulation', or 'auto'"
    )

class ConnectResponse(BaseModel):
    """Response model for Revit connection."""

    success: bool
    message: str
    connected: bool
    connection_method: Optional[str] = None


class StatusResponse(BaseModel):
    """Response model for connection status."""

    connected: bool
    message: str
    connection_method: Optional[str] = None
    document_info: Optional[Dict[str, Any]] = None


# =============================================================================
# DOCUMENT MODELS
# =============================================================================

class DocumentOpenRequest(BaseModel):
    """Request to open an RVT file."""

    filepath: str = Field(..., description="Path to the RVT file")


class DocumentSaveRequest(BaseModel):
    """Request to save the document."""

    filepath: Optional[str] = Field(None, description="Optional new path to save as")


class DocumentCloseRequest(BaseModel):
    """Request to close the document."""

    save_changes: bool = Field(True, description="Whether to save changes before closing")


# =============================================================================
# ELEMENT CREATE MODELS
# =============================================================================

class CreateWallRequest(BaseModel):
    """Request to create a wall.
    
    Attributes:
        start_point: Start coordinates [x, y, z] in mm
        end_point: End coordinates [x, y, z] in mm
        height: Wall height in mm (default 3000)
        level: Level name to place wall (default "Level 1")
        wall_type: Wall type name (default "Basic Wall")

    """

    start_point: List[float] = Field(..., description="Start point [x, y, z]")
    end_point: List[float] = Field(..., description="End point [x, y, z]")
    height: float = Field(3000.0, description="Wall height in mm")
    level: str = Field("Level 1", description="Level name")
    wall_type: str = Field("Basic Wall", description="Wall type name")


class CreateFloorRequest(BaseModel):
    """Request to create a floor.
    
    Attributes:
        boundary_points: List of [x, y, z] points forming closed boundary
        level: Level name (default "Level 1")
        floor_type: Floor type name (default "Floor")

    """

    boundary_points: List[List[float]] = Field(
        ...,
        description="Boundary points [[x,y,z], ...]"
    )
    level: str = Field("Level 1", description="Level name")
    floor_type: str = Field("Floor", description="Floor type name")


class CreateDoorRequest(BaseModel):
    """Request to create a door in a wall.
    
    Attributes:
        host_wall_id: Wall element ID to place door in
        location_point: [x, y, z] insertion point
        family_type: Door family type (default "M_Single-Flush")
        level: Level name (default "Level 1")

    """

    host_wall_id: str = Field(..., description="Host wall element ID")
    location_point: List[float] = Field(..., description="Insertion point [x, y, z]")
    family_type: str = Field("M_Single-Flush", description="Door family type")
    level: str = Field("Level 1", description="Level name")


class CreateWindowRequest(BaseModel):
    """Request to create a window in a wall."""

    host_wall_id: str = Field(..., description="Host wall element ID")
    location_point: List[float] = Field(..., description="Insertion point [x, y, z]")
    family_type: str = Field("M_Single-Flush", description="Window family type")
    level: str = Field("Level 1", description="Level name")


class CreateColumnRequest(BaseModel):
    """Request to create a structural column.
    
    Attributes:
        location_point: Base location [x, y, z]
        height: Column height in mm (default 3000)
        level: Base level name (default "Level 1")
        column_type: Column type name (default "M_Columns")

    """

    location_point: List[float] = Field(..., description="Base location [x, y, z]")
    height: float = Field(3000.0, description="Column height in mm")
    level: str = Field("Level 1", description="Base level name")
    column_type: str = Field("M_Columns", description="Column type name")


class CreateBeamRequest(BaseModel):
    """Request to create a structural beam."""

    start_point: List[float] = Field(..., description="Start point [x, y, z]")
    end_point: List[float] = Field(..., description="End point [x, y, z]")
    level: str = Field("Level 1", description="Level name")
    beam_type: str = Field("W-Wide Flange", description="Beam type name")


class CreateFamilyRequest(BaseModel):
    """Request to create a generic family instance.
    
    Attributes:
        family_name: Family type name (e.g., "M_Single-Flush")
        category: Category name (e.g., "Doors", "Windows", "Furniture")
        location_point: [x, y, z] insertion point
        level: Optional level for host-based families
        parameters: Optional dict of parameter name/value pairs

    """

    family_name: str = Field(..., description="Family type name")
    category: str = Field(..., description="Category name")
    location_point: List[float] = Field(..., description="Insertion point [x, y, z]")
    level: Optional[str] = Field(None, description="Level name (for hosted families)")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Parameter name/value pairs")


class ParameterUpdateRequest(BaseModel):
    """Request to update element parameters."""

    parameters: Dict[str, Any] = Field(..., description="Parameter name/value pairs")


class ElementResponse(BaseModel):
    """Response for element operations."""

    success: bool
    message: str
    element_id: Optional[str] = None
    element: Optional[Dict[str, Any]] = None


class ElementsResponse(BaseModel):
    """Response containing multiple elements."""

    success: bool
    elements: List[Dict[str, Any]]
    count: int


# =============================================================================
# SEARCH MODELS
# =============================================================================

class SearchAPIRequest(BaseModel):
    """Request to search local API data."""

    keyword: Optional[str] = Field(None, description="Search keyword")
    api_name: Optional[str] = Field(None, description="Filter by API name")
    namespace: Optional[str] = Field(None, description="Filter by namespace")
    api_type: Optional[str] = Field(None, description="Filter by type (property, method, class)")


class SearchOnlineRequest(BaseModel):
    """Request to search online."""

    query: str = Field(..., description="Search query")
    engine: str = Field("revitapidocs", description="Search engine: revitapidocs or revitapiforum")


class AICommandRequest(BaseModel):
    """Request to execute an AI command."""

    command: str = Field(..., description="Natural language command")
    context: Optional[Dict[str, Any]] = Field(None, description="Optional context data")


class LoadAPIDataRequest(BaseModel):
    """Request to load Revit API data."""

    json_path: str = Field(..., description="Path to RevitAPI.json file")


class APIResultResponse(BaseModel):
    """Response from API search."""

    success: bool
    results: List[Dict[str, Any]]
    count: int


class LoadFamilyRequest(BaseModel):
    """Request to load a family (.rfa) file."""

    family_path: str = Field(..., description="Path to family file")
    category: Optional[str] = Field(None, description="Optional category")

# =============================================================================
# CONNECTION ENDPOINTS
# =============================================================================

@router.post("/connect", response_model=ConnectResponse, tags=["revit"])
async def connect_to_revit(request: ConnectRequest = None) -> ConnectResponse:
    """Connect to Revit application.
    
    Connection Methods:
    - **api**: Direct Revit API via pythonnet (best performance, requires Revit)
    - **macro**: Revit Macro API (free, runs inside Revit)
    - **simulation**: Development mode (no Revit needed)
    - **auto**: Automatic detection of best method
    
    Args:
        request: Connection parameters with method selection
        
    Returns:
        Connection status with method used

    """
    try:
        svc = get_revit_service()
        method = request.method if request else "auto"
        success = svc.connect(method=method)

        return ConnectResponse(
            success=success,
            message=f"Connected via {svc.connection_method}" if success else "Connection failed",
            connected=svc.connected,
            connection_method=svc.connection_method
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(503, "Failed to connect to Revit", e)


@router.post("/disconnect", response_model=ConnectResponse, tags=["revit"])
async def disconnect_from_revit() -> ConnectResponse:
    """Disconnect from Revit application."""
    try:
        svc = get_revit_service()
        success = svc.disconnect()

        return ConnectResponse(
            success=success,
            message="Disconnected from Revit" if success else "Disconnect failed",
            connected=svc.connected
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Failed to disconnect from Revit", e)


@router.get("/status", response_model=StatusResponse, tags=["revit"])
async def get_revit_status() -> StatusResponse:
    """Get current connection status and capabilities."""
    try:
        svc = get_revit_service()
        doc_info = {}
        if svc.connected:
            doc_info = svc.get_document_info()

        return StatusResponse(
            connected=svc.connected,
            message="Revit service status" if svc.connected else "Revit not connected",
            connection_method=svc.connection_method,
            document_info=doc_info if doc_info else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error getting Revit status", e)


# =============================================================================
# DOCUMENT ENDPOINTS
# =============================================================================

@router.post("/document/open", tags=["revit"])
async def open_document(request: DocumentOpenRequest) -> Dict[str, Any]:
    """Open an RVT file."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    # FIX: Path traversal validation
    _validate_file_path(request.filepath)

    success = svc.open_document(request.filepath)
    if success:
        return {"success": True, "message": f"Opened: {request.filepath}"}
    raise HTTPException(status_code=500, detail="Failed to open document")


@router.post("/document/save", tags=["revit"])
async def save_document(request: DocumentSaveRequest) -> Dict[str, Any]:
    """Save the current document."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    # FIX: Path traversal validation for save path
    if request.filepath:
        _validate_file_path(request.filepath)

    success = svc.save_document(request.filepath)
    if success:
        return {"success": True, "message": "Document saved"}
    raise HTTPException(status_code=500, detail="Failed to save document")


@router.post("/document/close", tags=["revit"])
async def close_document(request: DocumentCloseRequest) -> Dict[str, Any]:
    """Close the current document."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    success = svc.close_document(request.save_changes)
    if success:
        return {"success": True, "message": "Document closed"}
    raise HTTPException(status_code=500, detail="Failed to close document")

# =============================================================================
# LEGACY FILE ENDPOINTS
# =============================================================================

@router.post("/read_rvt", tags=["revit"], dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])
async def read_rvt_file(filepath: str) -> Dict[str, Any]:
    """Read elements from an RVT file (legacy endpoint)."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    # FIX: Path traversal validation
    _validate_file_path(filepath)

    result = svc.read_rvt(filepath)
    if not result.get("success", False):
        raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
    return result


@router.post("/write_rvt", tags=["revit"], dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])
async def write_rvt_file(filepath: str, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Write elements to an RVT file (legacy endpoint)."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    # FIX: Path traversal validation
    _validate_file_path(filepath)

    success = svc.write_rvt(filepath, elements)
    if success:
        return {"success": True, "message": "File written successfully"}
    raise HTTPException(status_code=500, detail="Failed to write file")


@router.post("/upload_rvt", tags=["revit"], dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])
@limiter.limit("10/minute")
async def upload_and_read_rvt(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload an RVT file and read its contents.

    FIX: Path traversal prevention, upload size limit, guaranteed cleanup.
    """
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    # Read with size check
    contents = await file.read()
    if len(contents) > _MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    # FIX: Safe temp path instead of f"temp_{file.filename}"
    safe_name = re.sub(r'[^\w\-.]', '_', file.filename or "upload.rvt")
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{safe_name}")

    try:
        with open(temp_path, "wb") as buffer:
            buffer.write(contents)

        result = svc.read_rvt(temp_path)

        if not result.get("success", False):
            raise HTTPException(status_code=400, detail=result.get("error", "Unknown error"))
        return result
    finally:
        # Guaranteed cleanup
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                os.rmdir(temp_dir)
            except OSError:
                pass


# =============================================================================
# ELEMENT READ ENDPOINTS
# =============================================================================

@router.get("/elements", response_model=ElementsResponse, tags=["revit"])
async def get_elements(
    category: Optional[str] = Query(None, description="Filter by category (Walls, Floors, Doors, etc.)"),
    element_class: Optional[str] = Query(None, description="Filter by class name")
) -> ElementsResponse:
    """Get elements using FilteredElementCollector pattern."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    elements = svc.get_elements(category=category, element_class=element_class)
    return ElementsResponse(success=True, elements=elements, count=len(elements))


@router.get("/elements/selected", response_model=ElementsResponse, tags=["revit"])
async def get_selected_elements() -> ElementsResponse:
    """Get currently selected elements in Revit UI."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    elements = svc.get_selected_elements()
    return ElementsResponse(success=True, elements=elements, count=len(elements))


@router.get("/elements/{element_id}", tags=["revit"])
async def get_element(element_id: str) -> Dict[str, Any]:
    """Get a single element by ID."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    element = svc.get_element_by_id(element_id)
    if element:
        return {"success": True, "element": element}
    raise HTTPException(status_code=404, detail="Element not found")


@router.get("/elements/{element_id}/parameters", tags=["revit"])
async def get_element_parameters(element_id: str) -> Dict[str, Any]:
    """Get all parameters of an element."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    params = svc.get_element_parameters(element_id)
    return {"success": True, "parameters": params}


# =============================================================================
# ELEMENT CREATE ENDPOINTS
# =============================================================================

@router.post("/elements/create/wall", response_model=ElementResponse, tags=["revit"])
async def create_wall(request: CreateWallRequest) -> ElementResponse:
    """Create a wall in Revit."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    element_id = svc.create_wall(
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


@router.post("/elements/create/floor", response_model=ElementResponse, tags=["revit"])
async def create_floor(request: CreateFloorRequest) -> ElementResponse:
    """Create a floor in Revit."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    element_id = svc.create_floor(
        boundary_points=request.boundary_points,
        level=request.level,
        floor_type=request.floor_type
    )

    return ElementResponse(
        success=element_id is not None,
        message=f"Floor created: {element_id}" if element_id else "Failed to create floor",
        element_id=element_id
    )


@router.post("/elements/create/door", response_model=ElementResponse, tags=["revit"])
async def create_door(request: CreateDoorRequest) -> ElementResponse:
    """Create a door in a wall."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    element_id = svc.create_door(
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


@router.post("/elements/create/window", response_model=ElementResponse, tags=["revit"])
async def create_window(request: CreateWindowRequest) -> ElementResponse:
    """Create a window in a wall."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    element_id = svc.create_window(
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


@router.post("/elements/create/column", response_model=ElementResponse, tags=["revit"])
async def create_column(request: CreateColumnRequest) -> ElementResponse:
    """Create a structural column."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    element_id = svc.create_column(
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


@router.post("/elements/create/beam", response_model=ElementResponse, tags=["revit"])
async def create_beam(request: CreateBeamRequest) -> ElementResponse:
    """Create a structural beam."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    element_id = svc.create_beam(
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


@router.post("/elements/create/family", response_model=ElementResponse, tags=["revit"])
async def create_family(request: CreateFamilyRequest) -> ElementResponse:
    """Create a generic family instance."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    element_id = svc.create_family_instance(
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


# =============================================================================
# ELEMENT UPDATE/DELETE ENDPOINTS
# =============================================================================

@router.put("/elements/{element_id}/parameters", tags=["revit"])
async def update_parameters(
    element_id: str,
    request: ParameterUpdateRequest
) -> Dict[str, Any]:
    """Update element parameters."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    success = True
    for param_name, value in request.parameters.items():
        if not svc.set_element_parameter(element_id, param_name, value):
            success = False

    return {
        "success": success,
        "message": "Parameters updated" if success else "Some parameters failed"
    }


@router.delete("/elements/{element_id}", tags=["revit"])
async def delete_element(element_id: str) -> Dict[str, Any]:
    """Delete an element."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    success = svc.delete_element(element_id)
    if success:
        return {"success": True, "message": f"Element {element_id} deleted"}
    raise HTTPException(status_code=500, detail="Failed to delete element")


# =============================================================================
# VIEW/LEVEL/GRID ENDPOINTS
# =============================================================================

@router.get("/views", response_model=ElementsResponse, tags=["revit"])
async def get_views() -> ElementsResponse:
    """Get all views in the project."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    views = svc.get_views()
    return ElementsResponse(success=True, elements=views, count=len(views))


@router.get("/levels", response_model=ElementsResponse, tags=["revit"])
async def get_levels() -> ElementsResponse:
    """Get all levels in the project."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    levels = svc.get_levels()
    return ElementsResponse(success=True, elements=levels, count=len(levels))


@router.get("/grids", response_model=ElementsResponse, tags=["revit"])
async def get_grids() -> ElementsResponse:
    """Get all grids in the project."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    grids = svc.get_grids()
    return ElementsResponse(success=True, elements=grids, count=len(grids))


@router.get("/worksets", response_model=ElementsResponse, tags=["revit"])
async def get_worksets() -> ElementsResponse:
    """Get all worksets in the project."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    worksets = svc.get_worksets()
    return ElementsResponse(success=True, elements=worksets, count=len(worksets))


# =============================================================================
# FAMILY ENDPOINTS
# =============================================================================

@router.get("/families/{category}/symbols", tags=["revit"])
async def get_family_symbols(category: str) -> Dict[str, Any]:
    """Get all family symbols for a category.
    
    Categories: Doors, Windows, Columns, Furniture, etc.
    """
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    symbols = svc.get_family_symbols(category)
    return {"success": True, "symbols": symbols, "count": len(symbols)}


@router.post("/families/load", tags=["revit"])
async def load_family(request: LoadFamilyRequest) -> Dict[str, Any]:
    """Load a family (.rfa) file into the project."""
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    success = svc.load_family(request.family_path, request.category)
    if success:
        return {"success": True, "message": f"Family loaded: {request.family_path}"}
    raise HTTPException(status_code=500, detail="Failed to load family")


# =============================================================================
# API SEARCH ENDPOINTS
# =============================================================================

@router.post("/search/api/load", tags=["revit"])
async def load_api_data(request: LoadAPIDataRequest) -> Dict[str, Any]:
    """Load Revit API data from JSON file.
    
    Load revit_data/RevitAPI2022.json or revit_data/RevitAPI2023.json first.
    """
    svc = get_revit_service()
    success = svc.load_revit_api_data(request.json_path)
    if success:
        return {"success": True, "message": f"API data loaded from {request.json_path}"}
    raise HTTPException(status_code=500, detail="Failed to load API data")


@router.post("/search/api", response_model=APIResultResponse, tags=["revit"])
async def search_api_data(request: SearchAPIRequest) -> APIResultResponse:
    """Search loaded API data locally.
    
    Requires loading API data first via /search/api/load.
    """
    svc = get_revit_service()
    results = svc.search_api_data(
        keyword=request.keyword,
        api_name=request.api_name,
        namespace=request.namespace,
        api_type=request.api_type
    )

    api_results = [
        {
            "name": r.title,
            "api_name": r.api_name,
            "description": r.description,
            "type": r.type,
            "namespace": r.namespace,
            "url": svc.get_api_url(r)
        }
        for r in results
    ]

    return APIResultResponse(success=True, results=api_results, count=len(api_results))


@router.get("/search/online", response_model=APIResultResponse, tags=["revit"])
async def search_online(
    query: str = Query(..., description="Search query"),
    engine: str = Query("revitapidocs", description="Search engine")
) -> APIResultResponse:
    """Search Revit API documentation online (RevitAPIDocs.com)."""
    svc = get_revit_service()
    results = await svc.search_revit_api(query, engine)

    api_results = [
        {
            "name": r.related_key,
            "description": r.description,
            "url": r.url
        }
        for r in results
    ]

    return APIResultResponse(success=True, results=api_results, count=len(api_results))


# =============================================================================
# AI COMMAND ENDPOINT
# =============================================================================

@router.post("/execute", tags=["revit"], dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])
async def execute_ai_command(request: AICommandRequest) -> Dict[str, Any]:
    """Execute a natural language command from AI agent.
    
    Examples:
    - "Create a wall from 0,0,0 to 5000,0,0"
    - "Create a door in the selected wall"
    - "Get all walls in the project"
    - "Delete element with id 12345"
    - "Search api Wall.Create"

    """
    svc = get_revit_service()
    if not svc.connected:
        raise HTTPException(status_code=503, detail="Not connected to Revit")

    result = svc.execute_ai_command(request.command, request.context)
    return result
