"""
marine/lr_rules/fire_protection.py — Lloyd's Register Rules.
LR Rules Part 6: Fire Protection, Detection and Extinguishment.
Supplements SOLAS with stricter response times and loop limits.
"""
from __future__ import annotations

from marine.core.constants import (
    LR_FIRE_MAIN_REDUNDANCY,
    LR_MAX_DETECTOR_RESPONSE_S,
    LR_MAX_DETECTORS_PER_LOOP,
)
from marine.core.types import ComplianceResult


def validate_detector_response_time(actual_response_s: float) -> ComplianceResult:
    """LR: detector must respond within 30 s of fire start."""
    result = ComplianceResult(compliant=True, standard_reference="LR Part 6 §2.4")
    if actual_response_s > LR_MAX_DETECTOR_RESPONSE_S:
        result.add_finding(
            f"Detector response {actual_response_s:.1f}s exceeds LR max "
            f"{LR_MAX_DETECTOR_RESPONSE_S}s."
        )
    return result

def validate_loop_capacity(detectors_in_loop: int) -> ComplianceResult:
    """LR: max 200 detectors per addressable loop."""
    result = ComplianceResult(compliant=True, standard_reference="LR Part 6 §2.4")
    if detectors_in_loop > LR_MAX_DETECTORS_PER_LOOP:
        result.add_finding(
            f"Loop has {detectors_in_loop} detectors, exceeds LR max "
            f"{LR_MAX_DETECTORS_PER_LOOP}. Split into multiple loops."
        )
    return result

def validate_fire_main_redundancy(pump_count: int) -> ComplianceResult:
    """LR: ≥2 independent fire pumps required."""
    result = ComplianceResult(compliant=True, standard_reference="LR Part 6 §3.1")
    if pump_count < LR_FIRE_MAIN_REDUNDANCY:
        result.add_finding(
            f"Only {pump_count} fire pump(s) — LR requires ≥{LR_FIRE_MAIN_REDUNDANCY}."
        )
    return result

__all__ = [
    "validate_detector_response_time",
    "validate_fire_main_redundancy",
    "validate_loop_capacity",
]
