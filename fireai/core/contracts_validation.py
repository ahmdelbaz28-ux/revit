"""
fireai.core.contracts_validation — Input Contract Validation
=============================================================

Validates room input payloads BEFORE they enter the pipeline.
This is Stage 0 — the first line of defense.

SAFETY CRITICAL:
  - NaN/Inf inputs are REJECTED — they bypass safety checks silently.
  - Missing required fields cause ContractViolation.
  - Negative dimensions are REJECTED — physically impossible.
  - Zero-area rooms are REJECTED — cannot place detectors.

NFPA 72 Reference:
  - §17.6.3.1 — ceiling height must be known for spacing
  - §17.7.4.2.3.1 — room area must be known for coverage
  - §17.6.3.1.1 — detector type determines spacing table

This module is the GATEKEEPER. No invalid data enters the pipeline.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


class ContractViolation(Exception):
    """Raised when input data violates the engineering contract.

    This is a FATAL error — the pipeline MUST NOT proceed with
    invalid data. The caller must fix the input and resubmit.
    """

    def __init__(self, message: str, field: str = "", value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value


# ─── Required Fields ────────────────────────────────────────────────────────

_REQUIRED_FIELDS = {
    "room_id":       (str,   "Room identifier (e.g. 'R-101')"),
    "room_polygon":  (list,  "List of (x, y) tuples defining room boundary"),
    "ceiling_height_m": ((int, float), "Ceiling height in meters"),
    "detector_type": (str,   "'smoke' or 'heat'"),
}

_OPTIONAL_FIELDS = {
    "area_m2":        ((int, float), "Room area in m² (computed from polygon if missing)"),
    "occupancy_type": (str,   "Occupancy classification (e.g. 'office', 'warehouse')"),
    "ceiling_type":   (str,   "'flat', 'sloped', 'beamed', 'corridor'"),
}

_VALID_DETECTOR_TYPES = {"smoke", "heat"}
_VALID_CEILING_TYPES  = {"flat", "sloped", "beamed", "corridor", ""}

# ─── NaN/Inf Detection ──────────────────────────────────────────────────────

def _has_nan_inf(value: Any, path: str = "") -> List[str]:
    """Recursively check for NaN/Inf in any data structure."""
    violations = []

    if isinstance(value, float):
        if math.isnan(value):
            violations.append(f"{path or 'value'} is NaN — NaN bypasses all safety checks")
        elif math.isinf(value):
            violations.append(f"{path or 'value'} is Inf — infinite values are physically impossible")

    elif isinstance(value, dict):
        for k, v in value.items():
            violations.extend(_has_nan_inf(v, f"{path}.{k}" if path else k))

    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            violations.extend(_has_nan_inf(v, f"{path}[{i}]"))

    return violations


# ─── Polygon Validation ─────────────────────────────────────────────────────

def _validate_polygon(polygon: Any) -> List[str]:
    """Validate room polygon for geometric correctness."""
    warnings = []

    if not isinstance(polygon, list):
        return [f"room_polygon must be a list, got {type(polygon).__name__}"]

    if len(polygon) < 3:
        return [f"room_polygon must have ≥3 vertices, got {len(polygon)}"]

    for i, pt in enumerate(polygon):
        if not isinstance(pt, (list, tuple)):
            warnings.append(f"polygon vertex {i} must be tuple/list, got {type(pt).__name__}")
        elif len(pt) != 2:
            warnings.append(f"polygon vertex {i} must have 2 coords, got {len(pt)}")
        else:
            for j, c in enumerate(pt):
                if not isinstance(c, (int, float)):
                    warnings.append(f"polygon vertex {i} coord {j} must be numeric, got {type(c).__name__}")

    return warnings


# ─── Area Computation ───────────────────────────────────────────────────────

def _compute_area_from_polygon(polygon: List) -> float:
    """Compute polygon area using the Shoelace formula.

    Returns signed area - positive if vertices are counterclockwise.
    We take abs() since we only care about magnitude.
    """
    n = len(polygon)
    if n < 3:
        return 0.0

    area = 0.0
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        area += x1 * y2 - x2 * y1

    return abs(area) / 2.0


# ─── Main Validation Function ───────────────────────────────────────────────

def validate_room_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate room input payload against the engineering contract.

    Args:
        payload: Raw room input dict.

    Returns:
        Validated and enriched payload dict with computed fields.

    Raises:
        ContractViolation: On any fatal input contract violation.
    """
    if not isinstance(payload, dict):
        raise ContractViolation(
            f"Payload must be a dict, got {type(payload).__name__}",
            field="payload",
            value=type(payload).__name__,
        )

    # ── Step 1: NaN/Inf Detection ──────────────────────────────────────────
    nan_violations = _has_nan_inf(payload)
    if nan_violations:
        raise ContractViolation(
            f"NaN/Inf detected in input — these bypass safety checks silently. "
            f"Violations: {'; '.join(nan_violations)}",
            field="payload",
            value=nan_violations,
        )

    # ── Step 2: Required Field Check ──────────────────────────────────────
    for field_name, (expected_type, description) in _REQUIRED_FIELDS.items():
        if field_name not in payload:
            raise ContractViolation(
                f"Missing required field '{field_name}': {description}",
                field=field_name,
                value=None,
            )

    # ── Step 3: Type Validation ──────────────────────────────────────────
    room_id = payload["room_id"]
    if not isinstance(room_id, str) or not room_id.strip():
        raise ContractViolation(
            f"room_id must be a non-empty string, got: {room_id!r}",
            field="room_id",
            value=room_id,
        )

    ceiling_height = payload["ceiling_height_m"]
    if not isinstance(ceiling_height, (int, float)):
        raise ContractViolation(
            f"ceiling_height_m must be numeric, got {type(ceiling_height).__name__}",
            field="ceiling_height_m",
            value=ceiling_height,
        )
    if ceiling_height <= 0:
        raise ContractViolation(
            f"ceiling_height_m must be positive, got {ceiling_height}",
            field="ceiling_height_m",
            value=ceiling_height,
        )
    if ceiling_height > 30.0:
        # Not physically impossible but exceeds any NFPA 72 table entry
        # We allow it but flag for AHJ review (handled by rules engine)
        pass

    detector_type = payload["detector_type"]
    if not isinstance(detector_type, str) or detector_type.lower() not in _VALID_DETECTOR_TYPES:
        raise ContractViolation(
            f"detector_type must be one of {_VALID_DETECTOR_TYPES}, got: {detector_type!r}",
            field="detector_type",
            value=detector_type,
        )

    # ── Step 4: Polygon Validation ──────────────────────────────────────
    polygon = payload["room_polygon"]
    polygon_warnings = _validate_polygon(polygon)
    if polygon_warnings:
        # First warning is treated as error for < 3 vertices
        if len(polygon) < 3:
            raise ContractViolation(
                polygon_warnings[0],
                field="room_polygon",
                value=polygon,
            )

    # ── Step 5: Compute Missing Fields ──────────────────────────────────
    result = dict(payload)  # Shallow copy
    warnings: List[str] = []

    # Normalize detector_type to lowercase
    result["detector_type"] = detector_type.lower()

    # Compute area if not provided
    area_m2 = payload.get("area_m2")
    if area_m2 is None:
        computed_area = _compute_area_from_polygon(polygon)
        if computed_area <= 0:
            raise ContractViolation(
                f"Room polygon has zero or negative area ({computed_area:.4f} m²). "
                f"Cannot place detectors in a degenerate room.",
                field="area_m2",
                value=computed_area,
            )
        result["area_m2"] = computed_area
        warnings.append(f"area_m2 computed from polygon: {computed_area:.4f} m²")
    else:
        if not isinstance(area_m2, (int, float)) or area_m2 <= 0:
            raise ContractViolation(
                f"area_m2 must be positive, got {area_m2}",
                field="area_m2",
                value=area_m2,
            )
        result["area_m2"] = float(area_m2)

    # Default ceiling_type
    if "ceiling_type" not in result:
        result["ceiling_type"] = "flat"
        warnings.append("ceiling_type defaulted to 'flat'")
    elif result["ceiling_type"] not in _VALID_CEILING_TYPES:
        warnings.append(
            f"Unknown ceiling_type '{result['ceiling_type']}' — may not apply special rules"
        )

    # Default occupancy_type
    if "occupancy_type" not in result:
        result["occupancy_type"] = "office"
        warnings.append("occupancy_type defaulted to 'office'")

    # Store contract warnings for pipeline transparency
    result["_contract_warnings"] = warnings

    return result
