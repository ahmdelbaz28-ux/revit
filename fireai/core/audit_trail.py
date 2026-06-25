from __future__ import annotations

"""
audit_trail.py — FireAI V5.3.0
Immutable audit log with per-entry hash, thread-safe append.

V5.3.0 Changes (Consolidation):
  - Merged V5.1.2 (log_rejection) and V5.2.0 (threading lock + new methods)
    into a single canonical version inside fireai/core/
  - All methods from both previous versions are now present
  - This is the ONLY AuditTrail — no duplicate at project root

V5.2.0 Changes:
  - Added threading.Lock for thread safety
  - Added log_placement() for detector placement tracking
  - Added log_wall_distance_violation() for NFPA §17.6.3.1.1
  - Added log_duct_detector_placement() for NFPA §17.7.5
  - Added log_safe_fallback_used() for Table 17.6.3.1
  - Added log_boundary_limit_warning() for BOUNDARY_LIMIT
  - Added count() method
  - Added entries() method

V5.1.2 Changes:
  - Added log_rejection() for fail-fast input validation
"""

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


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
        object.__setattr__(self, "entry_hash", self._compute_hash())

    def _compute_hash(self) -> str:
        content = json.dumps(
            {
                "timestamp_utc": self.timestamp_utc,
                "room_id": self.room_id,
                "operation": self.operation,
                "inputs": self.inputs,
                "outputs": self.outputs,
                "nfpa_reference": self.nfpa_reference,
                "notes": self.notes,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        # V114 FIX: Extend hash from 16→32 hex chars (64→128 bits).
        # 64-bit hashes are vulnerable to birthday collision (~4B attempts).
        # Matches V99 fix standard for cable_router.py and revit_exporter.py.
        return hashlib.sha256(content.encode()).hexdigest()[:32]

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
    """Immutable, thread-safe audit log with per-entry SHA-256 hash.

    All append operations are protected by a threading.Lock to ensure
    no entries are lost under concurrent writes (e.g. FastAPI async).

    Usage:
        trail = AuditTrail(project_name="my_project")
        trail.log_placement("R1", 3, "smoke_photoelectric", 99.5, [(1,1),(2,2)])
        trail.log_rejection("R2", "Invalid room type")
        assert trail.verify_integrity()
    """

    def __init__(self, project_name: str, floor_id: str = "FL01"):
        self.project_name = project_name
        self.floor_id = floor_id
        self.created_at = datetime.now(timezone.utc).isoformat()
        self._entries: List[AuditEntry] = []
        self._lock = threading.Lock()

    def _add(self, entry: AuditEntry):
        with self._lock:
            self._entries.append(entry)

    # ── Core logging methods (V5.1.2 originals) ──────────────────────

    def log_radius_lookup(self, room_id, ceiling_height_m, radius_m, table_row):
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="SMOKE_RADIUS_LOOKUP",
                inputs={"ceiling_height_m": ceiling_height_m},
                outputs={"radius_m": radius_m},
                nfpa_reference=f"NFPA 72 (2022) Table 17.6.3.1 — {table_row}",
            )
        )

    def log_rejection(self, room_id: str, reason: str):
        """Log rejected input before it reaches the solver."""
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="INPUT_REJECTED",
                inputs={"room_id": room_id},
                outputs={"reason": reason},
                nfpa_reference="Fail-fast validation",
            )
        )

    def log_heat_params(self, room_id, listed_spacing_m, adjusted_spacing_m, adjustments):
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="HEAT_DETECTOR_PARAMS",
                inputs={"listed_spacing_m": listed_spacing_m},
                outputs={"adjusted_spacing_m": adjusted_spacing_m},
                nfpa_reference="NFPA 72 (2022) Section 17.6.3.5",
                notes=adjustments,
            )
        )

    def log_coverage_result(self, room_id, detector_count, coverage_pct, worst_case_m, status):
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="COVERAGE_VERIFICATION",
                inputs={"detector_count": detector_count, "grid_resolution_m": 0.20},
                outputs={"coverage_pct": coverage_pct, "worst_case_m": worst_case_m, "status": status},
                nfpa_reference="NFPA 72 (2022) Section 17.6.3",
            )
        )

    def log_dxf_parse(self, source_file, units, scale, rooms_found, rooms_skipped):
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id="__FLOOR__",
                operation="DXF_PARSE",
                inputs={"source_file": source_file},
                outputs={"units": units, "scale": scale, "rooms_found": rooms_found, "rooms_skipped": rooms_skipped},
                nfpa_reference="N/A — DXF input processing",
            )
        )

    def log_nfpa_violation(self, room_id, violation, nfpa_ref):
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="NFPA_COMPLIANCE_ERROR",
                inputs={},
                outputs={"violation": violation},
                nfpa_reference=nfpa_ref,
                notes=["DESIGN CANNOT PROCEED", violation],
            )
        )

    # ── V5.2.0 new methods ───────────────────────────────────────────

    def log_placement(self, room_id, detector_count, detector_type, coverage_pct, positions):
        """Log a detector placement decision. NFPA 72 §17.6.3."""
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="DETECTOR_PLACEMENT",
                inputs={"grid_resolution_m": 0.25},
                outputs={
                    "detector_count": detector_count,
                    "detector_type": detector_type,
                    "coverage_pct": coverage_pct,
                    "positions_count": len(positions),
                },
                nfpa_reference="NFPA 72 (2022) Section 17.6.3",
            )
        )

    def log_wall_distance_violation(self, room_id, detector_index, position, wall, distance_m):
        """Log a wall distance violation. NFPA 72 §17.6.3.1.1."""
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="WALL_DISTANCE_VIOLATION",
                inputs={"detector_index": detector_index, "position": position},
                outputs={"distance_m": distance_m, "required_m": 0.10},
                nfpa_reference="NFPA 72 (2022) §17.6.3.1.1",
                notes=[f"Detector {detector_index} at {position} is {distance_m:.3f}m from {wall} wall (min 0.10m)"],
            )
        )

    def log_duct_detector_placement(self, room_id, duct_id, detector_count, positions):
        """Log duct detector placement. NFPA 72 §17.7.5."""
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="DUCT_DETECTOR_PLACEMENT",
                inputs={"duct_id": duct_id},
                outputs={"detector_count": detector_count, "positions": positions},
                nfpa_reference="NFPA 72 (2022) §17.7.5",
            )
        )

    def log_safe_fallback_used(self, room_id, original_height_m, clamped_height_m, effective_height_m):
        """Log safe fallback activation for out-of-range ceiling height. Table 17.6.3.1."""
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="SAFE_FALLBACK_ACTIVATED",
                inputs={"original_height_m": original_height_m},
                outputs={"clamped_height_m": clamped_height_m, "effective_height_m": effective_height_m},
                nfpa_reference="NFPA 72 (2022) Table 17.6.3.1",
                notes=[f"Ceiling height {original_height_m}m clamped to {clamped_height_m}m for safe calculation"],
            )
        )

    def log_boundary_limit_warning(self, room_id, coverage_pct):
        """Log BOUNDARY_LIMIT warning when coverage > 99.9% but proof_valid=False."""
        self._add(
            AuditEntry(
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                room_id=room_id,
                operation="BOUNDARY_LIMIT_WARNING",
                inputs={"grid_resolution_m": 0.20},
                outputs={"coverage_pct": coverage_pct, "proof_valid": False},
                nfpa_reference="NFPA 72 (2022) Section 17.6.3",
                notes=[
                    f"Coverage {coverage_pct:.2f}% exceeds 99.9% but grid verification at step=0.20m "
                    f"could not confirm 100%. Known limitation (0.8% of rooms). PE review recommended.",
                ],
            )
        )

    # ── Query methods (thread-safe) ───────────────────────────────────

    def count(self) -> int:
        """Return total number of audit entries (thread-safe)."""
        with self._lock:
            return len(self._entries)

    def get_room_trail(self, room_id: str) -> List[AuditEntry]:
        with self._lock:
            return [e for e in self._entries if e.room_id == room_id]

    def to_list(self) -> List[dict]:
        with self._lock:
            return [e.to_dict() for e in self._entries]

    def verify_integrity(self) -> bool:
        with self._lock:
            for entry in self._entries:
                if entry._compute_hash() != entry.entry_hash:
                    return False
            return True

    def entries(self) -> List[AuditEntry]:
        """Return a copy of all entries (thread-safe)."""
        with self._lock:
            return list(self._entries)

    def summary(self) -> Dict[str, Any]:
        """Return a summary dict of the audit trail."""
        with self._lock:
            return {
                "project_name": self.project_name,
                "floor_id": self.floor_id,
                "created_at": self.created_at,
                "entry_count": len(self._entries),
                "operations": list({e.operation for e in self._entries}),
            }
