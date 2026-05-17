"""
audit_trail.py — FireAI V5.1.2
Immutable audit log with per-entry hash and geometry hash.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import hashlib


@dataclass(frozen=True)
class AuditEntry:
    timestamp_utc: str
    room_id: str
    operation: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    nfpa_reference: str
    notes: List[str] = field(default_factory=list)
    entry_hash: str = field(default="", init=False)

    def __post_init__(self):
        self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        content = json.dumps({
            "timestamp_utc": self.timestamp_utc,
            "room_id": self.room_id,
            "operation": self.operation,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "nfpa_reference": self.nfpa_reference,
            "notes": self.notes,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "timestamp_utc": self.timestamp_utc,
            "room_id": self.room_id,
            "operation": self.operation,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "nfpa_reference": self.nfpa_reference,
            "notes": self.notes,
            "entry_hash": self.entry_hash,
        }


class AuditTrail:
    def __init__(self, project_name: str, floor_id: str = "FL01"):
        self.project_name = project_name
        self.floor_id = floor_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self._entries: List[AuditEntry] = []

    def log_radius_lookup(self, room_id, ceiling_height_m, radius_m, table_row):
        self._add(AuditEntry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            room_id=room_id,
            operation="SMOKE_RADIUS_LOOKUP",
            inputs={"ceiling_height_m": ceiling_height_m},
            outputs={"radius_m": radius_m},
            nfpa_reference=f"NFPA 72 (2022) Table 17.6.3.1 — {table_row}",
        ))

    def log_rejection(self, room_id: str, reason: str):
        """Log rejected input before it reaches the solver"""
        self._add(AuditEntry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            room_id=room_id,
            operation="INPUT_REJECTED",
            inputs={"room_id": room_id},
            outputs={"reason": reason},
            nfpa_reference="Fail-fast validation",
        ))

    def log_heat_params(self, room_id, listed_spacing_m, adjusted_spacing_m, adjustments):
        self._add(AuditEntry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            room_id=room_id,
            operation="HEAT_DETECTOR_PARAMS",
            inputs={"listed_spacing_m": listed_spacing_m},
            outputs={"adjusted_spacing_m": adjusted_spacing_m},
            nfpa_reference="NFPA 72 (2022) Section 17.6.3.5",
            notes=adjustments,
        ))

    def log_coverage_result(self, room_id, detector_count, coverage_pct, worst_case_m, status):
        self._add(AuditEntry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            room_id=room_id,
            operation="COVERAGE_VERIFICATION",
            inputs={"detector_count": detector_count, "grid_resolution_m": 0.1},
            outputs={"coverage_pct": coverage_pct, "worst_case_m": worst_case_m, "status": status},
            nfpa_reference="NFPA 72 (2022) Section 17.6.3",
        ))

    def log_dxf_parse(self, source_file, units, scale, rooms_found, rooms_skipped):
        self._add(AuditEntry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            room_id="__FLOOR__",
            operation="DXF_PARSE",
            inputs={"source_file": source_file},
            outputs={"units": units, "scale": scale, "rooms_found": rooms_found, "rooms_skipped": rooms_skipped},
            nfpa_reference="N/A — DXF input processing",
        ))

    def log_nfpa_violation(self, room_id, violation, nfpa_ref):
        self._add(AuditEntry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            room_id=room_id,
            operation="NFPA_COMPLIANCE_ERROR",
            inputs={},
            outputs={"violation": violation},
            nfpa_reference=nfpa_ref,
            notes=["DESIGN CANNOT PROCEED", violation],
        ))

    def count(self) -> int:
        """Return the number of audit entries recorded."""
        return len(self._entries)

    def get_room_trail(self, room_id: str) -> List[AuditEntry]:
        return [e for e in self._entries if e.room_id == room_id]

    def to_list(self) -> List[dict]:
        return [e.to_dict() for e in self._entries]

    def verify_integrity(self) -> bool:
        for entry in self._entries:
            if entry._compute_hash() != entry.entry_hash:
                return False
        return True

    def _add(self, entry: AuditEntry):
        self._entries.append(entry)