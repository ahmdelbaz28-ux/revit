"""
backend/project_bridge.py — Cross-database project synchronization bridge.

Ensures that project creation, update, and deletion in System A
(digital_twin.db) is reflected in System B (udm_elements.db).

This is a SAFETY-CRITICAL bridge — orphaned project references in
either database can lead to data corruption and incorrect engineering
calculations.

Field mapping between System A and System B:
    System A `id`           → System B `project_id`
    System A `createdAt`    → System B `created_timestamp`
    System A `updatedAt`    → System B `last_modified_timestamp`
    System A `deviceCount`  → (not in System B — computed field)
    System A `author`       → System B `metadata.author`
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
            logger.info(
                "Project %s already exists in UDM — skipping sync", project_id
            )
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
            logger.error(
                "Failed to sync project %s to UDM: %s", project_id, e
            )
            return False

    except Exception as e:
        logger.critical(
            "UDM bridge unavailable during project sync: %s", e
        )
        return False


def sync_project_update_to_udm(
    project_id: str, updates: Dict[str, Any]
) -> bool:
    """Sync a project update from System A to System B.

    Returns True if sync succeeded, False if it failed (but does NOT block).
    """
    try:
        from backend.db_service import DatabaseService

        udm = DatabaseService()

        # Check if project exists in UDM
        existing = udm.get_project(project_id)
        if existing is None:
            logger.warning(
                "Project %s not found in UDM — attempting to create", project_id
            )
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
                        f"UPDATE projects SET {', '.join(set_clauses)} "
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
                        udm._projects[project_id][
                            "last_modified_timestamp"
                        ] = now
                        # Update metadata.author if author changed
                        if "author" in updates and updates["author"] is not None:
                            meta = udm._projects[project_id].get("metadata", {})
                            meta["author"] = updates["author"]
                            udm._projects[project_id]["metadata"] = meta

            logger.info("Project %s update synced to UDM", project_id)
            return True
        except Exception as e:
            logger.error(
                "Failed to sync project %s update to UDM: %s", project_id, e
            )
            return False

    except Exception as e:
        logger.critical(
            "UDM bridge unavailable during project update: %s", e
        )
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
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS element_projects (
                        element_id TEXT,
                        project_id TEXT,
                        PRIMARY KEY (element_id, project_id)
                    )
                ''')

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
            logger.error(
                "Failed to sync project %s deletion to UDM: %s", project_id, e
            )
            return False

    except Exception as e:
        logger.critical(
            "UDM bridge unavailable during project deletion: %s", e
        )
        return False
