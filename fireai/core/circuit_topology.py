"""fireai.core.circuit_topology — NFPA 72 Circuit Topology Classes
===============================================================

Implements circuit topology models for fire alarm system wiring:

1. CircuitTopology — Class A (loop) and Class B (star/branch) circuit types
2. SLC (Signaling Line Circuit) and NAC (Notification Appliance Circuit) support
3. Device count limits per NFPA 72 §12.3 (max 32 devices between isolators on SLC)
4. Circuit validation against NFPA 72 requirements

SAFETY CRITICAL:
  - All NaN/Inf inputs MUST be REJECTED
  - All negative inputs MUST be REJECTED
  - Device count between isolators MUST NOT exceed 32 per NFPA 72 §12.3.1
  - Class A circuits require return path verification
  - Every validation rule MUST trace to NFPA 72 source section

ENGINEERING SOURCES:
  - NFPA 72-2022 §12.3 — SLC fault isolator requirements
  - NFPA 72-2022 §12.2 — Circuit class designations (Class A, Class B)
  - NFPA 72-2022 §10.6.4 — Secondary power / voltage drop
  - NFPA 72-2022 §18.3 — Notification Appliance Circuits
  - NEC 760 — Fire alarm circuit wiring requirements

All formulas are traced to their NFPA/NEC source sections.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# CIRCUIT CLASS DESIGNATION — NFPA 72 §12.2
# ═══════════════════════════════════════════════════════════════════════════════


class CircuitClass(enum.Enum):
    """NFPA 72 circuit class designations.

    NFPA 72 §12.2 defines two primary circuit styles:

    - Class A: Circuit that features a return path so that a single open
      on the circuit does not cause loss of operation of any device.
      Both the outgoing and return conductors must be routed separately
      (not in the same cable, conduit, or raceway) per NFPA 72 §12.2.2.

    - Class B: Circuit that does NOT have a return path. A single open
      on the circuit causes loss of operation of all devices beyond the
      open point. This is the simpler, less fault-tolerant topology.
      Per NFPA 72 §12.2.3, Class B circuits must still operate all
      devices under normal (non-fault) conditions.
    """

    CLASS_A = "CLASS_A"  # Loop circuit — return path, survives single open
    CLASS_B = "CLASS_B"  # Star/branch circuit — no return path


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCUIT TYPE — SLC vs NAC
# ═══════════════════════════════════════════════════════════════════════════════


class CircuitType(enum.Enum):
    """Fire alarm circuit functional types.

    NFPA 72 §3.3 defines:
    - SLC (Signaling Line Circuit): Carries data between the control unit
      and addressable devices (detectors, modules). Per NFPA 72 §12.3,
      SLCs must have fault isolators limiting each segment to ≤32 devices.
    - NAC (Notification Appliance Circuit): Powers notification appliances
      (horns, strobes, speakers). Per NFPA 72 §18.3, NACs must be
      supervised and capable of operating all connected appliances.
    """

    SLC = "SLC"  # Signaling Line Circuit — addressable data circuit
    NAC = "NAC"  # Notification Appliance Circuit — audible/visible signaling


# ═══════════════════════════════════════════════════════════════════════════════
# DEVICE COUNT LIMITS — NFPA 72 §12.3.1
# ═══════════════════════════════════════════════════════════════════════════════

# NFPA 72 §12.3.1: Maximum devices between fault isolators on SLC
# A single fault must not disable more than 32 addressable devices.
MAX_DEVICES_BETWEEN_ISOLATORS = 32

# Practical maximum total devices per SLC (typical panel limit)
# This is a common manufacturer limit, not a code minimum.
MAX_SLC_DEVICES_DEFAULT = 250

# Typical maximum NAC devices (limited by current, not count)
MAX_NAC_DEVICES_DEFAULT = 99


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCUIT DEVICE — A device on a circuit
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CircuitDevice:
    """A device connected to a fire alarm circuit.

    Represents any addressable or conventional device on an SLC or NAC.
    For SLC circuits, the device_type must include 'isolator' for fault
    isolator devices per NFPA 72 §12.3.

    Attributes:
        device_id: Unique device identifier.
        device_type: Type of device (e.g. 'detector', 'module', 'isolator',
                     'horn', 'strobe', 'horn_strobe').
        position_x: X coordinate in meters (building coordinate system).
        position_y: Y coordinate in meters.
        position_z: Z coordinate in meters (floor/ceiling height).
        current_a: Current draw in alarm condition (amperes).
        zone_id: Optional zone identifier for NFPA 72 zone mapping.

    """

    device_id: str
    device_type: str
    position_x: float = 0.0
    position_y: float = 0.0
    position_z: float = 0.0
    current_a: float = 0.0
    zone_id: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCUIT TOPOLOGY — Main class
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class CircuitTopology:
    """NFPA 72 circuit topology representation.

    Models a fire alarm circuit with its class designation (A or B),
    functional type (SLC or NAC), connected devices, and total cable
    length. Provides validation against NFPA 72 requirements.

    NFPA 72 References:
      - §12.2: Circuit class designations (Class A, Class B)
      - §12.3: SLC fault isolator requirements (max 32 devices per segment)
      - §10.6.4: Voltage drop verification
      - §18.3: NAC requirements

    SAFETY CRITICAL:
      - Device count between isolators MUST NOT exceed 32 (§12.3.1)
      - Class A circuits require return path length tracking
      - All NaN/Inf coordinate values are REJECTED on validation

    Attributes:
        circuit_id: Unique circuit identifier.
        circuit_class: Class A (loop) or Class B (star/branch).
        circuit_type: SLC (Signaling Line Circuit) or NAC (Notification
                      Appliance Circuit).
        devices: Ordered list of devices on this circuit.
        cable_length_m: Total one-way cable length in meters.
        return_length_m: For Class A, the return path cable length in meters.
                         For Class B, this must be 0.0.
        panel_position: (x, y, z) coordinates of the fire alarm panel
                        or NAC power source.

    """

    circuit_id: str
    circuit_class: CircuitClass = CircuitClass.CLASS_B
    circuit_type: CircuitType = CircuitType.SLC
    devices: List[CircuitDevice] = field(default_factory=list)
    cable_length_m: float = 0.0
    return_length_m: float = 0.0
    panel_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    # ─── Device management ─────────────────────────────────────────────────

    def add_device(self, device: CircuitDevice) -> None:
        """Add a device to this circuit.

        Args:
            device: CircuitDevice to add.

        Raises:
            ValueError: If device coordinates contain NaN/Inf values.

        """
        self._validate_device_coordinates(device)
        self.devices.append(device)

    def remove_device(self, device_id: str) -> bool:
        """Remove a device by its ID.

        Args:
            device_id: The device_id to remove.

        Returns:
            True if device was found and removed, False otherwise.

        """
        for i, dev in enumerate(self.devices):
            if dev.device_id == device_id:
                self.devices.pop(i)
                return True
        return False

    def get_isolator_indices(self) -> List[int]:
        """Return indices of fault isolator devices in the device list.

        Per NFPA 72 §12.3, fault isolators must be placed on SLC circuits
        to limit the number of devices disabled by a single fault.

        Returns:
            List of indices where devices have 'isolator' in their type.

        """
        return [i for i, dev in enumerate(self.devices) if "isolator" in dev.device_type.lower()]

    def get_device_count_between_isolators(self) -> List[int]:
        """Calculate device counts between consecutive isolators.

        NFPA 72 §12.3.1: No more than 32 addressable devices shall be
        connected between isolators on an SLC.

        Returns:
            List of device counts for each segment between isolators.
            Includes segment before first isolator and after last isolator.

        """
        if not self.devices:
            return []

        isolator_indices = self.get_isolator_indices()

        # If no isolators, all devices are in one segment
        if not isolator_indices:
            non_isolator_count = sum(1 for d in self.devices if "isolator" not in d.device_type.lower())
            return [non_isolator_count]

        counts = []
        # Segment before first isolator
        first_isolator = isolator_indices[0]
        counts.append(first_isolator)

        # Segments between isolators
        for k in range(len(isolator_indices) - 1):
            start = isolator_indices[k] + 1
            end = isolator_indices[k + 1]
            counts.append(end - start)

        # Segment after last isolator
        last_isolator = isolator_indices[-1]
        counts.append(len(self.devices) - last_isolator - 1)

        return counts

    # ─── Length tracking ───────────────────────────────────────────────────

    def total_cable_length_m(self) -> float:
        """Calculate total cable length for this circuit.

        For Class A circuits (NFPA 72 §12.2.2), the total cable length
        includes both the outgoing AND return conductors. The return
        path must be physically separated from the outgoing path.

        For Class B circuits, only the one-way cable length is counted.

        Formula:
          Class A: L_total = L_outgoing + L_return
          Class B: L_total = L_outgoing

        Returns:
            Total cable length in meters.

        """
        if self.circuit_class == CircuitClass.CLASS_A:
            return self.cable_length_m + self.return_length_m
        return self.cable_length_m

    # ─── Validation ────────────────────────────────────────────────────────

    def validate(self) -> Dict[str, Any]:
        """Validate this circuit topology against NFPA 72 requirements.

        Checks:
          1. Device count between isolators ≤ 32 (NFPA 72 §12.3.1)
          2. Class A return path is present (NFPA 72 §12.2.2)
          3. Device coordinates are finite (data integrity)
          4. Cable lengths are non-negative and finite
          5. SLC circuits have isolators if device count > 32

        Returns:
            Dict with 'compliant' (bool), 'violations' (list),
            'warnings' (list), and NFPA section references.

        """
        violations = []
        warnings = []

        # ── Check 1: Device count between isolators (NFPA 72 §12.3.1) ──
        if self.circuit_type == CircuitType.SLC:
            segment_counts = self.get_device_count_between_isolators()
            for i, count in enumerate(segment_counts):
                if count > MAX_DEVICES_BETWEEN_ISOLATORS:
                    violations.append(
                        {
                            "type": "too_many_devices_between_isolators",
                            "segment_index": i,
                            "device_count": count,
                            "max_allowed": MAX_DEVICES_BETWEEN_ISOLATORS,
                            "nfpa_section": "NFPA 72 §12.3.1",
                            "message": (
                                f"SLC segment {i} has {count} devices between "
                                f"isolators (max {MAX_DEVICES_BETWEEN_ISOLATORS} "
                                f"per NFPA 72 §12.3.1)"
                            ),
                        }
                    )

            # Warning: SLC with many devices but no isolators
            if len(self.devices) > MAX_DEVICES_BETWEEN_ISOLATORS and not self.get_isolator_indices():
                warnings.append(
                    {
                        "type": "no_isolators_on_large_slc",
                        "device_count": len(self.devices),
                        "max_without_isolators": MAX_DEVICES_BETWEEN_ISOLATORS,
                        "nfpa_section": "NFPA 72 §12.3",
                        "message": (
                            f"SLC has {len(self.devices)} devices with no fault "
                            f"isolators — NFPA 72 §12.3 requires isolators when "
                            f"device count exceeds {MAX_DEVICES_BETWEEN_ISOLATORS}"
                        ),
                    }
                )

        # ── Check 2: Class A return path (NFPA 72 §12.2.2) ──
        if self.circuit_class == CircuitClass.CLASS_A:
            if self.return_length_m <= 0:
                violations.append(
                    {
                        "type": "class_a_missing_return_path",
                        "return_length_m": self.return_length_m,
                        "nfpa_section": "NFPA 72 §12.2.2",
                        "message": ("Class A circuit requires a return path with positive length per NFPA 72 §12.2.2"),
                    }
                )

            # Return path length should be reasonable relative to outgoing
            # (typically similar but may differ due to routing)
            if self.cable_length_m > 0 and self.return_length_m > self.cable_length_m * 3.0:
                warnings.append(
                    {
                        "type": "class_a_return_path_excessively_long",
                        "outgoing_m": self.cable_length_m,
                        "return_m": self.return_length_m,
                        "ratio": round(self.return_length_m / self.cable_length_m, 2),
                        "nfpa_section": "NFPA 72 §12.2.2",
                        "message": (
                            f"Class A return path ({self.return_length_m:.1f}m) "
                            f"is >3× outgoing path ({self.cable_length_m:.1f}m) "
                            f"— verify routing separation per NFPA 72 §12.2.2"
                        ),
                    }
                )
        else:
            # Class B should not have return length
            if self.return_length_m > 0:
                warnings.append(
                    {
                        "type": "class_b_has_return_length",
                        "return_length_m": self.return_length_m,
                        "nfpa_section": "NFPA 72 §12.2.3",
                        "message": (
                            f"Class B circuit has return_length_m={self.return_length_m} "
                            f"— Class B circuits do not have return paths"
                        ),
                    }
                )

        # ── Check 3: Device coordinate validity ──
        for _i, dev in enumerate(self.devices):
            if not math.isfinite(dev.position_x):
                violations.append(
                    {
                        "type": "invalid_device_coordinate",
                        "device_id": dev.device_id,
                        "coordinate": "position_x",
                        "value": dev.position_x,
                        "nfpa_section": "DATA_INTEGRITY",
                        "message": (f"Device '{dev.device_id}' has non-finite position_x={dev.position_x}"),
                    }
                )
            if not math.isfinite(dev.position_y):
                violations.append(
                    {
                        "type": "invalid_device_coordinate",
                        "device_id": dev.device_id,
                        "coordinate": "position_y",
                        "value": dev.position_y,
                        "nfpa_section": "DATA_INTEGRITY",
                        "message": (f"Device '{dev.device_id}' has non-finite position_y={dev.position_y}"),
                    }
                )
            if not math.isfinite(dev.position_z):
                violations.append(
                    {
                        "type": "invalid_device_coordinate",
                        "device_id": dev.device_id,
                        "coordinate": "position_z",
                        "value": dev.position_z,
                        "nfpa_section": "DATA_INTEGRITY",
                        "message": (f"Device '{dev.device_id}' has non-finite position_z={dev.position_z}"),
                    }
                )

        # ── Check 4: Cable length validity ──
        if not math.isfinite(self.cable_length_m) or self.cable_length_m < 0:
            violations.append(
                {
                    "type": "invalid_cable_length",
                    "cable_length_m": self.cable_length_m,
                    "nfpa_section": "DATA_INTEGRITY",
                    "message": (f"cable_length_m must be non-negative finite, got {self.cable_length_m}"),
                }
            )

        if self.circuit_class == CircuitClass.CLASS_A and (
            not math.isfinite(self.return_length_m) or self.return_length_m < 0
        ):
            violations.append(
                {
                    "type": "invalid_return_length",
                    "return_length_m": self.return_length_m,
                    "nfpa_section": "DATA_INTEGRITY",
                    "message": (f"return_length_m must be non-negative finite, got {self.return_length_m}"),
                }
            )

        # ── Check 5: Panel position at origin (0,0,0) — V96 FIX ──
        # A panel at (0,0,0) likely means the position was never set, which
        # causes segment lengths to be computed from the building origin
        # instead of the actual panel location — catastrophic voltage drop errors.
        if self.panel_position == (0.0, 0.0, 0.0) and len(self.devices) > 0:
            warnings.append(
                {
                    "type": "panel_at_origin",
                    "panel_position": self.panel_position,
                    "nfpa_section": "DATA_INTEGRITY",
                    "message": (
                        "Panel position is (0,0,0) — if this is not the actual "
                        "panel location, segment lengths and voltage drops will be "
                        "WRONG. Set panel_position to the real coordinates."
                    ),
                }
            )

        # ── Check 6: NAC device current draw ──
        if self.circuit_type == CircuitType.NAC:
            for dev in self.devices:
                if not math.isfinite(dev.current_a) or dev.current_a < 0:
                    violations.append(
                        {
                            "type": "invalid_device_current",
                            "device_id": dev.device_id,
                            "current_a": dev.current_a,
                            "nfpa_section": "NFPA 72 §10.6.4",
                            "message": (f"NAC device '{dev.device_id}' has invalid current_a={dev.current_a}"),
                        }
                    )

        compliant = len(violations) == 0

        return {
            "compliant": compliant,
            "violations": violations,
            "warnings": warnings,
            "device_count": len(self.devices),
            "isolator_count": len(self.get_isolator_indices()),
            "total_cable_length_m": self.total_cable_length_m(),
            "nfpa_sections": [
                "NFPA 72 §12.2",
                "NFPA 72 §12.3",
                "NFPA 72 §10.6.4",
            ],
        }

    # ─── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _validate_device_coordinates(device: CircuitDevice) -> None:
        """Validate that device coordinates are finite numbers.

        SAFETY CRITICAL: NaN/Inf coordinates indicate data corruption
        and MUST be rejected. A device with NaN coordinates cannot be
        located in 3D space, making cable routing impossible.

        Args:
            device: CircuitDevice to validate.

        Raises:
            ValueError: If any coordinate is NaN or Inf.

        """
        for name, value in [
            ("position_x", device.position_x),
            ("position_y", device.position_y),
            ("position_z", device.position_z),
        ]:
            if not math.isfinite(value):
                raise ValueError(f"Device '{device.device_id}' has non-finite {name}={value}")
