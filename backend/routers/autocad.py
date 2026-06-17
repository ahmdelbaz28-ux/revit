"""
AutoCAD Integration Endpoints.

============================

REST API endpoints for AutoCAD integration operations.
Provides connection, file operations, drawing, layer, block, dimension, and AI operations.

CONNECTION METHODS:
- COM: Windows-only (win32com.client)
- Simulation: Cross-platform (no AutoCAD required)

ENDPOINTS:
- POST /api/v1/autocad/connect - Connect to AutoCAD
- POST /api/v1/autocad/disconnect - Disconnect from AutoCAD
- GET  /api/v1/autocad/status - Get connection status

LAYERS:
- POST /api/v1/autocad/layers - Create layer
- GET  /api/v1/autocad/layers - Get all layers
- PUT  /api/v1/autocad/layers/{name}/color - Set layer color
- PUT  /api/v1/autocad/layers/{name}/lock - Lock/unlock layer
- DELETE /api/v1/autocad/layers/{name} - Delete layer

DRAWING:
- POST /api/v1/autocad/draw/line - Draw line
- POST /api/v1/autocad/draw/rectangle - Draw rectangle
- POST /api/v1/autocad/draw/circle - Draw circle
- POST /api/v1/autocad/draw/arc - Draw arc
- POST /api/v1/autocad/draw/ellipse - Draw ellipse
- POST /api/v1/autocad/draw/polyline - Draw polyline
- POST /api/v1/autocad/draw/text - Draw text

DIMENSIONS:
- POST /api/v1/autocad/dimension/aligned - Aligned dimension
- POST /api/v1/autocad/dimension/linear - Linear dimension
- POST /api/v1/autocad/dimension/radial - Radial dimension
- POST /api/v1/autocad/dimension/diameter - Diameter dimension

ENTITIES:
- GET  /api/v1/autocad/entities - Get all entities
- GET  /api/v1/autocad/entities/{handle} - Get entity by handle
- DELETE /api/v1/autocad/entities/{handle} - Delete entity
- POST /api/v1/autocad/entities/{handle}/move - Move entity
- POST /api/v1/autocad/entities/{handle}/rotate - Rotate entity
- POST /api/v1/autocad/entities/{handle}/scale - Scale entity

GROUPS:
- POST /api/v1/autocad/groups - Create group
- GET  /api/v1/autocad/groups - Get all groups
- DELETE /api/v1/autocad/groups/{name} - Delete group

BLOCKS:
- POST /api/v1/autocad/blocks/insert - Insert block
- GET  /api/v1/autocad/blocks - Get all blocks

DOCUMENT:
- GET  /api/v1/autocad/document/info - Get document info
- POST /api/v1/autocad/document/read - Read DWG file
- POST /api/v1/autocad/document/write - Write DWG file
- POST /api/v1/autocad/document/save - Save document

AI:
- POST /api/v1/autocad/execute - Execute AI command
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.autocad_service import AutoCADService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["AutoCAD"])

# Global service instance
_autocad_service: Optional[AutoCADService] = None


def get_autocad_service() -> AutoCADService:
    """Get or initialize AutoCAD service singleton."""
    global _autocad_service
    if _autocad_service is None:
        _autocad_service = AutoCADService()
    return _autocad_service


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class ConnectRequest(BaseModel):
    """Connect to AutoCAD with specified method."""

    method: str = "auto"  # "auto", "com", "simulation"


class ConnectResponse(BaseModel):
    """Connection response."""

    success: bool
    message: str
    connected: bool
    method: Optional[str] = None


class StatusResponse(BaseModel):
    """Status response."""

    connected: bool
    method: Optional[str] = None
    platform: str
    com_available: bool


class CreateLayerRequest(BaseModel):
    """Create layer request."""

    name: str
    color: int = 7
    visible: bool = True


class LayerColorRequest(BaseModel):
    """Set layer color request."""

    color: int


class LayerLockRequest(BaseModel):
    """Lock/unlock layer request."""

    lock: bool = True


class LayerResponse(BaseModel):
    """Layer data response."""

    name: str
    color: int
    visible: bool
    locked: bool


class DrawLineRequest(BaseModel):
    """Draw line request."""

    start_point: List[float]
    end_point: List[float]
    layer: str = "0"
    color: int = 0


class DrawRectangleRequest(BaseModel):
    """Draw rectangle request."""

    lower_left: List[float]
    upper_right: List[float]
    layer: str = "0"
    color: int = 0


class DrawCircleRequest(BaseModel):
    """Draw circle request."""

    center: List[float]
    radius: float
    layer: str = "0"
    color: int = 0


class DrawArcRequest(BaseModel):
    """Draw arc request."""

    center: List[float]
    radius: float
    start_angle: float
    end_angle: float
    layer: str = "0"
    color: int = 0


class DrawEllipseRequest(BaseModel):
    """Draw ellipse request."""

    center: List[float]
    major_axis: List[float]
    ratio: float
    layer: str = "0"
    color: int = 0


class DrawPolylineRequest(BaseModel):
    """Draw polyline request."""

    vertices: List[List[float]]
    layer: str = "0"
    color: int = 0
    closed: bool = False


class DrawTextRequest(BaseModel):
    """Draw text request."""

    text: str
    insertion_point: List[float]
    height: float = 0.2
    layer: str = "0"
    color: int = 0


class DimAlignedRequest(BaseModel):
    """Aligned dimension request."""

    start_point: List[float]
    end_point: List[float]
    text_point: List[float]
    layer: str = "0"
    color: int = 0


class DimLinearRequest(BaseModel):
    """Linear dimension request."""

    start_point: List[float]
    end_point: List[float]
    text_point: List[float]
    angle: float = 0
    layer: str = "0"
    color: int = 0


class DimRadialRequest(BaseModel):
    """Radial dimension request."""

    center: List[float]
    chord_point: List[float]
    leader_length: float = 0
    layer: str = "0"
    color: int = 0


class DimDiameterRequest(BaseModel):
    """Diameter dimension request."""

    center: List[float]
    chord_point: List[float]
    leader_length: float = 0
    layer: str = "0"
    color: int = 0


class EntityResponse(BaseModel):
    """Entity data response."""

    handle: str
    type: str
    properties: Dict[str, Any]


class EntityListResponse(BaseModel):
    """List of entities response."""

    success: bool
    entities: List[EntityResponse]
    count: int


class MoveRequest(BaseModel):
    """Move entity request."""

    new_point: List[float]


class RotateRequest(BaseModel):
    """Rotate entity request."""

    base_point: List[float]
    angle: float


class ScaleRequest(BaseModel):
    """Scale entity request."""

    base_point: List[float]
    scale_factor: float


class CreateGroupRequest(BaseModel):
    """Create group request."""

    group_name: str
    handles: List[str]


class GroupResponse(BaseModel):
    """Group data response."""

    name: str
    count: Optional[int] = None
    entities: Optional[List[str]] = None


class InsertBlockRequest(BaseModel):
    """Insert block request."""

    file_path: str
    insertion_point: List[float]
    scale: float = 1.0
    rotation: float = 0
    layer: str = "0"


class BlockResponse(BaseModel):
    """Block data response."""

    name: str
    count: int


class DocumentInfoResponse(BaseModel):
    """Document info response."""

    name: str
    path: str
    title: Optional[str] = None
    active_space: Optional[str] = None
    entity_count: Optional[int] = None
    layer_count: Optional[int] = None
    mode: str


class ReadDwgRequest(BaseModel):
    """Read DWG request."""

    filepath: str


class WriteDwgRequest(BaseModel):
    """Write DWG request."""

    filepath: str
    entities: List[Dict[str, Any]]


class SaveRequest(BaseModel):
    """Save document request."""

    filepath: str


class AICommandRequest(BaseModel):
    """AI command request."""

    command: str


class AICommandResponse(BaseModel):
    """AI command response."""

    success: bool
    action: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    handle: Optional[str] = None
    count: Optional[int] = None
    entities: Optional[List[Dict[str, Any]]] = None
    layers: Optional[List[Dict[str, Any]]] = None
    suggestion: Optional[str] = None


class OperationResponse(BaseModel):
    """Generic operation response."""

    success: bool
    message: str
    handle: Optional[str] = None


# =============================================================================
# CONNECTION ENDPOINTS
# =============================================================================

@router.post("/connect", response_model=ConnectResponse)
async def connect(request: ConnectRequest) -> ConnectResponse:
    """Connect to AutoCAD using specified method."""
    service = get_autocad_service()
    success = service.connect(method=request.method)

    return ConnectResponse(
        success=success,
        message=f"Connected via {service.connection_method.value}" if success else "Connection failed",
        connected=success,
        method=service.connection_method.value if success else None,
    )


@router.post("/disconnect", response_model=ConnectResponse)
async def disconnect() -> ConnectResponse:
    """Disconnect from AutoCAD."""
    service = get_autocad_service()
    success = service.disconnect()

    return ConnectResponse(
        success=success,
        message="Disconnected" if success else "Disconnect failed",
        connected=False,
        method=None,
    )


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Get connection status."""
    service = get_autocad_service()
    status = service.get_status()

    return StatusResponse(**status)


# =============================================================================
# LAYER ENDPOINTS
# =============================================================================

@router.post("/layers", response_model=OperationResponse)
async def create_layer(request: CreateLayerRequest) -> OperationResponse:
    """Create a new layer."""
    service = get_autocad_service()
    success = service.create_layer(request.name, request.color, request.visible)

    return OperationResponse(
        success=success,
        message=f"Layer '{request.name}' created" if success else f"Failed to create layer '{request.name}'",
    )


@router.get("/layers", response_model=List[LayerResponse])
async def get_layers() -> List[LayerResponse]:
    """Get all layers."""
    service = get_autocad_service()
    layers = service.get_layers()

    return [LayerResponse(**layer) for layer in layers]


@router.put("/layers/{name}/color", response_model=OperationResponse)
async def set_layer_color(name: str, request: LayerColorRequest) -> OperationResponse:
    """Set layer color."""
    service = get_autocad_service()
    success = service.set_layer_color(name, request.color)

    return OperationResponse(
        success=success,
        message=f"Layer '{name}' color set to {request.color}" if success else f"Failed to set color for '{name}'",
    )


@router.put("/layers/{name}/lock", response_model=OperationResponse)
async def lock_layer(name: str, request: LayerLockRequest) -> OperationResponse:
    """Lock or unlock a layer."""
    service = get_autocad_service()
    success = service.lock_layer(name, request.lock)

    return OperationResponse(
        success=success,
        message=f"Layer '{name}' {'locked' if request.lock else 'unlocked'}" if success else f"Failed to lock layer '{name}'",
    )


@router.delete("/layers/{name}", response_model=OperationResponse)
async def delete_layer(name: str) -> OperationResponse:
    """Delete a layer."""
    service = get_autocad_service()
    success = service.delete_layer(name)

    return OperationResponse(
        success=success,
        message=f"Layer '{name}' deleted" if success else f"Failed to delete layer '{name}'",
    )


# =============================================================================
# DRAWING ENDPOINTS
# =============================================================================

@router.post("/draw/line", response_model=OperationResponse)
async def draw_line(request: DrawLineRequest) -> OperationResponse:
    """Draw a line."""
    service = get_autocad_service()
    handle = service.draw_line(request.start_point, request.end_point, request.layer, request.color)

    return OperationResponse(
        success=handle is not None,
        message="Line drawn" if handle else "Failed to draw line",
        handle=handle,
    )


@router.post("/draw/rectangle", response_model=OperationResponse)
async def draw_rectangle(request: DrawRectangleRequest) -> OperationResponse:
    """Draw a rectangle."""
    service = get_autocad_service()
    handle = service.draw_rectangle(request.lower_left, request.upper_right, request.layer, request.color)

    return OperationResponse(
        success=handle is not None,
        message="Rectangle drawn" if handle else "Failed to draw rectangle",
        handle=handle,
    )


@router.post("/draw/circle", response_model=OperationResponse)
async def draw_circle(request: DrawCircleRequest) -> OperationResponse:
    """Draw a circle."""
    service = get_autocad_service()
    handle = service.draw_circle(request.center, request.radius, request.layer, request.color)

    return OperationResponse(
        success=handle is not None,
        message="Circle drawn" if handle else "Failed to draw circle",
        handle=handle,
    )


@router.post("/draw/arc", response_model=OperationResponse)
async def draw_arc(request: DrawArcRequest) -> OperationResponse:
    """Draw an arc."""
    service = get_autocad_service()
    handle = service.draw_arc(
        request.center, request.radius, request.start_angle, request.end_angle, request.layer, request.color
    )

    return OperationResponse(
        success=handle is not None,
        message="Arc drawn" if handle else "Failed to draw arc",
        handle=handle,
    )


@router.post("/draw/ellipse", response_model=OperationResponse)
async def draw_ellipse(request: DrawEllipseRequest) -> OperationResponse:
    """Draw an ellipse."""
    service = get_autocad_service()
    handle = service.draw_ellipse(request.center, request.major_axis, request.ratio, request.layer, request.color)

    return OperationResponse(
        success=handle is not None,
        message="Ellipse drawn" if handle else "Failed to draw ellipse",
        handle=handle,
    )


@router.post("/draw/polyline", response_model=OperationResponse)
async def draw_polyline(request: DrawPolylineRequest) -> OperationResponse:
    """Draw a polyline."""
    service = get_autocad_service()
    handle = service.draw_polyline(request.vertices, request.layer, request.color, request.closed)

    return OperationResponse(
        success=handle is not None,
        message=f"Polyline drawn ({len(request.vertices)} vertices)" if handle else "Failed to draw polyline",
        handle=handle,
    )


@router.post("/draw/text", response_model=OperationResponse)
async def draw_text(request: DrawTextRequest) -> OperationResponse:
    """Draw text."""
    service = get_autocad_service()
    handle = service.draw_text(request.text, request.insertion_point, request.height, request.layer, request.color)

    return OperationResponse(
        success=handle is not None,
        message=f"Text '{request.text}' drawn" if handle else "Failed to draw text",
        handle=handle,
    )


# =============================================================================
# DIMENSION ENDPOINTS
# =============================================================================

@router.post("/dimension/aligned", response_model=OperationResponse)
async def draw_aligned_dimension(request: DimAlignedRequest) -> OperationResponse:
    """Draw aligned dimension."""
    service = get_autocad_service()
    handle = service.draw_dimension_aligned(
        request.start_point, request.end_point, request.text_point, request.layer, request.color
    )

    return OperationResponse(
        success=handle is not None,
        message="Aligned dimension drawn" if handle else "Failed to draw aligned dimension",
        handle=handle,
    )


@router.post("/dimension/linear", response_model=OperationResponse)
async def draw_linear_dimension(request: DimLinearRequest) -> OperationResponse:
    """Draw linear dimension."""
    service = get_autocad_service()
    handle = service.draw_dimension_linear(
        request.start_point, request.end_point, request.text_point, request.angle, request.layer, request.color
    )

    return OperationResponse(
        success=handle is not None,
        message="Linear dimension drawn" if handle else "Failed to draw linear dimension",
        handle=handle,
    )


@router.post("/dimension/radial", response_model=OperationResponse)
async def draw_radial_dimension(request: DimRadialRequest) -> OperationResponse:
    """Draw radial dimension."""
    service = get_autocad_service()
    handle = service.draw_dimension_radial(
        request.center, request.chord_point, request.leader_length, request.layer, request.color
    )

    return OperationResponse(
        success=handle is not None,
        message="Radial dimension drawn" if handle else "Failed to draw radial dimension",
        handle=handle,
    )


@router.post("/dimension/diameter", response_model=OperationResponse)
async def draw_diameter_dimension(request: DimDiameterRequest) -> OperationResponse:
    """Draw diameter dimension."""
    service = get_autocad_service()
    handle = service.draw_dimension_diameter(
        request.center, request.chord_point, request.leader_length, request.layer, request.color
    )

    return OperationResponse(
        success=handle is not None,
        message="Diameter dimension drawn" if handle else "Failed to draw diameter dimension",
        handle=handle,
    )


# =============================================================================
# ENTITY ENDPOINTS
# =============================================================================

@router.get("/entities", response_model=EntityListResponse)
async def get_entities(entity_type: Optional[str] = None) -> EntityListResponse:
    """Get all entities, optionally filtered by type."""
    service = get_autocad_service()
    entities = service.get_entities(entity_type)

    return EntityListResponse(
        success=True,
        entities=[EntityResponse(handle=e["handle"], type=e["type"], properties=e["properties"]) for e in entities],
        count=len(entities),
    )


@router.get("/entities/{handle}", response_model=Optional[EntityResponse])
async def get_entity(handle: str) -> Optional[EntityResponse]:
    """Get entity by handle."""
    service = get_autocad_service()
    entity = service.get_entity(handle)

    if entity:
        return EntityResponse(**entity)
    raise HTTPException(status_code=404, detail=f"Entity {handle} not found")


@router.delete("/entities/{handle}", response_model=OperationResponse)
async def delete_entity(handle: str) -> OperationResponse:
    """Delete an entity."""
    service = get_autocad_service()
    success = service.delete_entity(handle)

    return OperationResponse(
        success=success,
        message=f"Entity {handle} deleted" if success else f"Failed to delete entity {handle}",
    )


@router.post("/entities/{handle}/move", response_model=OperationResponse)
async def move_entity(handle: str, request: MoveRequest) -> OperationResponse:
    """Move an entity."""
    service = get_autocad_service()
    success = service.move_entity(handle, request.new_point)

    return OperationResponse(
        success=success,
        message=f"Entity {handle} moved to {request.new_point}" if success else f"Failed to move entity {handle}",
    )


@router.post("/entities/{handle}/rotate", response_model=OperationResponse)
async def rotate_entity(handle: str, request: RotateRequest) -> OperationResponse:
    """Rotate an entity."""
    service = get_autocad_service()
    success = service.rotate_entity(handle, request.base_point, request.angle)

    return OperationResponse(
        success=success,
        message=f"Entity {handle} rotated by {request.angle}" if success else f"Failed to rotate entity {handle}",
    )


@router.post("/entities/{handle}/scale", response_model=OperationResponse)
async def scale_entity(handle: str, request: ScaleRequest) -> OperationResponse:
    """Scale an entity."""
    service = get_autocad_service()
    success = service.scale_entity(handle, request.base_point, request.scale_factor)

    return OperationResponse(
        success=success,
        message=f"Entity {handle} scaled by {request.scale_factor}" if success else f"Failed to scale entity {handle}",
    )


# =============================================================================
# GROUP ENDPOINTS
# =============================================================================

@router.post("/groups", response_model=OperationResponse)
async def create_group(request: CreateGroupRequest) -> OperationResponse:
    """Create a group from entities."""
    service = get_autocad_service()
    success = service.create_group(request.group_name, request.handles)

    return OperationResponse(
        success=success,
        message=f"Group '{request.group_name}' created with {len(request.handles)} entities" if success else f"Failed to create group '{request.group_name}'",
    )


@router.get("/groups", response_model=List[GroupResponse])
async def get_groups() -> List[GroupResponse]:
    """Get all groups."""
    service = get_autocad_service()
    groups = service.get_groups()

    return [GroupResponse(**g) for g in groups]


@router.delete("/groups/{name}", response_model=OperationResponse)
async def delete_group(name: str) -> OperationResponse:
    """Delete a group."""
    service = get_autocad_service()
    success = service.delete_group(name)

    return OperationResponse(
        success=success,
        message=f"Group '{name}' deleted" if success else f"Failed to delete group '{name}'",
    )


# =============================================================================
# BLOCK ENDPOINTS
# =============================================================================

@router.post("/blocks/insert", response_model=OperationResponse)
async def insert_block(request: InsertBlockRequest) -> OperationResponse:
    """Insert a block from file."""
    service = get_autocad_service()
    handle = service.insert_block(
        request.file_path, request.insertion_point, request.scale, request.rotation, request.layer
    )

    return OperationResponse(
        success=handle is not None,
        message=f"Block from '{request.file_path}' inserted" if handle else f"Failed to insert block from '{request.file_path}'",
        handle=handle,
    )


@router.get("/blocks", response_model=List[BlockResponse])
async def get_blocks() -> List[BlockResponse]:
    """Get all block definitions."""
    service = get_autocad_service()
    blocks = service.get_blocks()

    return [BlockResponse(**b) for b in blocks]


# =============================================================================
# DOCUMENT ENDPOINTS
# =============================================================================

@router.get("/document/info", response_model=DocumentInfoResponse)
async def get_document_info() -> DocumentInfoResponse:
    """Get current document information."""
    service = get_autocad_service()
    info = service.get_document_info()

    return DocumentInfoResponse(**info)


@router.post("/document/read", response_model=EntityListResponse)
async def read_dwg(request: ReadDwgRequest) -> EntityListResponse:
    """Read entities from DWG file."""
    service = get_autocad_service()
    result = service.read_dwg(request.filepath)

    if result.get("success"):
        entities = result.get("entities", [])
        return EntityListResponse(
            success=True,
            entities=[
                EntityResponse(handle=e["handle"], type=e["type"], properties={"layer": e.get("layer")})
                for e in entities
            ],
            count=len(entities),
        )
    raise HTTPException(status_code=400, detail=result.get("error", "Failed to read DWG"))


@router.post("/document/write", response_model=OperationResponse)
async def write_dwg(request: WriteDwgRequest) -> OperationResponse:
    """Write entities to DWG file."""
    service = get_autocad_service()
    success = service.write_dwg(request.filepath, request.entities)

    return OperationResponse(
        success=success,
        message=f"Wrote {len(request.entities)} entities to '{request.filepath}'" if success else f"Failed to write to '{request.filepath}'",
    )


@router.post("/document/save", response_model=OperationResponse)
async def save_document(request: SaveRequest) -> OperationResponse:
    """Save current document."""
    service = get_autocad_service()
    success = service.save(request.filepath)

    return OperationResponse(
        success=success,
        message=f"Document saved to '{request.filepath}'" if success else f"Failed to save to '{request.filepath}'",
    )


# =============================================================================
# AI ENDPOINT
# =============================================================================

@router.post("/execute", response_model=AICommandResponse)
async def execute_ai_command(request: AICommandRequest) -> AICommandResponse:
    """
    Execute natural language command.

    Supported commands:
    - "draw line from 0,0,0 to 100,100,0"
    - "draw rectangle from 0,0 to 100,100"
    - "draw circle at 50,50 radius 25"
    - "create layer MyLayer"
    - "get all entities"
    - "delete entity <handle>"
    - "get layers"
    """
    service = get_autocad_service()
    result = service.execute_ai_command(request.command)

    return AICommandResponse(**result)
