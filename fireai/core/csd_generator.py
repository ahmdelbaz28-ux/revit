"""CSD (Control Station Device) Generation Module.
This module defines the necessary enums, dataclasses, and generator class for
CSD representation and compliance reporting.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class CSDDeviceType(Enum):
    """Supported types of Control Station Devices."""

    MAIN_CONTROL_STATION = "MAIN_CONTROL_STATION"
    REMOTE_CONTROL_STATION = "REMOTE_CONTROL_STATION"
    MONITORING_STATION = "MONITORING_STATION"
    BOOSTER_PANEL = "BOOSTER_PANEL"


class CSDDeviceStatus(Enum):
    """Operational status of a CSD."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"
    FAULT = "FAULT"


@dataclass
class CSDDevice:
    """Represents a Control Station Device."""

    device_id: str
    name: str
    device_type: CSDDeviceType
    status: CSDDeviceStatus
    location: str
    zone: int


@dataclass
class CSDComplianceReport:
    """Holds compliance report details for a set of CSDs."""

    report_id: str
    timestamp: datetime
    total_devices: int
    compliant_devices: int
    non_compliant_devices: int
    compliance_rate: float
    issues: List[str] = field(default_factory=list)


class CSDGenerator:
    """Generator for creating CSD devices and analyzing their compliance."""

    def generate_device(
        self,
        name: str,
        device_type: CSDDeviceType,
        location: str,
        zone: int,
        status: CSDDeviceStatus = CSDDeviceStatus.ACTIVE,
        device_id: Optional[str] = None
    ) -> CSDDevice:
        """Generates a new CSDDevice with a unique ID if not provided.
        """
        if not device_id:
            device_id = f"CSD-{uuid.uuid4().hex[:8].upper()}"
        return CSDDevice(
            device_id=device_id,
            name=name,
            device_type=device_type,
            status=status,
            location=location,
            zone=zone
        )

    def generate_compliance_report(self, devices: List[CSDDevice]) -> CSDComplianceReport:
        """Generates a compliance report for the provided list of CSD devices.
        A device is non-compliant if it is in FAULT or INACTIVE state.
        """
        report_id = f"REP-{uuid.uuid4().hex[:8].upper()}"
        timestamp = datetime.utcnow()
        total_devices = len(devices)

        if total_devices == 0:
            return CSDComplianceReport(
                report_id=report_id,
                timestamp=timestamp,
                total_devices=0,
                compliant_devices=0,
                non_compliant_devices=0,
                compliance_rate=100.0,
                issues=[]
            )

        compliant_devices = 0
        non_compliant_devices = 0
        issues = []

        for device in devices:
            if device.status in (CSDDeviceStatus.ACTIVE, CSDDeviceStatus.MAINTENANCE):
                compliant_devices += 1
            else:
                non_compliant_devices += 1
                issues.append(
                    f"Device {device.device_id} ({device.name}) is non-compliant due to status: {device.status.value}"
                )

        compliance_rate = (compliant_devices / total_devices) * 100.0

        return CSDComplianceReport(
            report_id=report_id,
            timestamp=timestamp,
            total_devices=total_devices,
            compliant_devices=compliant_devices,
            non_compliant_devices=non_compliant_devices,
            compliance_rate=round(compliance_rate, 2),
            issues=issues
        )
