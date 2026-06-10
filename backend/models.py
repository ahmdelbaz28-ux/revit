"""
backend/models.py — Pydantic V2 models for the Digital Twin REST API.

These models match the frontend TypeScript interfaces defined in
frontend/src/services/digitalTwinApi.ts exactly.

LIFE-SAFETY NOTE: All numerical fields use strict validation to prevent
silent data corruption that could lead to incorrect engineering calculations.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Pagination
# ============================================================================

class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints."""
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page")
    sort: str = Field(default="createdAt", description="Sort field")
    order: Literal["asc", "desc"] = Field(default="desc", description="Sort order")


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""
    data: list
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    limit: int = Field(ge=1)
    totalPages: int = Field(ge=0)


# ============================================================================
# Projects
# ============================================================================

class Project(BaseModel):
    """A fire alarm engineering project."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)  # V113: max_length prevents DoS via unbounded string
    author: str = Field(default="", max_length=255)  # V113: max_length prevents memory exhaustion
    createdAt: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updatedAt: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: Literal["active", "archived", "draft"] = Field(default="draft")
    deviceCount: int = Field(default=0, ge=0)
    connectionCount: int = Field(default=0, ge=0)


class CreateProjectInput(BaseModel):
    """Input for creating a new project."""
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5000)  # V113: max_length prevents 100MB body DoS
    author: str = Field(default="", max_length=255)  # V113: max_length prevents memory exhaustion


class UpdateProjectInput(BaseModel):
    """Input for updating an existing project."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)  # V113: max_length prevents DoS
    author: Optional[str] = Field(default=None, max_length=255)  # V113: max_length prevents DoS
    status: Optional[Literal["active", "archived", "draft"]] = Field(default=None)


# ============================================================================
# Devices
# ============================================================================

class Device(BaseModel):
    """A fire alarm device within a project."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    projectId: str
    type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    x: float
    y: float
    z: float = Field(default=0.0)
    rotation: float = Field(default=0.0)
    voltage: float = Field(default=0.0)
    current: float = Field(default=0.0)
    load: float = Field(default=0.0)
    properties: dict = Field(default_factory=dict)
    createdAt: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updatedAt: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("voltage", "current", "load")
    @classmethod
    def validate_non_negative(cls, v: float) -> float:
        """Electrical values must be non-negative for safety."""
        if v < 0:
            raise ValueError("Value must be non-negative")
        return v


class CreateDeviceInput(BaseModel):
    """Input for creating a new device."""
    type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    x: float
    y: float
    z: Optional[float] = Field(default=0.0)
    rotation: Optional[float] = Field(default=0.0)
    voltage: Optional[float] = Field(default=0.0, ge=0)
    current: Optional[float] = Field(default=0.0, ge=0)
    load: Optional[float] = Field(default=0.0, ge=0)
    load_unit: Literal["A", "mA", "W"] = Field(
        default="A",
        description=(
            "Unit for the load field. NFPA 72 battery calculations require "
            "Amperes (A). If mA or W provided, conversion is applied. "
            "This field prevents silent wrong-unit errors in life-safety "
            "battery sizing calculations."
        ),
    )
    properties: Optional[dict] = Field(default=None)

    @field_validator("load")
    @classmethod
    def validate_load_finite(cls, v: float) -> float:
        """Load must be a finite number (not inf or nan)."""
        import math
        if v and (math.isinf(v) or math.isnan(v)):
            raise ValueError("Load must be a finite number")
        return v


class UpdateDeviceInput(BaseModel):
    """Input for updating an existing device.

    SAFETY NOTE: load_unit is required when updating the load field to prevent
    silent wrong-unit errors. NFPA 72 battery calculations require Amperes.
    If mA or W is provided, the router converts to Amperes before storage.
    Without this field, updating load: 500 intending 500mA would store 500A —
    a 1000x error in life-safety battery sizing calculations.
    """
    name: Optional[str] = Field(default=None, min_length=1)
    x: Optional[float] = Field(default=None)
    y: Optional[float] = Field(default=None)
    z: Optional[float] = Field(default=None)
    rotation: Optional[float] = Field(default=None)
    voltage: Optional[float] = Field(default=None, ge=0)
    current: Optional[float] = Field(default=None, ge=0)
    load: Optional[float] = Field(default=None, ge=0)
    load_unit: Literal["A", "mA", "W"] = Field(
        default="A",
        description=(
            "Unit for the load field when updating. Defaults to Amperes (A). "
            "Must match the unit of the load value being set."
        ),
    )
    properties: Optional[dict] = Field(default=None)


# ============================================================================
# Connections
# ============================================================================

class Connection(BaseModel):
    """A cable connection between two devices."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    projectId: str
    fromId: str
    toId: str
    cableSize: str = Field(default="1.5mm²")
    length: float = Field(default=0.0, ge=0)
    type: str = Field(default="power")
    createdAt: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class CreateConnectionInput(BaseModel):
    """Input for creating a new connection."""
    fromId: str = Field(min_length=1)
    toId: str = Field(min_length=1)
    cableSize: Optional[str] = Field(default="1.5mm²")
    length: Optional[float] = Field(default=0.0, ge=0)
    type: Optional[str] = Field(default="power")

    @field_validator("toId")
    @classmethod
    def validate_different_endpoints(cls, v: str, info) -> str:
        """A connection must connect two different devices.

        A self-connection is meaningless in fire alarm wiring and
        could indicate a data entry error.
        """
        from_id = info.data.get("fromId")
        if from_id and v == from_id:
            raise ValueError("toId must be different from fromId — self-connections are not allowed")
        return v


class DeleteConnectionResponse(BaseModel):
    """Response for connection deletion."""
    success: bool
    message: str = ""


# ============================================================================
# Reports
# ============================================================================

class Report(BaseModel):
    """An engineering report for a project."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    projectId: str
    type: str = Field(min_length=1)
    name: str = Field(default="")
    parameters: dict = Field(default_factory=dict)
    status: Literal["pending", "completed", "failed"] = Field(default="pending")
    createdAt: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completedAt: Optional[str] = Field(default=None)


class GenerateReportInput(BaseModel):
    """Input for generating a new report."""
    type: str = Field(min_length=1)
    name: Optional[str] = Field(default=None)
    parameters: Optional[dict] = Field(default=None)


# ============================================================================
# Sync
# ============================================================================

class SyncStatus(BaseModel):
    """Status of project synchronization."""
    projectId: str
    status: Literal["syncing", "synced", "error"]
    lastSync: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    pendingChanges: int = Field(default=0, ge=0)
    error: Optional[str] = Field(default=None)


# ============================================================================
# Health
# ============================================================================

class HealthStatus(BaseModel):
    """Health check response."""
    status: Literal["ok", "degraded", "error"]
    version: str = Field(default="1.0.0")
    uptime: float = Field(default=0.0, ge=0)
    database: Literal["connected", "disconnected"]
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ============================================================================
# API Response — DELETED: Use backend.schemas.ApiResponse[T] instead.
# This non-generic version was causing type conflicts with the generic
# ApiResponse[T] in schemas.py. All routers must import from schemas.py.
# ============================================================================
