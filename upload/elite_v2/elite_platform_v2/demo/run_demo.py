"""V2 demo."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import uuid

from elite_platform_v2.contracts import RoomContract
from elite_platform_v2.evidence_chain import EvidenceChain
from elite_platform_v2.placement import analyze_room
from elite_platform_v2.release_gates import evaluate_release
from elite_platform_v2.twin_db import TwinSystemOfRecord


def build_snapshot(snapshot_id, revision_id, polygon):
    room = RoomContract.from_payload(
        {
            "room_id": "R-500",
            "name": "Mission Control",
            "floor_id": "L5",
            "polygon": polygon,
            "ceiling_height_m": 3.5,
            "use_type": "critical_ops",
        }
    )
    room_result = analyze_room(room, spacing_m=4.0, coverage_radius_m=5.7)
    snapshot_payload = {
        "snapshot_id": snapshot_id,
        "revision_id": revision_id,
        "source_system": "v2-demo",
        "source_model_id": "revit://hq/level-5",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "rooms": [room.to_payload()],
    }
    analysis_payload = {
        "snapshot_id": snapshot_id,
        "room_results": [room_result],
    }
    return snapshot_payload, analysis_payload


def main():
    root = Path(__file__).resolve().parents[1]
    artifacts_dir = root / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    db_path = artifacts_dir / ("elite_v2_%s.db" % uuid.uuid4().hex[:8])

    twin = TwinSystemOfRecord(str(db_path))
    chain = EvidenceChain(secret_key="elite-v2-secret", signer_id="chief-rd")

    snapshot_a, analysis_a = build_snapshot(
        "v2-snap-a",
        "rev-101",
        [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)],
    )
    envelope_a = chain.build_envelope(snapshot_a, analysis_a)
    twin.save_snapshot(snapshot_a, analysis_a, envelope_a)
    twin.register_connector_revision(
        "revit",
        snapshot_a["source_model_id"],
        snapshot_a["revision_id"],
        snapshot_a["snapshot_id"],
        envelope_a["created_at"],
    )

    snapshot_b, analysis_b = build_snapshot(
        "v2-snap-b",
        "rev-102",
        [(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0)],
    )
    envelope_b = chain.build_envelope(snapshot_b, analysis_b, previous_envelope=envelope_a)
    twin.save_snapshot(snapshot_b, analysis_b, envelope_b)
    twin.register_connector_revision(
        "revit",
        snapshot_b["source_model_id"],
        snapshot_b["revision_id"],
        snapshot_b["snapshot_id"],
        envelope_b["created_at"],
    )

    drift = twin.diff_snapshots("v2-snap-a", "v2-snap-b")
    latest_revision = twin.latest_connector_revision("revit://hq/level-5")
    release = evaluate_release(
        {
            "canonical_geometry": True,
            "evidence_chain_valid": chain.verify_envelope(
                envelope_b, snapshot_b, analysis_b, previous_envelope=envelope_a
            ),
            "connector_in_sync": latest_revision["revision_id"] == "rev-102",
            "version_authority_valid": True,
            "stale_surfaces_removed": True,
        }
    )

    output = {
        "db_path": str(db_path),
        "drift_count": len(drift),
        "drift": drift,
        "latest_revision": latest_revision,
        "release": release,
        "evidence_chain_valid": chain.verify_envelope(
            envelope_b, snapshot_b, analysis_b, previous_envelope=envelope_a
        ),
    }
    output_path = artifacts_dir / "demo_output_v2.json"
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
