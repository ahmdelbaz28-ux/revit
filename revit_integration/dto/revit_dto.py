"""
ETAP-AI-WORK Revit Integration DTOs
===================================

Data Transfer Objects for Revit integration.
Defines standardized contracts between Revit and ETAP systems.

Principal Software Architect: Eng. Ahmed Elbaz
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class RevitElementDTO(BaseModel):
    """
    Data Transfer Object for Revit elements.
    Represents individual elements from Revit models.
    """
    id: str = Field(..., description="Unique identifier for the element")
    name: str = Field(..., description="Display name of the element")
    category: str = Field(..., description="Revit category of the element")
    family: str = Field("", description="Family name of the element")
    type: str = Field("", description="Type name of the element")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Element parameters")
    location: Optional[Dict[str, float]] = Field(None, description="XYZ coordinates of the element")
    geometry: Optional[Dict[str, Any]] = Field(None, description="Geometric representation")
    level: Optional[str] = Field(None, description="Building level/phase")
    workset: Optional[str] = Field(None, description="Workset assignment")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class ElectricalAssetDTO(BaseModel):
    """
    Data Transfer Object for electrical assets extracted from Revit.
    Maps Revit electrical elements to ETAP electrical model.
    """
    element_id: str = Field(..., description="Original Revit element ID")
    asset_type: str = Field(..., description="Type of electrical asset")
    name: str = Field(..., description="Asset name")
    voltage_rating: Optional[float] = Field(None, description="Voltage rating in volts")
    power_rating: Optional[float] = Field(None, description="Power rating in watts/kVA")
    manufacturer: Optional[str] = Field(None, description="Manufacturer name")
    model: Optional[str] = Field(None, description="Model number")
    serial_number: Optional[str] = Field(None, description="Serial number")
    capacity: Optional[float] = Field(None, description="Capacity rating")
    connections: List[str] = Field(default_factory=list, description="Connected element IDs")
    location_coordinates: Optional[Dict[str, float]] = Field(None, description="GIS coordinates")
    electrical_parameters: Dict[str, Any] = Field(default_factory=dict, description="Electrical parameters")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")


class SyncStatusDTO(BaseModel):
    """
    Data Transfer Object for synchronization status.
    Tracks the progress and outcome of sync operations.
    """
    sync_id: str = Field(..., description="Unique sync operation ID")
    project_id: str = Field(..., description="Associated project ID")
    status: str = Field(..., description="Current sync status")
    progress: float = Field(0.0, description="Progress percentage (0.0-100.0)")
    total_elements: int = Field(0, description="Total elements to sync")
    processed_elements: int = Field(0, description="Elements processed")
    successful_elements: int = Field(0, description="Successfully synced elements")
    failed_elements: int = Field(0, description="Failed elements count")
    start_time: datetime = Field(default_factory=datetime.utcnow, description="Sync start time")
    end_time: Optional[datetime] = Field(None, description="Sync completion time")
    error_details: Optional[Dict[str, str]] = Field(None, description="Error details if any")
    message: Optional[str] = Field(None, description="Status message")


class ModelMetadataDTO(BaseModel):
    """
    Data Transfer Object for Revit model metadata.
    Contains information about the model structure and properties.
    """
    model_id: str = Field(..., description="Unique model identifier")
    project_name: str = Field(..., description="Project name from Revit")
    project_number: Optional[str] = Field(None, description="Project number")
    revit_version: str = Field(..., description="Revit version used")
    model_units: str = Field(..., description="Model units (metric/imperial)")
    total_elements: int = Field(0, description="Total number of elements in model")
    electrical_elements: int = Field(0, description="Number of electrical elements")
    geometry_elements: int = Field(0, description="Number of geometry elements")
    file_size: int = Field(0, description="Model file size in bytes")
    created_date: Optional[datetime] = Field(None, description="Model creation date")
    modified_date: Optional[datetime] = Field(None, description="Model last modified date")
    author: Optional[str] = Field(None, description="Model author")
    organization: Optional[str] = Field(None, description="Organization name")
    description: Optional[str] = Field(None, description="Model description")
    geographic_location: Optional[Dict[str, float]] = Field(None, description="Geographic coordinates")


class RevitProjectDTO(BaseModel):
    """
    Data Transfer Object for Revit project management.
    Manages project lifecycle within the ETAP integration.
    """
    project_id: str = Field(..., description="Unique project identifier")
    project_name: str = Field(..., description="Project name")
    revit_file_path: Optional[str] = Field(None, description="Path to Revit file")
    aps_project_id: Optional[str] = Field(None, description="APS project identifier")
    sync_enabled: bool = Field(True, description="Whether auto-sync is enabled")
    last_sync: Optional[datetime] = Field(None, description="Last sync timestamp")
    next_sync: Optional[datetime] = Field(None, description="Next scheduled sync")
    sync_interval: int = Field(3600, description="Sync interval in seconds")
    status: str = Field("active", description="Project status")
    owner: Optional[str] = Field(None, description="Project owner")
    permissions: Dict[str, bool] = Field(default_factory=dict, description="User permissions")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Project creation time")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Project update time")


class RevitSyncLogDTO(BaseModel):
    """
    Data Transfer Object for Revit synchronization logs.
    Records all sync operations for audit and troubleshooting.
    """
    log_id: str = Field(..., description="Unique log entry identifier")
    sync_id: str = Field(..., description="Associated sync operation ID")
    project_id: str = Field(..., description="Associated project ID")
    operation_type: str = Field(..., description="Type of sync operation")
    element_id: Optional[str] = Field(None, description="Affected element ID")
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Log message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Log timestamp")
    duration_ms: Optional[int] = Field(None, description="Operation duration in milliseconds")
    user_id: Optional[str] = Field(None, description="User who initiated sync")
    client_ip: Optional[str] = Field(None, description="Client IP address")