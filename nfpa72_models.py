"""
NFPA 72 Models — Canonical re-export module.

This file exists for backward compatibility with code that uses bare imports
like `from nfpa72_models import ...`.  It simply re-exports everything from
the canonical implementation at `fireai.core.nfpa72_models`.

⚠️  DO NOT add any logic or constants here — the single source of truth is
    `fireai/core/nfpa72_models.py`.  This file must remain a thin wrapper.

If you are writing NEW code, prefer the package import:
    from fireai.core.nfpa72_models import ...
"""

from fireai.core.nfpa72_models import *  # noqa: F401,F403
from fireai.core.nfpa72_models import (
    # Explicit re-exports for type-checkers and IDEs
    DetectorType,
    HeatDetectionMode,
    CeilingType,
    NFPAComplianceError,
    CeilingHeightError,
    CoverageError,
    SpacingError,
    RidgeZoneError,
    CeilingSpec,
    RoomSpec,
    SmokeDetectorSpec,
    HeatDetectorSpec,
    DetectorPlacement,
    CoverageResult,
    NFPAComplianceResult,
    FireAlarmPanel,
    PanelCapacityError,
    get_smoke_detector_radius,
    get_smoke_detector_radius_safe,
    get_smoke_detector_coverage_max,
    get_smoke_detector_coverage_max_safe,
    validate_ceiling_height,
    sanitize_string,
    logger,
)

__all__ = [
    "DetectorType",
    "HeatDetectionMode",
    "CeilingType",
    "NFPAComplianceError",
    "CeilingHeightError",
    "CoverageError",
    "SpacingError",
    "RidgeZoneError",
    "CeilingSpec",
    "RoomSpec",
    "SmokeDetectorSpec",
    "HeatDetectorSpec",
    "DetectorPlacement",
    "CoverageResult",
    "NFPAComplianceResult",
    "FireAlarmPanel",
    "PanelCapacityError",
    "get_smoke_detector_radius",
    "get_smoke_detector_radius_safe",
    "get_smoke_detector_coverage_max",
    "get_smoke_detector_coverage_max_safe",
    "validate_ceiling_height",
]
