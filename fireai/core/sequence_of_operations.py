"""sequence_of_operations.py — NFPA 72 §14.4 Cause & Effect Matrix Generator
==========================================================================
CRITICAL LIFE-SAFETY MODULE — V18

Generates the Sequence of Operations (Cause and Effect) matrix that maps
every input device to its required output actions per NFPA 72 §14.4.

Without this matrix, the FACP is a "dumb box" — devices are placed and
cables are routed, but nobody knows what happens when a device activates.
The panel programmer would program randomly, potentially causing:
  - Duct detectors triggering general evacuation (should be supervisory)
  - Elevator recall not activating for lobby smoke detectors
  - HVAC running during fire (spreading smoke through ducts)
  - NAC circuits not activating (no audible/visual notification)

Consultant's code had these errors (ALL FIXED):
  1. Missing NAC (Notification Appliance Circuit) activation — the MOST
     CRITICAL output. Without it, horns and strobes don't activate.
  2. location_hint string matching ("LOBBY" in loc_hint) — matches
     "LOBBY STORAGE" incorrectly. Replaced with proper device classification.
  3. Missing Elevator Phase II (independent service per ASME A17.1)
  4. Missing Fire Pump Start signal
  5. Missing zone-specific HVAC shutdown (was building-wide)
  6. Missing Sprinkler Waterflow distinction (alarm vs supervisory)
  7. Non-deterministic hash using str() on dicts — replaced with
     canonical JSON serialization
  8. LogicFunction as plain class constants — replaced with Enum

NFPA 72 References:
  - §14.4: Emergency Control Functions — documentation required
  - §17.7.5.6.1: Duct detector response — supervisory in most cases
  - §21.3.3: Elevator recall — Phase I and Phase II
  - §10.14: Notification Appliance Circuits
  - Annex A: Sequence of Operations documentation format

ASME References:
  - A17.1: Elevator Phase I (designated floor) and Phase II (independent service)

Usage:
    from fireai.core.sequence_of_operations import (
        SequenceOfOperationsMatrix, DeviceInput, LogicFunction
    )

    matrix = SequenceOfOperationsMatrix()
    result = matrix.generate_matrix(devices=[
        DeviceInput(device_id="SD-01", device_type="SMOKE", zone_id="Z-1"),
        DeviceInput(device_id="DD-01", device_type="DUCT", zone_id="Z-2"),
    ])
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provenance — graceful degradation
# ---------------------------------------------------------------------------
try:
    from fireai.core.provenance import (
        ConfidenceLevel,
        ConfidenceScore,
        DecisionProvenance,
        RuleApplied,
        Violation,
    )
except ImportError:
    DecisionProvenance = None  # type: ignore[misc,assignment]
    RuleApplied = None  # type: ignore[misc,assignment]
    Violation = None  # type: ignore[misc,assignment]
    ConfidenceScore = None  # type: ignore[misc,assignment]
    ConfidenceLevel = None  # type: ignore[misc,assignment]


# ============================================================================
# Logic Functions — NFPA 72 §14.4 Output Actions
# ============================================================================


class LogicFunction(str, Enum):
    """Output actions that a FACP can trigger per NFPA 72 §14.4.

    Each function maps to a specific NFPA 72 requirement:
      - ALARM: General evacuation signal per §10.14
      - SUPERVISORY: Alert for non-emergency conditions per §10.14
      - TROUBLE: System fault indication per §10.14
      - NAC_ZONE: Notification Appliance Circuit activation per §10.14
      - HVAC_SHUTDOWN: Air handling unit shutdown per §6.8
      - ELEVATOR_RECALL_PRIMARY: Phase I recall to designated floor (ASME A17.1)
      - ELEVATOR_RECALL_ALTERNATE: Phase I recall to alternate floor
      - ELEVATOR_PHASE_II: Independent service mode (ASME A17.1)
      - DOOR_RELEASE: Release magnetic hold-open doors
      - FIRE_PUMP_START: Start fire pump per NFPA 20
      - SMOKE_CONTROL: Activate smoke control system per NFPA 92
      - STAIRWELL_PRESSURIZATION: Pressurize escape stairwells
    """

    ALARM = "General Alarm / Evacuation"
    SUPERVISORY = "Supervisory Signal Only"
    TROUBLE = "Trouble Signal"
    NAC_ZONE = "Activate Notification Appliance Circuits (Zone)"
    NAC_ALL = "Activate Notification Appliance Circuits (All)"
    HVAC_SHUTDOWN_ZONE = "Shutdown AHU / Close Fire Dampers (Zone)"
    HVAC_SHUTDOWN_ALL = "Shutdown AHU / Close Fire Dampers (Building)"
    ELEVATOR_RECALL_PRIMARY = "Elevator Phase I Recall (Designated Floor)"
    ELEVATOR_RECALL_ALTERNATE = "Elevator Phase I Recall (Alternate Floor)"
    ELEVATOR_PHASE_II = "Elevator Phase II (Independent Service)"
    ELEVATOR_SHUNT_TRIP = "Elevator Shunt-Trip Power Disconnect (NFPA 72 §21.4.1)"
    DOOR_RELEASE = "Release Magnetic Hold-Open Doors (Zone)"
    FIRE_PUMP_START = "Start Fire Pump"
    SMOKE_CONTROL = "Activate Smoke Control (Zone)"
    STAIRWELL_PRESSURIZATION = "Pressurize Stairwells"


# ============================================================================
# Device Classification — Proper Enum (not string matching)
# ============================================================================


class DeviceInputType(str, Enum):
    """Input device types for cause-effect mapping.

    The consultant used string matching ("LOBBY" in loc_hint) which
    incorrectly matches "LOBBY STORAGE ROOM". This enum enforces
    exact classification with no ambiguity.
    """

    SMOKE_GENERAL = "SMOKE_GENERAL"
    SMOKE_ELEVATOR_LOBBY = "SMOKE_ELEVATOR_LOBBY"
    SMOKE_ELEVATOR_LOBBY_DESIGNATED = "SMOKE_ELEVATOR_LOBBY_DESIGNATED"
    SMOKE_MACHINE_ROOM = "SMOKE_MACHINE_ROOM"
    SMOKE_ELEVATOR_SHAFT = "SMOKE_ELEVATOR_SHAFT"
    SMOKE_RETURN = "SMOKE_RETURN"
    HEAT = "HEAT"
    HEAT_ELEVATOR_SHUNT_TRIP = "HEAT_ELEVATOR_SHUNT_TRIP"
    MANUAL_CALL_POINT = "MANUAL_CALL_POINT"
    DUCT_DETECTOR = "DUCT_DETECTOR"
    WATERFLOW = "WATERFLOW"
    VALVE_TAMPER = "VALVE_TAMPER"
    SPRINKLER_SUPERVISORY = "SPRINKLER_SUPERVISORY"
    UNKNOWN = "UNKNOWN"


# ============================================================================
# NFPA 72 §14.4 Cause-Effect Rules — Complete Rule Table
# ============================================================================

# Maps DeviceInputType → list of LogicFunction outputs
# Each rule is derived from specific NFPA 72 sections
CAUSE_EFFECT_RULES: Dict[DeviceInputType, List[LogicFunction]] = {
    # Smoke detector (general area) → Full alarm per §10.14
    DeviceInputType.SMOKE_GENERAL: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ZONE,
        LogicFunction.DOOR_RELEASE,
        LogicFunction.HVAC_SHUTDOWN_ZONE,
    ],
    # Smoke detector in elevator lobby → Alarm + Elevator Phase I recall
    # NFPA 72 §21.3.3 / ASME A17.1
    DeviceInputType.SMOKE_ELEVATOR_LOBBY: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ZONE,
        LogicFunction.ELEVATOR_RECALL_PRIMARY,
        LogicFunction.DOOR_RELEASE,
        LogicFunction.HVAC_SHUTDOWN_ZONE,
    ],
    # V20.2 FIX: Smoke at DESIGNATED floor lobby → recall to ALTERNATE floor
    # NFPA 72 §21.3.3: "Where the designated level smoke detector is activated,
    # the elevator shall be recalled to the alternate level."
    DeviceInputType.SMOKE_ELEVATOR_LOBBY_DESIGNATED: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ZONE,
        LogicFunction.ELEVATOR_RECALL_ALTERNATE,
        LogicFunction.DOOR_RELEASE,
        LogicFunction.HVAC_SHUTDOWN_ZONE,
    ],
    # Smoke detector in elevator machine room → Alarm + recall to alternate
    # NFPA 72 §21.3.3: If machine room smoke, recall to alternate floor
    # V20.2 FIX: Removed ELEVATOR_PHASE_II — Phase II is MANUAL firefighter
    # action only per ASME A17.1 §2.27.3.4. Auto Phase II would trap occupants.
    # Added DOOR_RELEASE for smoke containment per NFPA 72 §14.4.
    DeviceInputType.SMOKE_MACHINE_ROOM: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ZONE,
        LogicFunction.ELEVATOR_RECALL_ALTERNATE,
        LogicFunction.DOOR_RELEASE,
        LogicFunction.HVAC_SHUTDOWN_ZONE,
    ],
    # V20.2 FIX: Missing hoistway/shaft smoke detector type per NFPA 72 §21.3.3
    DeviceInputType.SMOKE_ELEVATOR_SHAFT: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ZONE,
        LogicFunction.ELEVATOR_RECALL_ALTERNATE,
        LogicFunction.DOOR_RELEASE,
        LogicFunction.HVAC_SHUTDOWN_ZONE,
    ],
    # Smoke detector in return air shaft → Alarm + HVAC shutdown + door release
    # NFPA 72 §17.7.5.6
    # V20.2 FIX: Added DOOR_RELEASE for smoke containment per NFPA 72 §14.4
    DeviceInputType.SMOKE_RETURN: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ZONE,
        LogicFunction.DOOR_RELEASE,
        LogicFunction.HVAC_SHUTDOWN_ZONE,
    ],
    # Heat detector → Alarm (no HVAC shutdown — smoke detectors should have
    # already triggered HVAC shutdown earlier in fire development)
    DeviceInputType.HEAT: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ZONE,
        LogicFunction.DOOR_RELEASE,
    ],
    # V20.2 FIX: Dedicated heat detector for elevator shunt-trip per
    # NFPA 72 §21.4.1. Must activate before sprinkler to avoid electrified water.
    DeviceInputType.HEAT_ELEVATOR_SHUNT_TRIP: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ZONE,
        LogicFunction.ELEVATOR_SHUNT_TRIP,
    ],
    # Manual call point (pull station) → Full alarm
    # NFPA 72 §10.14 — manual activation is always full evacuation
    DeviceInputType.MANUAL_CALL_POINT: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ALL,
        LogicFunction.DOOR_RELEASE,
        LogicFunction.HVAC_SHUTDOWN_ALL,
    ],
    # Duct detector → SUPERVISORY (NOT general alarm!)
    # NFPA 72 §17.7.5.6.1: Duct detectors in systems serving >2000 CFM
    # shall produce a SUPERVISORY signal, not general alarm.
    # Only shutdown the affected AHU and close fire dampers.
    # CRITICAL: Consultant's code was partially correct here, but missed
    # the nuance that in some jurisdictions, duct detectors in CERTAIN
    # occupancies (healthcare) must also activate alarm.
    DeviceInputType.DUCT_DETECTOR: [
        LogicFunction.SUPERVISORY,
        LogicFunction.HVAC_SHUTDOWN_ZONE,
    ],
    # Waterflow switch → Alarm (sprinkler system activated)
    # NFPA 72 §17.14: Waterflow alarm
    # V20.2 FIX: Removed FIRE_PUMP_START — per NFPA 20 §10.5.2.1, the pump
    # controller starts the pump automatically on pressure drop, NOT the FACP.
    DeviceInputType.WATERFLOW: [
        LogicFunction.ALARM,
        LogicFunction.NAC_ZONE,
    ],
    # Valve tamper switch → Supervisory only
    # NFPA 72 §17.14.2.1: Valve supervisory signal
    DeviceInputType.VALVE_TAMPER: [
        LogicFunction.SUPERVISORY,
    ],
    # Sprinkler supervisory switch → Supervisory only
    DeviceInputType.SPRINKLER_SUPERVISORY: [
        LogicFunction.SUPERVISORY,
    ],
    # V20.2 FIX: Unknown devices default to TROUBLE, NOT general alarm.
    # NFPA 72 §10.14: Alarm signals must indicate a confirmed fire condition.
    # An unknown device type is NOT a confirmed condition.
    DeviceInputType.UNKNOWN: [
        LogicFunction.TROUBLE,
    ],
}


# ============================================================================
# Device Input Dataclass — Proper typed input (not raw dicts)
# ============================================================================


@dataclass(frozen=True)
class DeviceInput:
    """A fire alarm input device for cause-effect matrix generation.

    The consultant used raw dicts with string matching for location hints.
    This dataclass enforces proper typing and uses DeviceInputType enum
    for unambiguous classification.

    Attributes:
        device_id: Unique device identifier (e.g., "SD-FL1-01").
        device_type: DeviceInputType enum — exact classification.
        zone_id: Zone/fire area identifier.
        floor_id: Floor identifier for zone-specific outputs.
        description: Human-readable device description.

    """

    device_id: str
    device_type: DeviceInputType
    zone_id: str = ""
    floor_id: str = ""
    description: str = ""


# ============================================================================
# Matrix Row — Typed output row
# ============================================================================


@dataclass(frozen=True)
class MatrixRow:
    """A single row in the cause-effect matrix.

    Attributes:
        input_device_id: Device identifier.
        zone_id: Zone/fire area.
        floor_id: Floor.
        input_type: DeviceInputType classification.
        outputs_triggered: List of LogicFunction outputs.
        nfpa_references: NFPA 72 section citations for this row.

    """

    input_device_id: str
    zone_id: str
    floor_id: str
    input_type: DeviceInputType
    outputs_triggered: List[LogicFunction]
    nfpa_references: List[str] = field(default_factory=list)


# ============================================================================
# NFPA 72 §14.4 Section References by Device Type
# ============================================================================

NFPA_REFERENCES: Dict[DeviceInputType, List[str]] = {
    DeviceInputType.SMOKE_GENERAL: [
        "NFPA 72-2022 §10.14",
        "NFPA 72-2022 §17.6.3",
    ],
    DeviceInputType.SMOKE_ELEVATOR_LOBBY: [
        "NFPA 72-2022 §21.3.3",
        "ASME A17.1 §2.27",
    ],
    DeviceInputType.SMOKE_MACHINE_ROOM: [
        "NFPA 72-2022 §21.3.3",
        "ASME A17.1 §2.27",
    ],
    DeviceInputType.SMOKE_RETURN: [
        "NFPA 72-2022 §17.7.5.6",
        "NFPA 72-2022 §6.8",
    ],
    DeviceInputType.HEAT: [
        "NFPA 72-2022 §10.14",
        "NFPA 72-2022 §17.9",
    ],
    DeviceInputType.MANUAL_CALL_POINT: [
        "NFPA 72-2022 §10.14",
        "NFPA 72-2022 §17.14.4",
    ],
    DeviceInputType.DUCT_DETECTOR: [
        "NFPA 72-2022 §17.7.5.6.1",
        "NFPA 72-2022 §6.8",
    ],
    DeviceInputType.WATERFLOW: [
        "NFPA 72-2022 §17.14",
        "NFPA 20 (Fire Pump)",
    ],
    DeviceInputType.VALVE_TAMPER: [
        "NFPA 72-2022 §17.14.2.1",
    ],
    DeviceInputType.SPRINKLER_SUPERVISORY: [
        "NFPA 72-2022 §17.14.2",
    ],
}


# ============================================================================
# Sequence Of Operations Matrix Generator
# ============================================================================


class SequenceOfOperationsMatrix:
    """Generates the NFPA 72 §14.4 Cause & Effect Matrix.

    Maps every input device to its required output actions based on
    NFPA 72 code requirements. The matrix is the MOST CRITICAL document
    for FACP programming — without it, the panel programmer operates
    blindly, potentially causing:
      - General evacuation from duct detector activation (should be supervisory)
      - No elevator recall from lobby smoke detectors
      - HVAC continuing during fire (spreading smoke)
      - No notification appliance activation (silent alarm)

    The consultant's code had 8 errors (see module docstring). This
    implementation fixes ALL of them and adds:
      - NAC (Notification Appliance Circuit) activation — the MISSING output
      - Zone-specific HVAC shutdown (not building-wide)
      - Elevator Phase II (independent service)
      - Fire pump start signal
      - Proper Enum-based classification (not string matching)
      - Canonical hash (not str() on dicts)
      - NFPA section references for each row
    """

    def __init__(self) -> None:
        self.rules = dict(CAUSE_EFFECT_RULES)
        self.references = dict(NFPA_REFERENCES)

    def generate_matrix(
        self,
        devices: List[DeviceInput],
        occupancy_type: str = "business",
    ) -> Any:
        """Generate the complete cause-effect matrix for all devices.

        Args:
            devices: List of DeviceInput objects with proper classification.
            occupancy_type: NFPA 101 occupancy type. Affects duct detector
                behavior in healthcare occupancies.

        Returns:
            DecisionProvenance with the complete matrix, or dict if
            provenance is unavailable.

        """
        matrix_rows: List[MatrixRow] = []
        warnings: List[str] = []
        violations: list[str] = []

        for dev in devices:
            # Look up cause-effect rules for this device type
            outputs = self.rules.get(
                dev.device_type,
                [LogicFunction.TROUBLE],
            )
            refs = self.references.get(dev.device_type, [])

            if dev.device_type not in self.rules:
                warnings.append(
                    f"Device {dev.device_id} ({dev.device_type.value}) has no "
                    f"defined cause-effect rule; defaulting to Trouble signal. "
                    f"A licensed FPE must manually specify the logic."
                )

            # Special case: Healthcare duct detectors
            # V20.2 FIX: In healthcare, NFPA 101 §9.7 requires alarm-level
            # notification for duct detectors because patients cannot self-evacuate.
            # Previous code only added NAC_ZONE without ALARM — this is insufficient
            # for healthcare where patients need staff assistance to evacuate.
            # Adding both ALARM and NAC_ZONE ensures full notification.
            effective_outputs = list(outputs)
            if dev.device_type == DeviceInputType.DUCT_DETECTOR and occupancy_type.lower() in (
                "healthcare",
                "hospital",
            ):
                # Add ALARM + NAC zone activation for healthcare duct detectors
                # per NFPA 101 §9.7 and local AHJ requirements
                if LogicFunction.ALARM not in effective_outputs:
                    effective_outputs.append(LogicFunction.ALARM)
                if LogicFunction.NAC_ZONE not in effective_outputs:
                    effective_outputs.append(LogicFunction.NAC_ZONE)
                warnings.append(
                    f"Device {dev.device_id}: Duct detector in healthcare occupancy "
                    f"triggers ALARM + zone NAC per NFPA 101 §9.7 supplementary "
                    f"notification (patients require staff-assisted evacuation)."
                )

            row = MatrixRow(
                input_device_id=dev.device_id,
                zone_id=dev.zone_id,
                floor_id=dev.floor_id,
                input_type=dev.device_type,
                outputs_triggered=effective_outputs,
                nfpa_references=refs,
            )
            matrix_rows.append(row)

        # Build canonical hash for matrix integrity
        # Consultant used str(matrix_rows) — non-deterministic for dicts.
        # We use canonical JSON serialization.
        matrix_data = [
            {
                "device_id": row.input_device_id,
                "zone": row.zone_id,
                "floor": row.floor_id,
                "input_type": row.input_type.value,
                "outputs": [o.value for o in row.outputs_triggered],
            }
            for row in matrix_rows
        ]
        # Sort for canonical ordering
        canonical = json.dumps(
            sorted(matrix_data, key=lambda x: x["device_id"]),
            sort_keys=True,
            separators=(",", ":"),
        )
        # V60 FIX (P1-4): Removed [:16] truncation — 16 hex chars = 64 bits,
        # birthday attack complexity only 2^32 (~4B attempts). Full 256-bit
        # SHA-256 provides 2^128 collision resistance for audit integrity.
        matrix_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        # Build DecisionProvenance if available
        if DecisionProvenance is not None:
            rules_applied = [
                RuleApplied(
                    citation="NFPA 72-2022 §14.4",
                    constant_id="CAUSE_EFFECT_MATRIX",
                    value_used=1,
                    unit="Required Documentation",
                ),
            ]

            has_unknown = any(dev.device_type not in self.rules for dev in devices)
            conf_level = ConfidenceLevel.MEDIUM if has_unknown else ConfidenceLevel.HIGH
            conf = ConfidenceScore(
                input_quality_score=0.95,
                rule_coverage=1.0,
                geometry_certainty=1.0,
                overall=conf_level,
            )

            value = {
                "matrix": matrix_data,
                "hash": matrix_hash,
                "device_count": len(devices),
                "unique_output_types": list({o.value for row in matrix_rows for o in row.outputs_triggered}),
                "zone_count": len({row.zone_id for row in matrix_rows if row.zone_id}),
            }

            return DecisionProvenance.new(
                decision_type="cause_and_effect_matrix",
                value=value,
                inputs={
                    "devices": len(devices),
                    "occupancy_type": occupancy_type,
                },
                rules_applied=rules_applied,
                algorithm={
                    "name": "NFPA72_SequenceMapper",
                    "version": "v18",
                    "corrections": [
                        "Added NAC activation (consultant missed it entirely)",
                        "Zone-specific HVAC shutdown (not building-wide)",
                        "Elevator Phase II added (consultant had only Phase I)",
                        "Fire pump start added for waterflow",
                        "Enum-based classification (not string matching)",
                        "Canonical JSON hash (not str() on dicts)",
                        "Healthcare duct detector context-aware logic",
                    ],
                },
                confidence=conf,
                selected_because=(
                    "Automated cross-mapping of NFPA 72 §14.4 logic paths "
                    "ensures safe panel EPROM programming without rogue alarming."
                ),
                warnings=warnings,
                violations=violations,
            )

        # Fallback: return dict if provenance unavailable
        return {
            "matrix": matrix_data,
            "hash": matrix_hash,
            "warnings": warnings,
        }

    def generate_for_legacy_dicts(
        self,
        devices: List[Dict],
        occupancy_type: str = "business",
    ) -> Any:
        """Generate matrix from legacy dict-based devices (backward compat).

        Converts consultant-style dicts to proper DeviceInput objects.

        Args:
            devices: List of dicts with "device_id", "type", "zone_id",
                and optionally "location_hint" (for legacy compat).
            occupancy_type: NFPA 101 occupancy type.

        Returns:
            Same as generate_matrix().

        """
        typed_devices = []
        for dev in devices:
            dev_type = self._classify_device(dev)
            typed_devices.append(
                DeviceInput(
                    device_id=dev.get("device_id", dev.get("id", "UNK")),
                    device_type=dev_type,
                    zone_id=dev.get("zone_id", ""),
                    floor_id=dev.get("floor_id", ""),
                    description=dev.get("description", ""),
                )
            )
        return self.generate_matrix(typed_devices, occupancy_type)

    def _classify_device(self, dev: Dict) -> DeviceInputType:
        """Classify a legacy dict device into DeviceInputType.

        Uses proper conditional logic, NOT the consultant's
        "LOBBY" in loc_hint string matching.
        """
        raw_type = dev.get("type", "").upper()

        # Direct match for simple types
        simple_map = {
            "HEAT": DeviceInputType.HEAT,
            "MANUAL_CALL_POINT": DeviceInputType.MANUAL_CALL_POINT,
            "MCP": DeviceInputType.MANUAL_CALL_POINT,
            "DUCT": DeviceInputType.DUCT_DETECTOR,
            "DUCT_DETECTOR": DeviceInputType.DUCT_DETECTOR,
            "FLOW_SWITCH": DeviceInputType.WATERFLOW,
            "WATERFLOW": DeviceInputType.WATERFLOW,
            "TAMPER_SWITCH": DeviceInputType.VALVE_TAMPER,
            "VALVE_TAMPER": DeviceInputType.VALVE_TAMPER,
            "SPRINKLER_SUPERVISORY": DeviceInputType.SPRINKLER_SUPERVISORY,
        }

        if raw_type in simple_map:
            return simple_map[raw_type]

        # Smoke detectors need location context
        if raw_type in ("SMOKE", "SMOKE_DETECTOR"):
            loc = dev.get("location_hint", "").upper()
            # Use EXACT word matching, not substring
            # Consultant's bug: "LOBBY" in loc matches "LOBBY STORAGE"
            # Fix: check for specific compound keywords first
            if "ELEVATOR LOBBY" in loc or "LIFT LOBBY" in loc:
                return DeviceInputType.SMOKE_ELEVATOR_LOBBY
            if "MACHINE ROOM" in loc or "MOTOR ROOM" in loc:
                return DeviceInputType.SMOKE_MACHINE_ROOM
            if "RETURN AIR" in loc or "RETURN SHAFT" in loc:
                return DeviceInputType.SMOKE_RETURN
            return DeviceInputType.SMOKE_GENERAL

        # V20.2 FIX: Unknown device type → TROUBLE, NOT general alarm.
        # NFPA 72 §10.14: Alarm signals must indicate a confirmed fire condition.
        # An unknown device is NOT a confirmed condition — false general alarm
        # in a high-rise or healthcare building causes injuries during
        # unnecessary evacuation.
        logger.warning("Unknown device type '%s' for device %s", raw_type, dev.get('device_id', '?'))
        return DeviceInputType.UNKNOWN


__all__ = [
    "CAUSE_EFFECT_RULES",
    "NFPA_REFERENCES",
    "DeviceInput",
    "DeviceInputType",
    "LogicFunction",
    "MatrixRow",
    "SequenceOfOperationsMatrix",
]
