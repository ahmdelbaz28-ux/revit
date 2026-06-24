"""fireai/integration/field_data_service.py
==========================================
Field Data Integration — Mobile data capture, inspection feedback,
and asset synchronization with conflict detection.

References:
  - NFPA 72-2022 §14.4 — Inspection, testing and maintenance
  - NFPA 72-2022 §7.5 — Records and recordkeeping

"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from fireai.core.event_bus import EventBus, Events

logger = logging.getLogger(__name__)


# ===========================================================================
# Enums
# ===========================================================================


class FindingCategory(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class InspectionStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class SyncStatus(str, Enum):
    SYNCED = "SYNCED"
    CONFLICT = "CONFLICT"
    PENDING = "PENDING"
    FAILED = "FAILED"


# ===========================================================================
# Data Models
# ===========================================================================


@dataclass(frozen=True)
class Finding:
    category: FindingCategory
    description: str
    location: str
    recommendation: str = ""
    photo_urls: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("Finding description must not be empty")
        if not self.location.strip():
            raise ValueError("Finding location must not be empty")


@dataclass(frozen=True)
class FieldInspection:
    inspection_id: str
    inspector_id: str
    building_id: str
    asset_id: str
    findings: List[Finding]
    timestamp: datetime
    status: InspectionStatus = InspectionStatus.PENDING
    photos: List[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.inspection_id.strip():
            raise ValueError("inspection_id must not be empty")
        if not self.inspector_id.strip():
            raise ValueError("inspector_id must not be empty")
        if not self.building_id.strip():
            raise ValueError("building_id must not be empty")
        if not self.asset_id.strip():
            raise ValueError("asset_id must not be empty")
        now = datetime.now(timezone.utc)
        if self.timestamp > now:
            raise ValueError("Inspection timestamp cannot be in the future")


@dataclass(frozen=True)
class InspectionResult:
    inspection_id: str
    accepted: bool
    findings_count: int
    critical_findings: int
    warnings: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class FieldUpdate:
    update_id: str
    building_id: str
    asset_id: str
    field_name: str
    old_value: Optional[str]
    new_value: str
    updated_by: str
    updated_at: datetime
    source: str  # "mobile", "web", "api"


@dataclass(frozen=True)
class InspectionTask:
    task_id: str
    building_id: str
    asset_id: str
    assigned_to: str
    due_date: datetime
    description: str
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    status: InspectionStatus = InspectionStatus.PENDING


@dataclass(frozen=True)
class SyncResult:
    asset_id: str
    synced: bool
    conflict: bool
    local_version: int
    remote_version: int
    resolved_value: Optional[str] = None


# ===========================================================================
# Field Data Service
# ===========================================================================


class FieldDataService:
    """Mobile data capture, inspection feedback, and asset synchronization.

    Features:
      - Inspection submission with validation
      - Field update retrieval with timestamp-based filtering
      - Asset sync with last-write-wins conflict resolution
      - Outstanding inspection task management
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus or EventBus.instance()
        self._inspections: Dict[str, FieldInspection] = {}
        self._field_updates: List[FieldUpdate] = []
        self._tasks: Dict[str, InspectionTask] = {}
        self._asset_versions: Dict[str, int] = {}

    # ── Inspection Submission ───────────────────────────────────────────

    def submit_inspection(
        self, inspection: FieldInspection
    ) -> InspectionResult:
        self._validate_inspection(inspection)

        critical = [
            f
            for f in inspection.findings
            if f.category == FindingCategory.CRITICAL
        ]
        warnings: List[str] = []

        if critical:
            warnings.append(
                f"Inspection {inspection.inspection_id} has "
                f"{len(critical)} critical finding(s)"
            )

        if inspection.inspection_id in self._inspections:
            warnings.append(
                f"Inspection {inspection.inspection_id} already exists "
                f"— overwriting"
            )

        self._inspections[inspection.inspection_id] = inspection

        self._event_bus.publish(
            "field.inspection.submitted",
            data={
                "inspection_id": inspection.inspection_id,
                "building_id": inspection.building_id,
                "asset_id": inspection.asset_id,
                "findings_count": len(inspection.findings),
                "critical_count": len(critical),
            },
            source="field_data_service",
        )

        for finding in inspection.findings:
            if finding.category in (
                FindingCategory.CRITICAL,
                FindingCategory.HIGH,
            ):
                self._event_bus.publish(
                    "field.critical_finding",
                    data={
                        "inspection_id": inspection.inspection_id,
                        "asset_id": inspection.asset_id,
                        "category": finding.category.value,
                        "description": finding.description,
                        "location": finding.location,
                    },
                    source="field_data_service",
                )

        return InspectionResult(
            inspection_id=inspection.inspection_id,
            accepted=True,
            findings_count=len(inspection.findings),
            critical_findings=len(critical),
            warnings=warnings,
        )

    # ── Field Updates ───────────────────────────────────────────────────

    def get_field_updates(
        self, since: datetime
    ) -> List[FieldUpdate]:
        if not isinstance(since, datetime):
            raise TypeError("since must be a datetime object")

        return [
            u
            for u in self._field_updates
            if u.updated_at > since
        ]

    def record_field_update(self, update: FieldUpdate) -> None:
        self._field_updates.append(update)
        self._event_bus.publish(
            "field.update.recorded",
            data={
                "update_id": update.update_id,
                "asset_id": update.asset_id,
                "field_name": update.field_name,
                "source": update.source,
            },
            source="field_data_service",
        )

    # ── Asset Synchronization ───────────────────────────────────────────

    def sync_asset(
        self,
        asset: AssetData,
        remote_version: Optional[int] = None,
    ) -> SyncResult:
        asset_id = asset.asset_id
        local_version = self._asset_versions.get(asset_id, 0)
        remote_ver = remote_version or 0

        conflict = local_version > 0 and remote_ver > local_version

        if conflict:
            resolved = self._resolve_conflict(
                asset_id, local_version, remote_ver
            )
            result = SyncResult(
                asset_id=asset_id,
                synced=True,
                conflict=True,
                local_version=local_version,
                remote_version=remote_ver,
                resolved_value=resolved,
            )
        else:
            new_version = max(local_version, remote_ver) + 1
            self._asset_versions[asset_id] = new_version
            result = SyncResult(
                asset_id=asset_id,
                synced=True,
                conflict=False,
                local_version=local_version,
                remote_version=remote_ver,
            )

        self._event_bus.publish(
            Events.TWIN_SYNC,
            data={
                "asset_id": asset_id,
                "conflict": result.conflict,
                "local_version": result.local_version,
                "remote_version": result.remote_version,
            },
            source="field_data_service",
        )
        return result

    def get_outstanding_inspections(
        self, building_id: str
    ) -> List[InspectionTask]:
        if not building_id.strip():
            raise ValueError("building_id must not be empty")

        return [
            task
            for task in self._tasks.values()
            if task.building_id == building_id
            and task.status
            in (InspectionStatus.PENDING, InspectionStatus.IN_PROGRESS)
        ]

    def assign_inspection_task(self, task: InspectionTask) -> None:
        if task.task_id in self._tasks:
            logger.warning(
                "Task %s already exists, overwriting", task.task_id
            )
        self._tasks[task.task_id] = task

    def update_task_status(
        self, task_id: str, status: InspectionStatus
    ) -> bool:
        if task_id not in self._tasks:
            return False
        task = self._tasks[task_id]
        self._tasks[task_id] = InspectionTask(
            task_id=task.task_id,
            building_id=task.building_id,
            asset_id=task.asset_id,
            assigned_to=task.assigned_to,
            due_date=task.due_date,
            description=task.description,
            priority=task.priority,
            status=status,
        )
        return True

    # ── Internal ────────────────────────────────────────────────────────

    def _validate_inspection(
        self, inspection: FieldInspection
    ) -> None:
        if not inspection.inspection_id.strip():
            raise ValueError("inspection_id is required")
        if not inspection.inspector_id.strip():
            raise ValueError("inspector_id is required")
        if not inspection.asset_id.strip():
            raise ValueError("asset_id is required")
        if not inspection.building_id.strip():
            raise ValueError("building_id is required")
        if inspection.timestamp.tzinfo is None:
            raise ValueError(
                "timestamp must be timezone-aware"
            )
        now = datetime.now(timezone.utc)
        if inspection.timestamp > now:
            raise ValueError(
                f"Inspection timestamp {inspection.timestamp} "
                f"is in the future"
            )

    def _resolve_conflict(
        self, asset_id: str, local_ver: int, remote_ver: int
    ) -> str:
        """Last-write-wins conflict resolution.

        The higher version number wins. If versions are equal,
        the remote version is preferred (field data is considered
        more authoritative).
        """
        if remote_ver >= local_ver:
            self._asset_versions[asset_id] = remote_ver
            return "remote"
        self._asset_versions[asset_id] = local_ver
        return "local"


# ===========================================================================
# Self-Test
# ===========================================================================

if __name__ == "__main__":
    from fireai.core.event_bus import EventBus

    bus = EventBus()
    service = FieldDataService(bus)

    finding = Finding(
        category=FindingCategory.CRITICAL,
        description="Detector cover loose, exposed wiring",
        location="Building A - Room 201 - Ceiling grid",
        recommendation="Secure detector cover and verify wiring",
    )

    inspection = FieldInspection(
        inspection_id="INSP-2026-001",
        inspector_id="TECH-042",
        building_id="BLDG-A",
        asset_id="DET-SMK-201",
        findings=[finding],
        timestamp=datetime.now(timezone.utc),
    )

    result = service.submit_inspection(inspection)
    print(f"Inspection accepted: {result.accepted}")
    print(f"Critical findings: {result.critical_findings}")

    updates = service.get_field_updates(
        datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    print(f"Field updates: {len(updates)}")

    from fireai.analytics.predictive_maintenance import (
        AssetData,
        AssetType,
    )

    asset = AssetData(
        asset_id="DET-SMK-201",
        asset_type=AssetType.DETECTOR_SMOKE,
        installation_date=datetime(2019, 1, 1, tzinfo=timezone.utc),
    )
    sync = service.sync_asset(asset)
    print(f"Sync OK: {sync.synced}, conflict: {sync.conflict}")
