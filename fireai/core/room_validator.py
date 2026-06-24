"""Room Validator - Strict validation for FireAI V10
Validates RoomSpec before analysis to prevent crashes and ensure data integrity.
"""

from __future__ import annotations

from typing import Set

from .nfpa72_models import RoomSpec

# Known occupancy types per NFPA 72
# V20.2 FIX: Removed "kitchen" and "assembly" — these are DANGEROUS types
# that require licensed FPE review per nfpa72_models.py. Having them here
# created an inconsistency: room_validator accepted them but RoomSpec
# construction would reject them. Kitchen requires heat detectors (not smoke)
# per NFPA 72 §17.6.4. Assembly requires special occupant load calculations.
VALID_OCCUPANCY_TYPES: Set[str] = {
    "business",
    "educational",
    "factory",
    "hazardous",
    "institutional",
    "mercantile",
    "residential",
    "storage",
    "utility",
    # Common variants
    "office",
    "corridor",
    "atrium",
    "sleeping",
    "living",
    "bathroom",
    "mechanical",
    "electrical",
    "data_center",
    "laboratory",
}


def validate_room_spec(room_spec: RoomSpec) -> None:
    """Validate RoomSpec before analysis.

    Args:
        room_spec: RoomSpec to validate
    Raises:
        ValueError: If validation fails

    """
    errors = []

    # a. Check polygon exists and has >= 3 points
    if room_spec.polygon is None:
        errors.append("polygon is None - polygon is required")
    else:
        if hasattr(room_spec.polygon, "exterior"):
            coords = list(room_spec.polygon.exterior.coords)
            if len(coords) < 4:  # Need at least 3 points + closing point
                errors.append(f"polygon has only {len(coords) - 1} points - need at least 3")
        else:
            errors.append("polygon is not a valid Shapely Polygon")

    # b. Check polygon area > 0
    if room_spec.polygon is not None:
        try:
            area = room_spec.polygon.area
            if area <= 0:
                errors.append(f"polygon area is {area}m² - must be > 0")
        except Exception as e:
            errors.append(f"cannot calculate polygon area: {e}")

    # c. Check width and depth > 0 (if provided)
    if hasattr(room_spec, "width_m") and room_spec.width_m is not None:
        if room_spec.width_m <= 0:
            errors.append(f"width_m is {room_spec.width_m} - must be > 0")

    if hasattr(room_spec, "depth_m") and room_spec.depth_m is not None:
        if room_spec.depth_m <= 0:
            errors.append(f"depth_m is {room_spec.depth_m} - must be > 0")

    # d. Check occupancy_type is valid
    if not room_spec.occupancy_type:
        errors.append("occupancy_type is empty or None")
    elif room_spec.occupancy_type.lower() not in VALID_OCCUPANCY_TYPES:
        errors.append(
            f"occupancy_type '{room_spec.occupancy_type}' is not recognized. Valid types: {sorted(VALID_OCCUPANCY_TYPES)}"
        )

    # e. Check room_id is not empty
    if not room_spec.room_id:
        errors.append("room_id is empty or None")

    # Raise if any errors
    if errors:
        raise ValueError(f"Room validation failed for '{room_spec.room_id}': " + "; ".join(errors))
