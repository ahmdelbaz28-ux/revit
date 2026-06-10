"""
backend/project_bridge.py — Cross-database project & device synchronization bridge.

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


def sync_project_to_udm(project_data: Dict[str, Any]) -> bool:
    """Sync a project from System A to System B after creation.

    Maps System A fields to System B fields and creates the project
    in the UDM database.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.db_service import DatabaseService

        udm = DatabaseService()

        project_id = project_data.get("id", "")

        # Check if project already exists in UDM
        existing = udm.get_project(project_id)
        if existing is not None:
            logger.info("Project %s already exists in UDM — skipping sync", project_id)
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
            with udm._service_lock:
                conn = udm._data_model._conn
                cursor = conn.cursor()
                cursor.execute(
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
                conn.commit()

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
            return True
        except Exception as e:
            logger.error("Failed to sync project %s to UDM: %s", project_id, e)
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during project sync: %s", e)
        return False


def sync_project_update_to_udm(project_id: str, updates: Dict[str, Any]) -> bool:
    """Sync a project update from System A to System B.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.db_service import DatabaseService

        udm = DatabaseService()

        # Check if project exists in UDM
        existing = udm.get_project(project_id)
        if existing is None:
            logger.warning("Project %s not found in UDM — attempting to create", project_id)
            # Attempt to create it from scratch
            return sync_project_to_udm({"id": project_id, **updates})

        # Build SET clauses for the update
        try:
            with udm._service_lock:
                conn = udm._data_model._conn
                cursor = conn.cursor()

                set_clauses = []
                values = []

                # Map System A update fields to System B columns
                if "name" in updates and updates["name"] is not None:
                    set_clauses.append("name = ?")
                    values.append(updates["name"])
                if "description" in updates and updates["description"] is not None:
                    set_clauses.append("description = ?")
                    values.append(updates["description"])
                if "status" in updates and updates["status"] is not None:
                    set_clauses.append("status = ?")
                    values.append(updates["status"])

                # Always update the modification timestamp
                now = datetime.now(timezone.utc).isoformat()
                set_clauses.append("last_modified_timestamp = ?")
                values.append(now)

                # If author is being updated, merge into metadata JSON
                if "author" in updates and updates["author"] is not None:
                    # Read current metadata, merge author, write back
                    metadata = existing.metadata if existing.metadata else {}
                    metadata["author"] = updates["author"]
                    set_clauses.append("metadata = ?")
                    values.append(json.dumps(metadata))

                if set_clauses:
                    values.append(project_id)
                    cursor.execute(
                        f"UPDATE projects SET {', '.join(set_clauses)} "  # noqa: S608 — set_clauses built from whitelisted column names
                        f"WHERE project_id = ?",
                        values,
                    )
                    conn.commit()

                    # Update in-memory cache
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
                        # Update metadata.author if author changed
                        if "author" in updates and updates["author"] is not None:
                            meta = udm._projects[project_id].get("metadata", {})
                            meta["author"] = updates["author"]
                            udm._projects[project_id]["metadata"] = meta

            logger.info("Project %s update synced to UDM", project_id)
            return True
        except Exception as e:
            logger.error("Failed to sync project %s update to UDM: %s", project_id, e)
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during project update: %s", e)
        return False


def sync_project_delete_to_udm(project_id: str) -> bool:
    """Sync a project deletion from System A to System B.

    Deletes the project and all element associations from UDM.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.db_service import DatabaseService

        udm = DatabaseService()

        try:
            with udm._service_lock:
                conn = udm._data_model._conn
                cursor = conn.cursor()

                # Ensure element_projects table exists before deleting from it.
                # This table is created lazily by DatabaseService; it may not
                # exist yet if no elements have ever been associated with a project.
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS element_projects (
                        element_id TEXT,
                        project_id TEXT,
                        PRIMARY KEY (element_id, project_id)
                    )
                """)

                # Delete element associations first (referential integrity)
                cursor.execute(
                    "DELETE FROM element_projects WHERE project_id = ?",
                    (project_id,),
                )
                cursor.execute(
                    "DELETE FROM projects WHERE project_id = ?",
                    (project_id,),
                )
                conn.commit()

                # Update in-memory cache
                if project_id in udm._projects:
                    del udm._projects[project_id]

            logger.info("Project %s deletion synced to UDM", project_id)
            return True
        except Exception as e:
            logger.error("Failed to sync project %s deletion to UDM: %s", project_id, e)
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during project deletion: %s", e)
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

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.db_service import DatabaseService

        udm = DatabaseService()

        device_id = device_data.get("id", "")

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
            with udm._service_lock:
                conn = udm._data_model._conn
                cursor = conn.cursor()

                # Ensure elements table exists
                cursor.execute("""
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

                # Ensure element_projects table exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS element_projects (
                        element_id TEXT,
                        project_id TEXT,
                        PRIMARY KEY (element_id, project_id)
                    )
                """)

                # Insert or replace element
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute(
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

                # Link element to project
                cursor.execute(
                    "INSERT OR IGNORE INTO element_projects (element_id, project_id) "
                    "VALUES (?, ?)",
                    (device_id, project_id),
                )

                conn.commit()

            logger.info("Device %s synced to UDM for project %s", device_id, project_id)
            return True
        except Exception as e:
            logger.error("Failed to sync device %s to UDM: %s", device_id, e)
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during device sync: %s", e)
        return False


def sync_device_update_to_udm(project_id: str, device_id: str, updates: Dict[str, Any]) -> bool:
    """Sync a device update from System A to System B.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.db_service import DatabaseService

        udm = DatabaseService()

        try:
            with udm._service_lock:
                conn = udm._data_model._conn
                cursor = conn.cursor()

                set_clauses = []
                values = []

                # Map device fields to element fields
                if "type" in updates and updates["type"] is not None:
                    set_clauses.append("element_type = ?")
                    values.append(updates["type"])

                if "name" in updates and updates["name"] is not None:
                    set_clauses.append("name = ?")
                    values.append(updates["name"])

                # Update position if x, y, or z changed
                position_fields = {"x", "y", "z"}
                if position_fields.intersection(updates.keys()):
                    # Read current position and merge
                    cursor.execute(
                        "SELECT position FROM elements WHERE element_id = ?",
                        (device_id,),
                    )
                    row = cursor.fetchone()
                    current_pos = json.loads(row[0]) if row and row[0] else {}
                    for axis in ("x", "y", "z"):
                        if axis in updates and updates[axis] is not None:
                            current_pos[axis] = updates[axis]
                    set_clauses.append("position = ?")
                    values.append(json.dumps(current_pos))

                # Update properties with device metadata
                property_fields = {"voltage", "current", "load", "rotation", "category", "properties"}
                if property_fields.intersection(updates.keys()):
                    cursor.execute(
                        "SELECT properties FROM elements WHERE element_id = ?",
                        (device_id,),
                    )
                    row = cursor.fetchone()
                    current_props = json.loads(row[0]) if row and row[0] else {}
                    if "voltage" in updates:
                        current_props["voltage"] = updates["voltage"]
                    if "current" in updates:
                        current_props["current"] = updates["current"]
                    if "load" in updates:
                        current_props["load_amperes"] = updates["load"]
                    if "rotation" in updates:
                        current_props["rotation"] = updates["rotation"]
                    if "category" in updates:
                        current_props["device_category"] = updates["category"]
                    if "properties" in updates and updates["properties"]:
                        current_props.update(updates["properties"])
                    set_clauses.append("properties = ?")
                    values.append(json.dumps(current_props))

                if set_clauses:
                    now = datetime.now(timezone.utc).isoformat()
                    set_clauses.append("last_modified_timestamp = ?")
                    values.append(now)

                    values.append(device_id)
                    cursor.execute(
                        f"UPDATE elements SET {', '.join(set_clauses)} "  # noqa: S608 — set_clauses built from whitelisted column names
                        f"WHERE element_id = ?",
                        values,
                    )
                    conn.commit()

            logger.info("Device %s update synced to UDM for project %s", device_id, project_id)
            return True
        except Exception as e:
            logger.error("Failed to sync device %s update to UDM: %s", device_id, e)
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during device update: %s", e)
        return False


def sync_device_delete_to_udm(project_id: str, device_id: str) -> bool:
    """Sync a device deletion from System A to System B.

    Soft-deletes the element and removes its project association.
    Soft delete preserves the audit trail for NFPA 72 traceability.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.db_service import DatabaseService

        udm = DatabaseService()

        try:
            with udm._service_lock:
                conn = udm._data_model._conn
                cursor = conn.cursor()

                # Soft-delete the element (preserve audit trail)
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    "UPDATE elements SET is_deleted = 1, last_modified_timestamp = ? "
                    "WHERE element_id = ?",
                    (now, device_id),
                )

                # Remove project association
                cursor.execute(
                    "DELETE FROM element_projects WHERE element_id = ? AND project_id = ?",
                    (device_id, project_id),
                )
                conn.commit()

            logger.info("Device %s deletion synced to UDM for project %s", device_id, project_id)
            return True
        except Exception as e:
            logger.error("Failed to sync device %s deletion to UDM: %s", device_id, e)
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during device deletion: %s", e)
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

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.db_service import DatabaseService

        udm = DatabaseService()

        connection_id = connection_data.get("id", "")
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
            with udm._service_lock:
                conn = udm._data_model._conn
                cursor = conn.cursor()

                # Ensure relationships table exists with is_deleted and
                # last_modified_timestamp columns. The table may have been
                # created by UniversalDataModel without these columns, so we
                # also ALTER TABLE to add them if missing.
                cursor.execute("""
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

                # Add is_deleted column if it doesn't exist (the table may
                # have been created by UniversalDataModel without it)
                try:
                    cursor.execute(
                        "ALTER TABLE relationships ADD COLUMN is_deleted INTEGER DEFAULT 0"
                    )
                except Exception:
                    pass  # Column already exists — safe to ignore

                # Add last_modified_timestamp column if it doesn't exist
                try:
                    cursor.execute(
                        "ALTER TABLE relationships ADD COLUMN last_modified_timestamp TEXT"
                    )
                except Exception:
                    pass  # Column already exists — safe to ignore

                # Insert or replace relationship
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute(
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

                conn.commit()

            logger.info("Connection %s synced to UDM for project %s", connection_id, project_id)
            return True
        except Exception as e:
            logger.error("Failed to sync connection %s to UDM: %s", connection_id, e)
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during connection sync: %s", e)
        return False


def sync_connection_delete_to_udm(project_id: str, connection_id: str) -> bool:
    """Sync a connection deletion from System A to System B.

    Soft-deletes the relationship in UDM. Soft delete preserves the
    audit trail for NFPA 72 traceability — cable connection deletions
    must be traceable for liability and inspection compliance.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.db_service import DatabaseService

        udm = DatabaseService()

        try:
            with udm._service_lock:
                conn = udm._data_model._conn
                cursor = conn.cursor()

                # Ensure is_deleted and last_modified_timestamp columns exist
                # (same safety net as sync_connection_to_udm)
                try:
                    cursor.execute(
                        "ALTER TABLE relationships ADD COLUMN is_deleted INTEGER DEFAULT 0"
                    )
                except Exception:
                    pass
                try:
                    cursor.execute(
                        "ALTER TABLE relationships ADD COLUMN last_modified_timestamp TEXT"
                    )
                except Exception:
                    pass

                # Soft-delete the relationship (preserve audit trail)
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    "UPDATE relationships SET is_deleted = 1, last_modified_timestamp = ? "
                    "WHERE relationship_id = ?",
                    (now, connection_id),
                )

                # Also soft-delete any reverse_cable_connection entry for the
                # same device pair. When a connection is created, the UDM may
                # store a reverse relationship for bidirectional traversal
                # (matching the pattern in DatabaseService.create_connection).
                cursor.execute(
                    "SELECT from_element_id, to_element_id FROM relationships "
                    "WHERE relationship_id = ?",
                    (connection_id,),
                )
                row = cursor.fetchone()
                if row:
                    from_id, to_id = row[0], row[1]
                    cursor.execute(
                        "UPDATE relationships SET is_deleted = 1, last_modified_timestamp = ? "
                        "WHERE from_element_id = ? AND to_element_id = ? "
                        "AND relationship_type = ?",
                        (now, to_id, from_id, "reverse_cable_connection"),
                    )

                conn.commit()

            logger.info("Connection %s deletion synced to UDM for project %s", connection_id, project_id)
            return True
        except Exception as e:
            logger.error("Failed to sync connection %s deletion to UDM: %s", connection_id, e)
            return False

    except Exception as e:
        logger.critical("UDM bridge unavailable during connection deletion: %s", e)
        return False
