from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from backend.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class DeviceRepository(BaseRepository):
    """Repository handling device CRUD operations."""

    def create_device(self, project_id: str, device_data: dict) -> dict:
        """Insert a new device and return it."""
        now = datetime.now(timezone.utc).isoformat()
        device_data.setdefault("id", str(uuid.uuid4()))
        device_data["projectId"] = project_id
        device_data["createdAt"] = now
        device_data["updatedAt"] = now
        device_data.setdefault("z", 0.0)
        device_data.setdefault("rotation", 0.0)
        device_data.setdefault("voltage", 0.0)
        device_data.setdefault("current", 0.0)
        device_data.setdefault("load", 0.0)
        device_data.setdefault("properties", {})

        props_json = json.dumps(device_data["properties"])

        with self.db._transaction() as cur:
            cur.execute(
                f"""INSERT INTO devices
                   (id, project_id, type, name, category, x, y, z, rotation,
                    voltage, current, load, properties, created_at, updated_at)
                   VALUES ({self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()})""",
                (
                    device_data["id"],
                    project_id,
                    device_data["type"],
                    device_data["name"],
                    device_data["category"],
                    device_data["x"],
                    device_data["y"],
                    device_data["z"],
                    device_data["rotation"],
                    device_data["voltage"],
                    device_data["current"],
                    device_data["load"],
                    props_json,
                    device_data["createdAt"],
                    device_data["updatedAt"],
                ),
            )

        return self.get_device(project_id, device_data["id"])

    def get_device(self, project_id: str, device_id: str) -> dict | None:
        """Get a device by ID within a project."""
        with self.db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM devices WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                (device_id, project_id),
            )
            row = cur.fetchone()
            if not row:
                return None
        return self.db._row_to_device(row)

    def list_devices(
        self,
        project_id: str,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """List devices in a project with pagination."""
        _ALLOWED_DEVICE_SORTS = frozenset({
            "id", "created_at", "updated_at", "name", "type",
            "category", "voltage", "current", "load",
        })
        if sort not in _ALLOWED_DEVICE_SORTS:
            sort = "created_at"
        order = "ASC" if order.upper() == "ASC" else "DESC"

        with self.db._transaction() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM devices WHERE project_id = {self.db._ph()}",
                (project_id,),
            )
            total = self.db._scalar(cur)

            offset = (page - 1) * limit
            cur.execute(
                f"SELECT * FROM devices WHERE project_id = {self.db._ph()} ORDER BY {sort} {order} LIMIT {self.db._ph()} OFFSET {self.db._ph()}",
                (project_id, limit, offset),
            )
            rows = cur.fetchall()

        devices = [self.db._row_to_device(row) for row in rows]
        total_pages = max(1, (total + limit - 1) // limit)
        return {
            "data": devices,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        }

    def update_device(self, project_id: str, device_id: str, updates: dict) -> dict | None:
        """Update a device. Returns updated device or None if not found."""
        existing = self.get_device(project_id, device_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"updated_at = {self.db._ph()}"]
        values = [now]

        simple_fields = {
            "name": "name",
            "x": "x",
            "y": "y",
            "z": "z",
            "rotation": "rotation",
            "voltage": "voltage",
            "current": "current",
            "load": "load",
        }
        for api_field, db_field in simple_fields.items():
            if api_field in updates and updates[api_field] is not None:
                set_clauses.append(f"{db_field} = {self.db._ph()}")
                values.append(updates[api_field])

        # Handle properties merge
        if "properties" in updates and updates["properties"] is not None:
            merged = {**existing["properties"], **updates["properties"]}
            set_clauses.append(f"properties = {self.db._ph()}")
            values.append(json.dumps(merged))

        values.extend([device_id, project_id])

        with self.db._transaction() as cur:
            cur.execute(
                f"UPDATE devices SET {', '.join(set_clauses)} WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                values,
            )

        return self.get_device(project_id, device_id)

    def delete_device(self, project_id: str, device_id: str) -> bool:
        """Delete a device and its associated connections."""
        with self.db._transaction() as cur:
            # Delete orphaned connections first (no FK cascade on from_id/to_id)
            cur.execute(
                f"DELETE FROM connections WHERE (from_id = {self.db._ph()} OR to_id = {self.db._ph()}) AND project_id = {self.db._ph()}",
                (device_id, device_id, project_id),
            )
            deleted_conns = cur.rowcount
            if deleted_conns > 0:
                logger.info(
                    f"Deleted {deleted_conns} orphaned connection(s) for device {device_id}"
                )
            cur.execute(
                f"DELETE FROM devices WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                (device_id, project_id),
            )
            return cur.rowcount > 0

    def get_all_devices_for_project(self, project_id: str) -> list[dict]:
        """Get ALL devices for a project (no pagination, used for exports)."""
        with self.db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM devices WHERE project_id = {self.db._ph()}",
                (project_id,),
            )
            rows = cur.fetchall()
        return [self.db._row_to_device(row) for row in rows]
