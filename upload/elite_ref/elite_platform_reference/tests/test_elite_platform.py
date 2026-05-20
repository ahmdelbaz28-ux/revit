from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elite_platform.connector_journal import ConnectorJournal
from elite_platform.evidence_ledger import EvidenceLedger
from elite_platform.geometry_kernel import bounding_box, point_in_polygon, polygon_area
from elite_platform.models import BuildingSnapshot, RoomGeometry
from elite_platform.placement_service import PlacementService
from elite_platform.twin_store import TwinStateStore


def _snapshot(snapshot_id, revision_id, polygon):
    room = RoomGeometry(
        room_id="R-1",
        name="Ops",
        floor_id="L1",
        polygon=polygon,
        ceiling_height_m=3.0,
    )
    record = PlacementService(default_spacing_m=4.0).analyze_room(room)
    return BuildingSnapshot(
        snapshot_id=snapshot_id,
        revision_id=revision_id,
        created_at=datetime.utcnow().isoformat() + "Z",
        source_system="pytest",
        source_model_id="revit://ops/l1",
        room_records=[record],
    )


def test_polygon_metrics_are_derived_from_polygon():
    polygon = [(10.0, 20.0), (18.0, 20.0), (18.0, 26.0), (10.0, 26.0)]
    box = bounding_box(polygon)
    assert box["width_m"] == 8.0
    assert box["depth_m"] == 6.0
    assert polygon_area(polygon) == 48.0


def test_candidate_detector_is_inside_polygon():
    snapshot = _snapshot(
        "snap-1",
        "rev-1",
        [(0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0)],
    )
    detector = snapshot.room_records[0].detectors[0]
    room_polygon = snapshot.room_records[0].room.polygon
    assert point_in_polygon((detector.x, detector.y), room_polygon)


def test_evidence_ledger_detects_tampering():
    snapshot = _snapshot(
        "snap-2",
        "rev-2",
        [(0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0)],
    )
    ledger = EvidenceLedger(secret_key="test-secret")
    manifest = ledger.build_manifest(snapshot, "solver-1", "rules-1")
    assert ledger.verify_manifest(manifest) is True

    tampered = dict(manifest)
    tampered["room_hashes"] = dict(tampered["room_hashes"])
    tampered["room_hashes"]["R-1"] = "bad-hash"
    assert ledger.verify_manifest(tampered) is False


def test_twin_state_store_diff_is_version_based(tmp_path):
    store = TwinStateStore(tmp_path)
    store.save_snapshot(
        _snapshot(
            "snap-a",
            "rev-a",
            [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
        )
    )
    store.save_snapshot(
        _snapshot(
            "snap-b",
            "rev-b",
            [(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0)],
        )
    )
    drift = store.diff_snapshots("snap-a", "snap-b")
    assert any(item.drift_type == "geometry_changed" for item in drift)


def test_connector_journal_detects_external_revision_drift():
    journal = ConnectorJournal()
    journal.register_revision("revit", "revit://ops/l1", "rev-7", "snap-7")
    status = journal.detect_revision_drift("revit://ops/l1", "rev-8")
    assert status["status"] == "drift_detected"
    assert status["expected_revision_id"] == "rev-7"
