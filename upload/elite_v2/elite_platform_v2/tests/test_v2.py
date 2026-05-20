from __future__ import annotations

from elite_platform_v2.contracts import ContractViolation, RoomContract
from elite_platform_v2.evidence_chain import EvidenceChain
from elite_platform_v2.geometry import GeometryValidationError, polygon_area
from elite_platform_v2.placement import analyze_room
from elite_platform_v2.release_gates import evaluate_release
from elite_platform_v2.twin_db import TwinSystemOfRecord


def _room_payload(polygon):
    return {
        "room_id": "R-1",
        "name": "Ops",
        "floor_id": "L1",
        "polygon": polygon,
        "ceiling_height_m": 3.0,
    }


def test_contract_rejects_derived_field_injection():
    payload = _room_payload([(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)])
    payload["width_m"] = 999.0
    try:
        RoomContract.from_payload(payload)
    except ContractViolation as exc:
        assert "derived internally" in str(exc)
    else:
        raise AssertionError("derived field injection must be rejected")


def test_contract_rejects_self_intersecting_polygon():
    try:
        RoomContract.from_payload(
            _room_payload([(0.0, 0.0), (4.0, 4.0), (0.0, 4.0), (4.0, 0.0)])
        )
    except GeometryValidationError as exc:
        assert "self-intersect" in str(exc)
    else:
        raise AssertionError("self-intersecting polygon must be rejected")


def test_evidence_chain_detects_tampering():
    room = RoomContract.from_payload(
        _room_payload([(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)])
    )
    snapshot = {
        "snapshot_id": "S1",
        "revision_id": "R1",
        "source_system": "pytest",
        "source_model_id": "revit://ops/l1",
        "created_at": "2026-05-20T00:00:00Z",
        "rooms": [room.to_payload()],
    }
    analysis = {"snapshot_id": "S1", "room_results": [analyze_room(room, 4.0, 5.7)]}
    chain = EvidenceChain(secret_key="secret", signer_id="qa")
    envelope = chain.build_envelope(snapshot, analysis)
    assert chain.verify_envelope(envelope, snapshot, analysis) is True

    bad_analysis = dict(analysis)
    bad_analysis["room_results"] = list(analysis["room_results"])
    bad_analysis["room_results"][0] = dict(bad_analysis["room_results"][0])
    bad_analysis["room_results"][0]["metrics"] = dict(bad_analysis["room_results"][0]["metrics"])
    bad_analysis["room_results"][0]["metrics"]["area_m2"] = 999.0
    assert chain.verify_envelope(envelope, snapshot, bad_analysis) is False


def test_twin_db_persists_and_diffs_versions(tmp_path):
    twin = TwinSystemOfRecord(str(tmp_path / "elite.db"))
    chain = EvidenceChain(secret_key="secret", signer_id="qa")

    room_a = RoomContract.from_payload(
        _room_payload([(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)])
    )
    room_b = RoomContract.from_payload(
        _room_payload([(0.0, 0.0), (10.0, 0.0), (10.0, 6.0), (0.0, 6.0)])
    )

    snapshot_a = {
        "snapshot_id": "S-A",
        "revision_id": "REV-A",
        "source_system": "pytest",
        "source_model_id": "revit://ops/l1",
        "created_at": "2026-05-20T00:00:00Z",
        "rooms": [room_a.to_payload()],
    }
    analysis_a = {"snapshot_id": "S-A", "room_results": [analyze_room(room_a, 4.0, 5.7)]}
    envelope_a = chain.build_envelope(snapshot_a, analysis_a)
    twin.save_snapshot(snapshot_a, analysis_a, envelope_a)

    snapshot_b = {
        "snapshot_id": "S-B",
        "revision_id": "REV-B",
        "source_system": "pytest",
        "source_model_id": "revit://ops/l1",
        "created_at": "2026-05-20T00:00:01Z",
        "rooms": [room_b.to_payload()],
    }
    analysis_b = {"snapshot_id": "S-B", "room_results": [analyze_room(room_b, 4.0, 5.7)]}
    envelope_b = chain.build_envelope(snapshot_b, analysis_b, previous_envelope=envelope_a)
    twin.save_snapshot(snapshot_b, analysis_b, envelope_b)

    drift = twin.diff_snapshots("S-A", "S-B")
    assert any(item["drift_type"] == "geometry_changed" for item in drift)


def test_release_gate_blocks_when_connector_is_out_of_sync():
    result = evaluate_release(
        {
            "canonical_geometry": True,
            "evidence_chain_valid": True,
            "connector_in_sync": False,
            "version_authority_valid": True,
            "stale_surfaces_removed": True,
        }
    )
    assert result["release_status"] == "blocked"
    assert "connector_in_sync" in result["blockers"]
