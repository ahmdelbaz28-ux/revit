"""marine/output/test_procedures.py — Factory Acceptance Test (FAT) procedures.

Generates test procedures for marine fire-detection and extinguishing systems
prior to installation on board.
"""
from __future__ import annotations

from typing import Dict, List

from marine.core.types import DetectorType, ExtinguishingSystem


FAT_PROCEDURES: Dict[str, List[Dict[str, str]]] = {
    "heat_fixed": [
        {"step": "1", "action": "Verify rated temperature marking (e.g. 54 °C / 78 °C)."},
        {"step": "2", "action": "Apply controlled heat source; confirm alarm within rated tolerance."},
        {"step": "3", "action": "Test self-test/fault reporting on the addressable loop."},
    ],
    "smoke_photo": [
        {"step": "1", "action": "Verify optical chamber cleanliness and LED status."},
        {"step": "2", "action": "Inject calibrated smoke aerosol; confirm alarm threshold."},
        {"step": "3", "action": "Confirm drift compensation and maintenance flag operation."},
    ],
    "flame_uv_ir": [
        {"step": "1", "action": "Verify UV/IR sensor windows are clean and undamaged."},
        {"step": "2", "action": "Expose to calibrated flame simulator; confirm alarm response."},
        {"step": "3", "action": "Confirm false-alarm rejection for sunlight / hot objects."},
    ],
    "water_mist": [
        {"step": "1", "action": "Hydrostatic test pump and piping to 1.5× design pressure."},
        {"step": "2", "action": "Verify nozzle spray pattern and droplet size (DV0.99 <1000 µm)."},
        {"step": "3", "action": "Test system discharge timing and control-valve operation."},
    ],
    "co2_total": [
        {"step": "1", "action": "Weigh CO2 cylinders and verify 100% charge."},
        {"step": "2", "action": "Pneumatically test release panel and time-delay circuit."},
        {"step": "3", "action": "Verify pre-discharge alarm and evacuation interlock."},
    ],
}


def generate_detector_fat(detector_types: List[DetectorType]) -> Dict[str, List[Dict[str, str]]]:
    """Return FAT procedures for the selected detector types."""
    result: Dict[str, List[Dict[str, str]]] = {}
    for dt in detector_types:
        result[dt.value] = FAT_PROCEDURES.get(dt.value, [
            {"step": "1", "action": f"Verify detector type {dt.value} per manufacturer data sheet."},
            {"step": "2", "action": "Confirm alarm and fault reporting on the addressable loop."},
        ])
    return result


def generate_extinguishing_fat(
    systems: List[ExtinguishingSystem],
) -> Dict[str, List[Dict[str, str]]]:
    """Return FAT procedures for the selected extinguishing systems."""
    result: Dict[str, List[Dict[str, str]]] = {}
    for sys in systems:
        result[sys.value] = FAT_PROCEDURES.get(sys.value, [
            {"step": "1", "action": f"Inspect system {sys.value} components and certifications."},
            {"step": "2", "action": "Test control-release circuit and safety interlocks."},
        ])
    return result


__all__ = [
    "FAT_PROCEDURES",
    "generate_detector_fat",
    "generate_extinguishing_fat",
]
