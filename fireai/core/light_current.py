"""fireai.core.light_current — QOMN-FIRE Light Current System Design
=================================================================

Deterministic engineering calculations for light current systems.

Standards:
- TIA-568.2-D: Commercial Building Telecommunications Cabling
- TIA-598: Optical Fiber Cable Color Coding
- TIA-569-E: Telecommunications Pathways and Spaces
- IEC 60268: Sound System Equipment
- IEC 60839: Alarm and Electronic Security Systems
- NFPA 101: Life Safety Code (egress requirements)
- NFPA 72 Ch.18: Emergency Communications

QOMN-FIRE Principles:
- Every formula cites standard section number
- Every constant cites table reference
- Every output includes computation hash
- Every error includes code reference and remediation
- Same input → same IEEE-754 bit-exact output, always
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Tuple

# ─── Contract Violation (reuse from contracts_validation if available) ────────


class ContractViolation(Exception):
    """Raised when input data violates the engineering contract."""

    def __init__(self, message: str, code_ref: str = ""):
        super().__init__(message)
        self.code_ref = code_ref


# ─── Enums ──────────────────────────────────────────────────────────────────


class CableType(Enum):
    """Structured cabling types per TIA-568."""

    CAT6 = "CAT6"
    CAT6A = "CAT6A"
    CAT7 = "CAT7"


class FiberType(Enum):
    """Fiber optic types per TIA-598."""

    OS1 = "OS1"
    OS2 = "OS2"
    OM3 = "OM3"
    OM4 = "OM4"


class EgressType(Enum):
    """Access control egress types per NFPA 101."""

    FAIL_SAFE = "fail_safe"
    FAIL_SECURE = "fail_secure"


# ─── QOMN-FIRE Layer 1 Reference Constants ──────────────────────────────────

# TIA-568 Cable Specifications
_CABLE_SPECS: dict[CableType, dict[str, Any]] = {
    CableType.CAT6: {
        "max_horizontal_m": 90.0,
        "max_total_m": 100.0,
        "diameter_mm": 6.0,
        "bend_radius_factor": 4,
        "standard_ref": "TIA-568.2-D",
    },
    CableType.CAT6A: {
        "max_horizontal_m": 90.0,
        "max_total_m": 100.0,
        "diameter_mm": 7.0,
        "bend_radius_factor": 4,
        "standard_ref": "TIA-568.2-D",
    },
    CableType.CAT7: {
        "max_horizontal_m": 90.0,
        "max_total_m": 100.0,
        "diameter_mm": 8.0,
        "bend_radius_factor": 4,
        "standard_ref": "TIA-568.2-D",
    },
}

_MIN_POWER_SEPARATION_MM = 300.0  # TIA-569-E

# TIA-598 Fiber Specifications
_FIBER_SPECS: dict[FiberType, dict[str, Any]] = {
    FiberType.OS1: {
        "max_length_m": 10000.0,
        "max_attenuation_db_km": 1.0,
        "wavelength_nm": 1310,
        "diameter_mm": 3.0,
        "bend_radius_factor": 10,
        "color_code": "yellow",
        "mode": "single-mode",
        "standard_ref": "TIA-598 / TIA-568.3-D",
    },
    FiberType.OS2: {
        "max_length_m": 10000.0,
        "max_attenuation_db_km": 1.0,
        "wavelength_nm": 1310,
        "diameter_mm": 3.0,
        "bend_radius_factor": 10,
        "color_code": "yellow",
        "mode": "single-mode",
        "standard_ref": "TIA-598 / TIA-568.3-D",
    },
    FiberType.OM3: {
        "max_length_m": 550.0,
        "max_attenuation_db_km": 3.5,
        "wavelength_nm": 850,
        "diameter_mm": 3.0,
        "bend_radius_factor": 10,
        "color_code": "aqua",
        "mode": "multimode",
        "standard_ref": "TIA-598 / TIA-568.3-D",
    },
    FiberType.OM4: {
        "max_length_m": 550.0,
        "max_attenuation_db_km": 3.0,
        "wavelength_nm": 850,
        "diameter_mm": 3.0,
        "bend_radius_factor": 10,
        "color_code": "magenta",
        "mode": "multimode",
        "standard_ref": "TIA-598 / TIA-568.3-D",
    },
}

# CCTV Lens Specifications
_LENS_COVERAGE = {
    3.6: 90.0,  # 3.6mm lens = 90° coverage
    6.0: 60.0,  # 6mm lens = 60° coverage
    12.0: 30.0,  # 12mm lens = 30° coverage
}

_MIN_CCTV_HEIGHT_M = 2.5  # Minimum height for facial recognition
_MAX_CCTV_HEIGHT_M = 3.5  # Maximum height for facial recognition
_MIN_LUX_COLOR = 50.0  # Minimum lux for color camera
_MIN_LUX_IR = 0.1  # Minimum lux for IR camera
_MIN_OVERLAP_PCT = 20.0  # Minimum overlap between adjacent cameras

# Access Control Specifications per NFPA 101 / ADA
_MIN_READER_HEIGHT_M = 1.07  # 42" AFF per ADA
_MAX_READER_HEIGHT_M = 1.22  # 48" AFF per ADA
_DEFAULT_READER_HEIGHT_M = 1.22  # 48" AFF (standard practice)


# ─── Frozen Result Dataclasses ──────────────────────────────────────────────


@dataclass(frozen=True)
class StructuredCablingResult:
    """Result of structured cabling validation per TIA-568."""

    max_horizontal_m: float
    max_total_m: float
    bend_radius_mm: float
    separation_mm: float
    cable_type: str
    is_compliant: bool
    violations: Tuple[str, ...] = ()
    standard_ref: str = "TIA-568.2-D"
    computation_hash: str = ""

    def __post_init__(self):
        if self.computation_hash == "":
            raw = f"{self.max_horizontal_m}|{self.max_total_m}|{self.cable_type}|{self.is_compliant}"
            object.__setattr__(self, "computation_hash", hashlib.sha256(raw.encode()).hexdigest()[:32])


@dataclass(frozen=True)
class FiberOpticResult:
    """Result of fiber optic link validation per TIA-598."""

    fiber_type: str
    max_length_m: float
    max_attenuation_db_km: float
    wavelength_nm: int
    bend_radius_mm: float
    color_code: str
    is_compliant: bool
    total_attenuation_db: float = 0.0
    violations: Tuple[str, ...] = ()
    standard_ref: str = "TIA-598 / TIA-568.3-D"
    computation_hash: str = ""

    def __post_init__(self):
        if self.computation_hash == "":
            raw = f"{self.fiber_type}|{self.max_length_m}|{self.is_compliant}|{self.total_attenuation_db}"
            object.__setattr__(self, "computation_hash", hashlib.sha256(raw.encode()).hexdigest()[:32])


@dataclass(frozen=True)
class CCTVResult:
    """Result of CCTV camera coverage calculation."""

    camera_count: int
    lens_mm: float
    coverage_angle_deg: float
    height_m: float
    overlap_pct: float
    is_compliant: bool
    violations: Tuple[str, ...] = ()
    standard_ref: str = "Project Specification / IEC 62676"
    computation_hash: str = ""

    def __post_init__(self):
        if self.computation_hash == "":
            raw = f"{self.camera_count}|{self.lens_mm}|{self.height_m}|{self.is_compliant}"
            object.__setattr__(self, "computation_hash", hashlib.sha256(raw.encode()).hexdigest()[:32])


@dataclass(frozen=True)
class AccessControlResult:
    """Result of access control validation per NFPA 101 / ADA."""

    reader_height_m: float
    egress_type: str
    has_door_switch: bool
    has_rte: bool
    is_compliant: bool
    violations: Tuple[str, ...] = ()
    standard_ref: str = "NFPA 101 §7.2.1.6 / ADA"
    computation_hash: str = ""

    def __post_init__(self):
        if self.computation_hash == "":
            raw = f"{self.reader_height_m}|{self.egress_type}|{self.has_door_switch}|{self.has_rte}|{self.is_compliant}"
            object.__setattr__(self, "computation_hash", hashlib.sha256(raw.encode()).hexdigest()[:32])


# ─── Input Validation Helpers ───────────────────────────────────────────────


def _validate_finite(value: float, name: str) -> None:
    """Validate that a value is finite (not NaN or Inf)."""
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractViolation(
            f"{name} = {value!r} is not a finite number — QOMN-FIRE Layer 0 rejects NaN/Inf inputs.",
            code_ref="IEEE-754 / QOMN-FIRE L0",
        )


def _validate_positive(value: float, name: str, code_ref: str = "") -> None:
    """Validate that a value is positive and finite."""
    _validate_finite(value, name)
    if value <= 0:
        raise ContractViolation(
            f"{name} = {value} must be positive. Physically impossible negative or zero value.",
            code_ref=code_ref,
        )


# ─── Structured Cabling ────────────────────────────────────────────────────


def validate_horizontal_cable(
    length_m: float,
    cable_type: CableType = CableType.CAT6,
    patch_cord_m: float = 5.0,
) -> StructuredCablingResult:
    """Validate horizontal cabling run per TIA-568.2-D.

    TIA-568 Rules:
    - Maximum horizontal cable: 90m
    - Maximum total channel: 100m (including patch cords)
    - Bend radius: 4 × cable diameter minimum
    - Separation from power: 300mm minimum (TIA-569-E)

    Args:
        length_m: Horizontal cable length in meters.
        cable_type: Cable type (CAT6, CAT6A, CAT7).
        patch_cord_m: Total patch cord length in meters (default 5.0m).

    Returns:
        StructuredCablingResult with compliance status.

    Raises:
        ContractViolation: If inputs are invalid (NaN/Inf, negative).

    """
    _validate_positive(length_m, "length_m", "TIA-568.2-D")
    _validate_positive(patch_cord_m, "patch_cord_m", "TIA-568.2-D")

    spec = _CABLE_SPECS[cable_type]
    total_m = length_m + patch_cord_m
    bend_radius_mm = spec["diameter_mm"] * spec["bend_radius_factor"]

    violations = []
    is_compliant = True

    if length_m > spec["max_horizontal_m"]:
        violations.append(
            f"Horizontal length {length_m:.1f}m exceeds maximum {spec['max_horizontal_m']}m per {spec['standard_ref']}"
        )
        is_compliant = False

    if total_m > spec["max_total_m"]:
        violations.append(
            f"Total channel length {total_m:.1f}m exceeds maximum {spec['max_total_m']}m per {spec['standard_ref']}"
        )
        is_compliant = False

    return StructuredCablingResult(
        max_horizontal_m=spec["max_horizontal_m"],
        max_total_m=spec["max_total_m"],
        bend_radius_mm=bend_radius_mm,
        separation_mm=_MIN_POWER_SEPARATION_MM,
        cable_type=cable_type.value,
        is_compliant=is_compliant,
        violations=tuple(violations),
        standard_ref=spec["standard_ref"],
    )


# ─── Fiber Optic ────────────────────────────────────────────────────────────


def validate_fiber_link(
    length_m: float,
    fiber_type: FiberType = FiberType.OM3,
    attenuation_margin_db: float = 3.0,
) -> FiberOpticResult:
    """Validate fiber optic link per TIA-598 / TIA-568.3-D.

    TIA-598 Rules:
    - OS1/OS2: max 1.0 dB/km at 1310nm
    - OM3: max 550m at 10Gbps, 3.5 dB/km at 850nm
    - OM4: max 550m at 10Gbps, 3.0 dB/km at 850nm
    - Bend radius: 10 × cable diameter minimum
    - Color code: yellow=single-mode, aqua=OM3, magenta=OM4

    Args:
        length_m: Fiber link length in meters.
        fiber_type: Fiber type (OS1, OS2, OM3, OM4).
        attenuation_margin_db: Safety margin in dB (default 3.0).

    Returns:
        FiberOpticResult with compliance status.

    Raises:
        ContractViolation: If inputs are invalid (NaN/Inf, negative).

    """
    _validate_positive(length_m, "length_m", "TIA-598")
    _validate_finite(attenuation_margin_db, "attenuation_margin_db")
    if attenuation_margin_db < 0:
        raise ContractViolation(
            f"attenuation_margin_db = {attenuation_margin_db} must be non-negative.",
            code_ref="TIA-598",
        )

    spec = _FIBER_SPECS[fiber_type]
    total_attenuation = (length_m / 1000.0) * spec["max_attenuation_db_km"]
    bend_radius_mm = spec["diameter_mm"] * spec["bend_radius_factor"]

    violations = []
    is_compliant = True

    if length_m > spec["max_length_m"]:
        violations.append(
            f"Fiber length {length_m:.1f}m exceeds maximum {spec['max_length_m']}m "
            f"for {fiber_type.value} per {spec['standard_ref']}"
        )
        is_compliant = False

    if total_attenuation + attenuation_margin_db > 20.0:
        violations.append(
            f"Total attenuation {total_attenuation:.2f}dB + margin {attenuation_margin_db}dB "
            f"exceeds typical link budget. Per {spec['standard_ref']}"
        )
        is_compliant = False

    return FiberOpticResult(
        fiber_type=fiber_type.value,
        max_length_m=spec["max_length_m"],
        max_attenuation_db_km=spec["max_attenuation_db_km"],
        wavelength_nm=spec["wavelength_nm"],
        bend_radius_mm=bend_radius_mm,
        color_code=spec["color_code"],
        is_compliant=is_compliant,
        total_attenuation_db=round(total_attenuation, 4),
        violations=tuple(violations),
        standard_ref=spec["standard_ref"],
    )


# ─── CCTV ────────────────────────────────────────────────────────────────────


def calculate_cctv_coverage(
    room_length_m: float,
    room_width_m: float,
    lens_mm: float = 3.6,
    height_m: float = 3.0,
    min_overlap_pct: float = 20.0,
) -> CCTVResult:
    """Calculate CCTV camera coverage for a room.

    Rules:
    - Height: 2.5m-3.5m for facial recognition
    - Coverage angle by lens: 3.6mm=90°, 6mm=60°, 12mm=30°
    - Overlap: 20% minimum between adjacent cameras
    - Lighting: 50 lux minimum for color, 0.1 lux for IR

    Args:
        room_length_m: Room length in meters.
        room_width_m: Room width in meters.
        lens_mm: Lens focal length in mm (3.6, 6.0, or 12.0).
        height_m: Camera mounting height in meters.
        min_overlap_pct: Minimum overlap between cameras (default 20%).

    Returns:
        CCTVResult with camera count and compliance status.

    Raises:
        ContractViolation: If inputs are invalid.

    """
    _validate_positive(room_length_m, "room_length_m", "IEC 62676")
    _validate_positive(room_width_m, "room_width_m", "IEC 62676")
    _validate_positive(height_m, "height_m", "IEC 62676")
    _validate_finite(lens_mm, "lens_mm")
    _validate_finite(min_overlap_pct, "min_overlap_pct")

    # Get coverage angle (default to 90° for unknown lens)
    coverage_angle = _LENS_COVERAGE.get(lens_mm, 90.0)

    # Calculate effective coverage width at camera height
    # Using tangent for half-angle: coverage_width = 2 × height × tan(angle/2)
    half_angle_rad = math.radians(coverage_angle / 2.0)
    coverage_width = 2.0 * height_m * math.tan(half_angle_rad)

    # Account for overlap: effective coverage = coverage × (1 - overlap/100)
    effective_coverage = coverage_width * (1.0 - min_overlap_pct / 100.0)
    if effective_coverage <= 0:
        effective_coverage = coverage_width  # Fallback

    # Calculate camera count
    cameras_along_length = max(1, math.ceil(room_length_m / effective_coverage)) if effective_coverage > 0 else 1
    cameras_along_width = max(1, math.ceil(room_width_m / effective_coverage)) if effective_coverage > 0 else 1
    camera_count = cameras_along_length * cameras_along_width

    # Validate height
    violations = []
    is_compliant = True

    if height_m < _MIN_CCTV_HEIGHT_M:
        violations.append(
            f"Camera height {height_m:.1f}m is below minimum {_MIN_CCTV_HEIGHT_M}m for facial recognition per IEC 62676"
        )
        is_compliant = False
    if height_m > _MAX_CCTV_HEIGHT_M:
        violations.append(
            f"Camera height {height_m:.1f}m exceeds maximum {_MAX_CCTV_HEIGHT_M}m for facial recognition per IEC 62676"
        )
        is_compliant = False

    return CCTVResult(
        camera_count=camera_count,
        lens_mm=lens_mm,
        coverage_angle_deg=coverage_angle,
        height_m=height_m,
        overlap_pct=min_overlap_pct,
        is_compliant=is_compliant,
        violations=tuple(violations),
    )


# ─── Access Control ──────────────────────────────────────────────────────────


def validate_access_control(
    reader_height_m: float = 1.22,
    # V114 FIX: Fail-safe — door monitoring and RTE must be confirmed, not assumed
    has_door_switch: bool = False,
    has_rte: bool = False,
    egress_type: str = "fail_safe",
) -> AccessControlResult:
    """Validate access control installation per NFPA 101 / ADA.

    NFPA 101 Rules:
    - Free egress required per §7.2.1.6
    - Fail-safe locks must release on power failure
    - Door position switch: monitor door status
    - Request-to-exit: motion sensor or push button

    ADA Rules:
    - Reader height: 42"-48" AFF (1.07m-1.22m)

    Args:
        reader_height_m: Card reader height in meters (default 1.22m / 48" AFF).
        has_door_switch: Whether door has position switch (default True).
        has_rte: Whether door has request-to-exit (default True).
        egress_type: Lock type ("fail_safe" or "fail_secure").

    Returns:
        AccessControlResult with compliance status.

    Raises:
        ContractViolation: If inputs are invalid.

    """
    _validate_finite(reader_height_m, "reader_height_m")

    violations = []
    is_compliant = True

    # Reader height check per ADA
    if reader_height_m < _MIN_READER_HEIGHT_M or reader_height_m > _MAX_READER_HEIGHT_M:
        violations.append(
            f"Reader height {reader_height_m:.2f}m is outside ADA range "
            f'{_MIN_READER_HEIGHT_M}m-{_MAX_READER_HEIGHT_M}m (42"-48" AFF)'
        )
        is_compliant = False

    # Egress type check per NFPA 101 §7.2.1.6
    if egress_type not in ("fail_safe", "fail_secure"):
        violations.append(
            f"Egress type '{egress_type}' is not recognized. Must be 'fail_safe' or 'fail_secure' per NFPA 101 §7.2.1.6"
        )
        is_compliant = False

    # Fail-secure on egress doors violates NFPA 101
    if egress_type == "fail_secure":
        violations.append(
            "Fail-secure locks on egress doors violate NFPA 101 §7.2.1.6 — "
            "doors must unlock upon power failure for free egress"
        )
        is_compliant = False

    # Door position switch check
    if not has_door_switch:
        violations.append(
            "Door position switch missing — NFPA 72 requires door monitoring "
            "for access-controlled egress doors per §21.9.2"
        )
        is_compliant = False

    # Request-to-exit check
    if not has_rte:
        violations.append(
            "Request-to-exit missing — NFPA 101 §7.2.1.6 requires "
            "a means to exit without credentials (motion sensor or push button)"
        )
        is_compliant = False

    return AccessControlResult(
        reader_height_m=reader_height_m,
        egress_type=egress_type,
        has_door_switch=has_door_switch,
        has_rte=has_rte,
        is_compliant=is_compliant,
        violations=tuple(violations),
    )
