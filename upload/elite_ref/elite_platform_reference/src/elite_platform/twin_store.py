"""Persistent twin snapshot storage and deterministic diffing."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from .models import BuildingSnapshot, DriftRecord


class TwinStateStore(object):
    """File-backed snapshot store to avoid memory-only history."""

    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot):
        path = self.root_dir / (snapshot.snapshot_id + ".json")
        payload = {
            "snapshot_id": snapshot.snapshot_id,
            "revision_id": snapshot.revision_id,
            "created_at": snapshot.created_at,
            "source_system": snapshot.source_system,
            "source_model_id": snapshot.source_model_id,
            "room_records": [self._record_to_dict(record) for record in snapshot.room_records],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def load_snapshot(self, snapshot_id):
        path = self.root_dir / (snapshot_id + ".json")
        return json.loads(path.read_text(encoding="utf-8"))

    def diff_snapshots(self, old_snapshot_id, new_snapshot_id):
        old = self.load_snapshot(old_snapshot_id)
        new = self.load_snapshot(new_snapshot_id)
        return self._diff_loaded_snapshots(old, new)

    def _diff_loaded_snapshots(self, old, new):
        old_rooms = self._room_map(old)
        new_rooms = self._room_map(new)
        room_ids = sorted(set(old_rooms.keys()) | set(new_rooms.keys()))
        drift = []

        for room_id in room_ids:
            old_record = old_rooms.get(room_id)
            new_record = new_rooms.get(room_id)
            if old_record is None:
                drift.append(
                    DriftRecord(room_id=room_id, drift_type="room_added", details={"new": new_record})
                )
                continue
            if new_record is None:
                drift.append(
                    DriftRecord(room_id=room_id, drift_type="room_removed", details={"old": old_record})
                )
                continue

            if old_record["room"]["polygon"] != new_record["room"]["polygon"]:
                drift.append(
                    DriftRecord(
                        room_id=room_id,
                        drift_type="geometry_changed",
                        details={
                            "old_polygon": old_record["room"]["polygon"],
                            "new_polygon": new_record["room"]["polygon"],
                        },
                    )
                )

            old_detectors = self._detector_map(old_record["detectors"])
            new_detectors = self._detector_map(new_record["detectors"])
            detector_ids = sorted(set(old_detectors.keys()) | set(new_detectors.keys()))
            for detector_id in detector_ids:
                old_detector = old_detectors.get(detector_id)
                new_detector = new_detectors.get(detector_id)
                if old_detector is None:
                    drift.append(
                        DriftRecord(
                            room_id=room_id,
                            drift_type="detector_added",
                            details={"detector": new_detector},
                        )
                    )
                    continue
                if new_detector is None:
                    drift.append(
                        DriftRecord(
                            room_id=room_id,
                            drift_type="detector_removed",
                            details={"detector": old_detector},
                        )
                    )
                    continue
                old_pos = (old_detector["x"], old_detector["y"], old_detector["z"])
                new_pos = (new_detector["x"], new_detector["y"], new_detector["z"])
                if old_pos != new_pos:
                    drift.append(
                        DriftRecord(
                            room_id=room_id,
                            drift_type="detector_moved",
                            details={
                                "detector_id": detector_id,
                                "old_position": old_pos,
                                "new_position": new_pos,
                            },
                        )
                    )
        return drift

    def _room_map(self, snapshot_payload):
        return {
            record["room"]["room_id"]: record
            for record in snapshot_payload["room_records"]
        }

    def _detector_map(self, detectors):
        return {detector["detector_id"]: detector for detector in detectors}

    def _record_to_dict(self, record):
        room = {
            "room_id": record.room.room_id,
            "name": record.room.name,
            "floor_id": record.room.floor_id,
            "polygon": record.room.polygon,
            "ceiling_height_m": record.room.ceiling_height_m,
            "use_type": record.room.use_type,
        }
        detectors = [
            {
                "detector_id": detector.detector_id,
                "room_id": detector.room_id,
                "x": detector.x,
                "y": detector.y,
                "z": detector.z,
                "detector_type": detector.detector_type,
                "coverage_radius_m": detector.coverage_radius_m,
            }
            for detector in record.detectors
        ]
        return {
            "room": room,
            "detectors": detectors,
            "rule_decisions": [asdict(rule) for rule in record.rule_decisions],
            "metadata": dict(record.metadata),
        }
