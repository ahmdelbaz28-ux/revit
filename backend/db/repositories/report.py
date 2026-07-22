from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from backend.db.repositories.base import BaseRepository


class ReportRepository(BaseRepository):
    """Repository handling report CRUD operations."""

    def create_report(self, project_id: str, report_data: dict) -> dict:
        """Insert a new report and return it."""
        now = datetime.now(timezone.utc).isoformat()
        report_data.setdefault("id", str(uuid.uuid4()))
        report_data["projectId"] = project_id
        report_data["createdAt"] = now
        report_data.setdefault("name", "")
        report_data.setdefault("parameters", {})
        report_data.setdefault("status", "pending")
        report_data["completedAt"] = None

        params_json = json.dumps(report_data["parameters"])

        with self.db._transaction() as cur:
            cur.execute(
                f"""INSERT INTO reports
                   (id, project_id, type, name, parameters, status, created_at, completed_at)
                   VALUES ({self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()})""",
                (
                    report_data["id"],
                    project_id,
                    report_data["type"],
                    report_data["name"],
                    params_json,
                    report_data["status"],
                    report_data["createdAt"],
                    report_data["completedAt"],
                ),
            )

        return self.get_report(project_id, report_data["id"])

    def get_report(self, project_id: str, report_id: str) -> dict | None:
        """Get a report by ID within a project."""
        with self.db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM reports WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                (report_id, project_id),
            )
            row = cur.fetchone()
            if not row:
                return None
        return self.db._row_to_report(row)

    def list_reports(
        self,
        project_id: str,
        page: int = 1,
        limit: int = 20,
        sort: str = "created_at",
        order: str = "desc",
    ) -> dict:
        """List reports in a project with pagination."""
        _ALLOWED_REPORT_SORTS = frozenset({"id", "created_at", "type", "status", "name"})
        if sort not in _ALLOWED_REPORT_SORTS:
            sort = "created_at"
        order = "ASC" if order.upper() == "ASC" else "DESC"

        with self.db._transaction() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM reports WHERE project_id = {self.db._ph()}",
                (project_id,),
            )
            total = self.db._scalar(cur)

            offset = (page - 1) * limit
            cur.execute(
                f"SELECT * FROM reports WHERE project_id = {self.db._ph()} ORDER BY {sort} {order} LIMIT {self.db._ph()} OFFSET {self.db._ph()}",
                (project_id, limit, offset),
            )
            rows = cur.fetchall()

        reports = [self.db._row_to_report(row) for row in rows]
        total_pages = max(1, (total + limit - 1) // limit)
        return {
            "data": reports,
            "total": total,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        }

    def update_report(self, project_id: str, report_id: str, updates: dict) -> dict | None:
        """Update a report. Returns updated report or None if not found."""
        set_clauses = []
        values = []

        simple_fields = {
            "status": "status",
            "name": "name",
            "completedAt": "completed_at",
        }
        for api_field, db_field in simple_fields.items():
            if api_field in updates and updates[api_field] is not None:
                set_clauses.append(f"{db_field} = {self.db._ph()}")
                values.append(updates[api_field])

        if "parameters" in updates and updates["parameters"] is not None:
            set_clauses.append(f"parameters = {self.db._ph()}")
            values.append(json.dumps(updates["parameters"]))

        if not set_clauses:
            return self.get_report(project_id, report_id)

        values.extend([report_id, project_id])
        with self.db._transaction() as cur:
            cur.execute(
                f"UPDATE reports SET {', '.join(set_clauses)} WHERE id = {self.db._ph()} AND project_id = {self.db._ph()}",
                values,
            )

        return self.get_report(project_id, report_id)
