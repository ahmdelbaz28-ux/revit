"""
marine/output/commissioning_checklist.py — Shipboard commissioning checklist.

Generates a structured checklist for commissioning marine fire-detection,
alarm, and extinguishing systems after installation on board.
"""
from __future__ import annotations

from marine.core.types import DetectorType, ExtinguishingSystem

COMMISSIONING_ITEMS: list[dict[str, str]] = [
    {
        "id": "C-01",
        "category": "Documentation",
        "item": "Verify approved fire plan and as-built drawings are on board.",
        "acceptance_criteria": "Stamped drawings available in ship safety centre.",
    },
    {
        "id": "C-02",
        "category": "Power",
        "item": "Verify main, emergency, and UPS supply to fire-detection system.",
        "acceptance_criteria": "≥30 min UPS autonomy demonstrated (SOLAS II-2/5.1.3).",
    },
    {
        "id": "C-03",
        "category": "Detection",
        "item": "Walk-test 100% of detectors; confirm loop continuity and addressing.",
        "acceptance_criteria": "No open/short circuits; all devices respond to test.",
    },
    {
        "id": "C-04",
        "category": "Alarm",
        "item": "Trigger general alarm from each detector zone.",
        "acceptance_criteria": "Alarm audible on all decks and visible on mimic panel.",
    },
    {
        "id": "C-05",
        "category": "Extinguishing",
        "item": "Function-test release panels and pre-discharge alarms.",
        "acceptance_criteria": "Time delay, abort, and manual release operate correctly.",
    },
    {
        "id": "C-06",
        "category": "Escape Routes",
        "item": "Verify escape route markings and low-location lighting.",
        "acceptance_criteria": "Markings visible in darkness; routes unobstructed.",
    },
    {
        "id": "C-07",
        "category": "Fire Divisions",
        "item": "Inspect A-class and B-class penetrations and seals.",
        "acceptance_criteria": "All cable/pipe transits fire-stopped to required class.",
    },
]


def generate_commissioning_checklist(
    detector_types: list[DetectorType] | None = None,
    extinguishing_systems: list[ExtinguishingSystem] | None = None,
) -> list[dict[str, str]]:
    """Return a commissioning checklist, optionally tailored to the systems."""
    checklist = list(COMMISSIONING_ITEMS)
    if detector_types:
        for dt in detector_types:
            checklist.append({
                "id": f"C-DET-{dt.value.upper()}",
                "category": "Detection",
                "item": f"Commission and calibrate {dt.value} detectors.",
                "acceptance_criteria": "Factory calibration certificate on file.",
            })
    if extinguishing_systems:
        for sys in extinguishing_systems:
            checklist.append({
                "id": f"C-EXT-{sys.value.upper()}",
                "category": "Extinguishing",
                "item": f"Commission {sys.value} system and verify discharge simulation.",
                "acceptance_criteria": "System discharges within design time with no leaks.",
            })
    return checklist


__all__ = [
    "COMMISSIONING_ITEMS",
    "generate_commissioning_checklist",
]
