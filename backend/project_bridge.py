"""backend/project_bridge.py — Cross-database project & device synchronization bridge.

Ensures that project creation, update, and deletion in System A
(digital_twin.db) is reflected in System B (udm_elements.db).

Also synchronizes devices (fire alarm components) so that the conflict
detection system running on udm_elements.db can detect spatial conflicts
between devices from different projects.

This is a SAFETY-CRITICAL bridge — orphaned project references in
either database can lead to data corruption and incorrect engineering
calculations. Devices that are not synced to UDM will not participate
in conflict detection, potentially allowing spatial overlaps between
fire alarm components from different projects.

Field mapping between System A and System B:
    System A `id`           → System B `project_id`
    System A `createdAt`    → System B `created_timestamp`
    System A `updatedAt`    → System B `last_modified_timestamp`
    System A `deviceCount`  → (not in System B — computed field)
    System A `author`       → System B `metadata.author`

Device mapping between System A and System B:
    System A device `id`         → System B element `element_id`
    System A device `type`       → System B element `element_type`
    System A device `project_id` → System B element `project_id` (via element_projects)
    System A device `x,y,z`      → System B element `position` (JSON {x,y,z})
    System A device `properties` → System B element `properties`
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

_TARGET_DB = "udm_elements"


def sync_project_to_udm(project_data: Dict[str, Any]) -> bool:
    """Sync a project from System A to System B after creation.

    Maps System A fields to System B fields and creates the project
    in the UDM database. Records the sync status in sync_operations.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    project_id = project_data.get("id", "")

    try:
        from backend.database import get_db
        from backend.db_service import get_db_service

        udm = get_db_service()
        db = get_db()

        # Record sync attempt as "syncing"
        db.record_sync("project", project_id, _TARGET_DB, "syncing")

        # Check if project already exists in UDM
        existing = udm.get_project(project_id)
        if existing is not None:
            logger.info("Project %s already exists in UDM — skipping sync", project_id)
            db.record_sync("project", project_id, _TARGET_DB, "synced")
            return True

        # Create in UDM — use the SAME ID from System A.
        # DatabaseService.create_project() generates its own UUID,
        # so we directly insert with the System A ID.
        now = datetime.now(timezone.utc).isoformat()

        name = project_data.get("name", "Untitled")
        description = project_data.get("description", "")
        status = project_data.get("status", "draft")
        author = project_data.get("author", "")
        created_at = project_data.get("createdAt", now)
        updated_at = project_data.get("updatedAt", now)

        metadata = {
            "source": "digital_twin",
            "original_id": project_id,
            "author": author,
        }

        try:
            udm.bridge_insert(
                "INSERT OR IGNORE INTO projects "
                "(project_id, name, description, status, metadata, "
                "created_timestamp, last_modified_timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    name,
                    description,
                    status,
                    json.dumps(metadata),
                    created_at,
                    updated_at,
                ),
            )

            # Update in-memory cache
            udm._projects[project_id] = {
                "project_id": project_id,
                "name": name,
                "description": description,
                "status": status,
                "metadata": metadata,
                "created_timestamp": created_at,
                "last_modified_timestamp": updated_at,
            }

            logger.info("Project %s synced to UDM successfully", project_id)
            db.record_sync("project", project_id, _TARGET_DB, "synced")
            return True
        except Exception as e:
            logger.error("Failed to sync project %s to UDM: %s", project_id, e)
            db.record_sync("project", project_id, _TARGET_DB, "error", str(e))
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during project sync: %s", e)
        # Try to record the failure — may also fail if DB is unavailable
        try:
            from backend.database import get_db
            get_db().record_sync("project", project_id, _TARGET_DB, "error", str(e))
        except Exception:
            pass
        return False


def sync_project_update_to_udm(project_id: str, updates: Dict[str, Any]) -> bool:
    """Sync a project update from System A to System B.

    Records the sync status in sync_operations.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.database import get_db
        from backend.db_service import get_db_service

        udm = get_db_service()
        db = get_db()

        db.record_sync("project", project_id, _TARGET_DB, "syncing")

        # Check if project exists in UDM
        existing = udm.get_project(project_id)
        if existing is None:
            logger.warning("Project %s not found in UDM — attempting to create", project_id)
            # Attempt to create it from scratch
            return sync_project_to_udm({"id": project_id, **updates})

        # Build SET clauses for the update
        try:
            set_clauses = []
            values = []

            if "name" in updates and updates["name"] is not None:
                set_clauses.append("name = ?")
                values.append(updates["name"])
            if "description" in updates and updates["description"] is not None:
                set_clauses.append("description = ?")
                values.append(updates["description"])
            if "status" in updates and updates["status"] is not None:
                set_clauses.append("status = ?")
                values.append(updates["status"])

            now = datetime.now(timezone.utc).isoformat()
            set_clauses.append("last_modified_timestamp = ?")
            values.append(now)

            if "author" in updates and updates["author"] is not None:
                metadata = existing.metadata if existing.metadata else {}
                metadata["author"] = updates["author"]
                set_clauses.append("metadata = ?")
                values.append(json.dumps(metadata))

            if set_clauses:
                values.append(project_id)
                udm.bridge_sql(
                    f"UPDATE projects SET {', '.join(set_clauses)} WHERE project_id = ?",
                    tuple(values),
                    commit=True,
                )

                if project_id in udm._projects:
                    field_map = {
                        "name": "name",
                        "description": "description",
                        "status": "status",
                    }
                    for field, value in updates.items():
                        if value is not None and field in field_map:
                            udm._projects[project_id][field_map[field]] = value
                    udm._projects[project_id]["last_modified_timestamp"] = now
                    if "author" in updates and updates["author"] is not None:
                        meta = udm._projects[project_id].get("metadata", {})
                        meta["author"] = updates["author"]
                        udm._projects[project_id]["metadata"] = meta

            logger.info("Project %s update synced to UDM", project_id)
            db.record_sync("project", project_id, _TARGET_DB, "synced")
            return True
        except Exception as e:
            logger.error("Failed to sync project %s update to UDM: %s", project_id, e)
            db.record_sync("project", project_id, _TARGET_DB, "error", str(e))
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during project update: %s", e)
        try:
            from backend.database import get_db
            get_db().record_sync("project", project_id, _TARGET_DB, "error", str(e))
        except Exception:
            pass
        return False


def sync_project_delete_to_udm(project_id: str) -> bool:
    """Sync a project deletion from System A to System B.

    Deletes the project and all element associations from UDM.
    Records the sync status in sync_operations.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.database import get_db
        from backend.db_service import get_db_service

        udm = get_db_service()
        db = get_db()

        db.record_sync("project", project_id, _TARGET_DB, "syncing")

        try:
            udm.bridge_create_table("""
                CREATE TABLE IF NOT EXISTS element_projects (
                    element_id TEXT,
                    project_id TEXT,
                    PRIMARY KEY (element_id, project_id)
                )
            """)

            udm.bridge_sql(
                "DELETE FROM element_projects WHERE project_id = ?",
                (project_id,),
                commit=True,
            )
            udm.bridge_sql(
                "DELETE FROM projects WHERE project_id = ?",
                (project_id,),
                commit=True,
            )

            if project_id in udm._projects:
                del udm._projects[project_id]

            logger.info("Project %s deletion synced to UDM", project_id)
            db.record_sync("project", project_id, _TARGET_DB, "synced")
            return True
        except Exception as e:
            logger.error("Failed to sync project %s deletion to UDM: %s", project_id, e)
            db.record_sync("project", project_id, _TARGET_DB, "error", str(e))
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during project deletion: %s", e)
        try:
            from backend.database import get_db
            get_db().record_sync("project", project_id, _TARGET_DB, "error", str(e))
        except Exception:
            pass
        return False


# ── Device Synchronization ─────────────────────────────────────────────────
# Devices (smoke detectors, pull stations, NACs, etc.) are created in
# System A (digital_twin.db) but must be synced to System B (udm_elements.db)
# for the conflict detection system to detect spatial overlaps.
#
# SAFETY: Without device sync, two devices from different projects could
# occupy the same physical location without triggering a conflict alert.
# In a fire alarm system, this could mean:
#   - Overlapping coverage zones not detected
#   - Devices blocking each other's detection radius
#   - Redundant devices that waste budget without adding coverage


def sync_device_to_udm(project_id: str, device_data: Dict[str, Any]) -> bool:
    """Sync a device from System A to System B after creation.

    Maps System A device fields to System B element fields so that
    the conflict detection system can detect spatial overlaps.
    Records the sync status in sync_operations.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    device_id = device_data.get("id", "")

    try:
        from backend.database import get_db
        from backend.db_service import get_db_service

        udm = get_db_service()
        db = get_db()

        db.record_sync("device", device_id, _TARGET_DB, "syncing")

        # Build position JSON from x, y, z coordinates
        position = {
            "x": device_data.get("x", 0.0),
            "y": device_data.get("y", 0.0),
            "z": device_data.get("z", 0.0),
        }

        # Build properties with device metadata
        properties = device_data.get("properties", {}) or {}
        properties.update({
            "source": "digital_twin_device",
            "device_type": device_data.get("type", ""),
            "device_name": device_data.get("name", ""),
            "device_category": device_data.get("category", ""),
            "voltage": device_data.get("voltage", 0.0),
            "current": device_data.get("current", 0.0),
            "load_amperes": device_data.get("load", 0.0),
            "rotation": device_data.get("rotation", 0.0),
            "original_id": device_id,
        })

        try:
            udm.bridge_create_table("""
                CREATE TABLE IF NOT EXISTS elements (
                    element_id TEXT PRIMARY KEY,
                    element_type TEXT NOT NULL,
                    name TEXT,
                    position TEXT,
                    properties TEXT,
                    created_timestamp TEXT,
                    last_modified_timestamp TEXT,
                    is_deleted INTEGER DEFAULT 0
                )
            """)

            # V129 FIX: Migrate existing elements table that was created by
            # core/database.py (which doesn't have name/position/is_deleted
            # columns). CREATE TABLE IF NOT EXISTS silently skips if the table
            # already exists, so we need ALTER TABLE to add missing columns.
            for migration in [
                "ALTER TABLE elements ADD COLUMN name TEXT",
                "ALTER TABLE elements ADD COLUMN position TEXT",
                "ALTER TABLE elements ADD COLUMN properties TEXT",
                "ALTER TABLE elements ADD COLUMN is_deleted INTEGER DEFAULT 0",
            ]:
                try:
                    udm.bridge_sql(migration)
                except Exception:
                    pass  # Column already exists — expected

            udm.bridge_create_table("""
                CREATE TABLE IF NOT EXISTS element_projects (
                    element_id TEXT,
                    project_id TEXT,
                    PRIMARY KEY (element_id, project_id)
                )
            """)

            # Performance indexes for UDM tables
            udm.bridge_sql("CREATE INDEX IF NOT EXISTS idx_ep_project ON element_projects(project_id)")
            udm.bridge_sql("CREATE INDEX IF NOT EXISTS idx_elements_type ON elements(element_type)")

            now = datetime.now(timezone.utc).isoformat()
            udm.bridge_insert(
                "INSERT OR REPLACE INTO elements "
                "(element_id, element_type, name, position, properties, "
                "created_timestamp, last_modified_timestamp, is_deleted) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    device_id,
                    device_data.get("type", "device"),
                    device_data.get("name", ""),
                    json.dumps(position),
                    json.dumps(properties),
                    now,
                    now,
                ),
            )

            udm.bridge_insert(
                "INSERT OR IGNORE INTO element_projects (element_id, project_id) "
                "VALUES (?, ?)",
                (device_id, project_id),
            )

            logger.info("Device %s synced to UDM for project %s", device_id, project_id)
            db.record_sync("device", device_id, _TARGET_DB, "synced")
            return True
        except Exception as e:
            logger.error("Failed to sync device %s to UDM: %s", device_id, e)
            db.record_sync("device", device_id, _TARGET_DB, "error", str(e))
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during device sync: %s", e)
        try:
            from backend.database import get_db
            get_db().record_sync("device", device_id, _TARGET_DB, "error", str(e))
        except Exception:
            pass
        return False


def sync_device_update_to_udm(project_id: str, device_id: str, updates: Dict[str, Any]) -> bool:
    """Sync a device update from System A to System B.

    Records the sync status in sync_operations.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.database import get_db
        from backend.db_service import get_db_service

        udm = get_db_service()
        db = get_db()

        db.record_sync("device", device_id, _TARGET_DB, "syncing")

        # SECURITY FIX: Explicit field whitelist — only allow known safe fields
        # to be updated. Previously, arbitrary keys from `updates` dict could
        # be used to set SQL column names, creating a potential injection risk
        # if the dict ever contained user-controlled keys. This mirrors the
        # field_map pattern used in sync_project_update_to_udm().
        _ALLOWED_FIELDS = {"type", "name"}
        _POSITION_FIELDS = {"x", "y", "z"}
        _PROPERTY_FIELDS = {"voltage", "current", "load", "rotation", "category", "properties"}

        try:
            set_clauses = []
            values = []

            if "type" in updates and updates["type"] is not None and "type" in _ALLOWED_FIELDS:
                set_clauses.append("element_type = ?")
                values.append(updates["type"])

            if "name" in updates and updates["name"] is not None and "name" in _ALLOWED_FIELDS:
                set_clauses.append("name = ?")
                values.append(updates["name"])

            if _POSITION_FIELDS.intersection(updates.keys()):
                # Validate that only known position fields are processed
                safe_position_updates = {k: v for k, v in updates.items() if k in _POSITION_FIELDS and v is not None}
                if safe_position_updates:
                    row = udm.bridge_sql(
                        "SELECT position FROM elements WHERE element_id = ?",
                        (device_id,),
                        fetch=True,
                    )
                    row_data = row.fetchone() if hasattr(row, 'fetchone') else None
                    current_pos = json.loads(row_data[0]) if row_data and row_data[0] else {}
                    for axis in ("x", "y", "z"):
                        if axis in safe_position_updates:
                            current_pos[axis] = safe_position_updates[axis]
                    set_clauses.append("position = ?")
                    values.append(json.dumps(current_pos))

            if _PROPERTY_FIELDS.intersection(updates.keys()):
                # Validate that only known property fields are processed
                safe_property_updates = {k: v for k, v in updates.items() if k in _PROPERTY_FIELDS and v is not None}
                if safe_property_updates:
                    row = udm.bridge_sql(
                        "SELECT properties FROM elements WHERE element_id = ?",
                        (device_id,),
                        fetch=True,
                    )
                    row_data = row.fetchone() if hasattr(row, 'fetchone') else None
                    current_props = json.loads(row_data[0]) if row_data and row_data[0] else {}
                    if "voltage" in safe_property_updates:
                        current_props["voltage"] = safe_property_updates["voltage"]
                    if "current" in safe_property_updates:
                        current_props["current"] = safe_property_updates["current"]
                    if "load" in safe_property_updates:
                        current_props["load_amperes"] = safe_property_updates["load"]
                    if "rotation" in safe_property_updates:
                        current_props["rotation"] = safe_property_updates["rotation"]
                    if "category" in safe_property_updates:
                        current_props["device_category"] = safe_property_updates["category"]
                    if safe_property_updates.get("properties"):
                        current_props.update(safe_property_updates["properties"])
                    set_clauses.append("properties = ?")
                    values.append(json.dumps(current_props))

            if set_clauses:
                now = datetime.now(timezone.utc).isoformat()
                set_clauses.append("last_modified_timestamp = ?")
                values.append(now)
                values.append(device_id)
                udm.bridge_sql(
                    f"UPDATE elements SET {', '.join(set_clauses)} WHERE element_id = ?",
                    tuple(values),
                    commit=True,
                )

            logger.info("Device %s update synced to UDM for project %s", device_id, project_id)
            db.record_sync("device", device_id, _TARGET_DB, "synced")
            return True
        except Exception as e:
            logger.error("Failed to sync device %s update to UDM: %s", device_id, e)
            db.record_sync("device", device_id, _TARGET_DB, "error", str(e))
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during device update: %s", e)
        try:
            from backend.database import get_db
            get_db().record_sync("device", device_id, _TARGET_DB, "error", str(e))
        except Exception:
            pass
        return False


def sync_device_delete_to_udm(project_id: str, device_id: str) -> bool:
    """Sync a device deletion from System A to System B.

    Soft-deletes the element and removes its project association.
    Soft delete preserves the audit trail for NFPA 72 traceability.
    Records the sync status in sync_operations.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.database import get_db
        from backend.db_service import get_db_service

        udm = get_db_service()
        db = get_db()

        db.record_sync("device", device_id, _TARGET_DB, "syncing")

        try:
            now = datetime.now(timezone.utc).isoformat()
            udm.bridge_sql(
                "UPDATE elements SET is_deleted = 1, last_modified_timestamp = ? "
                "WHERE element_id = ?",
                (now, device_id),
                commit=True,
            )
            udm.bridge_sql(
                "DELETE FROM element_projects WHERE element_id = ? AND project_id = ?",
                (device_id, project_id),
                commit=True,
            )

            logger.info("Device %s deletion synced to UDM for project %s", device_id, project_id)
            db.record_sync("device", device_id, _TARGET_DB, "synced")
            return True
        except Exception as e:
            logger.error("Failed to sync device %s deletion to UDM: %s", device_id, e)
            db.record_sync("device", device_id, _TARGET_DB, "error", str(e))
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during device deletion: %s", e)
        try:
            from backend.database import get_db
            get_db().record_sync("device", device_id, _TARGET_DB, "error", str(e))
        except Exception:
            pass
        return False


# ── Connection Synchronization ───────────────────────────────────────────────
# Connections (cable wiring between fire alarm devices) are created in
# System A (digital_twin.db) but must be synced to System B (udm_elements.db)
# so that the conflict detection system has a complete picture of the project.
#
# SAFETY: Without connection sync, the UDM has an incomplete view of cable
# relationships between devices. This means:
#   - Spatial analysis in System B doesn't know about cable connections
#   - Voltage drop calculations in the conflict system lack cable length data
#   - Circuit topology is invisible to cross-project conflict detection
#
# Connection mapping between System A and System B:
#     System A connection `id`       → System B relationship `relationship_id`
#     System A connection `fromId`   → System B relationship `from_element_id`
#     System A connection `toId`     → System B relationship `to_element_id`
#     (constant)                     → System B relationship `relationship_type` = "cable_connection"
#     System A connection fields     → System B relationship `metadata` (JSON)


def sync_connection_to_udm(project_id: str, connection_data: Dict[str, Any]) -> bool:
    """Sync a connection from System A to System B after creation.

    Maps System A connection fields to System B relationship fields so that
    the conflict detection system can see cable wiring between devices.
    Records the sync status in sync_operations.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    connection_id = connection_data.get("id", "")

    try:
        from backend.database import get_db
        from backend.db_service import get_db_service

        udm = get_db_service()
        db = get_db()

        db.record_sync("connection", connection_id, _TARGET_DB, "syncing")
        from_id = connection_data.get("fromId", "")
        to_id = connection_data.get("toId", "")

        # Build properties JSON with cable metadata
        properties = {
            "source": "digital_twin_connection",
            "cableSize": connection_data.get("cableSize", ""),
            "length": connection_data.get("length", 0.0),
            "type": connection_data.get("type", ""),
            "original_id": connection_id,
            "project_id": project_id,
        }

        try:
            udm.bridge_create_table("""
                CREATE TABLE IF NOT EXISTS relationships (
                    relationship_id TEXT PRIMARY KEY,
                    from_element_id TEXT NOT NULL,
                    to_element_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    is_parametric INTEGER DEFAULT 0,
                    metadata JSON,
                    is_deleted INTEGER DEFAULT 0,
                    last_modified_timestamp TEXT
                )
            """)

            # Ensure compatibility columns exist (safe to ignore if already present)
            for col in [
                "ADD COLUMN is_deleted INTEGER DEFAULT 0",
                "ADD COLUMN last_modified_timestamp TEXT",
            ]:
                try:
                    udm.bridge_sql(f"ALTER TABLE relationships {col}")
                except Exception:
                    pass

            now = datetime.now(timezone.utc).isoformat()
            udm.bridge_insert(
                "INSERT OR REPLACE INTO relationships "
                "(relationship_id, from_element_id, to_element_id, "
                "relationship_type, is_parametric, metadata, "
                "is_deleted, last_modified_timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                (
                    connection_id,
                    from_id,
                    to_id,
                    "cable_connection",
                    0,
                    json.dumps(properties),
                    now,
                ),
            )

            logger.info("Connection %s synced to UDM for project %s", connection_id, project_id)
            db.record_sync("connection", connection_id, _TARGET_DB, "synced")
            return True
        except Exception as e:
            logger.error("Failed to sync connection %s to UDM: %s", connection_id, e)
            db.record_sync("connection", connection_id, _TARGET_DB, "error", str(e))
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during connection sync: %s", e)
        try:
            from backend.database import get_db
            get_db().record_sync("connection", connection_id, _TARGET_DB, "error", str(e))
        except Exception:
            pass
        return False


def sync_connection_delete_to_udm(project_id: str, connection_id: str) -> bool:
    """Sync a connection deletion from System A to System B.

    Soft-deletes the relationship in UDM. Soft delete preserves the
    audit trail for NFPA 72 traceability — cable connection deletions
    must be traceable for liability and inspection compliance.
    Records the sync status in sync_operations.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.database import get_db
        from backend.db_service import get_db_service

        udm = get_db_service()
        db = get_db()

        db.record_sync("connection", connection_id, _TARGET_DB, "syncing")

        try:
            for col in [
                "ADD COLUMN is_deleted INTEGER DEFAULT 0",
                "ADD COLUMN last_modified_timestamp TEXT",
            ]:
                try:
                    udm.bridge_sql(f"ALTER TABLE relationships {col}")
                except Exception:
                    pass

            now = datetime.now(timezone.utc).isoformat()
            udm.bridge_sql(
                "UPDATE relationships SET is_deleted = 1, last_modified_timestamp = ? "
                "WHERE relationship_id = ?",
                (now, connection_id),
                commit=True,
            )

            row = udm.bridge_sql(
                "SELECT from_element_id, to_element_id FROM relationships "
                "WHERE relationship_id = ?",
                (connection_id,),
                fetch=True,
            )
            row_data = row.fetchone() if hasattr(row, 'fetchone') else None
            if row_data:
                from_id, to_id = row_data[0], row_data[1]
                udm.bridge_sql(
                    "UPDATE relationships SET is_deleted = 1, last_modified_timestamp = ? "
                    "WHERE from_element_id = ? AND to_element_id = ? "
                    "AND relationship_type = ?",
                    (now, to_id, from_id, "reverse_cable_connection"),
                    commit=True,
                )

            logger.info("Connection %s deletion synced to UDM for project %s", connection_id, project_id)
            db.record_sync("connection", connection_id, _TARGET_DB, "synced")
            return True
        except Exception as e:
            logger.error("Failed to sync connection %s deletion to UDM: %s", connection_id, e)
            db.record_sync("connection", connection_id, _TARGET_DB, "error", str(e))
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during connection deletion: %s", e)
        try:
            from backend.database import get_db
            get_db().record_sync("connection", connection_id, _TARGET_DB, "error", str(e))
        except Exception:
            pass
        return False
