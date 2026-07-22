from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.db.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):
    """Repository handling project CRUD and counts operations."""

    def create_project(self, project_data: dict) -> dict:
        """Insert a new project and return it."""
        now = datetime.now(timezone.utc).isoformat()
        project_data.setdefault("id", str(uuid.uuid4()))
        project_data["createdAt"] = now
        project_data["updatedAt"] = now
        project_data.setdefault("status", "draft")
        project_data.setdefault("description", "")
        project_data.setdefault("author", "")

        with self.db._transaction() as cur:
            cur.execute(
                f"""INSERT INTO projects (id, name, description, author, created_at, updated_at, status)
                   VALUES ({self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()})""",
                (
                    project_data["id"],
                    project_data["name"],
                    project_data["description"],
                    project_data["author"],
                    project_data["createdAt"],
                    project_data["updatedAt"],
                    project_data["status"],
                ),
            )

        return self.get_project(project_data["id"])

    def get_project(self, project_id: str) -> dict | None:
        """Get a project by ID, with device and connection counts — single query."""
        with self.db._transaction() as cur:
            cur.execute(
                f"""
                SELECT
                    p.*,
                    COALESCE(d.device_count, 0) AS device_count,
                    COALESCE(c.connection_count, 0) AS connection_count
                FROM projects p
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS device_count
                    FROM devices
                    GROUP BY project_id
                ) d ON p.id = d.project_id
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS connection_count
                    FROM connections
                    GROUP BY project_id
                ) c ON p.id = c.project_id
                WHERE p.id = {self.db._ph()}
                """,
                (project_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

        return self.db._row_to_project(row, row["device_count"], row["connection_count"])

    def list_projects(
        self,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """List projects with pagination — uses JOIN to avoid N+1 counts."""
        _ALLOWED_PROJECT_SORTS = frozenset({"id", "name", "created_at", "updated_at", "status", "author"})
        if sort not in _ALLOWED_PROJECT_SORTS:
            sort = "created_at"
        order = "ASC" if order.upper() == "ASC" else "DESC"

        with self.db._transaction() as cur:
            # Get total count
            cur.execute("SELECT COUNT(*) FROM projects")
            total = self.db._scalar(cur)

            # Get paginated results with device/connection counts in ONE query (no N+1)
            offset = (page - 1) * limit
            cur.execute(
                f"""
                SELECT
                    p.*,
                    COALESCE(d.device_count, 0) AS device_count,
                    COALESCE(c.connection_count, 0) AS connection_count
                FROM projects p
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS device_count
                    FROM devices
                    GROUP BY project_id
                ) d ON p.id = d.project_id
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS connection_count
                    FROM connections
                    GROUP BY project_id
                ) c ON p.id = c.project_id
                ORDER BY p.{sort} {order}
                LIMIT {self.db._ph()} OFFSET {self.db._ph()}
                """,
                (limit, offset),
            )
            rows = cur.fetchall()

            projects = [
                self.db._row_to_project(row, row["device_count"], row["connection_count"])
                for row in rows
            ]

        total_pages = max(1, (total + limit - 1) // limit)
        return {
            "data": projects,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        }

    def update_project(self, project_id: str, updates: dict) -> dict | None:
        """Update a project. Returns updated project or None if not found."""
        existing = self.get_project(project_id)
        if not existing:
            return None

        now = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"updated_at = {self.db._ph()}"]
        values = [now]

        field_map = {
            "name": "name",
            "description": "description",
            "author": "author",
            "status": "status",
        }
        for api_field, db_field in field_map.items():
            if api_field in updates and updates[api_field] is not None:
                set_clauses.append(f"{db_field} = {self.db._ph()}")
                values.append(updates[api_field])

        values.append(project_id)

        with self.db._transaction() as cur:
            cur.execute(
                f"UPDATE projects SET {', '.join(set_clauses)} WHERE id = {self.db._ph()}",
                values,
            )

        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its children (CASCADE)."""
        with self.db._transaction() as cur:
            cur.execute(f"DELETE FROM sync_status WHERE project_id = {self.db._ph()}", (project_id,))
            cur.execute(f"DELETE FROM reports WHERE project_id = {self.db._ph()}", (project_id,))
            cur.execute(f"DELETE FROM connections WHERE project_id = {self.db._ph()}", (project_id,))
            cur.execute(f"DELETE FROM devices WHERE project_id = {self.db._ph()}", (project_id,))
            cur.execute(f"DELETE FROM projects WHERE id = {self.db._ph()}", (project_id,))
            return cur.rowcount > 0

    def get_global_counts(self) -> dict:
        """Get total counts of devices, connections, and active projects."""
        with self.db._transaction() as cur:
            cur.execute("SELECT COUNT(*) FROM devices")
            total_devices = self.db._scalar(cur)
            cur.execute("SELECT COUNT(*) FROM connections")
            total_connections = self.db._scalar(cur)
            cur.execute("SELECT COUNT(*) FROM projects WHERE status = 'active'")
            active_projects = self.db._scalar(cur)
        return {
            "total_devices": total_devices,
            "total_connections": total_connections,
            "active_projects": active_projects,
        }
