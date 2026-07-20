# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions are preserved.
"""
backend/integrations/etap_schemas.py — Pydantic schemas for ETAP integration.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class EtapConnectionSettings(BaseModel):
    """Connection settings for ETAP server."""

    host: str = Field(..., min_length=1, max_length=255, description="ETAP server hostname or IP")
    port: int = Field(..., ge=1, le=65535, description="ETAP server port")
    username: str = Field(..., min_length=1, max_length=255, description="ETAP username")
    password: str = Field(..., min_length=1, max_length=255, description="ETAP password (plaintext in transit, encrypted at rest)")
    timeout_seconds: int = Field(30, ge=5, le=300, description="Connection timeout in seconds")

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Host cannot be empty")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Username cannot be empty")
        return v


class EtapConnectionTestResponse(BaseModel):
    """Response from testing ETAP connection."""

    success: bool
    message: str
    latency_ms: Optional[int] = None
    server_version: Optional[str] = None


class EtapProjectInfo(BaseModel):
    """ETAP project metadata."""

    project_id: str
    name: str
    modified_at: Optional[datetime] = None
    size_mb: Optional[float] = None
    is_remote: bool = True


class EtapExportRequest(BaseModel):
    """Request to export data to ETAP."""

    project_id: str = Field(..., description="Local project ID")
    include_loads: bool = Field(True, description="Include fire-system loads")
    include_sources: bool = Field(True, description="Include power sources")
    include_topology: bool = Field(False, description="Include network topology")
    format: str = Field("csv", pattern="^(csv|ort)$", description="Export format")


class EtapImportRequest(BaseModel):
    """Request to import data from ETAP."""

    project_id: str = Field(..., description="Local project ID")
    etap_project_id: str = Field(..., description="ETAP project ID")
    import_loads: bool = Field(True, description="Import load data")
    import_sources: bool = Field(True, description="Import source data")
    conflict_resolution: str = Field("skip", pattern="^(skip|overwrite|merge)$", description="How to handle conflicts")


class EtapSyncLog(BaseModel):
    """Sync operation log entry."""

    id: str
    direction: str  # 'export' | 'import'
    status: str  # 'success' | 'error' | 'partial'
    records_synced: int
    error_message: Optional[str] = None
    created_at: datetime


class EtapSyncLogResponse(BaseModel):
    """Paginated sync logs response."""

    items: List[EtapSyncLog]
    total: int
    page: int
    page_size: int


class EtapSettingsResponse(BaseModel):
    """ETAP integration settings (safe for API response — no secrets)."""

    id: str
    project_id: str
    host: str
    port: int
    username: str
    enabled: bool
    last_sync: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class EtapSettingsUpdate(BaseModel):
    """Update ETAP settings (password is optional — only update if provided)."""

    host: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = Field(None, min_length=1, max_length=255)
    password: Optional[str] = Field(None, min_length=1, max_length=255)
    timeout_seconds: Optional[int] = Field(None, ge=5, le=300)
    enabled: Optional[bool] = None

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Host cannot be empty")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Username cannot be empty")
        return v
