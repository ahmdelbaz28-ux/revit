"""
FireAI Digital Twin - Pydantic V2 API Schemas
=============================================
Maps to core/models.py dataclasses for REST API request/response validation.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# INPUT NORMALIZATION HELPER (Arabic-mistype → English QWERTY recovery)
# ════════════════════════════════════════════════════════════════════════════
#
# When a user types English text with their OS keyboard layout set to
# Arabic, every keystroke produces an Arabic glyph instead of the
# intended Latin one. This helper recovers the intended English text.
#
# OFF by default (per agent.md "Safety > Convenience"). Enabled when
# FIREAI_INPUT_NORMALIZATION_ENABLED=true. See fireai/core/input_normalizer.py
# for the full pipeline and fireai/env_config.py for the config flag.
#
# Sensitive fields (password, api_key, imo_number, etc.) are NEVER
# normalized — see DENYLIST_FIELD_NAMES in fireai/core/input_normalizer.py.

_NORMALIZER_CONFIG_CACHE: Optional[bool] = None


def _is_input_normalization_enabled() -> bool:
    """Read the input-normalization config flag (cached at first call).

    The config object is created at fireai.env_config module import
    time, so we import lazily here to avoid circular imports during
    backend startup.
    """
    global _NORMALIZER_CONFIG_CACHE
    if _NORMALIZER_CONFIG_CACHE is not None:
        return _NORMALIZER_CONFIG_CACHE
    try:
        from fireai.env_config import config
        _NORMALIZER_CONFIG_CACHE = config.input_normalization_enabled
    except Exception:  # noqa: BLE001
        # If config fails to load, NEVER normalize (safety default).
        _NORMALIZER_CONFIG_CACHE = False
    return _NORMALIZER_CONFIG_CACHE


def _normalize_free_text_field(value: Optional[str], field_name: str) -> Optional[str]:
    """Apply input normalization to a free-text field, gated by config.

    Called by Pydantic field_validators on free-text fields like
    ``name``, ``description``, ``material``, ``fire_rating``, etc.

    Safety:
      - Returns ``value`` unchanged if:
        * value is None or not a string
        * the config flag is OFF
        * the field name is in DENYLIST_FIELD_NAMES (defensive — these
          fields should not have a validator calling this helper at
          all, but we double-check)
      - Otherwise, calls ``normalize_user_text(value, context="free_text")``
        and returns the ``normalized`` text. Logs the transform at INFO
        level for audit trail.

    Args:
        value: The raw input value (may be None).
        field_name: The Pydantic field name (e.g. "name", "description").

    Returns:
        The normalized text, or the original value if normalization is
        disabled or not applicable.
    """
    if value is None or not isinstance(value, str) or not value:
        return value
    if not _is_input_normalization_enabled():
        return value
    # Defensive: never touch sensitive fields even if a validator is
    # accidentally attached to one.
    try:
        from fireai.core.input_normalizer import (
            is_sensitive_field_name, normalize_user_text,
        )
    except ImportError:
        # If the normalizer module is unavailable (e.g. broken install),
        # fall back to passthrough rather than crash the request.
        return value
    if is_sensitive_field_name(field_name):
        return value
    try:
        result = normalize_user_text(value, context="free_text")
        if result.transform_applied != "none":
            logger.info(
                "pydantic_field_normalized",
                extra={
                    "field": field_name,
                    "transform": result.transform_applied,
                    "confidence": result.confidence,
                    "detected_language": result.detected_language,
                },
            )
        return result.normalized
    except Exception:  # noqa: BLE001
        # Normalization must NEVER break request validation.
        logger.exception("input_normalization_failed", extra={"field": field_name})
        return value


def _validate_json_size_and_depth(
    value: Any, field_name: str, max_bytes: int = 10240, max_depth: int = 5
) -> Any:
    """Validate JSON dict size and nesting depth.

    Prevents denial-of-service via deeply nested or oversized JSON payloads.
    - max_bytes: Maximum serialized JSON size in bytes (default 10KB)
    - max_depth: Maximum nesting depth (default 5)
    """
    import json as _json

    # Check serialized size
    try:
        serialized = _json.dumps(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field_name}: must be JSON-serializable ({e})")

    if len(serialized) > max_bytes:
        raise ValueError(
            f"{field_name}: JSON size ({len(serialized)} bytes) exceeds "
            f"maximum ({max_bytes} bytes)"
        )

    # Check nesting depth
    def _get_depth(obj: Any, current: int = 0) -> int:
        if isinstance(obj, dict):
            if not obj:
                return current
            return max(_get_depth(v, current + 1) for v in obj.values())
        elif isinstance(obj, list):
            if not obj:
                return current
            return max(_get_depth(item, current + 1) for item in obj)
        return current

    depth = _get_depth(value)
    if depth > max_depth:
        raise ValueError(
            f"{field_name}: nesting depth ({depth}) exceeds maximum ({max_depth})"
        )

    return value


# V108 FIX: Add camelCase alias generator so Pydantic schemas serialize
# to camelCase (matching the API contract in backend/contract.py) while
# keeping Python snake_case attribute names internally.
def _to_camel(field_name: str) -> str:
    """Convert snake_case to camelCase for API serialization."""
    components = field_name.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


# V108 FIX: Base model with camelCase serialization.
# All Response schemas serialize to camelCase (e.g., element_id → elementId),
# matching the API contract in backend/contract.py. Create/Update schemas
# also accept camelCase input via populate_by_name=True.
class CamelModel(BaseModel):
    """Base model that serializes snake_case fields as camelCase."""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,  # Accept both snake_case and camelCase input
    )


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
    points: List[Point3DCreate]
    polyline_closed: bool = False


class GeometryResponse(CamelModel):
    points: List[Point3DResponse]
    polyline_closed: bool = False
    area: float = 0.0
    perimeter: float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# SEMANTIC PROPERTIES SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class SemanticPropertiesCreate(BaseModel):
    element_type: ElementType
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    material: Optional[str] = Field(None, max_length=255)
    fire_rating: Optional[str] = Field(None, max_length=255)
    height: Optional[float] = None
    width: Optional[float] = None
    load_bearing: bool = False
    layer: Optional[str] = Field(None, max_length=255)
    revit_category: Optional[str] = Field(None, max_length=255)

    @field_validator("name", "description", "material", "fire_rating", "layer", "revit_category")
    @classmethod
    def normalize_free_text_fields(cls, v, info):
        """Recover Arabic-mistype input to its intended English QWERTY text.

        No-op unless FIREAI_INPUT_NORMALIZATION_ENABLED=true. See the
        docstring of ``_normalize_free_text_field`` for details.
        """
        return _normalize_free_text_field(v, info.field_name)


class SemanticPropertiesUpdate(BaseModel):
    element_type: Optional[ElementType] = None
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    material: Optional[str] = Field(None, max_length=255)
    fire_rating: Optional[str] = Field(None, max_length=255)
    height: Optional[float] = None
    width: Optional[float] = None
    load_bearing: Optional[bool] = None
    layer: Optional[str] = Field(None, max_length=255)
    revit_category: Optional[str] = Field(None, max_length=255)

    @field_validator("name", "description", "material", "fire_rating", "layer", "revit_category")
    @classmethod
    def normalize_free_text_fields(cls, v, info):
        """Recover Arabic-mistype input to its intended English QWERTY text."""
        return _normalize_free_text_field(v, info.field_name)


class SemanticPropertiesResponse(CamelModel):
    element_type: str
    name: str
    description: Optional[str] = None
    material: Optional[str] = None
    fire_rating: Optional[str] = None
    height: Optional[float] = None
    width: Optional[float] = None
    load_bearing: bool = False
    layer: Optional[str] = None
    revit_category: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════
# ELEMENT SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class ElementCreate(BaseModel):
    """Schema for creating a new element."""
    # SECURITY FIX (BUG-35): Changed extra from "allow" to "forbid".
    # In a safety-critical system, extra fields could indicate a client bug
    # or injection attempt. They should be rejected with a 422 error.
    model_config = ConfigDict(extra="forbid")

    element_id: Optional[str] = None
    properties: SemanticPropertiesCreate
    geometry: Optional[GeometryCreate] = None
    source_file: Optional[str] = None
    last_modified_by: Optional[str] = None
    autocad_handle: Optional[str] = None
    revit_element_id: Optional[int] = None
    project_id: Optional[str] = None


class ElementUpdate(BaseModel):
    """Schema for updating an existing element."""
    # SECURITY FIX (BUG-35): Changed extra from "allow" to "forbid".
    model_config = ConfigDict(extra="forbid")

    properties: Optional[SemanticPropertiesUpdate] = None
    geometry: Optional[GeometryCreate] = None
    source_file: Optional[str] = None
    last_modified_by: Optional[str] = None
    is_deleted: Optional[bool] = None


class ElementResponse(CamelModel):
    """Full element response."""
    element_id: str
    properties: Optional[SemanticPropertiesResponse] = None
    geometry: Optional[GeometryResponse] = None
    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    created_timestamp: Optional[str] = None
    last_modified_timestamp: Optional[str] = None
    last_modified_by: Optional[str] = None
    source_file: Optional[str] = None
    version: int = 0
    is_deleted: bool = False
    autocad_handle: Optional[str] = None
    revit_element_id: Optional[int] = None
    project_id: Optional[str] = None


class ElementListResponse(CamelModel):
    """Paginated element list response."""
    items: List[ElementResponse]
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
    description: Optional[str] = None
    status: ProjectStatus = ProjectStatus.DRAFT
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("name", "description")
    @classmethod
    def normalize_free_text_fields(cls, v, info):
        """Recover Arabic-mistype input to its intended English QWERTY text.

        No-op unless FIREAI_INPUT_NORMALIZATION_ENABLED=true.
        """
        return _normalize_free_text_field(v, info.field_name)

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, v):
        """Limit metadata JSON size to 10KB and nesting depth to 5."""
        if v is None:
            return v
        return _validate_json_size_and_depth(v, "metadata", max_bytes=10240, max_depth=5)


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("name", "description")
    @classmethod
    def normalize_free_text_fields(cls, v, info):
        """Recover Arabic-mistype input to its intended English QWERTY text."""
        return _normalize_free_text_field(v, info.field_name)

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
    description: Optional[str] = None
    status: str = "draft"
    metadata: Optional[Dict[str, Any]] = None
    element_count: int = 0
    created_timestamp: Optional[str] = None
    last_modified_timestamp: Optional[str] = None


class ProjectListResponse(CamelModel):
    """Paginated project list response."""
    items: List[ProjectResponse]
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
    position: Optional[Dict[str, float]] = None  # {x, y, z}
    room_id: Optional[str] = None
    project_id: Optional[str] = None
    z_height: float = 2.4
    coverage_radius: float = 6.37
    properties: Optional[SemanticPropertiesCreate] = None
    geometry: Optional[GeometryCreate] = None

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
    position: Optional[Dict[str, float]] = None
    room_id: Optional[str] = None
    project_id: Optional[str] = None
    z_height: float = 2.4
    coverage_radius: float = 6.37
    element_id: str
    created_timestamp: Optional[str] = None
    last_modified_timestamp: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════
# CONNECTION / RELATIONSHIP SCHEMAS
# ════════════════════════════════════════════════════════════════════════════

class ConnectionCreate(BaseModel):
    """Schema for creating a connection (relationship)."""
    from_element_id: str
    to_element_id: str
    relationship_type: str = Field(..., min_length=1, max_length=255)
    is_parametric: bool = False
    metadata: Optional[Dict[str, Any]] = None

    @field_validator("to_element_id")
    @classmethod
    def validate_different_endpoints(cls, v: str, info) -> str:
        """A connection must connect two different elements.

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
    metadata: Optional[Dict[str, Any]] = None


class ConnectionListResponse(CamelModel):
    """Paginated connection list response."""
    items: List[ConnectionResponse]
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
    resolution: Optional[Dict[str, Any]] = None


class ConflictResponse(CamelModel):
    """Conflict response."""
    conflict_id: str
    element_id: str = ""
    conflict_type: str
    timestamp: Optional[str] = None
    source_a: Optional[str] = None
    source_b: Optional[str] = None
    change_a: Optional[Dict[str, Any]] = None
    change_b: Optional[Dict[str, Any]] = None
    resolution: Optional[Dict[str, Any]] = None
    resolved: bool = False


class ConflictListResponse(CamelModel):
    """Paginated conflict list response."""
    items: List[ConflictResponse]
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
    last_sync: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════════
# UNIVERSAL RESPONSE WRAPPER
# ════════════════════════════════════════════════════════════════════════════

T = TypeVar("T")


class ApiResponse(CamelModel, Generic[T]):
    """Universal response wrapper for all API endpoints."""
    success: bool
    data: Optional[T] = None
    message: Optional[str] = None


class PaginatedData(CamelModel, Generic[T]):
    """Wrapper for paginated data inside ApiResponse."""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class ExportRequest(BaseModel):
    """Request body for data export."""
    project_id: Optional[str] = None
    element_types: Optional[List[str]] = None
    include_deleted: bool = False
    format: str = "json"


class ConnectionUpdate(BaseModel):
    """Schema for updating an existing connection."""
    cable_size: Optional[str] = Field(None, max_length=255)
    length: Optional[float] = Field(None, ge=0)
    type: Optional[str] = Field(None, max_length=255)
