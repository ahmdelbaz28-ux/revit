"""SQLite-backed twin system of record."""

from __future__ import annotations

import json
import sqlite3


class TwinSystemOfRecord(object):
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL,
                    source_model_id TEXT NOT NULL,
                    snapshot_payload_json TEXT NOT NULL,
                    analysis_payload_json TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_revisions (
                    connector_name TEXT NOT NULL,
                    source_model_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_snapshot(self, snapshot_payload, analysis_payload, envelope):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO snapshots (
                    snapshot_id,
                    revision_id,
                    source_model_id,
                    snapshot_payload_json,
                    analysis_payload_json,
                    envelope_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_payload["snapshot_id"],
                    snapshot_payload["revision_id"],
                    snapshot_payload["source_model_id"],
                    json.dumps(snapshot_payload, sort_keys=True),
                    json.dumps(analysis_payload, sort_keys=True),
                    json.dumps(envelope, sort_keys=True),
                    envelope["created_at"],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def load_snapshot_bundle(self, snapshot_id):
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT snapshot_payload_json, analysis_payload_json, envelope_json
                FROM snapshots
                WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchone()
            if row is None:
                raise KeyError("snapshot not found: %s" % snapshot_id)
            return {
                "snapshot": json.loads(row[0]),
                "analysis": json.loads(row[1]),
                "envelope": json.loads(row[2]),
            }
        finally:
            conn.close()

    def register_connector_revision(self, connector_name, source_model_id, revision_id, snapshot_id, created_at):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO connector_revisions (
                    connector_name,
                    source_model_id,
                    revision_id,
                    snapshot_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (connector_name, source_model_id, revision_id, snapshot_id, created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def latest_connector_revision(self, source_model_id):
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT connector_name, source_model_id, revision_id, snapshot_id, created_at
                FROM connector_revisions
                WHERE source_model_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (source_model_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "connector_name": row[0],
                "source_model_id": row[1],
                "revision_id": row[2],
                "snapshot_id": row[3],
                "created_at": row[4],
            }
        finally:
            conn.close()

    def diff_snapshots(self, old_snapshot_id, new_snapshot_id):
        old_bundle = self.load_snapshot_bundle(old_snapshot_id)
        new_bundle = self.load_snapshot_bundle(new_snapshot_id)

        old_rooms = {
            room["room_id"]: room for room in old_bundle["snapshot"]["rooms"]
        }
        new_rooms = {
            room["room_id"]: room for room in new_bundle["snapshot"]["rooms"]
        }
        old_results = {
            item["room_id"]: item for item in old_bundle["analysis"]["room_results"]
        }
        new_results = {
            item["room_id"]: item for item in new_bundle["analysis"]["room_results"]
        }

        drift = []
        for room_id in sorted(set(old_rooms.keys()) | set(new_rooms.keys())):
            old_room = old_rooms.get(room_id)
            new_room = new_rooms.get(room_id)
            if old_room is None:
                drift.append({"room_id": room_id, "drift_type": "room_added"})
                continue
            if new_room is None:
                drift.append({"room_id": room_id, "drift_type": "room_removed"})
                continue
            if old_room["polygon"] != new_room["polygon"]:
                drift.append({"room_id": room_id, "drift_type": "geometry_changed"})

            old_detectors = {
                item["detector_id"]: item
                for item in old_results.get(room_id, {}).get("detectors", [])
            }
            new_detectors = {
                item["detector_id"]: item
                for item in new_results.get(room_id, {}).get("detectors", [])
            }
            for detector_id in sorted(set(old_detectors.keys()) | set(new_detectors.keys())):
                old_detector = old_detectors.get(detector_id)
                new_detector = new_detectors.get(detector_id)
                if old_detector is None:
                    drift.append({"room_id": room_id, "drift_type": "detector_added", "detector_id": detector_id})
                    continue
                if new_detector is None:
                    drift.append({"room_id": room_id, "drift_type": "detector_removed", "detector_id": detector_id})
                    continue
                old_position = (old_detector["x"], old_detector["y"], old_detector["z"])
                new_position = (new_detector["x"], new_detector["y"], new_detector["z"])
                if old_position != new_position:
                    drift.append({"room_id": room_id, "drift_type": "detector_moved", "detector_id": detector_id})
        return drift
