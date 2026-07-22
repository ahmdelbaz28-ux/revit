"""
FireAI Digital Twin - Pydantic V2 API Schemas.
=============================================
Maps to core/models.py dataclasses for REST API request/response validation.

V300: Shared base utilities (CamelModel, _to_camel, _validate_json_size_and_depth)
now live in backend/schema_base.py to eliminate duplication with backend/models.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schema_base import (
    CamelModel,
    _validate_json_size_and_depth,
)

# ============================================================================
# JSON size/depth validation
# ============================================================================

# to camelCase (matching the API contract in backend/contract.py) while
# keeping Python snake_case attribute names internally.


# All Response schemas serialize to camelCase (e.g., element_id → elementId),
# matching the API contract in backend/contract.py. Create/Update schemas
# also accept camelCase input via populate_by_name=True.
# (CamelModel, _to_camel, _validate_json_size_and_depth now in schema_base.py)


# ════════════════════════════════════════════════════════════════════════════
# ENUMERATIONS (mirroring core/models.py)
# ════════════════════════════════════════════════════════════════════════════

class ElementType(str, Enum):
    WALL = "wall"
    DOOR = "door"
    WINDOW = "window"
    ROOM = "room"
    EQUIPMENT = "equipment"
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    UNKNOWN = "unknown"


class ChangeSource(str, Enum):
    AUTOCAD = "autocad"
    REVIT = "revit"
    MANUAL = "manual"
    SYSTEM = "system"


class ConflictType(str, Enum):
    GEOMETRY_MISMATCH = "geometry_mismatch"
    PROPERTY_CONFLICT = "property_conflict"
    DELETION_CONFLICT = "deletion_conflict"
    TIMING_CONFLICT = "timing_conflict"


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


# ════════════════════════════════════════════════════════════════════════════
# GEOMETRY SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class Point3DCreate(BaseModel):
    x: float
    y: float
    z: float = 0.0


class Point3DResponse(CamelModel):
    x: float
    y: float
    z: float = 0.0


class GeometryCreate(BaseModel):
    points: list[Point3DCreate]
    polyline_closed: bool = False


class GeometryResponse(CamelModel):
    points: list[Point3DResponse]
    polyline_closed: bool = False
    area: float = 0.0
    perimeter: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# SEMANTIC PROPERTIES SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class SemanticPropertiesCreate(BaseModel):
    element_type: ElementType
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    material: str | None = Field(None, max_length=255)
    fire_rating: str | None = Field(None, max_length=255)
    height: float | None = None
    width: float | None = None
    load_bearing: bool = False
    layer: str | None = Field(None, max_length=255)
    revit_category: str | None = Field(None, max_length=255)


class SemanticPropertiesUpdate(BaseModel):
    element_type: ElementType | None = None
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    material: str | None = Field(None, max_length=255)
    fire_rating: str | None = Field(None, max_length=255)
    height: float | None = None
    width: float | None = None
    load_bearing: bool | None = None
    layer: str | None = Field(None, max_length=255)
    revit_category: str | None = Field(None, max_length=255)


class SemanticPropertiesResponse(CamelModel):
    element_type: str
    name: str
    description: str | None = None
    material: str | None = None
    fire_rating: str | None = None
    height: float | None = None
    width: float | None = None
    load_bearing: bool = False
    layer: str | None = None
    revit_category: str | None = None


# ════════════════════════════════════════════════════════════════════════════
# ELEMENT SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class ElementCreate(BaseModel):
    """Schema for creating a new element."""

    # SECURITY FIX (BUG-35): Changed extra from "allow" to "forbid".
    # In a safety-critical system, extra fields could indicate a client bug
    # or injection attempt. They should be rejected with a 422 error.
    model_config = ConfigDict(extra="forbid")

    element_id: str | None = None
    properties: SemanticPropertiesCreate
    geometry: GeometryCreate | None = None
    source_file: str | None = None
    last_modified_by: str | None = None
    autocad_handle: str | None = None
    revit_element_id: int | None = None
    project_id: str | None = None


class ElementUpdate(BaseModel):
    """Schema for updating an existing element."""

    # SECURITY FIX (BUG-35): Changed extra from "allow" to "forbid".
    model_config = ConfigDict(extra="forbid")

    properties: SemanticPropertiesUpdate | None = None
    geometry: GeometryCreate | None = None
    source_file: str | None = None
    last_modified_by: str | None = None
    is_deleted: bool | None = None


class ElementResponse(CamelModel):
    """Full element response."""

    element_id: str
    properties: SemanticPropertiesResponse | None = None
    geometry: GeometryResponse | None = None
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    created_timestamp: str | None = None
    last_modified_timestamp: str | None = None
    last_modified_by: str | None = None
    source_file: str | None = None
    version: int = 0
    is_deleted: bool = False
    autocad_handle: str | None = None
    revit_element_id: int | None = None
    project_id: str | None = None


class ElementListResponse(CamelModel):
    """Paginated element list response."""

    items: list[ElementResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ════════════════════════════════════════════════════════════════════════════
# PROJECT SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    status: ProjectStatus = ProjectStatus.DRAFT
    metadata: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v):
        """V140 FIX: Strip null bytes and control characters from name."""
        if v is None:
            return v
        # Remove null bytes (C string truncation attack)
        v = v.replace("\x00", "")
        # Remove other control chars except newline/tab
        v = "".join(c for c in v if c == "\n" or c == "\t" or ord(c) >= 32)
        if not v.strip():
            raise ValueError("name must not be empty after sanitization")
        return v

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v):
        """V140 FIX: Strip null bytes from description."""
        if v is None:
            return v
        return v.replace("\x00", "")

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v):
        """Limit metadata JSON size to 10KB and nesting depth to 5."""
        if v is None:
            return v
        return _validate_json_size_and_depth(v, "metadata", max_bytes=10240, max_depth=5)


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: ProjectStatus | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v):
        """Limit metadata JSON size to 10KB and nesting depth to 5."""
        if v is None:
            return v
        return _validate_json_size_and_depth(v, "metadata", max_bytes=10240, max_depth=5)


class ProjectResponse(CamelModel):
    """Full project response."""

    project_id: str
    name: str
    description: str | None = None
    status: str = "draft"
    metadata: dict[str, Any] | None = None
    element_count: int = 0
    created_timestamp: str | None = None
    last_modified_timestamp: str | None = None


class ProjectListResponse(CamelModel):
    """Paginated project list response."""

    items: list[ProjectResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ════════════════════════════════════════════════════════════════════════════
# DEVICE SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class DeviceCreate(BaseModel):
    """Schema for creating a device (element with electrical/equipment type)."""

    device_type: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    position: dict[str, float] | None = None  # {x, y, z}
    room_id: str | None = None
    project_id: str | None = None
    z_height: float = 2.4
    coverage_radius: float = 6.37
    properties: SemanticPropertiesCreate | None = None
    geometry: GeometryCreate | None = None

    @field_validator("properties")
    @classmethod
    def validate_properties_size(cls, v):
        """Limit properties JSON size to 10KB and nesting depth to 5."""
        if v is None:
            return v
        # Validate the serialized size of the properties dict
        raw = v.model_dump() if hasattr(v, 'model_dump') else v
        _validate_json_size_and_depth(raw, "properties", max_bytes=10240, max_depth=5)
        return v


class DeviceResponse(CamelModel):
    """Device response."""

    device_id: str
    device_type: str
    name: str
    position: dict[str, float] | None = None
    room_id: str | None = None
    project_id: str | None = None
    z_height: float = 2.4
    coverage_radius: float = 6.37
    element_id: str
    created_timestamp: str | None = None
    last_modified_timestamp: str | None = None


# ════════════════════════════════════════════════════════════════════════════
# CONNECTION / RELATIONSHIP SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class ConnectionCreate(BaseModel):
    """Schema for creating a connection (relationship)."""

    from_element_id: str
    to_element_id: str
    relationship_type: str = Field(..., min_length=1, max_length=255)
    is_parametric: bool = False
    metadata: dict[str, Any] | None = None

    @field_validator("to_element_id")
    @classmethod
    def validate_different_endpoints(cls, v: str, info) -> str:
        """
        A connection must connect two different elements.

        A self-connection is meaningless in fire alarm wiring and
        could indicate a data entry error. This mirrors the same
        validation in backend/models.py CreateConnectionInput.
        """
        from_id = info.data.get("from_element_id")
        if from_id and v == from_id:
            raise ValueError("to_element_id must be different from from_element_id — self-connections are not allowed")
        return v


class ConnectionResponse(CamelModel):
    """Connection response."""

    connection_id: str
    from_element_id: str
    to_element_id: str
    relationship_type: str
    is_parametric: bool = False
    metadata: dict[str, Any] | None = None


class ConnectionListResponse(CamelModel):
    """Paginated connection list response."""

    items: list[ConnectionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ════════════════════════════════════════════════════════════════════════════
# CONFLICT SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class ConflictResolveRequest(BaseModel):
    """Schema for resolving a conflict."""

    strategy: str = Field(default="SEMANTIC_MERGE", pattern="^(LAST_WRITE_WINS|SEMANTIC_MERGE)$")
    resolution: dict[str, Any] | None = None


class ConflictResponse(CamelModel):
    """Conflict response."""

    conflict_id: str
    element_id: str = ""
    conflict_type: str
    timestamp: str | None = None
    source_a: str | None = None
    source_b: str | None = None
    change_a: dict[str, Any] | None = None
    change_b: dict[str, Any] | None = None
    resolution: dict[str, Any] | None = None
    resolved: bool = False


class ConflictListResponse(CamelModel):
    """Paginated conflict list response."""

    items: list[ConflictResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ════════════════════════════════════════════════════════════════════════════
# STATISTICS SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class StatisticsResponse(CamelModel):
    """Database statistics response."""

    total_elements: int = 0
    deleted_elements: int = 0
    active_elements: int = 0
    total_projects: int = 0
    active_projects: int = 0
    total_connections: int = 0
    total_conflicts: int = 0
    unresolved_conflicts: int = 0
    pending_autocad_to_revit: int = 0
    pending_revit_to_autocad: int = 0
    database_version: int = 0
    last_sync: str | None = None


# ════════════════════════════════════════════════════════════════════════════
# UNIVERSAL RESPONSE WRAPPER
# ════════════════════════════════════════════════════════════════════════════

T = TypeVar("T")


class ApiResponse(CamelModel, Generic[T]):
    """Universal response wrapper for all API endpoints."""

    success: bool
    data: T | None = None
    message: str | None = None


class PaginatedData(CamelModel, Generic[T]):
    """Wrapper for paginated data inside ApiResponse."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class ExportRequest(BaseModel):
    """Request body for data export."""

    project_id: str | None = None
    element_types: list[str] | None = None
    include_deleted: bool = False
    format: str = "json"


class ConnectionUpdate(BaseModel):
    """Schema for updating an existing connection."""

    cable_size: str | None = Field(None, max_length=255)
    length: float | None = Field(None, ge=0)
    type: str | None = Field(None, max_length=255)
