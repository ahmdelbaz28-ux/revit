"""fault_isolator_injector.py — SLC Loop Fault Isolation per NFPA 72
=================================================================
CRITICAL LIFE-SAFETY MODULE

Injects Fault Isolator Modules into SLC loop designs to ensure that
a single wire fault (short circuit or open circuit) does not disable
more than one zone or a specified maximum number of devices.

Without fault isolators, a single short circuit on an SLC loop can
disable ALL 250 devices on that loop — leaving an entire building
without fire detection. This module prevents that catastrophic failure.

NFPA 72 References:
  - §12.3.1:  Fault isolation required on addressable circuits
  - §12.3.2:  A single fault must not affect more than one zone
  - §21.4:    Class A circuit requirements
  - Annex A.12.3.1: Explanatory material on fault isolation architecture

The consultant's original code used §23.6.1 which refers to Emergency
Communications Systems — the correct reference is §12.3.1/§12.3.2.

Usage:
    from fireai.core.fault_isolator_injector import inject_fault_isolators

    secure_loop = inject_fault_isolators(
        loop_devices=loop.order,
        zone_map={"room_1": "Z1", "room_2": "Z2"},
        max_devices_between_isolators=20,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class IsolatorPlacement:
    """Record of a single fault isolator injection."""

    position_index: int  # Where in the loop sequence it was inserted
    position_xy: Tuple[float, float]  # Physical position (same as next device)
    reason: str  # Why it was inserted
    nfpa_citation: str  # Code reference
    zone_id_before: Optional[str]  # Zone before isolator
    zone_id_after: Optional[str]  # Zone after isolator


@dataclass
class IsolatorInjectionResult:
    """Complete result of fault isolator injection."""

    original_device_count: int
    injected_isolator_count: int
    total_device_count: int  # original + isolators
    secure_loop: List[Dict[str, Any]]  # Devices + isolators in order
    isolator_placements: List[IsolatorPlacement]
    violations: List[str] = field(default_factory=list)
    is_compliant: bool = False  # V112: FAIL-SAFE — starts NOT compliant until verified


# ============================================================================
# Constants — NFPA 72
# ============================================================================

# NFPA 72 §12.3.2: A single fault must not disable more than one zone.
# The code does not specify an exact device count — the limit is based
# on zones. However, as a conservative engineering practice, we also
# limit the number of devices between isolators to prevent cascading
# failures when zone boundaries are not clearly defined.
DEFAULT_MAX_DEVICES_BETWEEN_ISOLATORS = 32  # Conservative engineering limit
# (NFPA does not mandate a specific number, but common practice is 20-50)

ISOLATOR_DEVICE_TYPE = "FAULT_ISOLATOR"
NFPA_CITATION_ISOLATION = "NFPA 72-2022 §12.3.1"
NFPA_CITATION_ZONE_LIMIT = "NFPA 72-2022 §12.3.2"


# ============================================================================
# Core Injection Algorithm
# ============================================================================


def inject_fault_isolators(
    loop_devices: List[Dict[str, Any]],
    zone_map: Optional[Dict[str, str]] = None,
    max_devices_between_isolators: int = DEFAULT_MAX_DEVICES_BETWEEN_ISOLATORS,
    class_a: bool = False,
) -> IsolatorInjectionResult:
    """Inject fault isolator modules into an SLC loop design.

    Algorithm:
        1. Walk the loop in physical order.
        2. Insert an isolator BEFORE a device when:
           a. The device belongs to a DIFFERENT zone than the previous device,
              OR
           b. The number of devices since the last isolator exceeds
              max_devices_between_isolators.
        3. Always insert an isolator at the FIRST device (loop entry point).

    Args:
        loop_devices: Ordered list of devices on the loop. Each device dict
                      must have at least a 'device_idx' or 'id' key and
                      ideally a 'position' key (x, y tuple).
                      Optional keys: 'zone_id', 'room_id'.
        zone_map:     Optional mapping from device_id/room_id to zone string.
                      If devices have 'zone_id' key, this is not needed.
        max_devices_between_isolators: Maximum devices between consecutive
                      isolators (default 32 — conservative engineering).
        class_a:      Whether this is a Class A loop. If True, the algorithm
                      also inserts an isolator at the loop return point.

    Returns:
        IsolatorInjectionResult with the secure loop and placement records.

    """
    if not loop_devices:
        return IsolatorInjectionResult(
            original_device_count=0,
            injected_isolator_count=0,
            total_device_count=0,
            secure_loop=[],
            isolator_placements=[],
        )

    secure_loop: List[Dict[str, Any]] = []
    placements: List[IsolatorPlacement] = []
    violations: List[str] = []
    devices_since_last_isolator = 0
    current_zone: Optional[str] = None
    isolator_count = 0

    def _get_zone(device: Dict[str, Any]) -> Optional[str]:
        """Extract zone ID from device or zone_map."""
        if device.get("zone_id"):
            return str(device["zone_id"])
        if zone_map:
            for key in ("id", "device_id", "room_id", "device_idx"):
                if key in device:
                    mapped = zone_map.get(str(device[key]))
                    if mapped:
                        return str(mapped)
        return None

    def _get_position(device: Dict[str, Any]) -> Tuple[float, float]:
        """Extract (x, y) position from device."""
        pos = device.get("position") or device.get("pos")
        if pos is not None:
            if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                return (float(pos[0]), float(pos[1]))
        # Fallback: position from tuple key
        if "x" in device and "y" in device:
            return (float(device["x"]), float(device["y"]))
        return (0.0, 0.0)

    def _make_isolator(
        index: int,
        position: Tuple[float, float],
        reason: str,
        zone_before: Optional[str],
        zone_after: Optional[str],
    ) -> Dict[str, Any]:
        """Create a fault isolator device dict."""
        return {
            "device_type": ISOLATOR_DEVICE_TYPE,
            "device_idx": f"ISO-{index}",
            "position": position,
            "zone_id": zone_after,
            "is_injector_inserted": True,
            "injection_reason": reason,
            "nfpa_citation": NFPA_CITATION_ISOLATION,
        }

    # === Walk the loop and inject isolators ===
    for i, device in enumerate(loop_devices):
        device_zone = _get_zone(device)
        device_pos = _get_position(device)

        # Decision: should we insert an isolator before this device?
        need_isolator = False
        reason = ""

        # Rule 1: First device on the loop — always isolate at entry point
        if i == 0:
            need_isolator = True
            reason = f"Loop entry point isolator per {NFPA_CITATION_ISOLATION}"

        # Rule 2: Zone boundary crossed
        elif device_zone is not None and current_zone is not None and device_zone != current_zone:
            need_isolator = True
            reason = f"Zone boundary: {current_zone} -> {device_zone} per {NFPA_CITATION_ZONE_LIMIT}"

        # Rule 3: Max devices between isolators exceeded
        elif devices_since_last_isolator >= max_devices_between_isolators:
            need_isolator = True
            reason = (
                f"Max devices between isolators ({max_devices_between_isolators}) exceeded per engineering practice"
            )

        # Insert isolator if needed
        if need_isolator:
            isolator_count += 1
            iso_device = _make_isolator(
                index=isolator_count,
                position=device_pos,
                reason=reason,
                zone_before=current_zone,
                zone_after=device_zone,
            )
            secure_loop.append(iso_device)
            placements.append(
                IsolatorPlacement(
                    position_index=len(secure_loop) - 1,
                    position_xy=device_pos,
                    reason=reason,
                    nfpa_citation=NFPA_CITATION_ISOLATION,
                    zone_id_before=current_zone,
                    zone_id_after=device_zone,
                )
            )
            devices_since_last_isolator = 0

        # Add the actual device
        secure_loop.append(device)
        devices_since_last_isolator += 1
        current_zone = device_zone

    # Class A: insert isolator at the loop return point
    if class_a and loop_devices:
        last_pos = _get_position(loop_devices[-1])
        isolator_count += 1
        iso_device = _make_isolator(
            index=isolator_count,
            position=last_pos,
            reason="Class A loop return point per NFPA 72 §21.4",
            zone_before=current_zone,
            zone_after=None,
        )
        secure_loop.append(iso_device)
        placements.append(
            IsolatorPlacement(
                position_index=len(secure_loop) - 1,
                position_xy=last_pos,
                reason="Class A loop return point isolator",
                nfpa_citation="NFPA 72-2022 §21.4",
                zone_id_before=current_zone,
                zone_id_after=None,
            )
        )

    # Validate: check if any segment exceeds device limit
    count_since_isolator = 0
    for dev in secure_loop:
        if dev.get("device_type") == ISOLATOR_DEVICE_TYPE:
            count_since_isolator = 0
        else:
            count_since_isolator += 1
            if count_since_isolator > max_devices_between_isolators:
                violations.append(
                    f"Segment has {count_since_isolator} devices between "
                    f"isolators (max {max_devices_between_isolators})"
                )

    total_count = len(secure_loop)
    is_compliant = len(violations) == 0

    return IsolatorInjectionResult(
        original_device_count=len(loop_devices),
        injected_isolator_count=isolator_count,
        total_device_count=total_count,
        secure_loop=secure_loop,
        isolator_placements=placements,
        violations=violations,
        is_compliant=is_compliant,
    )


def verify_isolator_compliance(
    loop_devices: List[Dict[str, Any]],
    max_devices_between_isolators: int = DEFAULT_MAX_DEVICES_BETWEEN_ISOLATORS,
) -> Dict[str, Any]:
    """Verify that an existing loop already has adequate fault isolation.

    Useful for checking loops that were designed manually or by external tools.

    Args:
        loop_devices: Ordered list of devices (including any existing isolators).
        max_devices_between_isolators: Maximum allowed devices between isolators.

    Returns:
        Dict with 'compliant', 'max_segment_devices', 'isolator_count',
        'violations', and 'recommendation' keys.

    """
    if not loop_devices:
        return {
            "compliant": True,
            "max_segment_devices": 0,
            "isolator_count": 0,
            "violations": [],
            "recommendation": "Empty loop — no isolation needed",
        }

    max_segment = 0
    current_segment = 0
    isolator_count = 0
    violations = []
    has_isolator = False

    for dev in loop_devices:
        dtype = dev.get("device_type", "").upper()
        if dtype == ISOLATOR_DEVICE_TYPE or "ISOLATOR" in dtype:
            isolator_count += 1
            has_isolator = True
            max_segment = max(max_segment, current_segment)
            current_segment = 0
        else:
            current_segment += 1

    max_segment = max(max_segment, current_segment)

    if not has_isolator:
        violations.append(
            f"NO fault isolators found on this loop. A single fault will "
            f"disable all {len(loop_devices)} devices. "
            f"Per {NFPA_CITATION_ISOLATION}, fault isolation is required."
        )
    elif max_segment > max_devices_between_isolators:
        violations.append(
            f"Largest segment between isolators has {max_segment} devices "
            f"(max allowed: {max_devices_between_isolators}). "
            f"A fault in this segment would disable {max_segment} devices."
        )

    return {
        "compliant": len(violations) == 0,
        "max_segment_devices": max_segment,
        "isolator_count": isolator_count,
        "violations": violations,
        "recommendation": (
            "Loop complies with fault isolation requirements"
            if not violations
            else f"Inject fault isolators to address {len(violations)} violation(s)"
        ),
    }


__all__ = [
    "DEFAULT_MAX_DEVICES_BETWEEN_ISOLATORS",
    "ISOLATOR_DEVICE_TYPE",
    "NFPA_CITATION_ISOLATION",
    "NFPA_CITATION_ZONE_LIMIT",
    "IsolatorInjectionResult",
    "IsolatorPlacement",
    "inject_fault_isolators",
    "verify_isolator_compliance",
]
