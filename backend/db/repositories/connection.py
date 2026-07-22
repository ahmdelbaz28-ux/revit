from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from backend.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ConnectionRepository(BaseRepository):
    """Repository handling connection CRUD operations."""

    def create_connection(self, project_id: str, conn_data: dict) -> dict:
        """Insert a new connection and return it."""
        now = datetime.now(timezone.utc).isoformat()
        conn_data.setdefault("id", str(uuid.uuid4()))
        conn_data["projectId"] = project_id
        conn_data["createdAt"] = now
        conn_data.setdefault("cableSize", "1.5mm²")
        conn_data.setdefault("length", 0.0)
        conn_data.setdefault("type", "power")

        with self.db._transaction() as cur:
            # Validate that both devices exist in this project
            from_id = conn_data["fromId"]
            to_id = conn_data["toId"]
            cur.execute(
                f"SELECT id FROM devices WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                (from_id, project_id),
            )
            if not cur.fetchone():
                raise ValueError(
                    f"Cannot create connection: from_id '{from_id}' does not exist in project '{project_id}'"
                )
            cur.execute(
                f"SELECT id FROM devices WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                (to_id, project_id),
            )
            if not cur.fetchone():
                raise ValueError(f"Cannot create connection: to_id '{to_id}' does not exist in project '{project_id}'")

            cur.execute(
                f"""INSERT INTO connections
                   (id, project_id, from_id, to_id, cable_size, length, type, created_at)
                   VALUES ({self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()})""",
                (
                    conn_data["id"],
                    project_id,
                    conn_data["fromId"],
                    conn_data["toId"],
                    conn_data["cableSize"],
                    conn_data["length"],
                    conn_data["type"],
                    conn_data["createdAt"],
                ),
            )

        return self.get_connection(project_id, conn_data["id"])

    def get_connection(self, project_id: str, connection_id: str) -> dict | None:
        """Get a connection by ID within a project."""
        with self.db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM connections WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                (connection_id, project_id),
            )
            row = cur.fetchone()
            if not row:
                return None
        return self.db._row_to_connection(row)

    def list_connections(
        self,
        project_id: str,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """List connections in a project with pagination."""
        _ALLOWED_CONNECTION_SORTS = frozenset({"id", "created_at", "type", "length", "cable_size"})
        if sort not in _ALLOWED_CONNECTION_SORTS:
            sort = "created_at"
        order = "ASC" if order.upper() == "ASC" else "DESC"

        with self.db._transaction() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM connections WHERE project_id = {self.db._ph()}",
                (project_id,),
            )
            total = self.db._scalar(cur)

            offset = (page - 1) * limit
            cur.execute(
                f"SELECT * FROM connections WHERE project_id = {self.db._ph()} ORDER BY {sort} {order} LIMIT {self.db._ph()} OFFSET {self.db._ph()}",
                (project_id, limit, offset),
            )
            rows = cur.fetchall()

        connections = [self.db._row_to_connection(row) for row in rows]
        total_pages = max(1, (total + limit - 1) // limit)
        return {
            "data": connections,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        }

    def delete_connection(self, project_id: str, connection_id: str) -> bool:
        """Delete a connection."""
        with self.db._transaction() as cur:
            cur.execute(
                f"DELETE FROM connections WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                (connection_id, project_id),
            )
            return cur.rowcount > 0

    def update_connection(self, project_id: str, connection_id: str, updates: dict) -> dict | None:
        """Update specific fields of a connection."""
        connection = self.get_connection(project_id, connection_id)
        if not connection:
            return None

        _FIELD_MAP = {
            "cableSize": "cable_size",
            "length": "length",
            "type": "type",
            "fromId": "from_id",
            "toId": "to_id",
        }
        set_parts = []
        values = []
        for field, value in updates.items():
            if field in _FIELD_MAP:
                set_parts.append(f"{_FIELD_MAP[field]} = {self.db._ph()}")
                values.append(value)

        if not set_parts:
            return connection

        values.append(connection_id)
        values.append(project_id)

        with self.db._transaction() as cur:
            cur.execute(
                f"UPDATE connections SET {', '.join(set_parts)} WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                values,
            )
            if cur.rowcount == 0:
                return None

        return self.get_connection(project_id, connection_id)

    def get_all_connections_for_project(self, project_id: str) -> list[dict]:
        """Get ALL connections for a project (used for exports)."""
        with self.db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM connections WHERE project_id = {self.db._ph()}",
                (project_id,),
            )
            rows = cur.fetchall()
        return [self.db._row_to_connection(row) for row in rows]
