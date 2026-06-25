"""as_built_reconciliator.py — 3D As-Built Reconciliator for FireAI
================================================================

Compares design-time device placement against as-built (field-verified)
data using THREE-DIMENSIONAL position comparison. Buildings are 3D —
a 2D comparison that ignores elevation is a safety defect.

This module uses the existing Merkle tree from ``blockchain_readiness_gate``
for design-manifest integrity verification. It does NOT implement any
blockchain smart contracts, Solidity code, or distributed ledger.

NFPA References:
    - NFPA 72-2022 §17.6 — Smoke detector spacing and location
    - NFPA 72-2022 §17.7 — Heat detector spacing and location
    - NFPA 72-2022 §17.8 — Duct smoke detector installation
    - NFPA 72-2022 §17.12 — Manual fire alarm boxes (pull stations)
    - ADA Standards for Accessible Design §309 — Reach ranges for
      manual pull station mounting height (48 in / 1.22 m max above
      finished floor)

Device-type-specific tolerances are derived from the following rationale:

    - SMOKE detectors (0.3 m): NFPA 72 §17.6.3 spacing is sensitive to
      ceiling position. A drift of >0.3 m could push a detector outside
      its rated coverage area.
    - HEAT detectors (0.3 m): Similar spacing sensitivity per §17.7.
    - MANUAL_PULL_STATION (0.15 m): ADA §309 mandates a maximum
      mounting height of 48 in (1.22 m) above finished floor. The
      tolerance is tighter because accessibility compliance is a legal
      requirement, not just an engineering recommendation.
    - DUCT_SMOKE (0.5 m): Duct positions vary more in the field due to
      MEP coordination; the wider tolerance reflects as-built reality
      per §17.8.

Usage::

    from fireai.core.as_built_reconciliator import (
        AsBuiltReconciliator, ReconciliationResult, DEVICE_TOLERANCES,
    )

    reconciliator = AsBuiltReconciliator(
        design_manifest={"devices": [...]},
        merkle_root="abc123...",   # optional integrity check
    )
    result = reconciliator.reconcile(as_built_devices=[...])
    print(result.status)  # "VERIFIED" or "DEVIATION_DETECTED"
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from fireai.core.blockchain_readiness_gate import BlockchainReadinessGate

# ============================================================================
# Constants — Device-type-specific 3D position tolerances (metres)
# ============================================================================

DEVICE_TOLERANCES: Dict[str, float] = {
    "SMOKE": 0.3,
    # NFPA 72-2022 §17.6 — smoke detector spacing is sensitive to
    # ceiling position; drift beyond 0.3 m may place the detector
    # outside its rated coverage area.
    "HEAT": 0.3,
    # NFPA 72-2022 §17.7 — heat detector spacing; same spatial
    # sensitivity rationale as smoke detectors.
    "MANUAL_PULL_STATION": 0.15,
    # ADA §309 — reach-range compliance requires precise mounting
    # height (48 in / 1.22 m max AFF). Tighter tolerance because
    # accessibility is a legal mandate, not just engineering guidance.
    "DUCT_SMOKE": 0.5,
    # NFPA 72-2022 §17.8 — duct smoke detector location; wider
    # tolerance reflects field variability in duct routing after
    # MEP coordination.
}
"""Device-type-specific position tolerances in metres.

Keys are device type strings (case-insensitive lookup).  Devices not
listed here fall back to ``DEFAULT_TOLERANCE``.
"""

DEFAULT_TOLERANCE: float = 0.5
"""Fallback tolerance for device types without a specific entry."""

DEVICE_ID_KEY: str = "id"
"""Key used to identify a device uniquely in both design and as-built dicts."""

REQUIRED_DEVICE_KEYS: Tuple[str, ...] = ("id", "x", "y", "z", "device_type")
"""Keys that must be present in every device dict."""


# ============================================================================
# Helper Functions
# ============================================================================


def _get_tolerance(device_type: str) -> float:
    """Return the position tolerance for *device_type*.

    Lookup is case-insensitive.  Returns ``DEFAULT_TOLERANCE`` when the
    device type is not in ``DEVICE_TOLERANCES``.

    Args:
        device_type: The device type string (e.g. ``"SMOKE"``).

    Returns:
        Tolerance in metres.

    """
    return DEVICE_TOLERANCES.get(device_type.upper(), DEFAULT_TOLERANCE)


def _euclidean_distance_3d(
    x1: float,
    y1: float,
    z1: float,
    x2: float,
    y2: float,
    z2: float,
) -> float:
    """Compute the 3D Euclidean distance between two points.

    This is a FULL three-dimensional calculation — x, y, *and* z.
    A 2D comparison that ignores elevation would miss devices installed
    on the wrong floor or at the wrong ceiling height, which is a
    safety defect in fire protection engineering.

    Args:
        x1, y1, z1: Coordinates of the first point (design).
        x2, y2, z2: Coordinates of the second point (as-built).

    Returns:
        Euclidean distance in metres.

    """
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)


def _serialize_device(device: Dict) -> str:
    """Serialize a device dict to a canonical JSON string for hashing.

    Keys are sorted to ensure deterministic output regardless of dict
    insertion order.

    Args:
        device: Device dict with at least ``id``, ``x``, ``y``, ``z``,
            ``device_type`` keys.

    Returns:
        Canonical JSON string.

    """
    return json.dumps(device, sort_keys=True, separators=(",", ":"))


def _validate_device_dict(device: Dict, source: str) -> None:
    """Validate that a device dict has all required keys.

    Args:
        device: Device dict to validate.
        source: Description of the data source (for error messages).

    Raises:
        ValueError: If any required key is missing.

    """
    missing = [k for k in REQUIRED_DEVICE_KEYS if k not in device]
    if missing:
        raise ValueError(f"Device from {source} missing required keys: {missing}. Device: {device}")


# ============================================================================
# ReconciliationResult
# ============================================================================


@dataclass
class ReconciliationResult:
    """Result of comparing as-built device positions against design.

    Attributes:
        status: ``"VERIFIED"`` if all devices match within tolerance;
            ``"DEVIATION_DETECTED"`` if any device is rogue, missing, or
            drifted beyond tolerance.
        verified_count: Number of devices that matched within tolerance.
        rogue_devices: Devices found in as-built but NOT in design.
            Each entry is ``(device_id, message)``.
        missing_devices: Devices found in design but NOT in as-built.
            Each entry is ``(device_id, message)``.
        drifted_devices: Devices present in both but whose 3D position
            exceeds the device-type-specific tolerance.
            Each entry is ``(device_id, drift_m, tolerance_m, message)``.
        summary: Human-readable summary of the reconciliation.
        integrity_verified: Whether the Merkle integrity check passed.
            ``None`` if no merkle_root was provided.

    """

    status: str
    verified_count: int
    rogue_devices: List[Tuple[str, str]]
    missing_devices: List[Tuple[str, str]]
    drifted_devices: List[Tuple[str, float, float, str]]
    summary: str
    integrity_verified: Optional[bool] = None

    @property
    def total_deviations(self) -> int:
        """Total number of deviations (rogue + missing + drifted)."""
        return len(self.rogue_devices) + len(self.missing_devices) + len(self.drifted_devices)


# ============================================================================
# AsBuiltReconciliator
# ============================================================================


class AsBuiltReconciliator:
    """3D As-Built Reconciliator — compares design vs. field-verified data.

    This reconciliator performs a **three-dimensional** comparison of
    device positions between the design manifest and as-built survey
    data.  It detects three classes of deviation:

        1. **Rogue devices** — installed in the field but not in design.
        2. **Missing devices** — specified in design but not installed.
        3. **Drifted devices** — installed but not at the designed
           position (3D drift exceeds device-type-specific tolerance).

    Integrity of the design manifest is verified via the existing
    ``BlockchainReadinessGate`` (Merkle tree) when a ``merkle_root``
    is provided.  This is NOT a blockchain module — it merely uses the
    Merkle tree for tamper detection on the design data.

    Args:
        design_manifest: Dict with a ``"devices"`` key containing a list
            of device dicts.  Each device dict must have keys:
            ``id``, ``x``, ``y``, ``z``, ``device_type``.
        merkle_root: Previously recorded Merkle root for integrity
            verification.  If ``None``, integrity check is skipped.

    Raises:
        ValueError: If design_manifest is missing the ``"devices"`` key
            or any device dict is missing required keys.
        RuntimeError: If merkle_root is provided but integrity check
            fails (design manifest has been tampered with).

    """

    def __init__(
        self,
        design_manifest: Dict,
        merkle_root: Optional[str] = None,
    ) -> None:
        # --- Validate design manifest structure ---
        if "devices" not in design_manifest:
            raise ValueError("design_manifest must contain a 'devices' key with a list of device dicts.")

        design_devices = design_manifest["devices"]
        if not isinstance(design_devices, list):
            raise ValueError("design_manifest['devices'] must be a list of device dicts.")

        # Validate each device dict
        for dev in design_devices:
            _validate_device_dict(dev, source="design_manifest")

        # --- Merkle integrity check (optional) ---
        self._integrity_verified: Optional[bool] = None
        if merkle_root is not None:
            # Serialize each device to a canonical string and build a
            # Merkle tree over those artifacts.
            artifacts = [_serialize_device(dev) for dev in design_devices]
            gate = BlockchainReadinessGate(design_artifacts=artifacts)
            if not gate.check_tamper(merkle_root):
                raise RuntimeError(
                    "Design manifest integrity check FAILED — merkle_root "
                    "does not match. The design manifest may have been "
                    "tampered with or the merkle_root is stale."
                )
            self._integrity_verified = True

        # --- Index design devices by ID for O(1) lookup ---
        self._design_by_id: Dict[str, Dict] = {}
        for dev in design_devices:
            device_id = str(dev[DEVICE_ID_KEY])
            if device_id in self._design_by_id:
                raise ValueError(f"Duplicate device ID in design_manifest: {device_id!r}")
            self._design_by_id[device_id] = dev

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def reconcile(
        self,
        as_built_devices: List[Dict],
    ) -> ReconciliationResult:
        """Compare as-built devices against the design manifest.

        For each as-built device, the reconciliator checks:

            1. Whether the device exists in the design (rogue detection).
            2. If it exists, the 3D Euclidean drift from its designed
               position.
            3. Whether the drift exceeds the device-type-specific
               tolerance.

        It also checks for devices in the design that are NOT present
        in the as-built data (missing device detection — the contractor
        forgot to install them).

        Args:
            as_built_devices: List of dicts, each with keys ``id``,
                ``x``, ``y``, ``z``, ``device_type``.

        Returns:
            ``ReconciliationResult`` with full deviation details.

        Raises:
            ValueError: If any as-built device dict is missing required
                keys.

        """
        # Validate all as-built device dicts upfront
        for dev in as_built_devices:
            _validate_device_dict(dev, source="as_built_devices")

        # Index as-built devices by ID
        as_built_by_id: Dict[str, Dict] = {}
        for dev in as_built_devices:
            device_id = str(dev[DEVICE_ID_KEY])
            # Note: duplicate as-built IDs are allowed (last wins) but
            # we warn by simply overwriting — the field data is what it
            # is.
            as_built_by_id[device_id] = dev

        # --- Classification containers ---
        rogue_devices: List[Tuple[str, str]] = []
        missing_devices: List[Tuple[str, str]] = []
        drifted_devices: List[Tuple[str, float, float, str]] = []
        verified_count: int = 0

        # --- Pass 1: Check each as-built device against design ---
        for device_id, ab_dev in as_built_by_id.items():
            if device_id not in self._design_by_id:
                # ROGUE — installed but not in design
                msg = (
                    f"Device {device_id!r} found in as-built survey but "
                    f"not in design manifest. Possible unauthorized "
                    f"installation or ID mismatch."
                )
                rogue_devices.append((device_id, msg))
                continue

            # Device exists in design — compute 3D drift
            design_dev = self._design_by_id[device_id]
            drift = _euclidean_distance_3d(
                float(design_dev["x"]),
                float(design_dev["y"]),
                float(design_dev["z"]),
                float(ab_dev["x"]),
                float(ab_dev["y"]),
                float(ab_dev["z"]),
            )
            tolerance = _get_tolerance(str(ab_dev.get("device_type", "")))

            if drift > tolerance:
                # DRIFTED — beyond tolerance
                msg = (
                    f"Device {device_id!r} (type={ab_dev.get('device_type', 'UNKNOWN')}) "
                    f"drifted {drift:.3f} m from design position, exceeding "
                    f"tolerance of {tolerance:.3f} m. "
                    f"Design: ({design_dev['x']}, {design_dev['y']}, {design_dev['z']}) "
                    f"As-built: ({ab_dev['x']}, {ab_dev['y']}, {ab_dev['z']})"
                )
                drifted_devices.append((device_id, drift, tolerance, msg))
            else:
                verified_count += 1

        # --- Pass 2: Check for MISSING devices (design but not as-built) ---
        as_built_ids = set(as_built_by_id.keys())
        for device_id, design_dev in self._design_by_id.items():
            if device_id not in as_built_ids:
                msg = (
                    f"Device {device_id!r} (type={design_dev.get('device_type', 'UNKNOWN')}) "
                    f"specified in design but not found in as-built survey. "
                    f"Contractor may have omitted this device."
                )
                missing_devices.append((device_id, msg))

        # --- Determine overall status ---
        has_deviations = len(rogue_devices) > 0 or len(missing_devices) > 0 or len(drifted_devices) > 0
        status = "DEVIATION_DETECTED" if has_deviations else "VERIFIED"

        # --- Build summary ---
        summary = self._build_summary(
            status=status,
            verified_count=verified_count,
            rogue_count=len(rogue_devices),
            missing_count=len(missing_devices),
            drifted_count=len(drifted_devices),
            total_design=len(self._design_by_id),
            total_as_built=len(as_built_by_id),
        )

        return ReconciliationResult(
            status=status,
            verified_count=verified_count,
            rogue_devices=rogue_devices,
            missing_devices=missing_devices,
            drifted_devices=drifted_devices,
            summary=summary,
            integrity_verified=self._integrity_verified,
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_summary(
        *,
        status: str,
        verified_count: int,
        rogue_count: int,
        missing_count: int,
        drifted_count: int,
        total_design: int,
        total_as_built: int,
    ) -> str:
        """Build a human-readable summary string.

        Args:
            status: Overall reconciliation status.
            verified_count: Devices within tolerance.
            rogue_count: Rogue devices (in as-built, not in design).
            missing_count: Missing devices (in design, not in as-built).
            drifted_count: Drifted devices (beyond tolerance).
            total_design: Total devices in design manifest.
            total_as_built: Total devices in as-built survey.

        Returns:
            Multi-line summary string.

        """
        lines = [
            f"As-Built Reconciliation: {status}",
            f"  Design devices:    {total_design}",
            f"  As-built devices:  {total_as_built}",
            f"  Verified (within tolerance): {verified_count}",
        ]
        if rogue_count > 0:
            lines.append(f"  Rogue (not in design):      {rogue_count}")
        if missing_count > 0:
            lines.append(f"  Missing (not installed):    {missing_count}")
        if drifted_count > 0:
            lines.append(f"  Drifted (beyond tolerance): {drifted_count}")

        if status == "VERIFIED":
            lines.append("  All as-built devices match design within tolerance.")
        else:
            lines.append("  REVIEW REQUIRED — deviations detected between design and as-built.")
        return "\n".join(lines)


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    "DEFAULT_TOLERANCE",
    "DEVICE_TOLERANCES",
    "AsBuiltReconciliator",
    "ReconciliationResult",
]
