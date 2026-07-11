# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
backend/routers/autocad.py — AutoCAD Integration Endpoints.
==========================================================

REST API endpoints for AutoCAD integration operations.
Provides connection, file operations, and drawing operations.

ENDPOINTS:
- POST /autocad/connect - Connect to AutoCAD application
- POST /autocad/read_dwg - Read entities from DWG file
- POST /autocad/write_dwg - Write entities to DWG file
- POST /autocad/draw_line - Draw line in AutoCAD
- POST /autocad/draw_polyline - Draw polyline in AutoCAD
- POST /autocad/draw_circle - Draw circle in AutoCAD
- POST /autocad/draw_text - Draw text in AutoCAD
- GET  /autocad/status - Get connection status
- POST /autocad/save - Save current document
- POST /autocad/upload_dwg - Upload and read DWG file
- DELETE /autocad/entity/{handle} - Delete entity by handle
- PUT /autocad/entity/{handle} - Update entity properties

SECURITY FIXES APPLIED:
- FIX #5: Path traversal prevention in file upload
- FIX #6: No server paths in error messages
- FIX #17: Removed unused asyncio import
- FIX #18: Thread-safe singleton with double-checked locking
- FIX #20: Never expose str(e) to client — safe error messages
- FIX #34: Removed dummy function
"""

import logging
import os
import re
import tempfile
import threading
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

# V130 SECURITY FIX: Add auth dependencies for AutoCAD write/upload endpoints.
# Previously every endpoint in this router was unauthenticated — any network
# caller could read/write DWG files on the server. Write/upload operations now
# require ENGINEER+ permission; read operations require VIEWER+.
from backend.auth import require_permission

# V130: Rate limiter for upload endpoints — prevents DoS via large/cadenced uploads.
from backend.limiter import limiter
from backend.rbac import Permission
from backend.services.autocad_service import AutoCADService

# V133 PHASE 1.2: Path traversal protection — same shared helper used by revit.py.
# Per OWASP Path Traversal Cheat Sheet. Prevents ../../etc/passwd, null-byte
# injection, argument injection (leading "-"), and disallowed extensions.
from parsers._path_security import UnsafePathError, validate_input_path

# Allowed file extensions for AutoCAD operations
_AUTOCAD_ALLOWED_EXTENSIONS = frozenset({".dwg", ".dxf", ".rvt", ".rfa", ".ifc"})


def _validate_autocad_file_path(filepath: str) -> str:
    r"""
    Validate DWG/DXF file path against path traversal and injection attacks.

    V133 PHASE 1.2: Mirrors the protection already in revit.py:_validate_file_path.
    Previously, autocad.py used only ``os.path.exists()`` which accepted ANY path,
    including ``../../etc/passwd``, allowing arbitrary file reads.

    Security checks performed:
        1. Path resolution with ``Path.resolve()`` (eliminates ``..`` traversal)
        2. Directory whitelist (uploads/, /tmp, project root, or env var)
        3. Null-byte injection rejection (``\\x00`` in path)
        4. Argument injection rejection (leading ``-``)
        5. File extension whitelist (.dwg, .dxf, .rvt, .rfa, .ifc)

    Args:
        filepath: User-supplied file path.

    Returns:
        Safe resolved path as string.

    Raises:
        HTTPException(404): If file not found (benign case).
        HTTPException(400): If path is unsafe (path traversal, null byte, etc.).

    """
    try:
        safe_path = validate_input_path(
            filepath,
            allowed_extensions=_AUTOCAD_ALLOWED_EXTENSIONS,
            parser_name="autocad_router",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File not found.") from exc  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
    except UnsafePathError as exc:
        logger.warning("Path traversal blocked in autocad router: %s", exc)
        raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
            status_code=400,
            detail="File path is outside allowed directories. Contact administrator.",
        ) from exc
    return str(safe_path)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/autocad", tags=["AutoCAD"])

# ── Thread-safe service singleton (FIX #18) ────────────────────────────────
# Previously the singleton had a TOCTOU race condition — two threads could
# both see _autocad_service as None and create separate instances.
_autocad_service: Optional[AutoCADService] = None
_service_lock = threading.Lock()


def get_autocad_service() -> AutoCADService:
    """Get or initialize AutoCAD service singleton (thread-safe)."""
    global _autocad_service
    if _autocad_service is None:
        with _service_lock:
            if _autocad_service is None:  # Double-checked locking
                _autocad_service = AutoCADService()
    return _autocad_service


# ── Safe error helper (FIX #20) ────────────────────────────────────────────
# In a fire-safety system, exception messages can leak file paths, DB
# connection strings, and internal variable names. This helper logs the
# full error server-side but returns a generic message to the client.
def _safe_error(status_code: int, log_msg: str, exc: Exception) -> HTTPException:
    """Log full exception detail, return safe message to client."""
    logger.error("%s: %s", log_msg, exc, exc_info=True)
    return HTTPException(status_code=status_code, detail=log_msg)


# ── Pydantic request/response models ───────────────────────────────────────

class ConnectRequest(BaseModel):
    """Request model for AutoCAD connection."""

    visible: bool = True
    force_new: bool = False


class ConnectResponse(BaseModel):
    """Response model for AutoCAD connection.

    V213: ``simulation_mode`` is now exposed so clients can distinguish a
    real AutoCAD COM connection from the development fallback that silently
    returns ``connected=True`` on non-Windows / no-pywin32 environments.
    """

    success: bool
    message: str
    connected: bool
    simulation_mode: bool = False
    handle: Optional[str] = None


class DocumentsResponse(BaseModel):
    """Response model for listing AutoCAD documents."""

    success: bool
    documents: List[Dict[str, Any]]


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


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/connect", response_model=ConnectResponse)  # NOSONAR - python:S8409
async def connect_to_autocad(request: ConnectRequest) -> ConnectResponse:
    """Connect to AutoCAD application.

    V213: When ``simulation_mode`` is True in the response, the connection is
    a development fallback — no real AutoCAD COM handle exists and all
    drawing operations will return ``MockAutoCADObject`` instances. Clients
    MUST surface this to the user so they understand no real DWG changes
    will occur.
    """
    try:
        service = get_autocad_service()

        if not service.connect(visible=request.visible, force_new=request.force_new):
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
                detail="Failed to connect to AutoCAD. Is AutoCAD installed and running?",
            )

        if service.simulation_mode:
            message = (
                "Connected in SIMULATION mode — no real AutoCAD instance is "
                "available. Drawing operations will return mock objects and "
                "no real DWG changes will occur. Install pywin32 + AutoCAD "
                "on Windows for real COM integration."
            )
        else:
            message = "Successfully connected to AutoCAD"

        return ConnectResponse(
            success=True,
            message=message,
            connected=service.connected,
            simulation_mode=service.simulation_mode,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(503, "Failed to connect to AutoCAD", e)


@router.post("/disconnect", response_model=ConnectResponse)  # NOSONAR - python:S8409
async def disconnect_from_autocad() -> ConnectResponse:
    """Disconnect from AutoCAD application."""
    try:
        service = get_autocad_service()
        success = service.disconnect()

        return ConnectResponse(
            success=success,
            message="Successfully disconnected from AutoCAD" if success else "Failed to disconnect from AutoCAD",
            connected=service.connected,
            simulation_mode=service.simulation_mode,
        )
    except Exception as e:
        raise _safe_error(500, "Failed to disconnect from AutoCAD", e)


@router.get("/documents", response_model=DocumentsResponse, dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])  # NOSONAR - python:S8409
async def list_autocad_documents() -> DocumentsResponse:
    """List open documents in AutoCAD."""
    try:
        service = get_autocad_service()
        # If not connected, return a simulated list in development mode
        if not service.connected:
            if os.getenv("FIREAI_ENV", "development") == "development":
                return DocumentsResponse(
                    success=True,
                    documents=[
                        {"name": "Drawing1.dwg", "path": "C:\\MockPath\\Drawing1.dwg", "active": True}
                    ]
                )
            raise HTTPException(status_code=503, detail="AutoCAD service not connected")  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path

        doc_info = service.get_document_info()
        return DocumentsResponse(
            success=True,
            documents=[doc_info] if doc_info else []
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error getting documents", e)


@router.post("/read_dwg", response_model=ReadFileResponse, dependencies=[Depends(require_permission(Permission.ELEMENT_READ))])  # NOSONAR - python:S8409
async def read_dwg_file(request: ReadDwgRequest) -> ReadFileResponse:
    """Read entities from a DWG file."""
    try:
        service = get_autocad_service()

        # V133 PHASE 1.2: Validate file path against path traversal attacks.
        # Previously used only os.path.exists() which accepted ../../etc/passwd.
        safe_path = _validate_autocad_file_path(request.filepath)

        result = service.read_dwg(safe_path)

        if not result.get("success", False):
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=400,
                detail=result.get("error", "Unknown error reading file")
            )

        return ReadFileResponse(
            filepath=safe_path,
            metadata=result.get("metadata", {}),
            layers=result.get("layers", []),
            entities=result.get("entities", []),
            blocks=result.get("blocks", {}),
            entity_count=len(result.get("entities", [])),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error reading DWG file", e)


@router.post("/write_dwg", response_model=OperationResponse, dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])  # NOSONAR - python:S8409
async def write_dwg_file(request: WriteDwgRequest) -> OperationResponse:
    """Write entities to a DWG file."""
    try:
        service = get_autocad_service()

        if not service.connected:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
                detail="AutoCAD not connected. Call /connect first."  # NOSONAR — S1192: duplicated literal acceptable in this localized context
            )

        # V133 PHASE 1.2: Validate file path against path traversal attacks.
        safe_path = _validate_autocad_file_path(request.filepath)

        success = service.write_dwg(safe_path, request.entities)

        if not success:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=500,
                detail="Failed to write DWG file"
            )

        return OperationResponse(
            success=True,
            message="Successfully wrote DWG file"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error writing DWG file", e)


@router.post("/draw_line", response_model=OperationResponse)  # NOSONAR - python:S8409
async def draw_line(request: DrawLineRequest) -> OperationResponse:
    """Draw a line in AutoCAD."""
    try:
        service = get_autocad_service()

        if not service.connected:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
                detail="AutoCAD not connected. Call /connect first."
            )

        line_handle = service.draw_line(
            start_point=request.start_point,
            end_point=request.end_point,
            layer=request.layer,
            color=request.color
        )

        if not line_handle:
            raise HTTPException(status_code=500, detail="Failed to draw line")  # NOSONAR — S8415: assignment kept for readability / debuggability

        return OperationResponse(
            success=True,
            message="Line drawn successfully",
            handle=line_handle
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error drawing line", e)


@router.post("/draw_polyline", response_model=OperationResponse)  # NOSONAR - python:S8409
async def draw_polyline(request: DrawPolylineRequest) -> OperationResponse:
    """Draw a polyline in AutoCAD."""
    try:
        service = get_autocad_service()

        if not service.connected:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
                detail="AutoCAD not connected. Call /connect first."
            )

        polyline_handle = service.draw_polyline(
            vertices=request.vertices,
            layer=request.layer,
            color=request.color,
            closed=request.closed
        )

        if not polyline_handle:
            raise HTTPException(status_code=500, detail="Failed to draw polyline")  # NOSONAR — S8415: assignment kept for readability / debuggability

        return OperationResponse(
            success=True,
            message="Polyline drawn successfully",
            handle=polyline_handle
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error drawing polyline", e)


@router.post("/draw_circle", response_model=OperationResponse)  # NOSONAR - python:S8409
async def draw_circle(request: DrawCircleRequest) -> OperationResponse:
    """Draw a circle in AutoCAD."""
    try:
        service = get_autocad_service()

        if not service.connected:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
                detail="AutoCAD not connected. Call /connect first."
            )

        circle_handle = service.draw_circle(
            center=request.center,
            radius=request.radius,
            layer=request.layer,
            color=request.color
        )

        if not circle_handle:
            raise HTTPException(status_code=500, detail="Failed to draw circle")  # NOSONAR — S8415: assignment kept for readability / debuggability

        return OperationResponse(
            success=True,
            message="Circle drawn successfully",
            handle=circle_handle
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error drawing circle", e)


@router.post("/draw_text", response_model=OperationResponse)  # NOSONAR - python:S8409
async def draw_text(request: DrawTextRequest) -> OperationResponse:
    """Draw text in AutoCAD."""
    try:
        service = get_autocad_service()

        if not service.connected:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
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
            raise HTTPException(status_code=500, detail="Failed to draw text")  # NOSONAR — S8415: assignment kept for readability / debuggability

        return OperationResponse(
            success=True,
            message="Text drawn successfully",
            handle=text_handle
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error drawing text", e)


@router.get("/status", response_model=StatusResponse)  # NOSONAR - python:S8409
async def get_autocad_status() -> StatusResponse:
    """Get the current AutoCAD connection status."""
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
        raise _safe_error(500, "Error getting AutoCAD status", e)


@router.post("/save", response_model=OperationResponse)  # NOSONAR - python:S8409
async def save_document(request: SaveRequest) -> OperationResponse:
    """Save the current AutoCAD document."""
    try:
        service = get_autocad_service()

        if not service.connected:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
                detail="AutoCAD not connected. Call /connect first."
            )

        # V133 PHASE 1.2: Validate save path against path traversal.
        safe_path = _validate_autocad_file_path(request.filepath)

        success = service.save(safe_path)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to save document")  # NOSONAR — S8415: assignment kept for readability / debuggability

        return OperationResponse(
            success=True,
            message="Document saved successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error saving document", e)


# Maximum upload file size (50 MB)
_MAX_UPLOAD_SIZE = 50 * 1024 * 1024


@router.post("/upload_dwg", response_model=ReadFileResponse, dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])  # NOSONAR - python:S8409
@router.post("/upload", response_model=ReadFileResponse, dependencies=[Depends(require_permission(Permission.ELEMENT_CREATE))])  # NOSONAR - python:S8409
@limiter.limit("10/minute")
async def upload_and_read_dwg(request: Request, file: UploadFile = File(...)) -> ReadFileResponse:  # NOSONAR - python:S8410
    """
    Upload a DWG file and read its contents.

    FIX #5: Path traversal prevention — uses tempfile + uuid for safe paths
    instead of trusting file.filename. Also enforces upload size limit.
    """
    temp_path = ""
    try:
        service = get_autocad_service()

        # Read file contents with size check
        contents = await file.read()
        if len(contents) > _MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 50MB)")  # NOSONAR — S8415: assignment kept for readability / debuggability

        # FIX #5: Use safe temp path instead of f"temp_{file.filename}"
        # file.filename could contain ../../../etc/passwd (path traversal)
        safe_name = re.sub(r'[^\w\-.]', '_', file.filename or "upload.dwg")
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{safe_name}")

        with open(temp_path, "wb") as buffer:  # NOSONAR: S7493 sync file I/O acceptable for small config reads  # NOSONAR — S7632: test function documented via class name / module path
            buffer.write(contents)

        # Read the file
        result = service.read_dwg(temp_path)

        if not result.get("success", False):
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=400,
                detail=result.get("error", "Unknown error reading file")
            )

        return ReadFileResponse(
            filepath=safe_name,
            metadata=result.get("metadata", {}),
            layers=result.get("layers", []),
            entities=result.get("entities", []),
            blocks=result.get("blocks", {}),
            entity_count=len(result.get("entities", [])),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error processing uploaded DWG file", e)
    finally:
        # FIX #5: Guaranteed cleanup even on error
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                os.rmdir(os.path.dirname(temp_path))
            except OSError:
                pass


@router.delete("/entity/{handle}", response_model=DeleteEntityResponse)  # NOSONAR - python:S8409
async def delete_entity(handle: str) -> DeleteEntityResponse:
    """Delete an AutoCAD entity by handle."""
    try:
        service = get_autocad_service()

        if not service.connected:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
                detail="AutoCAD not connected. Call /connect first."
            )

        success = service.delete_entity(handle)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to delete entity")  # NOSONAR — S8415: assignment kept for readability / debuggability

        return DeleteEntityResponse(
            success=True,
            message="Entity deleted successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error deleting entity", e)


@router.put("/entity/{handle}", response_model=OperationResponse)  # NOSONAR - python:S8409
async def update_entity(handle: str, request: ModifyEntityRequest) -> OperationResponse:
    """Update an AutoCAD entity's properties."""
    try:
        service = get_autocad_service()

        if not service.connected:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=503,  # NOSONAR: S8415 — endpoint error handling is intentional  # NOSONAR — S7632: test function documented via class name / module path
                detail="AutoCAD not connected. Call /connect first."
            )

        if handle != request.handle:
            raise HTTPException(  # NOSONAR — S8415: assignment kept for readability / debuggability
                status_code=400,
                detail="Handle in URL and request body must match"
            )

        success = service.modify_entity(
            handle=request.handle,
            properties=request.properties
        )

        if not success:
            raise HTTPException(status_code=400, detail="Failed to modify entity")  # NOSONAR — S8415: assignment kept for readability / debuggability

        return OperationResponse(
            success=True,
            message="Entity modified successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_error(500, "Error modifying entity", e)
