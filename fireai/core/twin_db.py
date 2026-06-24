"""twin_db.py — SQLite-Backed Twin System of Record
=================================================
Adapted from Elite Platform V2 twin_db.py.

Provides persistent storage for building snapshots, analysis results,
and evidence envelopes using SQLite. This replaces memory-only storage
with a durable, queryable database that survives restarts.

Key features:
  - Save complete snapshot + analysis + evidence envelope as one bundle
  - Load any historical snapshot by ID
  - Diff two snapshots to detect drift (geometry, detectors, positions)
  - Track connector (BIM/IFC) revisions per source model

Usage:
    from fireai.core.twin_db import TwinSystemOfRecord

    db = TwinSystemOfRecord("/path/to/elite.db")
    db.save_snapshot(snapshot, analysis, envelope)
    bundle = db.load_snapshot_bundle("S-1")
    drift = db.diff_snapshots("S-1", "S-2")
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional


class TwinSystemOfRecord:
    """SQLite-backed twin snapshot store with drift detection.

    All data is stored in a single SQLite database file.
    Thread safety: uses a new connection per operation (safe for
    multi-threaded web servers, but NOT for concurrent writes from
    multiple processes — use WAL mode if needed).
    """

    def __init__(self, db_path: str):
        """Initialize the twin database.

        Args:
            db_path: Path to the SQLite database file.
                     Created automatically if it doesn't exist.

        """
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Create a new database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
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
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_connector_source
                ON connector_revisions (source_model_id, created_at DESC)
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_snapshot(
        self,
        snapshot_payload: Dict[str, Any],
        analysis_payload: Dict[str, Any],
        envelope: Dict[str, Any],
    ) -> None:
        """Save a complete snapshot bundle to the database.

        STRENGTHENED: Validates snapshot_id is non-empty before saving.
        An empty snapshot_id would create a corrupt record that overwrites
        any previous record with empty key (INSERT OR REPLACE).

        Args:
            snapshot_payload: Building snapshot data (rooms, geometry).
            analysis_payload: Analysis results (detector placements).
            envelope:         Signed evidence envelope.

        Raises:
            ValueError: If snapshot_id is missing or empty.

        """
        snapshot_id = snapshot_payload.get("snapshot_id", "")
        if not snapshot_id or not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ValueError(
                "snapshot_payload must have a non-empty 'snapshot_id' field. "
                "An empty ID would create a corrupt database record."
            )

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO snapshots (
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
                    snapshot_id,
                    snapshot_payload.get("revision_id", ""),
                    snapshot_payload.get("source_model_id", ""),
                    json.dumps(snapshot_payload, sort_keys=True),
                    json.dumps(analysis_payload, sort_keys=True),
                    json.dumps(envelope, sort_keys=True),
                    envelope.get("created_at", ""),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def load_snapshot_bundle(self, snapshot_id: str) -> Dict[str, Any]:
        """Load a complete snapshot bundle by ID.

        Args:
            snapshot_id: The snapshot ID to load.

        Returns:
            Dictionary with 'snapshot', 'analysis', and 'envelope' keys.

        Raises:
            KeyError: If snapshot_id not found.

        """
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
                raise KeyError(f"Snapshot not found: {snapshot_id}")
            return {
                "snapshot": json.loads(row[0]),
                "analysis": json.loads(row[1]),
                "envelope": json.loads(row[2]),
            }
        finally:
            conn.close()

    def register_connector_revision(
        self,
        connector_name: str,
        source_model_id: str,
        revision_id: str,
        snapshot_id: str,
        created_at: str,
    ) -> None:
        """Register a connector (BIM/IFC) revision.

        Args:
            connector_name:   Name of the connector (e.g. "revit", "ifc").
            source_model_id:  External model identifier.
            revision_id:      Revision ID from the source system.
            snapshot_id:      The snapshot this revision produced.
            created_at:       ISO timestamp.

        """
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO connector_revisions (
                    connector_name, source_model_id, revision_id,
                    snapshot_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (connector_name, source_model_id, revision_id, snapshot_id, created_at),
            )
            conn.commit()
        finally:
            conn.close()

    def latest_connector_revision(self, source_model_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest connector revision for a source model.

        Args:
            source_model_id: External model identifier.

        Returns:
            Dictionary with connector details, or None if not found.

        """
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT connector_name, source_model_id, revision_id,
                       snapshot_id, created_at
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

    # Minimum movement distance (meters) to count as "moved".
    # Prevents false drift alerts from floating-point rounding.
    # 0.01m = 10mm — any movement under 1cm is negligible for fire safety.
    MOVEMENT_THRESHOLD_M = 0.01

    # Polygon point comparison tolerance (meters).
    # Points within this distance are considered identical.
    POLYGON_TOLERANCE_M = 0.005  # 5mm

    def diff_snapshots(
        self,
        old_snapshot_id: str,
        new_snapshot_id: str,
        movement_threshold_m: Optional[float] = None,
        polygon_tolerance_m: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Diff two snapshots to detect drift.

        Compares rooms (added, removed, geometry changed) and
        detectors (added, removed, moved).

        STRENGTHENED: Uses floating-point tolerance for polygon and
        position comparisons. The original code used exact equality
        (==), which triggered false drift alerts from 0.001mm
        floating-point differences.

        Args:
            old_snapshot_id: Earlier snapshot ID.
            new_snapshot_id: Later snapshot ID.
            movement_threshold_m: Min distance to count as "moved".
            polygon_tolerance_m: Tolerance for polygon point comparison.

        Returns:
            List of drift records with room_id, drift_type, and details.

        """
        old_bundle = self.load_snapshot_bundle(old_snapshot_id)
        new_bundle = self.load_snapshot_bundle(new_snapshot_id)

        old_rooms = {room.get("room_id"): room for room in old_bundle["snapshot"].get("rooms", [])}
        new_rooms = {room.get("room_id"): room for room in new_bundle["snapshot"].get("rooms", [])}
        old_results = {item.get("room_id"): item for item in old_bundle["analysis"].get("room_results", [])}
        new_results = {item.get("room_id"): item for item in new_bundle["analysis"].get("room_results", [])}

        drift: List[Dict[str, Any]] = []
        for room_id in sorted(set(old_rooms.keys()) | set(new_rooms.keys())):
            old_room = old_rooms.get(room_id)
            new_room = new_rooms.get(room_id)

            if old_room is None:
                drift.append({"room_id": room_id, "drift_type": "room_added"})
                continue
            if new_room is None:
                drift.append({"room_id": room_id, "drift_type": "room_removed"})
                continue

            # Geometry change — STRENGTHENED: use tolerance instead of exact equality
            old_polygon = old_room.get("polygon", [])
            new_polygon = new_room.get("polygon", [])
            if not self._polygons_approx_equal(
                old_polygon, new_polygon, tolerance_m=polygon_tolerance_m or self.POLYGON_TOLERANCE_M
            ):
                drift.append(
                    {
                        "room_id": room_id,
                        "drift_type": "geometry_changed",
                        "detail": "Room polygon geometry changed beyond tolerance",
                    }
                )

            # STRENGTHENED v2: Ceiling height change detection.
            # Ceiling height directly affects detector spacing per NFPA 72
            # §17.6.3.1.1 — a 3m room uses 9.1m spacing, but a 6m room uses
            # 7.3m spacing. Missing this drift = wrong detector count.
            CEILING_HEIGHT_TOLERANCE_M = 0.01  # 10mm tolerance
            old_h = old_room.get("ceiling_height_m")
            new_h = new_room.get("ceiling_height_m")
            if old_h is not None and new_h is not None:
                try:
                    h_diff = abs(float(new_h) - float(old_h))
                    if h_diff > CEILING_HEIGHT_TOLERANCE_M:
                        drift.append(
                            {
                                "room_id": room_id,
                                "drift_type": "ceiling_height_changed",
                                "old_height_m": float(old_h),
                                "new_height_m": float(new_h),
                                "height_diff_m": round(h_diff, 4),
                                "detail": (
                                    f"Ceiling height changed from {float(old_h):.2f}m to "
                                    f"{float(new_h):.2f}m — affects detector spacing per "
                                    f"NFPA 72 §17.6.3.1.1"
                                ),
                            }
                        )
                except (TypeError, ValueError):
                    pass  # Non-numeric heights — skip comparison

            # STRENGTHENED v2: Detector type change detection.
            # Switching from SMOKE to HEAT changes spacing from 9.1m to 6.1m.
            # This is a critical design parameter change.
            old_dtype = old_room.get("detector_type")
            new_dtype = new_room.get("detector_type")
            if old_dtype is not None and new_dtype is not None and old_dtype != new_dtype:
                drift.append(
                    {
                        "room_id": room_id,
                        "drift_type": "detector_type_changed",
                        "old_type": old_dtype,
                        "new_type": new_dtype,
                        "detail": (
                            f"Detector type changed from {old_dtype} to {new_dtype} — "
                            f"changes spacing requirements per NFPA 72"
                        ),
                    }
                )

            # Detector changes
            old_detectors = {d.get("detector_id"): d for d in old_results.get(room_id, {}).get("detectors", [])}
            new_detectors = {d.get("detector_id"): d for d in new_results.get(room_id, {}).get("detectors", [])}
            for det_id in sorted(set(old_detectors.keys()) | set(new_detectors.keys())):
                old_det = old_detectors.get(det_id)
                new_det = new_detectors.get(det_id)
                if old_det is None:
                    drift.append(
                        {
                            "room_id": room_id,
                            "drift_type": "detector_added",
                            "detector_id": det_id,
                        }
                    )
                    continue
                if new_det is None:
                    drift.append(
                        {
                            "room_id": room_id,
                            "drift_type": "detector_removed",
                            "detector_id": det_id,
                        }
                    )
                    continue
                old_pos = (old_det.get("x"), old_det.get("y"), old_det.get("z"))
                new_pos = (new_det.get("x"), new_det.get("y"), new_det.get("z"))
                # STRENGTHENED: only flag movement above threshold
                move_dist = self._position_distance(old_pos, new_pos)
                threshold = movement_threshold_m or self.MOVEMENT_THRESHOLD_M
                if move_dist > threshold:
                    drift.append(
                        {
                            "room_id": room_id,
                            "drift_type": "detector_moved",
                            "detector_id": det_id,
                            "old_position": old_pos,
                            "new_position": new_pos,
                            "move_distance_m": round(move_dist, 4),
                        }
                    )

        return drift

    def list_snapshot_ids(self) -> List[str]:
        """List all snapshot IDs in the database, newest first."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT snapshot_id FROM snapshots ORDER BY created_at DESC").fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _position_distance(pos_a: tuple, pos_b: tuple) -> float:
        """Euclidean distance between two 3D positions.

        Handles None coordinates by treating them as 0.0.
        """
        import math

        ax, ay = float(pos_a[0] or 0), float(pos_a[1] or 0)
        az = float(pos_a[2] or 0) if len(pos_a) > 2 else 0.0
        bx, by = float(pos_b[0] or 0), float(pos_b[1] or 0)
        bz = float(pos_b[2] or 0) if len(pos_b) > 2 else 0.0
        return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)

    @staticmethod
    def _polygons_approx_equal(poly_a: list, poly_b: list, tolerance_m: float = 0.005) -> bool:
        """Check if two polygons are approximately equal within tolerance.

        Compares point-by-point. Returns False if:
          - Different number of points
          - Any corresponding points differ by more than tolerance_m
        """
        if len(poly_a) != len(poly_b):
            return False
        for pa, pb in zip(poly_a, poly_b, strict=False):
            # Handle tuples, lists, or dict representations
            if isinstance(pa, dict):
                ax, ay = float(pa.get("x", 0)), float(pa.get("y", 0))
            elif isinstance(pa, (list, tuple)) and len(pa) >= 2:
                ax, ay = float(pa[0]), float(pa[1])
            else:
                return False
            if isinstance(pb, dict):
                bx, by = float(pb.get("x", 0)), float(pb.get("y", 0))
            elif isinstance(pb, (list, tuple)) and len(pb) >= 2:
                bx, by = float(pb[0]), float(pb[1])
            else:
                return False
            dist = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
            if dist > tolerance_m:
                return False
        return True


__all__ = ["TwinSystemOfRecord"]
