"""Evidence ledger with deterministic signed manifests."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict
from typing import Dict, Iterable, List

from .models import BuildingSnapshot, DetectorPlacement, RoomAnalysisRecord, RoomGeometry, RuleDecision


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def geometry_hash(room):
    payload = {
        "room_id": room.room_id,
        "polygon": room.polygon,
        "ceiling_height_m": room.ceiling_height_m,
        "use_type": room.use_type,
    }
    return _sha256_text(json.dumps(payload, sort_keys=True))


def detector_hash(detector):
    payload = {
        "detector_id": detector.detector_id,
        "room_id": detector.room_id,
        "x": detector.x,
        "y": detector.y,
        "z": detector.z,
        "detector_type": detector.detector_type,
        "coverage_radius_m": detector.coverage_radius_m,
    }
    return _sha256_text(json.dumps(payload, sort_keys=True))


def record_hash(record):
    payload = {
        "room": geometry_hash(record.room),
        "detectors": [detector_hash(d) for d in record.detectors],
        "rules": [asdict(rule) for rule in record.rule_decisions],
        "metadata": dict(record.metadata),
    }
    return _sha256_text(json.dumps(payload, sort_keys=True))


class EvidenceLedger(object):
    """Signed run manifest for traceable engineering outputs."""

    def __init__(self, secret_key):
        if not secret_key:
            raise ValueError("secret_key must not be empty")
        self._secret_key = secret_key.encode("utf-8")

    def build_manifest(self, snapshot, solver_version, rule_bundle_version):
        room_hashes = {}
        detector_hashes = {}
        for record in snapshot.room_records:
            room_hashes[record.room.room_id] = geometry_hash(record.room)
            detector_hashes[record.room.room_id] = [
                detector_hash(detector) for detector in record.detectors
            ]

        manifest = {
            "snapshot_id": snapshot.snapshot_id,
            "revision_id": snapshot.revision_id,
            "created_at": snapshot.created_at,
            "source_system": snapshot.source_system,
            "source_model_id": snapshot.source_model_id,
            "solver_version": solver_version,
            "rule_bundle_version": rule_bundle_version,
            "room_hashes": room_hashes,
            "detector_hashes": detector_hashes,
            "record_hashes": {
                record.room.room_id: record_hash(record)
                for record in snapshot.room_records
            },
        }
        manifest["manifest_hash"] = _sha256_text(json.dumps(manifest, sort_keys=True))
        manifest["signature"] = self._sign(manifest["manifest_hash"])
        return manifest

    def verify_manifest(self, manifest):
        expected = dict(manifest)
        actual_signature = expected.pop("signature")
        manifest_hash = expected.pop("manifest_hash")
        rebuilt_hash = _sha256_text(json.dumps(expected, sort_keys=True))
        if rebuilt_hash != manifest_hash:
            return False
        return hmac.compare_digest(actual_signature, self._sign(manifest_hash))

    def _sign(self, payload_hash):
        return hmac.new(
            self._secret_key,
            payload_hash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
