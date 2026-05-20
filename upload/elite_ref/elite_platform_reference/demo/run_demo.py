"""Executable demo for the elite platform reference."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elite_platform.connector_journal import ConnectorJournal
from elite_platform.evidence_ledger import EvidenceLedger
from elite_platform.models import BuildingSnapshot, RoomGeometry
from elite_platform.placement_service import PlacementService
from elite_platform.twin_store import TwinStateStore


def build_demo_snapshot(snapshot_id, revision_id, room_polygon):
    room = RoomGeometry(
        room_id="R-101",
        name="Control Room",
        floor_id="L1",
        polygon=room_polygon,
        ceiling_height_m=3.2,
        use_type="critical_ops",
    )
    service = PlacementService(default_spacing_m=4.0, default_radius_m=5.7)
    record = service.analyze_room(room)
    return BuildingSnapshot(
        snapshot_id=snapshot_id,
        revision_id=revision_id,
        created_at=datetime.utcnow().isoformat() + "Z",
        source_system="reference-demo",
        source_model_id="revit://tower-a/level-1",
        room_records=[record],
    )


def main():
    artifacts_dir = ROOT / "artifacts"
    twin_dir = artifacts_dir / "twin_store"
    artifacts_dir.mkdir(exist_ok=True)
    twin_dir.mkdir(exist_ok=True)

    snapshot_a = build_demo_snapshot(
        "snapshot-a",
        "rev-001",
        [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
    )
    snapshot_b = build_demo_snapshot(
        "snapshot-b",
        "rev-002",
        [(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0)],
    )

    store = TwinStateStore(twin_dir)
    store.save_snapshot(snapshot_a)
    store.save_snapshot(snapshot_b)
    drift = store.diff_snapshots("snapshot-a", "snapshot-b")

    ledger = EvidenceLedger(secret_key="elite-secret")
    manifest = ledger.build_manifest(
        snapshot=snapshot_b,
        solver_version="elite-platform/0.1.0",
        rule_bundle_version="nfpa72-2022/reference",
    )

    journal = ConnectorJournal()
    journal.register_revision("revit", "revit://tower-a/level-1", "rev-002", "snapshot-b")
    drift_status = journal.detect_revision_drift("revit://tower-a/level-1", "rev-003")

    output = {
        "manifest_valid": ledger.verify_manifest(manifest),
        "drift_count": len(drift),
        "drift_types": [item.drift_type for item in drift],
        "connector_status": drift_status,
    }
    (artifacts_dir / "demo_output.json").write_text(
        json.dumps(output, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
