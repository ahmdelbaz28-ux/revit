from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class SyncRepository(BaseRepository):
    """Repository handling sync queue status and operations."""

    def get_sync_status(self, project_id: str) -> dict | None:
        """Get sync status for a project."""
        with self.db._transaction() as cur:
            cur.execute(
                f"SELECT * FROM sync_status WHERE project_id = {self.db._ph()}",
                (project_id,),
            )
            row = cur.fetchone()
            if not row:
                return {
                    "projectId": project_id,
                    "status": "synced",
                    "lastSync": datetime.now(timezone.utc).isoformat(),
                    "pendingChanges": 0,
                    "error": None,
                }
        return self.db._row_to_sync(row)

    def set_sync_status(self, project_id: str, status: dict) -> dict:
        """Upsert sync status for a project."""
        with self.db._transaction() as cur:
            if self.db._is_postgres:
                cur.execute(
                    f"""
                    INSERT INTO sync_status (project_id, status, last_sync, pending_changes, error)
                    VALUES ({self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()})
                    ON CONFLICT (project_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        last_sync = EXCLUDED.last_sync,
                        pending_changes = EXCLUDED.pending_changes,
                        error = EXCLUDED.error
                    """,
                    (
                        project_id,
                        status.get("status", "syncing"),
                        status.get("lastSync", datetime.now(timezone.utc).isoformat()),
                        status.get("pendingChanges", 0),
                        status.get("error"),
                    ),
                )
            else:
                cur.execute(
                    f"""INSERT OR REPLACE INTO sync_status
                       (project_id, status, last_sync, pending_changes, error)
                       VALUES ({self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()})""",
                    (
                        project_id,
                        status.get("status", "syncing"),
                        status.get("lastSync", datetime.now(timezone.utc).isoformat()),
                        status.get("pendingChanges", 0),
                        status.get("error"),
                    ),
                )

        return self.get_sync_status(project_id)

    def record_sync(
        self,
        entity_type: str,
        entity_id: str,
        target_db: str,
        status: str,
        error: str | None = None,
    ) -> int:
        """Record a sync operation status."""
        now = datetime.now(timezone.utc).isoformat()

        with self.db._transaction() as cur:
            # Check for an existing pending/syncing record for this entity
            cur.execute(
                f"""SELECT id, status, retry_count FROM sync_operations
                   WHERE entity_type = {self.db._ph()} AND entity_id = {self.db._ph()} AND target_db = {self.db._ph()}
                   ORDER BY id DESC LIMIT 1""",
                (entity_type, entity_id, target_db),
            )
            existing = cur.fetchone()

            if existing and existing["status"] in ("pending", "syncing", "error"):
                # Update existing record
                row_id = existing["id"]
                retry_count = existing["retry_count"]
                if status == "error":
                    retry_count += 1
                cur.execute(
                    f"""UPDATE sync_operations
                       SET status = {self.db._ph()}, last_sync_at = {self.db._ph()}, error_message = {self.db._ph()}, retry_count = {self.db._ph()}
                       WHERE id = {self.db._ph()}""",
                    (status, now, error, retry_count, row_id),
                )
            else:
                # Insert new record
                cur.execute(
                    f"""INSERT INTO sync_operations
                       (entity_type, entity_id, target_db, status, last_sync_at,
                        error_message, retry_count)
                       VALUES ({self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, {self.db._ph()}, 0)""",
                    (entity_type, entity_id, target_db, status, now, error),
                )
                row_id = cur.lastrowid

        return row_id

    def get_pending_syncs(self, max_retries: int = 3) -> list:
        """Get sync operations that need to be retried."""
        with self.db._transaction() as cur:
            cur.execute(
                f"""SELECT * FROM sync_operations
                   WHERE status IN ('pending', 'error')
                     AND retry_count < {self.db._ph()}
                   ORDER BY id ASC""",
                (max_retries,),
            )
            rows = cur.fetchall()

        return [
            {
                "id": row["id"],
                "entityType": row["entity_type"],
                "entityId": row["entity_id"],
                "targetDb": row["target_db"],
                "status": row["status"],
                "lastSyncAt": row["last_sync_at"],
                "errorMessage": row["error_message"],
                "retryCount": row["retry_count"],
            }
            for row in rows
        ]
