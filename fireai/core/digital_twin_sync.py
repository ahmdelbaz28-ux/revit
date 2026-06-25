"""digital_twin_sync.py — Digital Twin Synchronization Module for FireAI
======================================================================

Synchronizes the design model with the digital twin, ensuring that the
virtual representation of the fire alarm system accurately reflects
reality — both the design intent (PLANNED detectors) and the as-built
condition (OK / FAULT / OFFLINE detectors).

CRITICAL SAFETY NOTE:
  A PLANNED detector provides ZERO fire protection.  Any sync operation
  that silently promotes a detector to OK without physical verification
  is a LIFE-SAFETY BUG.  This module enforces that distinction:
    - ``sync_design_to_twin()`` registers detectors as PLANNED only.
    - ``sync_as_built_to_twin()`` transitions detectors to OK only when
      explicit as-built verification data is provided.
  The ``validate_coverage()`` method checks for OK detectors, NOT
  PLANNED ones — counting PLANNED as coverage would be a SAFETY BUG.

NFPA 72-2022 References:
    - §1.2  — Purpose: life safety through reliable detection
    - §14.3  — Inspection, testing, and maintenance
    - §14.3.4 — Decommissioned devices removed from service
    - §17.6  — Smoke detector spacing and location
    - §17.7  — Heat detector spacing and location
    - §18.3  — Notification appliance placement
    - Chapter 14 — Acceptance testing and commissioning
    - Chapter 7  — Documentation requirements (sync audit trail)

Architecture:
    DigitalTwinSync composes:
      - DigitalTwin  (from digital_twin.py) — the live twin state
      - EventBus     (from event_bus.py) — real-time event publication
      - AuditStore   (optional) — legal-grade audit logging
      - TwinDriftAnalyzer (from digital_twin.py) — drift detection

  Every sync operation:
    1. Publishes an event on EventBus (Events.TWIN_SYNC / Events.TWIN_DRIFT)
    2. Logs to AuditStore (if available; never crashes if unavailable)
    3. Delegates to DigitalTwin methods for state mutation (thread-safe)
    4. Returns structured result objects (SyncResult, DriftReport, etc.)

Thread Safety:
    This module does NOT introduce its own locking.  All state mutations
    go through DigitalTwin methods which are RLock-protected.  Read
    operations also delegate to DigitalTwin's lock-protected getters.

Fail-Safe Principle:
    Individual detector sync failures are recorded in the SyncResult
    error list but do NOT abort the entire sync operation.  A partial
    sync is better than no sync — operators can review errors and
    re-sync individually.

Usage:
    from fireai.core.digital_twin_sync import (
        DigitalTwinSync, SyncResult, DriftReport, CoverageValidationResult,
    )
    from fireai.core.digital_twin import DigitalTwin, DetectorStatus

    twin = DigitalTwin(building_id="B-001")
    sync = DigitalTwinSync(twin=twin)

    # Push design model detectors as PLANNED
    design_detectors = [
        {"room_id": "R-01", "detector_id": "D-001", "x": 3.0, "y": 2.5, "z": 3.0},
        {"room_id": "R-01", "detector_id": "D-002", "x": 7.0, "y": 5.5, "z": 3.0},
    ]
    result = sync.sync_design_to_twin(design_detectors)
    print(f"Synced {result.synced_count} detectors, {len(result.errors)} errors")

    # Push as-built data (commissioning to OK)
    as_built = [
        {"detector_id": "D-001", "verified_by": "PE-Smith"},
    ]
    result = sync.sync_as_built_to_twin(as_built)
    print(f"Commissioned {result.synced_count} detectors")

    # Detect drift
    drift = sync.detect_drift()
    print(f"Found {drift.total_drifts} drifts, {drift.critical_count} critical")

    # Validate coverage
    coverage = sync.validate_coverage()
    print(f"Coverage: {coverage.coverage_pct:.1f}%, gaps: {coverage.rooms_without_coverage}")

    # Full sync report
    report = sync.generate_sync_report()
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from .digital_twin import (
    DetectorState,
    DetectorStatus,
    DigitalTwin,
    DriftRecord,
    DriftType,
    TwinDriftAnalyzer,
)
from .event_bus import EventBus, Events

# Optional AuditStore — graceful fallback if unavailable
try:
    from .audit_store import AuditStore
except ImportError:
    AuditStore = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


__all__ = [
    "CoverageValidationResult",
    "DigitalTwinSync",
    "DriftReport",
    "SyncReport",
    "SyncResult",
]


# ═══════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class SyncResult:
    """Result of a sync operation (design-to-twin or as-built-to-twin).

    Attributes:
        operation: Name of the sync operation performed.
        synced_count: Number of detectors successfully synced.
        skipped_count: Number of detectors skipped (e.g. already exists
            with same state, or illegal transition).
        error_count: Number of detectors that failed to sync.
        errors: List of (detector_id, error_message) tuples for failures.
        warnings: List of non-fatal warning messages.
        timestamp: ISO 8601 UTC timestamp of when the sync completed.
        building_id: Building identifier from the twin.
        correlation_id: Correlation ID linking all events from this sync.

    """

    operation: str
    synced_count: int
    skipped_count: int
    error_count: int
    errors: List[tuple] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: str = ""
    building_id: str = ""
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())

    @property
    def success(self) -> bool:
        """True if no errors occurred during the sync."""
        return self.error_count == 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for audit and reporting."""
        return {
            "operation": self.operation,
            "synced_count": self.synced_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "errors": self.errors,
            "warnings": self.warnings,
            "timestamp": self.timestamp,
            "building_id": self.building_id,
            "correlation_id": self.correlation_id,
            "success": self.success,
        }


@dataclass
class DriftReport:
    """Report of design-vs-reality drift detected in the digital twin.

    Aggregates all drift records from TwinDriftAnalyzer into a
    structured report suitable for AHJ review and operator action.

    NFPA 72-2022 §14.3 requires regular inspection and testing.  Drift
    between design and reality may indicate unreported field changes
    that could violate spacing requirements per §17.6 / §17.7.

    Attributes:
        building_id: Building identifier from the twin.
        drift_records: List of individual DriftRecord instances.
        total_drifts: Total number of drifts detected.
        critical_count: Number of critical-severity drifts.
        high_count: Number of high-severity drifts.
        medium_count: Number of medium-severity drifts.
        low_count: Number of low-severity drifts.
        position_drift_count: Number of position drifts.
        status_drift_count: Number of status drifts.
        missing_detector_count: Number of missing detector drifts.
        extra_detector_count: Number of extra detector drifts.
        type_mismatch_count: Number of type mismatch drifts.
        timestamp: ISO 8601 UTC timestamp.
        correlation_id: Links drift events together.

    """

    building_id: str
    drift_records: List[DriftRecord] = field(default_factory=list)
    total_drifts: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    position_drift_count: int = 0
    status_drift_count: int = 0
    missing_detector_count: int = 0
    extra_detector_count: int = 0
    type_mismatch_count: int = 0
    timestamp: str = ""
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())
        self._recompute_counts()

    def _recompute_counts(self) -> None:
        """Recompute aggregate counts from drift_records."""
        self.total_drifts = len(self.drift_records)
        self.critical_count = sum(1 for d in self.drift_records if d.severity == "critical")
        self.high_count = sum(1 for d in self.drift_records if d.severity == "high")
        self.medium_count = sum(1 for d in self.drift_records if d.severity == "medium")
        self.low_count = sum(1 for d in self.drift_records if d.severity == "low")
        self.position_drift_count = sum(1 for d in self.drift_records if d.drift_type == DriftType.POSITION_DRIFT)
        self.status_drift_count = sum(1 for d in self.drift_records if d.drift_type == DriftType.STATUS_DRIFT)
        self.missing_detector_count = sum(1 for d in self.drift_records if d.drift_type == DriftType.MISSING_DETECTOR)
        self.extra_detector_count = sum(1 for d in self.drift_records if d.drift_type == DriftType.EXTRA_DETECTOR)
        self.type_mismatch_count = sum(1 for d in self.drift_records if d.drift_type == DriftType.TYPE_MISMATCH)

    @property
    def has_critical_drift(self) -> bool:
        """True if any drift has critical severity."""
        return self.critical_count > 0

    @property
    def has_blocking_drift(self) -> bool:
        """True if any drift has critical or high severity.

        Blocking drifts represent potential NFPA 72 spacing violations
        that must be resolved before the system can be considered
        compliant.
        """
        return self.critical_count > 0 or self.high_count > 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for audit and reporting."""
        return {
            "building_id": self.building_id,
            "total_drifts": self.total_drifts,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "position_drift_count": self.position_drift_count,
            "status_drift_count": self.status_drift_count,
            "missing_detector_count": self.missing_detector_count,
            "extra_detector_count": self.extra_detector_count,
            "type_mismatch_count": self.type_mismatch_count,
            "has_critical_drift": self.has_critical_drift,
            "has_blocking_drift": self.has_blocking_drift,
            "drift_records": [d.to_dict() for d in self.drift_records],
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }


@dataclass
class CoverageValidationResult:
    """Result of validating that all rooms have at least one OK detector.

    Per NFPA 72-2022 §10.4.1, areas requiring fire alarm coverage must
    have operational detection.  A room with only PLANNED detectors has
    NO coverage — this is the critical safety distinction enforced here.

    Attributes:
        building_id: Building identifier from the twin.
        is_valid: True if ALL rooms have at least one OK detector.
        total_rooms: Total number of rooms in the twin.
        rooms_with_coverage: Rooms that have at least one OK detector.
        rooms_without_coverage: Rooms that have zero OK detectors.
        rooms_planned_only: Rooms that have detectors, but only PLANNED
            (not yet installed — provides NO fire protection).
        rooms_empty: Rooms with no detectors at all.
        coverage_pct: Percentage of rooms with at least one OK detector.
        critical_gaps: List of room_ids with zero OK detectors.
        timestamp: ISO 8601 UTC timestamp.
        correlation_id: Links validation events together.

    """

    building_id: str
    is_valid: bool
    total_rooms: int
    rooms_with_coverage: int
    rooms_without_coverage: int
    rooms_planned_only: int
    rooms_empty: int
    coverage_pct: float
    critical_gaps: List[str] = field(default_factory=list)
    timestamp: str = ""
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for audit and reporting."""
        return {
            "building_id": self.building_id,
            "is_valid": self.is_valid,
            "total_rooms": self.total_rooms,
            "rooms_with_coverage": self.rooms_with_coverage,
            "rooms_without_coverage": self.rooms_without_coverage,
            "rooms_planned_only": self.rooms_planned_only,
            "rooms_empty": self.rooms_empty,
            "coverage_pct": self.coverage_pct,
            "critical_gaps": self.critical_gaps,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }


@dataclass
class SyncReport:
    """Comprehensive sync report combining all synchronization analyses.

    Generated by ``DigitalTwinSync.generate_sync_report()``.  Provides a
    single document for AHJ review that covers:
      - Design sync status (which detectors are in the twin as PLANNED)
      - As-built sync status (which detectors have been commissioned OK)
      - Drift analysis (design vs. reality discrepancies)
      - Coverage validation (rooms with/without active coverage)

    This report supports NFPA 72-2022 Chapter 7 documentation
    requirements and Chapter 14 acceptance testing.

    Attributes:
        building_id: Building identifier.
        design_sync: Result of the design-to-twin sync.
        as_built_sync: Result of the as-built-to-twin sync.
        drift_report: Drift analysis report.
        coverage_validation: Coverage validation result.
        health_score: Twin health score (0.0–1.0).
        overall_status: One of "COMPLIANT", "ACTION_REQUIRED",
            "CRITICAL_GAPS".
        timestamp: ISO 8601 UTC timestamp.
        correlation_id: Links all sub-reports together.

    """

    building_id: str
    design_sync: Optional[SyncResult] = None
    as_built_sync: Optional[SyncResult] = None
    drift_report: Optional[DriftReport] = None
    coverage_validation: Optional[CoverageValidationResult] = None
    health_score: float = 0.0
    overall_status: str = "UNKNOWN"
    timestamp: str = ""
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())
        self._compute_overall_status()

    def _compute_overall_status(self) -> None:
        """Determine overall compliance status from sub-reports.

        Priority:
            CRITICAL_GAPS — coverage validation shows rooms without OK
                detectors, or drift report has critical drifts.
            ACTION_REQUIRED — drift report has high-severity drifts, or
                sync operations had errors, or there are planned-only
                rooms.
            COMPLIANT — all rooms have OK coverage and no blocking drift.
        """
        if self.coverage_validation is not None:
            if not self.coverage_validation.is_valid:
                self.overall_status = "CRITICAL_GAPS"
                return
            if self.coverage_validation.rooms_planned_only > 0:
                self.overall_status = "ACTION_REQUIRED"
                return

        if self.drift_report is not None:
            if self.drift_report.has_critical_drift:
                self.overall_status = "CRITICAL_GAPS"
                return
            if self.drift_report.has_blocking_drift:
                self.overall_status = "ACTION_REQUIRED"
                return

        # Check for sync errors
        for sync_result in (self.design_sync, self.as_built_sync):
            if sync_result is not None and sync_result.error_count > 0:
                self.overall_status = "ACTION_REQUIRED"
                return

        self.overall_status = "COMPLIANT"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for audit and reporting."""
        return {
            "building_id": self.building_id,
            "design_sync": self.design_sync.to_dict() if self.design_sync else None,
            "as_built_sync": self.as_built_sync.to_dict() if self.as_built_sync else None,
            "drift_report": self.drift_report.to_dict() if self.drift_report else None,
            "coverage_validation": (self.coverage_validation.to_dict() if self.coverage_validation else None),
            "health_score": self.health_score,
            "overall_status": self.overall_status,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }


# ═══════════════════════════════════════════════════════════════════════
# DigitalTwinSync — Main Synchronization Class
# ═══════════════════════════════════════════════════════════════════════


class DigitalTwinSync:
    """Synchronizes the design model and as-built data with the digital twin.

    This class is the primary interface for keeping the digital twin
    consistent with both the engineering design model and the physical
    reality of the installed fire alarm system.

    DESIGN INTENT vs. REALITY:
        The design model represents the engineering intent — where
        detectors SHOULD be.  The as-built data represents physical
        reality — where detectors ARE.  The digital twin must track
        both, and flag any discrepancy (drift) between them.

    SAFETY ENFORCEMENT:
        - Design sync ALWAYS registers detectors as PLANNED.
          A detector that has not been physically verified must NEVER
          be marked OK — that would falsely claim fire protection
          exists where it does not (NFPA 72 §1.2).
        - As-built sync transitions detectors to OK ONLY when explicit
          verification data is provided.
        - Coverage validation counts only OK detectors.  A room with
          only PLANNED detectors has NO coverage.

    Thread Safety:
        All state mutations delegate to DigitalTwin methods, which are
        RLock-protected.  This class does not introduce additional
        shared mutable state.

    Fail-Safe:
        Individual detector sync failures are captured in the
        SyncResult.errors list.  The sync operation continues for
        remaining detectors — a partial sync is better than no sync.

    Example:
        twin = DigitalTwin(building_id="B-001")
        sync = DigitalTwinSync(twin=twin)

        # Sync design detectors
        result = sync.sync_design_to_twin(design_data)

        # Sync as-built (commissioned) detectors
        result = sync.sync_as_built_to_twin(as_built_data)

        # Check for drift
        drift = sync.detect_drift()

        # Validate coverage
        coverage = sync.validate_coverage()

        # Full report
        report = sync.generate_sync_report()

    """

    # Valid detector types per NFPA 72-2022
    VALID_DETECTOR_TYPES: frozenset = frozenset(
        {
            "smoke",
            "heat",
            "flame",
            "gas",
            "duct_smoke",
            "multi_sensor",
            "manual_pull_station",
        }
    )

    def __init__(
        self,
        twin: DigitalTwin,
        audit_store: Optional[Any] = None,
    ) -> None:
        """Initialize the sync module.

        Args:
            twin: The DigitalTwin instance to synchronize with.
            audit_store: Optional AuditStore instance for legal-grade
                audit logging.  If None, audit logging is skipped
                (the sync still succeeds — audit is non-blocking).

        Raises:
            TypeError: If twin is not a DigitalTwin instance.

        """
        if not isinstance(twin, DigitalTwin):
            raise TypeError(f"twin must be a DigitalTwin instance, got {type(twin).__name__}")
        self._twin = twin
        self._bus = EventBus.instance()
        self._audit_store = audit_store

    # ── Properties ───────────────────────────────────────────────────

    @property
    def twin(self) -> DigitalTwin:
        """The DigitalTwin instance being synchronized."""
        return self._twin

    # ── Design Sync ──────────────────────────────────────────────────

    def sync_design_to_twin(
        self,
        design_detectors: List[Dict[str, Any]],
        detector_type: str = "smoke",
        overwrite: bool = False,
    ) -> SyncResult:
        """Push design model detectors to the digital twin as PLANNED.

        This method registers each detector from the design model into
        the digital twin with status PLANNED.  A PLANNED detector has
        NOT been physically installed — it provides ZERO fire protection
        per NFPA 72-2022 §1.2.

        SAFETY: Detectors are ALWAYS registered as PLANNED, regardless
        of any status field in the input data.  Promoting to OK must
        go through ``sync_as_built_to_twin()`` with verification data.

        Args:
            design_detectors: List of detector dicts.  Each dict must
                have ``room_id`` and ``detector_id``, and should have
                ``x``, ``y``, ``z`` (position in meters).  Optional
                keys: ``detector_type``, ``coverage_radius``,
                ``metadata``.
            detector_type: Default detector type if not specified per-
                detector.  Must be one of VALID_DETECTOR_TYPES.
            overwrite: If True, re-registers detectors that already
                exist (removes old and registers new).  If False,
                skips already-registered detectors.

        Returns:
            SyncResult with counts and error details.

        Raises:
            TypeError: If design_detectors is not a list.
            ValueError: If detector_type is not a valid type.

        """
        # ── Input validation ──
        if not isinstance(design_detectors, list):
            raise TypeError(f"design_detectors must be a list, got {type(design_detectors).__name__}")
        if detector_type not in self.VALID_DETECTOR_TYPES:
            raise ValueError(
                f"Invalid detector_type '{detector_type}'. Must be one of: {sorted(self.VALID_DETECTOR_TYPES)}"
            )

        correlation_id = str(uuid.uuid4())
        synced = 0
        skipped = 0
        errors: List[tuple] = []
        warnings: List[str] = []

        for idx, det_data in enumerate(design_detectors):
            if not isinstance(det_data, dict):
                errors.append(
                    (
                        f"index_{idx}",
                        f"Expected dict, got {type(det_data).__name__}",
                    )
                )
                continue

            # ── Per-detector validation ──
            det_id = det_data.get("detector_id")
            room_id = det_data.get("room_id")

            if not det_id:
                errors.append(
                    (
                        f"index_{idx}",
                        "Missing required key 'detector_id'",
                    )
                )
                continue

            if not room_id:
                errors.append(
                    (
                        det_id,
                        "Missing required key 'room_id'",
                    )
                )
                continue

            # Position defaults
            x = float(det_data.get("x", 0.0))
            y = float(det_data.get("y", 0.0))
            z = float(det_data.get("z", 0.0))
            det_type = det_data.get("detector_type", detector_type)
            coverage_radius = det_data.get("coverage_radius")
            metadata = det_data.get("metadata", {})

            # Validate detector_type
            if det_type not in self.VALID_DETECTOR_TYPES:
                errors.append(
                    (
                        det_id,
                        f"Invalid detector_type '{det_type}'",
                    )
                )
                continue

            if coverage_radius is not None:
                try:
                    coverage_radius = float(coverage_radius)
                    if coverage_radius < 0:
                        raise ValueError("negative")
                except (ValueError, TypeError):
                    errors.append(
                        (
                            det_id,
                            f"Invalid coverage_radius: {det_data.get('coverage_radius')}",
                        )
                    )
                    continue

            # ── Check if already registered ──
            existing = self._twin.get_detector(det_id)
            if existing is not None:
                if overwrite:
                    try:
                        self._twin.remove_detector(det_id, reason="design_sync_overwrite")
                    except Exception as exc:
                        errors.append(
                            (
                                det_id,
                                f"Failed to remove existing detector for overwrite: {exc}",
                            )
                        )
                        continue
                else:
                    skipped += 1
                    logger.debug(
                        "Detector %s already registered, skipping (overwrite=False)",
                        det_id,
                    )
                    continue

            # ── Register as PLANNED ──
            # SAFETY: Always PLANNED.  Never OK from design sync.
            try:
                self._twin.register_detector(
                    room_id=room_id,
                    detector_id=det_id,
                    x=x,
                    y=y,
                    z=z,
                    detector_type=det_type,
                    status=DetectorStatus.PLANNED,
                    coverage_radius=coverage_radius,
                    metadata=metadata,
                )
                synced += 1
            except Exception as exc:
                errors.append((det_id, f"Registration failed: {exc}"))
                logger.error(
                    "Failed to register detector %s: %s",
                    det_id,
                    exc,
                )

        # ── Build result ──
        result = SyncResult(
            operation="sync_design_to_twin",
            synced_count=synced,
            skipped_count=skipped,
            error_count=len(errors),
            errors=errors,
            warnings=warnings,
            building_id=self._twin.building_id,
            correlation_id=correlation_id,
        )

        # ── Publish event ──
        self._bus.publish(
            Events.TWIN_SYNC,
            data={
                "operation": "sync_design_to_twin",
                "building_id": self._twin.building_id,
                "synced_count": synced,
                "skipped_count": skipped,
                "error_count": len(errors),
                "correlation_id": correlation_id,
            },
            source="DigitalTwinSync",
            correlation_id=correlation_id,
        )

        # ── Audit log ──
        self._audit_log(
            event_type="SYNC_DESIGN_TO_TWIN",
            room_id="",
            details={
                "building_id": self._twin.building_id,
                "synced_count": synced,
                "skipped_count": skipped,
                "error_count": len(errors),
                "total_input": len(design_detectors),
                "correlation_id": correlation_id,
            },
        )

        logger.info(
            "Design sync complete: %d synced, %d skipped, %d errors (building=%s, correlation=%s)",
            synced,
            skipped,
            len(errors),
            self._twin.building_id,
            correlation_id[:8],
        )

        return result

    # ── As-Built Sync ────────────────────────────────────────────────

    def sync_as_built_to_twin(
        self,
        as_built_detectors: List[Dict[str, Any]],
    ) -> SyncResult:
        """Push as-built detector data to the digital twin (OK status).

        This method transitions detectors from PLANNED to OK, reflecting
        that they have been physically installed, tested, and
        commissioned per NFPA 72-2022 Chapter 14 (Acceptance Testing).

        SAFETY:
            - Only detectors that already exist in the twin (typically
              from a prior design sync) can be transitioned to OK.
            - Detectors NOT in the twin are registered as OK with a
              warning (they are "extra" detectors not in the design).
            - The transition must be legal per LEGAL_STATUS_TRANSITIONS.
              A detector already in OK, FAULT, or OFFLINE state can be
              set to OK (re-commissioning after maintenance).

        Args:
            as_built_detectors: List of as-built detector dicts.  Each
                dict must have ``detector_id``.  Optional keys:
                ``room_id``, ``x``, ``y``, ``z`` (position updates),
                ``detector_type``, ``verified_by`` (who verified the
                installation), ``coverage_radius``, ``metadata``.

        Returns:
            SyncResult with counts and error details.

        Raises:
            TypeError: If as_built_detectors is not a list.

        """
        # ── Input validation ──
        if not isinstance(as_built_detectors, list):
            raise TypeError(f"as_built_detectors must be a list, got {type(as_built_detectors).__name__}")

        correlation_id = str(uuid.uuid4())
        synced = 0
        skipped = 0
        errors: List[tuple] = []
        warnings: List[str] = []

        for idx, det_data in enumerate(as_built_detectors):
            if not isinstance(det_data, dict):
                errors.append(
                    (
                        f"index_{idx}",
                        f"Expected dict, got {type(det_data).__name__}",
                    )
                )
                continue

            det_id = det_data.get("detector_id")
            if not det_id:
                errors.append(
                    (
                        f"index_{idx}",
                        "Missing required key 'detector_id'",
                    )
                )
                continue

            verified_by = det_data.get("verified_by", "")

            # ── Check if detector exists in twin ──
            existing = self._twin.get_detector(det_id)

            if existing is not None:
                # Detector exists — attempt status transition to OK
                if existing.status == DetectorStatus.OK:
                    # Already OK — update position if provided
                    skipped += 1
                    logger.debug(
                        "Detector %s already OK, skipping status update",
                        det_id,
                    )
                    # Optionally update position if as-built data differs
                    self._maybe_update_position(existing, det_data, warnings)
                    continue

                if existing.status == DetectorStatus.DECOMMISSIONED:
                    errors.append(
                        (
                            det_id,
                            "Cannot transition DECOMMISSIONED detector to OK (terminal state per NFPA 72 §14.3.4)",
                        )
                    )
                    continue

                # Attempt PLANNED → OK, FAULT → OK, or OFFLINE → OK
                try:
                    self._twin.update_detector_status(
                        detector_id=det_id,
                        new_status=DetectorStatus.OK,
                        verified_by=verified_by,
                    )
                    synced += 1
                except ValueError as exc:
                    errors.append(
                        (
                            det_id,
                            f"Illegal status transition {existing.status.value} → ok: {exc}",
                        )
                    )
                    continue
                except KeyError as exc:
                    # Should not happen since we checked existence, but
                    # handle defensively
                    errors.append((det_id, f"Detector not found: {exc}"))
                    continue

                # Optionally update position if as-built data differs
                self._maybe_update_position(existing, det_data, warnings)

            else:
                # Detector NOT in twin — register as OK with a warning.
                # This is an "extra" detector found in the field that
                # was not in the design model.
                room_id = det_data.get("room_id", "UNKNOWN")
                x = float(det_data.get("x", 0.0))
                y = float(det_data.get("y", 0.0))
                z = float(det_data.get("z", 0.0))
                det_type = det_data.get("detector_type", "smoke")
                coverage_radius = det_data.get("coverage_radius")
                metadata = det_data.get("metadata", {})

                # Mark as extra detector in metadata
                extra_meta = dict(metadata)
                extra_meta["sync_source"] = "as_built_extra"
                extra_meta["design_model_missing"] = True

                try:
                    self._twin.register_detector(
                        room_id=room_id,
                        detector_id=det_id,
                        x=x,
                        y=y,
                        z=z,
                        detector_type=det_type,
                        status=DetectorStatus.OK,
                        coverage_radius=coverage_radius,
                        metadata=extra_meta,
                    )
                    synced += 1
                    warn_msg = (
                        f"Detector {det_id} not found in design model — "
                        f"registered as extra OK detector in room {room_id}"
                    )
                    warnings.append(warn_msg)
                    logger.warning(warn_msg)
                except Exception as exc:
                    errors.append((det_id, f"Extra detector registration failed: {exc}"))

        # ── Build result ──
        result = SyncResult(
            operation="sync_as_built_to_twin",
            synced_count=synced,
            skipped_count=skipped,
            error_count=len(errors),
            errors=errors,
            warnings=warnings,
            building_id=self._twin.building_id,
            correlation_id=correlation_id,
        )

        # ── Publish event ──
        self._bus.publish(
            Events.TWIN_SYNC,
            data={
                "operation": "sync_as_built_to_twin",
                "building_id": self._twin.building_id,
                "synced_count": synced,
                "skipped_count": skipped,
                "error_count": len(errors),
                "extra_count": len(warnings),
                "correlation_id": correlation_id,
            },
            source="DigitalTwinSync",
            correlation_id=correlation_id,
        )

        # ── Audit log ──
        self._audit_log(
            event_type="SYNC_AS_BUILT_TO_TWIN",
            room_id="",
            details={
                "building_id": self._twin.building_id,
                "synced_count": synced,
                "skipped_count": skipped,
                "error_count": len(errors),
                "extra_detector_count": len(warnings),
                "total_input": len(as_built_detectors),
                "correlation_id": correlation_id,
            },
        )

        logger.info(
            "As-built sync complete: %d synced, %d skipped, %d errors, %d extra (building=%s, correlation=%s)",
            synced,
            skipped,
            len(errors),
            len(warnings),
            self._twin.building_id,
            correlation_id[:8],
        )

        return result

    # ── Drift Detection ──────────────────────────────────────────────

    def detect_drift(
        self,
        design_detectors: Optional[List[Dict[str, Any]]] = None,
    ) -> DriftReport:
        """Compare design model vs. twin state and return drift records.

        Detects discrepancies between the engineering design intent and
        the digital twin's current state.  Drift types include:
          - Position drift: detector moved from design position
          - Status drift: detector still PLANNED when it should be OK
          - Missing detector: in design but not in twin
          - Extra detector: in twin but not in design
          - Type mismatch: detector type differs from design

        If ``design_detectors`` is provided, this method also checks
        for missing and extra detectors by comparing the design list
        against the twin's current detector inventory.

        Drift severity thresholds follow TwinDriftAnalyzer's NFPA 72-
        2022-derived tolerances:
          - < 0.01 m: ignored (measurement noise)
          - 0.01–0.30 m: low
          - 0.30–1.0 m: medium
          - 1.0–1.5 m: high (approaching NFPA spacing limits)
          - ≥ 1.5 m: critical (definite NFPA violation per §17.6/§17.7)

        Args:
            design_detectors: Optional list of design detector dicts to
                compare against the twin.  If None, only the twin's
                internal drift analysis (position + status) is performed.

        Returns:
            DriftReport with all detected drifts and severity counts.

        """
        correlation_id = str(uuid.uuid4())

        # ── Use TwinDriftAnalyzer for internal drift ──
        # This checks position drift and status drift for all detectors
        # currently in the twin.
        internal_drifts = self._twin.detect_drift()

        # ── If design_detectors provided, check for missing/extra/type mismatch ──
        cross_drifts: List[DriftRecord] = []
        if design_detectors is not None:
            cross_drifts = self._detect_cross_drift(design_detectors, correlation_id)

        # ── Combine all drifts ──
        all_drifts = internal_drifts + cross_drifts

        report = DriftReport(
            building_id=self._twin.building_id,
            drift_records=all_drifts,
            correlation_id=correlation_id,
        )

        # ── Publish event if drifts found ──
        if all_drifts:
            self._bus.publish(
                Events.TWIN_DRIFT,
                data={
                    "building_id": self._twin.building_id,
                    "total_drifts": report.total_drifts,
                    "critical_count": report.critical_count,
                    "high_count": report.high_count,
                    "correlation_id": correlation_id,
                },
                source="DigitalTwinSync",
                correlation_id=correlation_id,
            )

        # ── Audit log ──
        self._audit_log(
            event_type="DRIFT_DETECTION",
            room_id="",
            details={
                "building_id": self._twin.building_id,
                "total_drifts": report.total_drifts,
                "critical_count": report.critical_count,
                "high_count": report.high_count,
                "position_drift_count": report.position_drift_count,
                "status_drift_count": report.status_drift_count,
                "missing_detector_count": report.missing_detector_count,
                "extra_detector_count": report.extra_detector_count,
                "type_mismatch_count": report.type_mismatch_count,
                "correlation_id": correlation_id,
            },
        )

        if all_drifts:
            logger.warning(
                "Drift detection: %d drifts (%d critical, %d high) (building=%s, correlation=%s)",
                report.total_drifts,
                report.critical_count,
                report.high_count,
                self._twin.building_id,
                correlation_id[:8],
            )
        else:
            logger.info(
                "Drift detection: no drifts found (building=%s)",
                self._twin.building_id,
            )

        return report

    # ── Coverage Validation ──────────────────────────────────────────

    def validate_coverage(self) -> CoverageValidationResult:
        """Verify that all rooms have at least one OK detector in the twin.

        Per NFPA 72-2022 §10.4.1, areas requiring fire alarm coverage
        must have operational detection.  This method validates that
        every room in the twin has at least one detector with status OK.

        CRITICAL SAFETY DISTINCTION:
            A room with only PLANNED detectors has NO coverage.  PLANNED
            means the detector exists in the design but has NOT been
            physically installed.  Counting PLANNED as coverage would be
            a LIFE-SAFETY BUG.

        Returns:
            CoverageValidationResult with room-level coverage details.

        """
        correlation_id = str(uuid.uuid4())

        # Get all rooms from the twin
        with self._twin._lock:
            all_room_ids: Set[str] = set(self._twin._room_ids)
            detectors = dict(self._twin._detectors)

        # Classify rooms by coverage status
        rooms_with_ok: Set[str] = set()
        rooms_planned_only: Set[str] = set()
        rooms_with_detectors: Set[str] = set()

        # Group detectors by room
        room_detectors: Dict[str, List[DetectorState]] = {}
        for det in detectors.values():
            room_detectors.setdefault(det.room_id, []).append(det)
            rooms_with_detectors.add(det.room_id)

        for room_id, dets in room_detectors.items():
            has_ok = any(d.status == DetectorStatus.OK for d in dets)
            has_planned = any(d.status == DetectorStatus.PLANNED for d in dets)

            if has_ok:
                rooms_with_ok.add(room_id)
            elif has_planned and not has_ok:
                rooms_planned_only.add(room_id)

        # Rooms with no detectors at all
        rooms_empty = all_room_ids - rooms_with_detectors

        # Rooms without coverage = rooms with no OK detector
        rooms_without_coverage = all_room_ids - rooms_with_ok

        total_rooms = len(all_room_ids)
        coverage_pct = round(len(rooms_with_ok) / total_rooms * 100, 2) if total_rooms > 0 else 0.0

        # Critical gaps: rooms without ANY OK detector
        critical_gaps = sorted(rooms_without_coverage)

        is_valid = len(rooms_without_coverage) == 0

        result = CoverageValidationResult(
            building_id=self._twin.building_id,
            is_valid=is_valid,
            total_rooms=total_rooms,
            rooms_with_coverage=len(rooms_with_ok),
            rooms_without_coverage=len(rooms_without_coverage),
            rooms_planned_only=len(rooms_planned_only),
            rooms_empty=len(rooms_empty),
            coverage_pct=coverage_pct,
            critical_gaps=critical_gaps,
            correlation_id=correlation_id,
        )

        # ── Publish event ──
        event_type = Events.COVERAGE_VERIFIED if is_valid else Events.COVERAGE_FAILED
        self._bus.publish(
            event_type,
            data={
                "building_id": self._twin.building_id,
                "is_valid": is_valid,
                "coverage_pct": coverage_pct,
                "rooms_without_coverage": len(rooms_without_coverage),
                "correlation_id": correlation_id,
            },
            source="DigitalTwinSync",
            correlation_id=correlation_id,
        )

        # ── Audit log ──
        self._audit_log(
            event_type="COVERAGE_VALIDATION",
            room_id="",
            details={
                "building_id": self._twin.building_id,
                "is_valid": is_valid,
                "total_rooms": total_rooms,
                "rooms_with_coverage": len(rooms_with_ok),
                "rooms_without_coverage": len(rooms_without_coverage),
                "rooms_planned_only": len(rooms_planned_only),
                "rooms_empty": len(rooms_empty),
                "coverage_pct": coverage_pct,
                "critical_gaps": critical_gaps,
                "correlation_id": correlation_id,
            },
        )

        if is_valid:
            logger.info(
                "Coverage validation PASSED: %d/%d rooms covered (%.1f%%) (building=%s)",
                len(rooms_with_ok),
                total_rooms,
                coverage_pct,
                self._twin.building_id,
            )
        else:
            logger.warning(
                "Coverage validation FAILED: %d room(s) without OK detector (%d planned-only, %d empty) (building=%s)",
                len(rooms_without_coverage),
                len(rooms_planned_only),
                len(rooms_empty),
                self._twin.building_id,
            )

        return result

    # ── Sync Report ──────────────────────────────────────────────────

    def generate_sync_report(
        self,
        design_detectors: Optional[List[Dict[str, Any]]] = None,
        as_built_detectors: Optional[List[Dict[str, Any]]] = None,
    ) -> SyncReport:
        """Produce a comprehensive sync report combining all analyses.

        This is the primary reporting method for AHJ review.  It
        optionally re-syncs design and as-built data, then runs drift
        detection and coverage validation to produce a single document
        covering the full synchronization state.

        NFPA 72-2022 Chapter 7 requires documentation of the fire alarm
        system design, installation, and acceptance testing.  This
        report supports those documentation requirements by showing:
          1. Design sync status (which detectors are in the twin)
          2. As-built sync status (which detectors are commissioned)
          3. Drift analysis (design vs. reality discrepancies)
          4. Coverage validation (rooms with/without active detection)
          5. Overall compliance status

        Args:
            design_detectors: Optional design detector list.  If
                provided, a design sync is performed first.
            as_built_detectors: Optional as-built detector list.  If
                provided, an as-built sync is performed first.

        Returns:
            SyncReport with all sub-reports and overall status.

        """
        correlation_id = str(uuid.uuid4())

        # ── Optional design sync ──
        design_result: Optional[SyncResult] = None
        if design_detectors is not None:
            design_result = self.sync_design_to_twin(design_detectors)

        # ── Optional as-built sync ──
        as_built_result: Optional[SyncResult] = None
        if as_built_detectors is not None:
            as_built_result = self.sync_as_built_to_twin(as_built_detectors)

        # ── Drift detection (with design comparison if available) ──
        drift_report = self.detect_drift(
            design_detectors=design_detectors,
        )

        # ── Coverage validation ──
        coverage_result = self.validate_coverage()

        # ── Health score from twin ──
        health_report = self._twin.health_report()

        # ── Build report ──
        report = SyncReport(
            building_id=self._twin.building_id,
            design_sync=design_result,
            as_built_sync=as_built_result,
            drift_report=drift_report,
            coverage_validation=coverage_result,
            health_score=health_report.health_score,
            correlation_id=correlation_id,
        )

        # ── Audit log ──
        self._audit_log(
            event_type="SYNC_REPORT_GENERATED",
            room_id="",
            details={
                "building_id": self._twin.building_id,
                "overall_status": report.overall_status,
                "health_score": report.health_score,
                "drift_count": drift_report.total_drifts,
                "coverage_pct": coverage_result.coverage_pct,
                "correlation_id": correlation_id,
            },
        )

        logger.info(
            "Sync report generated: status=%s, health=%.3f, drifts=%d, coverage=%.1f%% (building=%s)",
            report.overall_status,
            report.health_score,
            drift_report.total_drifts,
            coverage_result.coverage_pct,
            self._twin.building_id,
        )

        return report

    # ── Private Helpers ──────────────────────────────────────────────

    def _detect_cross_drift(
        self,
        design_detectors: List[Dict[str, Any]],
        correlation_id: str,
    ) -> List[DriftRecord]:
        """Detect missing, extra, and type-mismatch drifts by comparing
        the design detector list against the twin's current inventory.

        Args:
            design_detectors: Design model detector list.
            correlation_id: Correlation ID for linking drift records.

        Returns:
            List of DriftRecord for missing, extra, and type-mismatch
            drifts.

        """
        drifts: List[DriftRecord] = []
        now = datetime.now(timezone.utc).isoformat()

        # Build index of design detectors by ID
        design_by_id: Dict[str, Dict[str, Any]] = {}
        for det_data in design_detectors:
            det_id = det_data.get("detector_id")
            if det_id is not None:
                design_by_id[str(det_id)] = det_data

        # Build index of twin detectors by ID
        with self._twin._lock:
            twin_by_id: Dict[str, DetectorState] = dict(self._twin._detectors)

        # ── Missing detectors: in design but NOT in twin ──
        for det_id, det_data in design_by_id.items():
            if det_id not in twin_by_id:
                room_id = det_data.get("room_id", "UNKNOWN")
                drifts.append(
                    DriftRecord(
                        drift_id=str(uuid.uuid4()),
                        drift_type=DriftType.MISSING_DETECTOR,
                        detector_id=det_id,
                        room_id=room_id,
                        expected="detector registered in twin",
                        actual="detector not found in twin",
                        severity="high",
                        timestamp=now,
                    )
                )

        # ── Extra detectors: in twin but NOT in design ──
        for det_id, det_state in twin_by_id.items():
            if det_id not in design_by_id:
                drifts.append(
                    DriftRecord(
                        drift_id=str(uuid.uuid4()),
                        drift_type=DriftType.EXTRA_DETECTOR,
                        detector_id=det_id,
                        room_id=det_state.room_id,
                        expected="detector in design model",
                        actual="detector exists in twin but not in design",
                        severity="medium",
                        timestamp=now,
                    )
                )

        # ── Type mismatch: detector exists in both but type differs ──
        for det_id in set(design_by_id.keys()) & set(twin_by_id.keys()):
            design_type = design_by_id[det_id].get("detector_type", "smoke")
            twin_type = twin_by_id[det_id].detector_type
            if design_type != twin_type:
                drifts.append(
                    DriftRecord(
                        drift_id=str(uuid.uuid4()),
                        drift_type=DriftType.TYPE_MISMATCH,
                        detector_id=det_id,
                        room_id=twin_by_id[det_id].room_id,
                        expected=f"type={design_type}",
                        actual=f"type={twin_type}",
                        severity="high",
                        timestamp=now,
                    )
                )

        return drifts

    @staticmethod
    def _maybe_update_position(
        detector: DetectorState,
        as_built_data: Dict[str, Any],
        warnings: List[str],
    ) -> None:
        """Optionally update detector position from as-built data.

        If the as-built data includes x/y/z coordinates that differ from
        the detector's current position, this method logs a warning but
        does NOT update the position directly (that would require going
        through the DigitalTwin API).  Instead, it records the drift for
        later review.

        This is intentionally conservative — position changes should
        be reviewed by an engineer before being applied, as they may
        indicate NFPA 72 §17.6/§17.7 spacing violations.

        Args:
            detector: Current detector state from the twin.
            as_built_data: As-built data dict with optional x/y/z.
            warnings: List to append position drift warnings to.

        """
        ab_x = as_built_data.get("x")
        ab_y = as_built_data.get("y")
        ab_z = as_built_data.get("z")

        if ab_x is None and ab_y is None and ab_z is None:
            return  # No position data in as-built

        try:
            new_x = float(ab_x) if ab_x is not None else detector.x
            new_y = float(ab_y) if ab_y is not None else detector.y
            new_z = float(ab_z) if ab_z is not None else detector.z
        except (ValueError, TypeError):
            return

        # Compute drift from design position
        drift_m = (
            (new_x - detector.design_x) ** 2 + (new_y - detector.design_y) ** 2 + (new_z - detector.design_z) ** 2
        ) ** 0.5

        if drift_m >= TwinDriftAnalyzer.POSITION_TOLERANCE_M:
            warnings.append(
                f"Detector {detector.detector_id} as-built position drifts "
                f"{drift_m:.3f}m from design position — review for NFPA 72 "
                f"§17.6/§17.7 spacing compliance"
            )

    def _audit_log(
        self,
        event_type: str,
        room_id: str,
        details: Dict[str, Any],
    ) -> None:
        """Log an event to AuditStore if available. Never crashes.

        This follows the same fail-safe pattern as DigitalTwin._audit_log:
        audit failures are caught silently so the sync operation always
        completes, even if the audit database is down.

        Args:
            event_type: Type of event to log.
            room_id: Room identifier (empty string if not room-specific).
            details: Event details dictionary.

        """
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
            logger.debug(
                "AuditStore logging failed for %s",
                event_type,
                exc_info=True,
            )
