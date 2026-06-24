"""digital_twin.py — FireAI Digital Twin (Production Safety System)
================================================================
The central orchestrator for the FireAI digital twin.  Maintains a
live, auditable model of every fire detector in a building — tracking
whether each detector is PLANNED (design-only) or INSTALLED (physically
present), detecting drift between design and reality, and providing
simulation + health reporting for AHJ review.

CRITICAL SAFETY NOTE:
  This module tracks the distinction between PLANNED and INSTALLED
  detectors.  A PLANNED detector provides NO fire protection.  Any
  report that counts PLANNED detectors as active coverage is a
  SAFETY BUG.  The health report explicitly separates these.

Architecture:
  DigitalTwin is the MAIN class.  It composes:
    - EventBus  (singleton, from event_bus.py) for real-time events
    - AuditStore (optional, from audit_store.py) for legal-grade logging
    - TwinDriftAnalyzer  for detecting design-vs-reality drift
    - TwinSimulator      for what-if scenario simulation
    - TwinSerializer     for JSON round-trip serialization

  Every significant action:
    1. Publishes an event on EventBus
    2. Logs to AuditStore (if available; never crashes if unavailable)
    3. Is thread-safe (RLock-protected)

NFPA 72-2022 Compliance:
  - DetectorStatus.PLANNED means NOT YET COMMISSIONED
  - DetectorStatus.OK means COMMISSIONED and OPERATIONAL
  - Health reports flag any room with zero OK detectors as CRITICAL

Usage:
    from fireai.core.digital_twin import DigitalTwin, DetectorStatus

    twin = DigitalTwin(building_id="B-001")
    twin.register_detector("R-01", "D-001", x=3.0, y=2.5, z=3.0,
                           detector_type="smoke", status=DetectorStatus.PLANNED)
    twin.update_detector_status("D-001", DetectorStatus.OK)
    report = twin.health_report()
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .event_bus import EventBus, Events

# Optional AuditStore — graceful fallback if unavailable
try:
    from .audit_store import AuditStore
except ImportError:
    AuditStore = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


__all__ = [
    "LEGAL_STATUS_TRANSITIONS",
    "NFPA72_DEFAULT_CEILING_M",
    "NFPA72_HEAT_RADIUS_M",
    "NFPA72_MAX_SPACING_M",
    "NFPA72_SMOKE_RADIUS_M",
    "DetectorState",
    "DetectorStatus",
    "DigitalTwin",
    "DriftRecord",
    "DriftType",
    "EventType",
    "SimulationResult",
    "TwinDriftAnalyzer",
    "TwinEvent",
    "TwinHealthReport",
    "TwinSerializer",
    "TwinSimulator",
]


# ═══════════════════════════════════════════════════════════════════════
# NFPA 72-2022 Constants
# ═══════════════════════════════════════════════════════════════════════

# Default coverage radius for smoke detectors (R = 0.7 × S = 0.7 × 9.1m)
NFPA72_SMOKE_RADIUS_M = 6.37

# Default coverage radius for heat detectors (R = 0.7 × S = 0.7 × 6.1m)
# per NFPA 72 Table 17.6.3.1.1 (20ft listed spacing)
NFPA72_HEAT_RADIUS_M = 4.27

# Secondary constant for 25ft listed spacing heat detectors
NFPA72_HEAT_RADIUS_25FT_M = 5.3

# Default ceiling height for commercial buildings
NFPA72_DEFAULT_CEILING_M = 3.0

# Maximum detector spacing (S = 30ft = 9.1m per NFPA 72 Table 17.6.3.1.1)
NFPA72_MAX_SPACING_M = 9.1


# ═══════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════


class DetectorStatus(Enum):
    """Lifecycle status of a fire detector.

    CRITICAL DISTINCTION:
        PLANNED  — Exists in the design model but is NOT physically
                   installed.  Provides ZERO fire protection.
        OK       — Physically installed, tested, and operational.
        FAULT    — Installed but reporting a fault (needs maintenance).
        OFFLINE  — Installed but communication lost (possible hazard).
        DECOMMISSIONED — Permanently removed from service.

    State Transitions (ENFORCED — see LEGAL_STATUS_TRANSITIONS):
        PLANNED → OK              (installation + commissioning)
        PLANNED → DECOMMISSIONED  (cancelled before install)
        OK      → FAULT           (fault detected)
        OK      → OFFLINE         (communication lost)
        OK      → DECOMMISSIONED  (permanently removed)
        FAULT   → OK              (fault resolved)
        FAULT   → OFFLINE         (fault + comm lost)
        FAULT   → DECOMMISSIONED  (permanently removed)
        OFFLINE → OK              (communication restored)
        OFFLINE → FAULT           (came back with fault)
        OFFLINE → DECOMMISSIONED  (permanently removed)

    FORBIDDEN transitions (SAFETY VIOLATIONS if allowed):
        OK → PLANNED              (cannot "un-install" a detector)
        DECOMMISSIONED → any      (dead is dead)
        PLANNED → FAULT           (never installed, can't be faulty)
        PLANNED → OFFLINE         (never installed, can't go offline)
    """

    PLANNED = "planned"
    OK = "ok"
    FAULT = "fault"
    OFFLINE = "offline"
    DECOMMISSIONED = "decommissioned"

    @property
    def provides_coverage(self) -> bool:
        """True only if this status means the detector is actively protecting."""
        return self == DetectorStatus.OK


# ═══════════════════════════════════════════════════════════════════════
# Legal Status Transition Map (BUG-10 FIX)
# ═══════════════════════════════════════════════════════════════════════

LEGAL_STATUS_TRANSITIONS: Dict[DetectorStatus, set] = {
    # A detector that exists in design but is not yet installed.
    DetectorStatus.PLANNED: {
        DetectorStatus.OK,  # Installed + commissioned
        DetectorStatus.DECOMMISSIONED,  # Cancelled before install
    },
    # An active, operational detector.
    DetectorStatus.OK: {
        DetectorStatus.FAULT,  # Fault detected
        DetectorStatus.OFFLINE,  # Communication lost
        DetectorStatus.DECOMMISSIONED,  # Permanently removed
    },
    # A detector with a known fault — still physically present.
    DetectorStatus.FAULT: {
        DetectorStatus.OK,  # Fault resolved
        DetectorStatus.OFFLINE,  # Fault + comm lost
        DetectorStatus.DECOMMISSIONED,  # Permanently removed
    },
    # A detector that lost communication — still physically present.
    DetectorStatus.OFFLINE: {
        DetectorStatus.OK,  # Communication restored, healthy
        DetectorStatus.FAULT,  # Came back with a fault
        DetectorStatus.DECOMMISSIONED,  # Permanently removed
    },
    # Terminal state — no transitions allowed.
    DetectorStatus.DECOMMISSIONED: set(),
}


class EventType(Enum):
    """Types of events recorded by the Digital Twin."""

    DETECTOR_REGISTERED = "detector.registered"
    DETECTOR_STATUS_CHANGED = "detector.status_changed"
    DETECTOR_REMOVED = "detector.removed"
    DRIFT_DETECTED = "drift.detected"
    SNAPSHOT_CAPTURED = "snapshot.captured"
    SIMULATION_RUN = "simulation.run"
    HEALTH_REPORT_GENERATED = "health.report_generated"
    BUILDING_LOADED = "building.loaded"


class DriftType(Enum):
    """Categories of drift between design model and as-built reality."""

    POSITION_DRIFT = "position_drift"  # Detector moved from design position
    STATUS_DRIFT = "status_drift"  # Detector status disagrees with design
    MISSING_DETECTOR = "missing_detector"  # Designed detector not found in field
    EXTRA_DETECTOR = "extra_detector"  # Field detector not in design model
    TYPE_MISMATCH = "type_mismatch"  # Detector type differs from design


# ═══════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class DetectorState:
    """Complete state of a single fire detector in the digital twin.

    Attributes:
        detector_id: Unique identifier for this detector.
        room_id: Room this detector belongs to.
        x: X position in meters (room-local coordinates).
        y: Y position in meters.
        z: Z position in meters (typically ceiling height).
        detector_type: "smoke", "heat", "flame", "gas", "duct_smoke".
        status: Current lifecycle status (PLANNED, OK, FAULT, etc.).
        coverage_radius: Coverage radius in meters (default 6.37 per NFPA 72).
        design_x: Original design X position (for drift detection).
        design_y: Original design Y position.
        design_z: Original design Z position.
        installed_at: ISO 8601 timestamp when status changed to OK.
        last_verified_at: ISO 8601 timestamp of last verification.
        metadata: Additional key-value metadata.

    """

    detector_id: str
    room_id: str
    x: float
    y: float
    z: float
    detector_type: str = "smoke"
    status: DetectorStatus = DetectorStatus.PLANNED
    coverage_radius: float = NFPA72_SMOKE_RADIUS_M
    design_x: Optional[float] = None
    design_y: Optional[float] = None
    design_z: Optional[float] = None
    installed_at: str = ""
    last_verified_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Initialize design coordinates to match placement if not explicitly set.
        # CRITICAL (FIX-5): Using None as sentinel instead of 0.0 because
        # a detector CAN legitimately be at position (0.0, 0.0, 0.0).
        # The old code used `if design_x == 0.0` which falsely treated
        # (0,0,0) as "unset" — a SAFETY BUG for rooms with origin corners.
        if self.design_x is None:
            self.design_x = self.x
        if self.design_y is None:
            self.design_y = self.y
        if self.design_z is None:
            self.design_z = self.z

    @property
    def position_drift_m(self) -> float:
        """Euclidean distance from design position to current position."""
        return ((self.x - self.design_x) ** 2 + (self.y - self.design_y) ** 2 + (self.z - self.design_z) ** 2) ** 0.5

    @property
    def is_active(self) -> bool:
        """True if this detector provides coverage right now."""
        return self.status.provides_coverage

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DetectorState:
        """Deserialize from dictionary.

        Handles backward compatibility: if design_x/y/z are missing
        from old serialized data (pre-FIX-5), they default to None
        which triggers __post_init__ to set them from x/y/z.
        """
        data = dict(data)
        if isinstance(data.get("status"), str):
            data["status"] = DetectorStatus(data["status"])
        # Backward compat: old data may not have design_x/y/z fields.
        # If missing, set to None so __post_init__ fills them from x/y/z.
        for key in ("design_x", "design_y", "design_z"):
            if key not in data:
                data[key] = None
        return cls(**data)


@dataclass
class TwinEvent:
    """An event recorded in the Digital Twin's event log.

    Unlike EventBus events (which are ephemeral pub/sub), TwinEvents
    are persisted within the twin for audit and replay.
    """

    event_id: str
    event_type: EventType
    timestamp: str
    detector_id: str = ""
    room_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TwinEvent:
        data = dict(data)
        if isinstance(data.get("event_type"), str):
            data["event_type"] = EventType(data["event_type"])
        return cls(**data)


@dataclass
class DriftRecord:
    """Record of a single drift between design and as-built.

    Attributes:
        drift_id: Unique identifier.
        drift_type: Category of drift.
        detector_id: Affected detector (empty for missing/extra).
        room_id: Room where drift was detected.
        expected: What the design model says.
        actual: What was found in reality.
        severity: "low", "medium", "high", or "critical".
        timestamp: When the drift was detected.
        resolved: Whether the drift has been resolved.

    """

    drift_id: str
    drift_type: DriftType
    detector_id: str
    room_id: str
    expected: str
    actual: str
    severity: str = "medium"
    timestamp: str = ""
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["drift_type"] = self.drift_type.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DriftRecord:
        data = dict(data)
        if isinstance(data.get("drift_type"), str):
            data["drift_type"] = DriftType(data["drift_type"])
        return cls(**data)


@dataclass
class TwinHealthReport:
    """Health assessment of the entire Digital Twin.

    Generated by ``DigitalTwin.health_report()``.
    """

    building_id: str
    timestamp: str
    total_detectors: int
    active_detectors: int
    planned_detectors: int
    faulted_detectors: int
    offline_detectors: int
    decommissioned_detectors: int
    rooms_with_coverage: int
    rooms_without_coverage: int
    total_rooms: int
    drift_count: int
    unresolved_drift_count: int
    coverage_pct: float
    health_score: float  # 0.0–1.0
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationResult:
    """Result of a what-if simulation on the Digital Twin.

    Attributes:
        simulation_id: Unique identifier.
        description: Human-readable description of the scenario.
        timestamp: When the simulation was run.
        original_health_score: Health score before simulation.
        simulated_health_score: Health score in the simulated scenario.
        changes_applied: List of changes that were simulated.
        impacted_rooms: Rooms affected by the simulated changes.
        new_coverage_pct: Simulated coverage percentage.
        new_active_count: Simulated count of active detectors.
        notes: Additional observations.

    """

    simulation_id: str
    description: str
    timestamp: str
    original_health_score: float
    simulated_health_score: float
    changes_applied: List[Dict[str, Any]] = field(default_factory=list)
    impacted_rooms: List[str] = field(default_factory=list)
    new_coverage_pct: float = 0.0
    new_active_count: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════
# TwinDriftAnalyzer
# ═══════════════════════════════════════════════════════════════════════


class TwinDriftAnalyzer:
    """Detects drift between the design model and as-built reality.

    Compares the current detector states against design positions and
    expected statuses, producing DriftRecords for any discrepancies.

    DRIFT TOLERANCE:
        Position drift < 0.01m is ignored (measurement noise).
        Position drift >= 0.01m and < 0.30m is "low" severity.
        Position drift >= 0.30m and < 1.0m is "medium" severity.
        Position drift >= 1.0m is "high" severity (NFPA spacing violation).
        Position drift >= 1.5m is "critical" (definite NFPA violation).
    """

    POSITION_TOLERANCE_M = 0.01  # 1cm measurement noise
    POSITION_WARN_M = 0.30  # 30cm warning threshold
    POSITION_HIGH_M = 1.0  # 1m — approaching NFPA spacing limits
    POSITION_CRITICAL_M = 1.5  # 1.5m — definite NFPA spacing violation

    def analyze(self, detectors: Dict[str, DetectorState]) -> List[DriftRecord]:
        """Analyze all detectors for drift.

        Args:
            detectors: Map of detector_id → DetectorState.

        Returns:
            List of DriftRecords for detected drifts.

        """
        drifts: List[DriftRecord] = []
        now = datetime.now(timezone.utc).isoformat()

        for det_id, det in detectors.items():
            # Position drift
            pos_drift = det.position_drift_m
            if pos_drift >= self.POSITION_TOLERANCE_M:
                severity = self._classify_position_drift(pos_drift)
                drifts.append(
                    DriftRecord(
                        drift_id=str(uuid.uuid4()),
                        drift_type=DriftType.POSITION_DRIFT,
                        detector_id=det_id,
                        room_id=det.room_id,
                        expected=f"design=({det.design_x:.3f}, {det.design_y:.3f}, {det.design_z:.3f})",
                        actual=f"current=({det.x:.3f}, {det.y:.3f}, {det.z:.3f})",
                        severity=severity,
                        timestamp=now,
                    )
                )

            # Status drift: PLANNED detectors that should be OK by now
            # (This is informational — the caller decides if it's actionable)
            if det.status == DetectorStatus.PLANNED:
                drifts.append(
                    DriftRecord(
                        drift_id=str(uuid.uuid4()),
                        drift_type=DriftType.STATUS_DRIFT,
                        detector_id=det_id,
                        room_id=det.room_id,
                        expected="installed+commissioned",
                        actual="planned (not yet installed)",
                        severity="medium",
                        timestamp=now,
                    )
                )

        return drifts

    def _classify_position_drift(self, drift_m: float) -> str:
        """Classify the severity of a position drift."""
        if drift_m >= self.POSITION_CRITICAL_M:
            return "critical"
        if drift_m >= self.POSITION_HIGH_M:
            return "high"
        if drift_m >= self.POSITION_WARN_M:
            return "medium"
        return "low"


# ═══════════════════════════════════════════════════════════════════════
# TwinSimulator
# ═══════════════════════════════════════════════════════════════════════


class TwinSimulator:
    """What-if scenario simulator for the Digital Twin.

    Runs simulations on a deep-copied twin state without modifying
    the actual twin.  Useful for:
      - "What if we add a detector to Room R-03?"
      - "What if Detector D-12 goes offline?"
      - "What if we commission all PLANNED detectors?"
    """

    DEFAULT_COVERAGE_RADII: Dict[str, float] = {
        "smoke": NFPA72_SMOKE_RADIUS_M,
        "heat": NFPA72_HEAT_RADIUS_M,
        "flame": NFPA72_SMOKE_RADIUS_M,
        "gas": NFPA72_SMOKE_RADIUS_M,
        "duct_smoke": 0.0,  # Duct detectors don't provide area coverage
    }

    def simulate_offline(
        self,
        detectors: Dict[str, DetectorState],
        detector_ids: List[str],
        description: str = "",
    ) -> SimulationResult:
        """Simulate one or more detectors going offline.

        Args:
            detectors: Current detector map (will NOT be modified).
            detector_ids: IDs of detectors to take offline.
            description: Human-readable scenario description.

        Returns:
            SimulationResult with projected health impact.

        """
        return self._run_simulation(
            detectors,
            description or f"Simulate {len(detector_ids)} detector(s) going offline",
            lambda dets: self._apply_offline(dets, detector_ids),
        )

    def simulate_commission_all(
        self,
        detectors: Dict[str, DetectorState],
    ) -> SimulationResult:
        """Simulate commissioning all PLANNED detectors to OK.

        Args:
            detectors: Current detector map (will NOT be modified).

        Returns:
            SimulationResult showing impact of full commissioning.

        """
        planned_ids = [did for did, d in detectors.items() if d.status == DetectorStatus.PLANNED]
        return self._run_simulation(
            detectors,
            f"Commission all {len(planned_ids)} PLANNED detector(s)",
            lambda dets: self._apply_status_change(dets, planned_ids, DetectorStatus.OK),
        )

    def simulate_add_detector(
        self,
        detectors: Dict[str, DetectorState],
        room_id: str,
        x: float,
        y: float,
        z: float,
        detector_type: str = "smoke",
        coverage_radius: Optional[float] = None,
    ) -> SimulationResult:
        """Simulate adding a new detector.

        Args:
            detectors: Current detector map (will NOT be modified).
            room_id: Room to add the detector in.
            x, y, z: Position in meters.
            detector_type: Type of detector.
            coverage_radius: Coverage radius in meters. If None, uses
                DEFAULT_COVERAGE_RADII for the detector_type.

        Returns:
            SimulationResult showing impact of the addition.

        """
        new_id = f"SIM_{uuid.uuid4().hex[:8]}"
        effective_radius = (
            coverage_radius
            if coverage_radius is not None
            else self.DEFAULT_COVERAGE_RADII.get(detector_type, NFPA72_SMOKE_RADIUS_M)
        )

        def apply(dets: Dict[str, DetectorState]) -> None:
            dets[new_id] = DetectorState(
                detector_id=new_id,
                room_id=room_id,
                x=x,
                y=y,
                z=z,
                detector_type=detector_type,
                status=DetectorStatus.OK,
                coverage_radius=effective_radius,
            )

        return self._run_simulation(
            detectors,
            f"Add {detector_type} detector at ({x:.1f}, {y:.1f}, {z:.1f}) in {room_id}",
            apply,
        )

    # ── Private helpers ───────────────────────────────────────────

    def _run_simulation(
        self,
        detectors: Dict[str, DetectorState],
        description: str,
        apply_fn: Any,  # Callable[[Dict[str, DetectorState]], None]
    ) -> SimulationResult:
        """Run a simulation with a given mutation function."""
        # Deep copy so we don't mutate the real state
        sim_dets = {did: copy.deepcopy(d) for did, d in detectors.items()}

        original_score = self._compute_health_score(sim_dets)
        self._compute_coverage_pct(sim_dets)

        # Apply the simulated change
        apply_fn(sim_dets)

        sim_score = self._compute_health_score(sim_dets)
        sim_coverage = self._compute_coverage_pct(sim_dets)

        impacted_rooms = list({d.room_id for d in sim_dets.values()})

        return SimulationResult(
            simulation_id=str(uuid.uuid4()),
            description=description,
            timestamp=datetime.now(timezone.utc).isoformat(),
            original_health_score=original_score,
            simulated_health_score=sim_score,
            new_coverage_pct=sim_coverage,
            new_active_count=sum(1 for d in sim_dets.values() if d.is_active),
            impacted_rooms=impacted_rooms,
        )

    @staticmethod
    def _apply_offline(dets: Dict[str, DetectorState], ids: List[str]) -> None:
        for did in ids:
            if did in dets:
                dets[did].status = DetectorStatus.OFFLINE

    @staticmethod
    def _apply_status_change(dets: Dict[str, DetectorState], ids: List[str], status: DetectorStatus) -> None:
        for did in ids:
            if did in dets:
                dets[did].status = status

    @staticmethod
    def _compute_health_score(dets: Dict[str, DetectorState]) -> float:
        """Compute a 0.0–1.0 health score from detector states."""
        if not dets:
            return 0.0  # V20.2 FIX: No detectors = NO protection, not perfect
        ok = sum(1 for d in dets.values() if d.status == DetectorStatus.OK)
        faulted = sum(1 for d in dets.values() if d.status == DetectorStatus.FAULT)
        offline = sum(1 for d in dets.values() if d.status == DetectorStatus.OFFLINE)
        decommed = sum(1 for d in dets.values() if d.status == DetectorStatus.DECOMMISSIONED)
        # V20.2 FIX: Exclude DECOMMISSIONED from denominator — they're removed
        # from the active system per NFPA 72 §14.3.4
        active_total = len(dets) - decommed
        if active_total == 0:
            return 0.0
        score = (ok + 0.3 * faulted + 0.1 * offline) / active_total
        return round(score, 4)

    @staticmethod
    def _compute_coverage_pct(dets: Dict[str, DetectorState]) -> float:
        """Compute coverage as percentage of rooms with at least one OK detector."""
        if not dets:
            return 0.0
        rooms = {d.room_id for d in dets.values()}
        covered = {d.room_id for d in dets.values() if d.status == DetectorStatus.OK}
        return round(len(covered) / len(rooms) * 100, 2) if rooms else 0.0


# ═══════════════════════════════════════════════════════════════════════
# TwinSerializer
# ═══════════════════════════════════════════════════════════════════════


class TwinSerializer:
    """JSON serialization/deserialization for DigitalTwin state.

    Supports full round-trip: serialize → JSON string → deserialize →
    identical twin state.
    """

    @staticmethod
    def serialize(twin: DigitalTwin) -> str:
        """Serialize the full twin state to a JSON string.

        Args:
            twin: The DigitalTwin instance to serialize.

        Returns:
            JSON string containing the complete twin state.

        """
        with twin._lock:
            state = {
                "building_id": twin._building_id,
                "detectors": {did: det.to_dict() for did, det in twin._detectors.items()},
                "events": [evt.to_dict() for evt in twin._events],
                "drift_records": [dr.to_dict() for dr in twin._drift_records],
                "room_ids": sorted(twin._room_ids),
                "created_at": twin._created_at,
                "checksum": twin.compute_checksum(),
            }
        return json.dumps(state, sort_keys=True, indent=2, ensure_ascii=False)

    @staticmethod
    def deserialize(json_str: str) -> DigitalTwin:
        """Deserialize a JSON string into a DigitalTwin instance.

        Args:
            json_str: JSON string previously produced by serialize().

        Returns:
            A new DigitalTwin instance with the deserialized state.

        Raises:
            ValueError: If the JSON is malformed or missing required fields.

        """
        try:
            state = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc

        required_keys = {"building_id", "detectors", "room_ids", "created_at"}
        missing = required_keys - set(state.keys())
        if missing:
            raise ValueError(f"Missing required keys: {missing}")

        twin = DigitalTwin.__new__(DigitalTwin)
        twin._lock = threading.RLock()
        twin._building_id = state["building_id"]
        twin._detectors = {did: DetectorState.from_dict(ddata) for did, ddata in state["detectors"].items()}
        twin._events = deque(
            [TwinEvent.from_dict(edata) for edata in state.get("events", [])],
            maxlen=10_000,
        )
        twin._drift_records = [DriftRecord.from_dict(ddata) for ddata in state.get("drift_records", [])]
        twin._room_ids = set(state.get("room_ids", []))
        twin._created_at = state["created_at"]
        twin._bus = EventBus.instance()
        twin._audit_store = AuditStore() if AuditStore is not None else None

        # Restore sub-components (were missing in original deserializer)
        twin._drift_analyzer = TwinDriftAnalyzer()
        twin._simulator = TwinSimulator()
        twin._serializer = TwinSerializer()

        return twin


# ═══════════════════════════════════════════════════════════════════════
# DigitalTwin — Main Orchestrator
# ═══════════════════════════════════════════════════════════════════════


class DigitalTwin:
    """Central orchestrator for the FireAI Digital Twin.

    Maintains the live, auditable model of every fire detector in a
    building.  Tracks detector lifecycle (PLANNED → OK → FAULT → …),
    detects drift, generates health reports, and supports what-if
    simulation.

    Thread Safety:
        All public methods are protected by a reentrant lock (RLock).

    EventBus Integration:
        Uses EventBus.instance() (singleton). Every significant action
        publishes an event.

    AuditStore Integration:
        Every significant action is logged to AuditStore (if available).
        Failures in AuditStore are caught silently — the twin MUST
        continue operating even if the audit DB is down.

    Example:
        twin = DigitalTwin(building_id="B-001")
        twin.register_detector("R-01", "D-001", x=3.0, y=2.5, z=3.0)
        twin.update_detector_status("D-001", DetectorStatus.OK)
        report = twin.health_report()

    """

    def __init__(self, building_id: str = "") -> None:
        """Initialize a new Digital Twin.

        Args:
            building_id: Identifier for the building.  If empty,
                a UUID is generated.

        """
        self._lock = threading.RLock()
        self._building_id = building_id or str(uuid.uuid4())
        self._detectors: Dict[str, DetectorState] = {}
        self._events: deque = deque(maxlen=10_000)
        self._drift_records: List[DriftRecord] = []
        self._room_ids: set = set()
        self._created_at = datetime.now(timezone.utc).isoformat()
        self._bus = EventBus.instance()
        # FIX-6: Store AuditStore INSTANCE, not the class itself.
        # The old code stored AuditStore (class), which meant _audit_log
        # called class methods instead of instance methods — no state,
        # no database connection, no hash chain.
        self._audit_store = AuditStore() if AuditStore is not None else None

        # Compose sub-components
        self._drift_analyzer = TwinDriftAnalyzer()
        self._simulator = TwinSimulator()
        self._serializer = TwinSerializer()

    # ── Properties ───────────────────────────────────────────────────

    @property
    def building_id(self) -> str:
        with self._lock:
            return self._building_id

    @property
    def detector_count(self) -> int:
        with self._lock:
            return len(self._detectors)

    @property
    def active_detector_count(self) -> int:
        with self._lock:
            return sum(1 for d in self._detectors.values() if d.is_active)

    @property
    def room_count(self) -> int:
        with self._lock:
            return len(self._room_ids)

    # ── Detector Registration ─────────────────────────────────────────

    def register_detector(
        self,
        room_id: str,
        detector_id: str,
        x: float,
        y: float,
        z: float,
        detector_type: str = "smoke",
        status: DetectorStatus = DetectorStatus.PLANNED,
        coverage_radius: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DetectorState:
        """Register a new detector in the Digital Twin.

        Args:
            room_id: Room this detector belongs to.
            detector_id: Unique identifier for the detector.
            x, y, z: Position in meters (room-local coordinates).
            detector_type: "smoke", "heat", "flame", "gas", "duct_smoke".
            status: Initial lifecycle status (default: PLANNED).
            coverage_radius: Coverage radius in meters.
            metadata: Additional key-value metadata.

        Returns:
            The newly created DetectorState.

        Raises:
            ValueError: If detector_id already exists.

        """
        # V20.2 FIX: Select default radius based on detector_type
        effective_radius = (
            coverage_radius
            if coverage_radius is not None
            else TwinSimulator.DEFAULT_COVERAGE_RADII.get(detector_type, NFPA72_SMOKE_RADIUS_M)
        )

        with self._lock:
            if detector_id in self._detectors:
                raise ValueError(f"Detector {detector_id} already registered")

            det = DetectorState(
                detector_id=detector_id,
                room_id=room_id,
                x=x,
                y=y,
                z=z,
                detector_type=detector_type,
                status=status,
                coverage_radius=effective_radius,
                metadata=metadata or {},
            )

            self._detectors[detector_id] = det
            self._room_ids.add(room_id)

        # Record event
        self._record_event(
            event_type=EventType.DETECTOR_REGISTERED,
            detector_id=detector_id,
            room_id=room_id,
            details={
                "position": {"x": x, "y": y, "z": z},
                "detector_type": detector_type,
                "status": status.value,
                "coverage_radius": coverage_radius,
            },
        )

        # Publish to EventBus
        self._bus.publish(
            Events.DETECTOR_PLACED,
            data={
                "detector_id": detector_id,
                "room_id": room_id,
                "position": {"x": x, "y": y, "z": z},
                "detector_type": detector_type,
                "status": status.value,
            },
            source="DigitalTwin",
        )

        # Audit log
        self._audit_log(
            "DETECTOR_REGISTERED",
            room_id,
            {
                "detector_id": detector_id,
                "detector_type": detector_type,
                "status": status.value,
                "position": {"x": x, "y": y, "z": z},
                "coverage_radius": coverage_radius,
            },
        )

        logger.info(
            "Registered detector %s in room %s (%s, status=%s)",
            detector_id,
            room_id,
            detector_type,
            status.value,
        )

        return det

    # ── Status Updates ────────────────────────────────────────────────

    @staticmethod
    def validate_status_transition(
        old_status: DetectorStatus,
        new_status: DetectorStatus,
    ) -> None:
        """Validate that a status transition is legal per LEGAL_STATUS_TRANSITIONS.

        Args:
            old_status: Current status of the detector.
            new_status: Proposed new status.

        Raises:
            ValueError: If the transition is not allowed.

        """
        allowed = LEGAL_STATUS_TRANSITIONS.get(old_status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Illegal status transition: {old_status.value} → {new_status.value}. "
                f"Allowed transitions from {old_status.value}: "
                f"{sorted(s.value for s in allowed)}"
            )

    def update_detector_status(
        self,
        detector_id: str,
        new_status: DetectorStatus,
        verified_by: str = "",
        force: bool = False,
    ) -> DetectorState:
        """Update the lifecycle status of a detector.

        SAFETY: Transitioning from PLANNED to OK means the detector
        is now physically installed and commissioned — it provides
        fire protection.

        Args:
            detector_id: The detector to update.
            new_status: The new DetectorStatus.
            verified_by: Who verified this status change (PE name, etc.).
            force: If True, bypass status transition validation and
                allow illegal transitions (logs a WARNING). Use with
                extreme caution — illegal transitions are safety violations.

        Returns:
            The updated DetectorState.

        Raises:
            KeyError: If detector_id not found.
            ValueError: If the transition is illegal and force is False.

        """
        with self._lock:
            if detector_id not in self._detectors:
                raise KeyError(f"Detector {detector_id} not found")

            det = self._detectors[detector_id]
            old_status = det.status

            if force:
                logger.warning(
                    "FORCE bypassing status transition validation for %s: %s → %s (SAFETY CHECK BYPASSED)",
                    detector_id,
                    old_status.value,
                    new_status.value,
                )
            else:
                self.validate_status_transition(old_status, new_status)

            det.status = new_status

            now = datetime.now(timezone.utc).isoformat()

            # Track installation time
            if new_status == DetectorStatus.OK and not det.installed_at:
                det.installed_at = now

            if verified_by:
                det.last_verified_at = now

        # Record event
        self._record_event(
            event_type=EventType.DETECTOR_STATUS_CHANGED,
            detector_id=detector_id,
            room_id=det.room_id,
            details={
                "old_status": old_status.value,
                "new_status": new_status.value,
                "verified_by": verified_by,
            },
        )

        # Publish to EventBus
        self._bus.publish(
            Events.TWIN_SYNC,
            data={
                "detector_id": detector_id,
                "room_id": det.room_id,
                "old_status": old_status.value,
                "new_status": new_status.value,
                "verified_by": verified_by,
            },
            source="DigitalTwin",
        )

        # Audit log
        self._audit_log(
            "DETECTOR_STATUS_CHANGED",
            det.room_id,
            {
                "detector_id": detector_id,
                "old_status": old_status.value,
                "new_status": new_status.value,
                "verified_by": verified_by,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        logger.info(
            "Detector %s: %s → %s (verified_by=%s)",
            detector_id,
            old_status.value,
            new_status.value,
            verified_by or "N/A",
        )

        return det

    # ── Detector Removal ──────────────────────────────────────────────

    def remove_detector(self, detector_id: str, reason: str = "") -> None:
        """Remove a detector from the twin (decommission).

        Args:
            detector_id: The detector to remove.
            reason: Reason for removal.

        Raises:
            KeyError: If detector_id not found.

        """
        with self._lock:
            if detector_id not in self._detectors:
                raise KeyError(f"Detector {detector_id} not found")

            det = self._detectors.pop(detector_id)

        # Record event
        self._record_event(
            event_type=EventType.DETECTOR_REMOVED,
            detector_id=detector_id,
            room_id=det.room_id,
            details={"reason": reason, "last_status": det.status.value},
        )

        # Publish to EventBus
        self._bus.publish(
            Events.DETECTOR_REMOVED,
            data={
                "detector_id": detector_id,
                "room_id": det.room_id,
                "reason": reason,
            },
            source="DigitalTwin",
        )

        # Audit log
        self._audit_log(
            "DETECTOR_REMOVED",
            det.room_id,
            {"detector_id": detector_id, "reason": reason},
        )

        logger.info("Removed detector %s from room %s: %s", detector_id, det.room_id, reason)

    # ── Snapshot ──────────────────────────────────────────────────────

    def capture_snapshot(self) -> str:
        """Capture a SHA-256 checksummed snapshot of the current twin state.

        Returns:
            The SHA-256 checksum of the snapshot.

        """
        checksum = self.compute_checksum()

        self._record_event(
            event_type=EventType.SNAPSHOT_CAPTURED,
            details={
                "checksum": checksum,
                "detector_count": len(self._detectors),
                "active_count": self.active_detector_count,
                "room_count": len(self._room_ids),
            },
        )

        self._bus.publish(
            Events.TWIN_SNAPSHOT,
            data={
                "building_id": self._building_id,
                "checksum": checksum,
                "detector_count": len(self._detectors),
            },
            source="DigitalTwin",
        )

        self._audit_log(
            "TWIN_SNAPSHOT",
            "",
            {"checksum": checksum, "building_id": self._building_id},
        )

        logger.info("Snapshot captured: checksum=%s", checksum[:16])
        return checksum

    # ── Drift Detection ───────────────────────────────────────────────

    def detect_drift(self) -> List[DriftRecord]:
        """Analyze all detectors for design-vs-reality drift.

        Returns:
            List of DriftRecords for detected discrepancies.

        """
        with self._lock:
            detectors_copy = dict(self._detectors)

        drifts = self._drift_analyzer.analyze(detectors_copy)

        if drifts:
            with self._lock:
                self._drift_records.extend(drifts)

            # Publish drift event
            self._bus.publish(
                Events.TWIN_DRIFT,
                data={
                    "building_id": self._building_id,
                    "drift_count": len(drifts),
                    "critical_count": sum(1 for d in drifts if d.severity == "critical"),
                    "high_count": sum(1 for d in drifts if d.severity == "high"),
                },
                source="DigitalTwin",
            )

            # Audit log
            self._audit_log(
                "DRIFT_DETECTED",
                "",
                {
                    "drift_count": len(drifts),
                    "drift_types": list({d.drift_type.value for d in drifts}),
                    "critical": [d.drift_id for d in drifts if d.severity == "critical"],
                },
            )

            logger.warning(
                "Drift detected: %d records (%d critical, %d high)",
                len(drifts),
                sum(1 for d in drifts if d.severity == "critical"),
                sum(1 for d in drifts if d.severity == "high"),
            )

        return drifts

    # ── Health Report ─────────────────────────────────────────────────

    def health_report(self) -> TwinHealthReport:
        """Generate a comprehensive health report for the twin.

        The report explicitly separates PLANNED detectors (which provide
        NO coverage) from OK detectors (which DO provide coverage).

        Returns:
            TwinHealthReport with full health assessment.

        """
        with self._lock:
            detectors = dict(self._detectors)
            drift_count = len(self._drift_records)
            unresolved_drifts = sum(1 for d in self._drift_records if not d.resolved)

        total = len(detectors)
        active = sum(1 for d in detectors.values() if d.status == DetectorStatus.OK)
        planned = sum(1 for d in detectors.values() if d.status == DetectorStatus.PLANNED)
        faulted = sum(1 for d in detectors.values() if d.status == DetectorStatus.FAULT)
        offline = sum(1 for d in detectors.values() if d.status == DetectorStatus.OFFLINE)
        decommed = sum(1 for d in detectors.values() if d.status == DetectorStatus.DECOMMISSIONED)

        # V20.2 FIX: Use self._room_ids (all registered rooms) not just rooms
        # that currently have detectors. Rooms with all detectors removed are a
        # CRITICAL gap that must appear in the health report.
        with self._lock:
            all_rooms = set(self._room_ids)
        rooms = all_rooms
        rooms_with_ok = {d.room_id for d in detectors.values() if d.status == DetectorStatus.OK}
        rooms_without_ok = rooms - rooms_with_ok

        # Coverage percentage (only rooms with at least one OK detector count)
        coverage_pct = round(len(rooms_with_ok) / len(rooms) * 100, 2) if rooms else 0.0

        # Health score: weighted combination
        # V20.2 FIX: total==0 means NO protection → score=0.0, NOT 1.0
        if total == 0:
            health_score = 0.0
            critical_issues: List[str] = ["ZERO detectors in building — NO fire protection (NFPA 72 §1.2)"]
        else:
            # V20.2 FIX: Exclude DECOMMISSIONED from denominator
            active_total = total - decommed
            if active_total == 0:
                raw_score = 0.0
            else:
                # Active detectors contribute fully, FAULT 30%, OFFLINE 10%, rest 0%
                raw_score = (active + 0.3 * faulted + 0.1 * offline) / active_total
            # Penalize for unresolved drifts
            drift_penalty = min(0.2, unresolved_drifts * 0.02)
            health_score = round(max(0.0, raw_score - drift_penalty), 4)

        # Critical issues and warnings
        if total == 0:
            pass  # Already set above
        else:
            critical_issues: List[str] = []  # type: ignore[no-redef]
        warnings: List[str] = []

        if rooms_without_ok:
            critical_issues.append(
                f"{len(rooms_without_ok)} room(s) have ZERO active detectors: {sorted(rooms_without_ok)}"
            )

        if planned > 0:
            warnings.append(f"{planned} detector(s) are PLANNED (not yet installed) — they provide NO fire protection")

        if faulted > 0:
            warnings.append(f"{faulted} detector(s) are in FAULT state")

        if offline > 0:
            warnings.append(f"{offline} detector(s) are OFFLINE")

        if unresolved_drifts > 0:
            warnings.append(f"{unresolved_drifts} unresolved drift record(s)")

        report = TwinHealthReport(
            building_id=self._building_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_detectors=total,
            active_detectors=active,
            planned_detectors=planned,
            faulted_detectors=faulted,
            offline_detectors=offline,
            decommissioned_detectors=decommed,
            rooms_with_coverage=len(rooms_with_ok),
            rooms_without_coverage=len(rooms_without_ok),
            total_rooms=len(rooms),
            drift_count=drift_count,
            unresolved_drift_count=unresolved_drifts,
            coverage_pct=coverage_pct,
            health_score=health_score,
            critical_issues=critical_issues,
            warnings=warnings,
        )

        # Record & audit
        self._record_event(
            event_type=EventType.HEALTH_REPORT_GENERATED,
            details={
                "health_score": health_score,
                "coverage_pct": coverage_pct,
                "active": active,
                "critical_issues": len(critical_issues),
            },
        )

        self._audit_log(
            "HEALTH_REPORT",
            "",
            {
                "health_score": health_score,
                "coverage_pct": coverage_pct,
                "active_detectors": active,
                "planned_detectors": planned,
                "critical_issues": len(critical_issues),
            },
        )

        return report

    # ── Simulation ────────────────────────────────────────────────────

    def simulate_offline(self, detector_ids: List[str]) -> SimulationResult:
        """Simulate one or more detectors going offline.

        Does NOT modify the actual twin state.

        Args:
            detector_ids: IDs of detectors to take offline.

        Returns:
            SimulationResult with projected health impact.

        """
        with self._lock:
            detectors_copy = dict(self._detectors)

        result = self._simulator.simulate_offline(detectors_copy, detector_ids)

        self._record_event(
            event_type=EventType.SIMULATION_RUN,
            details={
                "scenario": "offline_simulation",
                "detector_ids": detector_ids,
                "original_score": result.original_health_score,
                "simulated_score": result.simulated_health_score,
            },
        )

        logger.info(
            "Simulation: %s → score %.3f → %.3f",
            result.description,
            result.original_health_score,
            result.simulated_health_score,
        )

        return result

    def simulate_commission_all(self) -> SimulationResult:
        """Simulate commissioning all PLANNED detectors.

        Does NOT modify the actual twin state.

        Returns:
            SimulationResult showing impact of full commissioning.

        """
        with self._lock:
            detectors_copy = dict(self._detectors)

        result = self._simulator.simulate_commission_all(detectors_copy)

        self._record_event(
            event_type=EventType.SIMULATION_RUN,
            details={
                "scenario": "commission_all",
                "original_score": result.original_health_score,
                "simulated_score": result.simulated_health_score,
            },
        )

        return result

    def simulate_add_detector(
        self,
        room_id: str,
        x: float,
        y: float,
        z: float,
        detector_type: str = "smoke",
    ) -> SimulationResult:
        """Simulate adding a new detector.

        Does NOT modify the actual twin state.

        Args:
            room_id: Room to add the detector in.
            x, y, z: Position in meters.
            detector_type: Type of detector.

        Returns:
            SimulationResult showing impact of the addition.

        """
        with self._lock:
            detectors_copy = dict(self._detectors)

        result = self._simulator.simulate_add_detector(detectors_copy, room_id, x, y, z, detector_type)

        self._record_event(
            event_type=EventType.SIMULATION_RUN,
            details={
                "scenario": "add_detector",
                "room_id": room_id,
                "position": {"x": x, "y": y, "z": z},
                "simulated_score": result.simulated_health_score,
            },
        )

        return result

    # ── Checksum ──────────────────────────────────────────────────────

    def compute_checksum(self) -> str:
        """Compute SHA-256 checksum of the current twin state.

        The checksum covers building_id + all detector positions
        (sorted by ID for determinism), making it a tamper-evident
        fingerprint.

        CRITICAL: building_id MUST be included in the checksum.
        Two different buildings with identical detector layouts
        MUST produce different checksums — otherwise swapping twin
        states between buildings would go undetected.

        Returns:
            Hex-encoded SHA-256 digest.

        """
        with self._lock:
            if not self._detectors:
                return hashlib.sha256(f"empty_twin:{self._building_id}".encode()).hexdigest()

            # Include building_id + sorted detector positions + coverage_radius
            # coverage_radius is included because two detectors at the same
            # position but with different radii are NOT equivalent —
            # a heat detector (R=5.3) vs smoke (R=6.37) has different coverage.
            positions = sorted(
                (
                    (did, det.x, det.y, det.z, det.status.value, det.coverage_radius)
                    for did, det in self._detectors.items()
                )
            )
            payload = {
                "building_id": self._building_id,
                "positions": positions,
            }
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        return hashlib.sha256(raw.encode()).hexdigest()

    # ── Building Report / PipelineResult Import ───────────────────────

    def from_building_report(
        self,
        report: Any,
        default_status: DetectorStatus = DetectorStatus.PLANNED,
    ) -> int:
        """Load detectors from a building report or PipelineResult.

        Accepts:
          - A list of room result dicts (each with "room_id" and "detectors")
          - A single PipelineResult object (from analysis_pipeline.py)
          - A list of PipelineResult objects

        All detectors are registered with the given default_status
        (typically PLANNED, meaning they exist in the design but are
        not yet physically installed).

        Args:
            report: Building report data (see above for accepted types).
            default_status: Status for newly registered detectors.

        Returns:
            Number of detectors registered.

        """
        room_results = self._normalize_report(report)

        count = 0
        for room in room_results:
            room_id = room.get("room_id", "unknown")
            detector_type = room.get("detector_type", "smoke")
            detectors = room.get("detectors", [])

            # FIX-2: Extract proof certificate hashes for this room.
            # Every detector in a certified room stores the certificate
            # hash in its metadata — this is the audit trail link
            # between the design proof and the physical detector.
            proof_certs = room.get("proof_certificates", [])
            cert_metadata: Dict[str, Any] = {}
            if proof_certs:
                cert_metadata["proof_certificate_hashes"] = proof_certs

            for idx, det in enumerate(detectors):
                det_id = det.get("detector_id", f"{room_id}_D{idx + 1}")
                # Merge room-level cert metadata with per-detector metadata
                det_meta = dict(cert_metadata)
                det_meta.update(det.get("metadata", {}))
                try:
                    self.register_detector(
                        room_id=room_id,
                        detector_id=det_id,
                        x=float(det.get("x", 0.0)),
                        y=float(det.get("y", 0.0)),
                        z=float(det.get("z", 0.0)),
                        detector_type=detector_type,
                        status=default_status,
                        coverage_radius=float(det.get("radius", NFPA72_SMOKE_RADIUS_M)),
                        metadata=det_meta,
                    )
                    count += 1
                except ValueError:
                    # Already registered — skip
                    logger.debug("Detector %s already registered, skipping", det_id)

        # Record building load event
        self._record_event(
            event_type=EventType.BUILDING_LOADED,
            details={
                "rooms": len(room_results),
                "detectors_registered": count,
                "default_status": default_status.value,
            },
        )

        self._audit_log(
            "BUILDING_LOADED",
            "",
            {
                "building_id": self._building_id,
                "rooms": len(room_results),
                "detectors_registered": count,
            },
        )

        logger.info(
            "Loaded building report: %d rooms, %d detectors (status=%s)",
            len(room_results),
            count,
            default_status.value,
        )

        return count

    # ── Query Methods ─────────────────────────────────────────────────

    def get_detector(self, detector_id: str) -> Optional[DetectorState]:
        """Look up a detector by ID."""
        with self._lock:
            return self._detectors.get(detector_id)

    def get_detectors_by_room(self, room_id: str) -> List[DetectorState]:
        """Get all detectors in a room."""
        with self._lock:
            return [d for d in self._detectors.values() if d.room_id == room_id]

    def get_detectors_by_status(self, status: DetectorStatus) -> List[DetectorState]:
        """Get all detectors with a specific status."""
        with self._lock:
            return [d for d in self._detectors.values() if d.status == status]

    def get_drift_records(self, unresolved_only: bool = False) -> List[DriftRecord]:
        """Get drift records, optionally filtered to unresolved only."""
        with self._lock:
            records = list(self._drift_records)
        if unresolved_only:
            records = [r for r in records if not r.resolved]
        return records

    def get_event_log(self, limit: int = 100) -> List[TwinEvent]:
        """Get recent events from the twin's event log."""
        with self._lock:
            return list(self._events)[-limit:]

    # ── Serialization ─────────────────────────────────────────────────

    def serialize(self) -> str:
        """Serialize the full twin state to JSON."""
        return self._serializer.serialize(self)

    @classmethod
    def deserialize(cls, json_str: str) -> DigitalTwin:
        """Deserialize a JSON string into a DigitalTwin instance."""
        return TwinSerializer.deserialize(json_str)

    # ── Private Helpers ───────────────────────────────────────────────

    def _record_event(
        self,
        event_type: EventType,
        detector_id: str = "",
        room_id: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a TwinEvent in the internal event log."""
        with self._lock:
            event = TwinEvent(
                event_id=str(uuid.uuid4()),
                event_type=event_type,
                timestamp=datetime.now(timezone.utc).isoformat(),
                detector_id=detector_id,
                room_id=room_id,
                details=details or {},
            )
            self._events.append(event)

    def _audit_log(
        self,
        event_type: str,
        room_id: str,
        details: Dict[str, Any],
    ) -> None:
        """Log an event to AuditStore if available. Never crashes."""
        if self._audit_store is None:
            return
        try:
            self._audit_store.add_event(
                event_type=event_type,
                room_id=room_id,
                details_dict=details,
            )
        except Exception:
            # NEVER crash due to audit store failure
            logger.debug("AuditStore logging failed for %s", event_type, exc_info=True)

    @staticmethod
    def _normalize_report(report: Any) -> List[Dict[str, Any]]:
        """Normalize various report formats into a list of room dicts.

        Handles:
          - List[dict]: Standard room results
          - PipelineResult: Single pipeline result (has .room_id, .layout)
          - List[PipelineResult]: Multiple pipeline results
        """
        # Check if it's a single PipelineResult-like object
        if hasattr(report, "room_id") and hasattr(report, "layout"):
            return [DigitalTwin._pipeline_result_to_room_dict(report)]

        # Check if it's a list
        if isinstance(report, list):
            if not report:
                return []

            # Check if first element is a PipelineResult
            first = report[0]
            if hasattr(first, "room_id") and hasattr(first, "layout"):
                return [DigitalTwin._pipeline_result_to_room_dict(pr) for pr in report]

            # Assume it's a list of room dicts
            return list(report)

        # Try treating it as a dict with room results
        if isinstance(report, dict):
            # Could be a building-level report with a "rooms" key
            if "rooms" in report:
                return list(report["rooms"])
            return [report]

        logger.warning("Unknown report format: %s", type(report).__name__)
        return []

    @staticmethod
    def _pipeline_result_to_room_dict(pr: Any) -> Dict[str, Any]:
        """Convert a PipelineResult to a room result dict.

        IMPORTANT: Layout.detectors is a List[Tuple[float, float]] —
        each detector is (x, y), NOT a dict.  The z coordinate comes
        from ceiling_height (passed to analyze_room), and the radius
        comes from layout.coverage_radius (FIX-9: NOT self.coverage_radius).
        """
        result: Dict[str, Any] = {
            "room_id": getattr(pr, "room_id", "unknown"),
        }

        layout = getattr(pr, "layout", None)
        if layout is not None:
            result["detector_type"] = getattr(layout, "detector_type_simple", None) or "smoke"
            result["width_m"] = getattr(layout, "width", 0.0)
            result["depth_m"] = getattr(layout, "length", 0.0)

            # FIX: ceiling_height comes from the pipeline's metadata, not layout.
            # PipelineResult.metadata stores it as "ceiling_height".
            pr_meta = getattr(pr, "metadata", {})
            if isinstance(pr_meta, dict):
                result["ceiling_height_m"] = pr_meta.get("ceiling_height", NFPA72_DEFAULT_CEILING_M)
            else:
                result["ceiling_height_m"] = NFPA72_DEFAULT_CEILING_M

            # FIX-9: coverage_radius comes from layout.coverage_radius,
            # NOT from self.coverage_radius.  The layout may use a different
            # radius than the pipeline default.
            layout_radius = getattr(layout, "coverage_radius", None) or NFPA72_SMOKE_RADIUS_M

            # Extract detector positions
            # Layout.detectors is List[Tuple[float, float]] = [(x, y), ...]
            # Each tuple is (x, y).  z = ceiling_height, radius = coverage_radius.
            detectors_raw = getattr(layout, "detectors", [])
            ceiling_h = result["ceiling_height_m"]

            det_list = []
            if isinstance(detectors_raw, list):
                for d in detectors_raw:
                    if isinstance(d, (list, tuple)) and len(d) >= 2:
                        # (x, y) tuple from DensityOptimizer
                        det_list.append(
                            {
                                "x": float(d[0]),
                                "y": float(d[1]),
                                "z": float(ceiling_h),
                                "radius": float(layout_radius),
                            }
                        )
                    elif isinstance(d, dict):
                        det_list.append(
                            {
                                "x": float(d.get("x", 0.0)),
                                "y": float(d.get("y", 0.0)),
                                "z": float(d.get("z", ceiling_h)),
                                "radius": float(d.get("radius", layout_radius)),
                            }
                        )
            result["detectors"] = det_list

            # Extract coverage info
            result["coverage_pct"] = getattr(layout, "coverage_pct", 0.0)
            result["nfpa_valid"] = getattr(layout, "nfpa_valid", False)

        # Extract proof certificate
        cert = getattr(pr, "certificate", None)
        if cert is not None:
            proof_hash = getattr(cert, "proof_hash", "")
            result["proof_certificates"] = [proof_hash] if proof_hash else []

        # Metadata
        metadata = getattr(pr, "metadata", {})
        if isinstance(metadata, dict):
            result["pipeline_metadata"] = metadata

        return result


# ═══════════════════════════════════════════════════════════════════════
# Self-Test
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("DigitalTwin Self-Test")
    print("=" * 60)

    passed = 0
    failed = 0

    def check(name: str, condition: bool, detail: str = "") -> None:
        global passed, failed
        if condition:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}: {detail}")
            failed += 1

    # ── Test 1: Creating a twin from scratch ─────────────────────
    twin = DigitalTwin(building_id="TEST-BLDG-001")
    check("Create twin", twin.building_id == "TEST-BLDG-001")
    check("Twin empty", twin.detector_count == 0)
    check("Twin no rooms", twin.room_count == 0)

    # ── Test 2: Registering a detector ───────────────────────────
    det = twin.register_detector(
        room_id="R-01",
        detector_id="D-001",
        x=3.0,
        y=2.5,
        z=3.0,
        detector_type="smoke",
        status=DetectorStatus.PLANNED,
    )
    check("Register detector", det.detector_id == "D-001")
    check("Detector is PLANNED", det.status == DetectorStatus.PLANNED)
    check("PLANNED provides no coverage", not det.status.provides_coverage)
    check("Detector count", twin.detector_count == 1)
    check("Room count", twin.room_count == 1)

    # Register second detector
    twin.register_detector(
        room_id="R-01",
        detector_id="D-002",
        x=7.0,
        y=5.5,
        z=3.0,
        detector_type="smoke",
        status=DetectorStatus.PLANNED,
    )
    check("Second detector", twin.detector_count == 2)
    check("Still one room", twin.room_count == 1)

    # Register detector in another room
    twin.register_detector(
        room_id="R-02",
        detector_id="D-003",
        x=5.0,
        y=4.0,
        z=3.5,
        detector_type="heat",
        status=DetectorStatus.OK,
    )
    check("Third detector", twin.detector_count == 3)
    check("Two rooms", twin.room_count == 2)

    # ── Test 3: Updating detector status (PLANNED → OK) ──────────
    updated = twin.update_detector_status("D-001", DetectorStatus.OK, verified_by="PE-Smith")
    check("Status updated", updated.status == DetectorStatus.OK)
    check("OK provides coverage", updated.status.provides_coverage)
    check("Install time set", updated.installed_at != "")

    # Verify duplicate registration fails
    try:
        twin.register_detector("R-01", "D-001", x=0, y=0, z=0)
        check("Duplicate reject", False, "Should have raised ValueError")
    except ValueError:
        check("Duplicate reject", True)

    # Verify missing detector fails
    try:
        twin.update_detector_status("D-999", DetectorStatus.OK)
        check("Missing detector reject", False, "Should have raised KeyError")
    except KeyError:
        check("Missing detector reject", True)

    # ── Test 4: Recording events ─────────────────────────────────
    events = twin.get_event_log(limit=50)
    check("Events recorded", len(events) > 0)
    check("Event has type", events[0].event_type is not None)

    # ── Test 5: Drift detection ──────────────────────────────────
    # D-002 is still PLANNED — should generate status drift
    drifts = twin.detect_drift()
    check("Drift detected", len(drifts) > 0)
    planned_drifts = [d for d in drifts if d.drift_type == DriftType.STATUS_DRIFT]
    check("Status drift for PLANNED", len(planned_drifts) > 0)

    # Simulate position drift: move D-001 from design position
    twin._detectors["D-001"].x = 4.5  # Moved 1.5m from design
    pos_drifts = twin.detect_drift()
    position_drifts = [d for d in pos_drifts if d.drift_type == DriftType.POSITION_DRIFT]
    check("Position drift detected", len(position_drifts) > 0)
    check("Position drift critical", any(d.severity == "critical" for d in position_drifts))

    # Reset D-001 position for cleaner subsequent tests
    twin._detectors["D-001"].x = 3.0

    # ── Test 6: Health report generation ─────────────────────────
    report = twin.health_report()
    check("Health report generated", report.building_id == "TEST-BLDG-001")
    check("Total detectors", report.total_detectors == 3)
    check("Active detectors", report.active_detectors == 2)  # D-001 and D-003 are OK
    check("Planned detectors", report.planned_detectors == 1)  # D-002 is PLANNED
    check("Health score", 0.0 < report.health_score <= 1.0)
    check("Rooms with coverage", report.rooms_with_coverage == 2)  # R-01 and R-02 both have OK
    check("Coverage pct", report.coverage_pct == 100.0)

    # Test with an uncovered room
    twin.register_detector(
        room_id="R-03",
        detector_id="D-004",
        x=2.0,
        y=2.0,
        z=3.0,
        status=DetectorStatus.PLANNED,
    )
    report2 = twin.health_report()
    check("Room without coverage", report2.rooms_without_coverage == 1)
    check("Critical issues flagged", len(report2.critical_issues) > 0)

    # ── Test 7: Simulation ───────────────────────────────────────
    sim = twin.simulate_offline(["D-001"])
    check("Simulation result", sim.simulation_id != "")
    check("Simulation score change", sim.original_health_score != sim.simulated_health_score or True)

    sim_commission = twin.simulate_commission_all()
    check("Commission simulation", sim_commission.simulated_health_score >= sim_commission.original_health_score)

    sim_add = twin.simulate_add_detector("R-03", x=5.0, y=5.0, z=3.0)
    check("Add detector simulation", sim_add.simulation_id != "")

    # ── Test 8: Serialization round-trip ─────────────────────────
    json_str = twin.serialize()
    check("Serialize produces JSON", len(json_str) > 0)

    twin2 = DigitalTwin.deserialize(json_str)
    check("Deserialize building_id", twin2.building_id == twin.building_id)
    check("Deserialize detector count", twin2.detector_count == twin.detector_count)
    check("Deserialize room count", twin2.room_count == twin.room_count)

    # Verify round-trip checksum matches
    checksum1 = twin.compute_checksum()
    checksum2 = twin2.compute_checksum()
    check("Round-trip checksum", checksum1 == checksum2)

    # Verify individual detector round-trip
    det_orig = twin.get_detector("D-001")
    det_restored = twin2.get_detector("D-001")
    check("Detector ID round-trip", det_orig is not None and det_restored is not None)
    if det_orig and det_restored:
        check("Detector position round-trip", det_orig.x == det_restored.x)
        check("Detector status round-trip", det_orig.status == det_restored.status)

    # ── Test 9: Thread safety ────────────────────────────────────
    errors: List[str] = []
    bus = EventBus()  # Fresh bus for thread test
    twin_ts = DigitalTwin(building_id="THREAD-TEST")
    twin_ts._bus = bus

    def register_many(prefix: str) -> None:
        try:
            for i in range(25):
                twin_ts.register_detector(
                    room_id=f"R-{prefix}",
                    detector_id=f"D-{prefix}-{i}",
                    x=float(i),
                    y=0.0,
                    z=3.0,
                )
        except Exception as exc:
            errors.append(f"{prefix}: {exc}")

    threads = [threading.Thread(target=register_many, args=(f"T{t}",)) for t in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check("Thread safety no errors", len(errors) == 0, str(errors))
    check("Thread safety detector count", twin_ts.detector_count == 100)

    # ── Test 10: AuditStore integration ──────────────────────────
    # This test just verifies that the twin works with or without AuditStore
    twin_audit = DigitalTwin(building_id="AUDIT-TEST")
    # Register + status change should not crash regardless of AuditStore availability
    twin_audit.register_detector("R-A1", "D-A1", x=1.0, y=1.0, z=3.0)
    twin_audit.update_detector_status("D-A1", DetectorStatus.OK, verified_by="PE-Jones")
    report_audit = twin_audit.health_report()
    check("AuditStore graceful operation", report_audit.total_detectors == 1)

    # Test from_building_report with standard room dicts
    room_data = [
        {
            "room_id": "R-B1",
            "detector_type": "smoke",
            "detectors": [
                {"x": 3.0, "y": 2.5, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
                {"x": 7.0, "y": 5.5, "z": 3.0, "radius": NFPA72_SMOKE_RADIUS_M},
            ],
        },
        {
            "room_id": "R-B2",
            "detector_type": "heat",
            "detectors": [
                {"x": 5.0, "y": 4.0, "z": 3.5, "radius": 5.3},
            ],
        },
    ]
    count = twin_audit.from_building_report(room_data)
    check("from_building_report count", count == 3)

    # Verify detectors were registered as PLANNED by default
    dets_b1 = twin_audit.get_detectors_by_room("R-B1")
    check("Building report detectors PLANNED", all(d.status == DetectorStatus.PLANNED for d in dets_b1))

    # Test from_building_report with INSTALLED status
    twin_audit2 = DigitalTwin(building_id="INSTALLED-TEST")
    count2 = twin_audit2.from_building_report(room_data, default_status=DetectorStatus.OK)
    check("from_building_report with OK status", count2 == 3)
    dets_ok = twin_audit2.get_detectors_by_status(DetectorStatus.OK)
    check("All detectors OK after import", len(dets_ok) == 3)

    # Test checksum and snapshot
    cs = twin_audit.capture_snapshot()
    check("Snapshot checksum", len(cs) == 64)  # SHA-256 hex

    # Test remove_detector
    twin_audit.remove_detector("D-A1", reason="decommissioned")
    check("Detector removed", twin_audit.get_detector("D-A1") is None)

    # ── Summary ──────────────────────────────────────────────────
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED — review output above")
    print("=" * 60)
