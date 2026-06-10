"""
backend/routers/devices.py — Devices CRUD endpoints.

LIFE-SAFETY NOTE: Devices represent fire alarm components (smoke detectors,
heat detectors, manual pull stations, notification appliances, etc.).
Their electrical parameters (voltage, current, load) are used in
circuit calculations that directly affect life safety.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query

from backend.database import get_db
from backend.models import (
    CreateDeviceInput,
    UpdateDeviceInput,
)
from backend.contract import validate_device, validate_paginated

router = APIRouter(prefix="/projects/{project_id}/devices", tags=["devices"])


def _verify_project(project_id: str) -> None:
    """Ensure the project exists before operating on its devices."""
    db = get_db()
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")


# camelCase → snake_case sort field mapping
_SORT_MAP = {
    "createdAt": "created_at",
    "updatedAt": "updated_at",
    "name": "name",
    "type": "type",
    "category": "category",
    "voltage": "voltage",
    "current": "current",
    "load": "load",
}


def _normalize_sort(sort: str) -> str:
    """Convert camelCase sort fields to snake_case for database.

    SECURITY FIX (BUG-32): Strict whitelist — rejects unknown sort fields.
    """
    return _SORT_MAP.get(sort, "created_at")


@router.get("")
async def list_devices(
    project_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query("createdAt"),
    order: str = Query("desc"),
):
    """List all devices in a project with pagination."""
    _verify_project(project_id)
    db = get_db()
    result = db.list_devices(project_id, page=page, limit=limit, sort=_normalize_sort(sort), order=order)
    validate_paginated(result, item_validator=validate_device)
    return {"success": True, "data": result}


@router.post("", status_code=201)
async def create_device(project_id: str, input_data: CreateDeviceInput):
    """Create a new device in a project.

    LIFE-SAFETY: The `load` field is converted to Amperes (A) before storage
    because NFPA 72 battery calculations in reports.py assume Amperes.
    If load_unit is "mA", load is divided by 1000.
    If load_unit is "W", load is divided by voltage (requires voltage > 0).
    The original unit and raw value are stored in properties for traceability.
    """
    _verify_project(project_id)
    db = get_db()

    # ── Unit conversion for life-safety ──────────────────────────────────
    raw_load = input_data.load if input_data.load is not None else 0.0
    load_unit = input_data.load_unit
    load_amperes = raw_load  # Default: already in Amperes

    if load_unit == "mA" and raw_load != 0.0:
        load_amperes = raw_load / 1000.0
    elif load_unit == "W" and raw_load != 0.0:
        voltage = input_data.voltage if input_data.voltage is not None else 0.0
        if voltage <= 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot convert Watts to Amperes: voltage must be > 0. "
                       "Provide voltage in Volts or specify load_unit as 'A'.",
            )
        load_amperes = raw_load / voltage

    # Store original unit info in properties for traceability and auditing
    properties = input_data.properties or {}
    if raw_load != 0.0 and load_unit != "A":
        properties["load_original_value"] = raw_load
        properties["load_original_unit"] = load_unit

    device_data = {
        "id": str(uuid.uuid4()),
        "type": input_data.type,
        "name": input_data.name,
        "category": input_data.category,
        "x": input_data.x,
        "y": input_data.y,
        "z": input_data.z if input_data.z is not None else 0.0,
        "rotation": input_data.rotation if input_data.rotation is not None else 0.0,
        "voltage": input_data.voltage if input_data.voltage is not None else 0.0,
        "current": input_data.current if input_data.current is not None else 0.0,
        "load": load_amperes,  # Always stored in Amperes for NFPA 72 calculations
        "properties": properties,
    }
    device = db.create_device(project_id, device_data)
    validate_device(device)

    # Sync device to UDM for conflict detection
    from backend.project_bridge import sync_device_to_udm
    sync_device_to_udm(project_id, device_data)

    return {"data": device, "success": True}


@router.get("/{device_id}")
async def get_device(project_id: str, device_id: str):
    """Get a device by ID within a project."""
    _verify_project(project_id)
    db = get_db()
    device = db.get_device(project_id, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    validate_device(device)
    return {"data": device, "success": True}


@router.put("/{device_id}")
async def update_device(
    project_id: str, device_id: str, input_data: UpdateDeviceInput
):
    """Update an existing device.

    LIFE-SAFETY: The load_unit field converts the load value to Amperes
    before storage, matching the create_device behavior. Without this
    conversion, updating load: 500 intending 500mA would store 500A —
    a 1000x error in NFPA 72 battery sizing calculations.
    """
    _verify_project(project_id)
    db = get_db()

    updates = input_data.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # ── Unit conversion for load updates (same as create_device) ─────────
    if "load" in updates:
        raw_load = updates["load"]
        load_unit = updates.pop("load_unit", "A")  # Remove from DB updates

        if raw_load is not None and raw_load != 0.0:
            if load_unit == "mA":
                updates["load"] = raw_load / 1000.0
            elif load_unit == "W":
                # Get current device voltage if voltage not in this update
                voltage = updates.get("voltage")
                if voltage is None:
                    existing = db.get_device(project_id, device_id)
                    voltage = existing.get("voltage", 0.0) if existing else 0.0
                if voltage <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot convert Watts to Amperes: voltage must be > 0. "
                               "Provide voltage in Volts or specify load_unit as 'A'.",
                    )
                updates["load"] = raw_load / voltage

            # Store traceability info in properties
            if load_unit != "A":
                properties = updates.get("properties", {})
                properties["load_original_value"] = raw_load
                properties["load_original_unit"] = load_unit
                updates["properties"] = properties
        elif raw_load == 0.0:
            # load_unit doesn't matter for zero load — remove from updates
            updates.pop("load_unit", None)

    device = db.update_device(project_id, device_id, updates)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    validate_device(device)

    # Sync device update to UDM for conflict detection
    from backend.project_bridge import sync_device_update_to_udm
    sync_device_update_to_udm(project_id, device_id, updates)

    return {"data": device, "success": True}


@router.delete("/{device_id}")
async def delete_device(project_id: str, device_id: str):
    """Delete a device from a project.

    V114 FIX: Safety-critical device deletion now logs audit trail.
    Fire alarm devices (smoke detectors, pull stations, notification appliances)
    are safety-critical — deletion must be traceable for liability and NFPA compliance.
    """
    _verify_project(project_id)
    db = get_db()
    # V114 FIX: Record device data BEFORE deletion for audit trail
    device = db.get_device(project_id, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    logging.getLogger("fireai.audit").critical(
        "SAFETY-CRITICAL: Device DELETED — project=%s device_id=%s "
        "device_type=%s name=%s — NFPA 72 requires traceability for all "
        "fire alarm device changes. Deletion affects coverage calculations.",
        project_id, device_id,
        device.get("type", "unknown"),
        device.get("name", "unknown"),
    )
    deleted = db.delete_device(project_id, device_id)

    # Sync device deletion to UDM (soft-delete for audit trail)
    from backend.project_bridge import sync_device_delete_to_udm
    sync_device_delete_to_udm(project_id, device_id)

    return {"data": None, "success": True, "message": "Device deleted"}
