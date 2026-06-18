"""marine/integration/revit_exporter.py — Revit Family + Model Generator.
Generates .rfa family definitions and .rvt model placements for marine
detectors, nozzles, alarm horns, and fire divisions."""
from __future__ import annotations
import json
from typing import List
from marine.core.types import DetectorPlacement, FireResistanceSpec


def generate_revit_family(detector: DetectorPlacement) -> dict:
    """Return a Revit family definition (JSON-serializable for OFP)."""
    return {
        "family_name": f"Marine_{detector.detector_type.value}",
        "category": "Fire Alarm Devices",
        "parameters": [
            {"name": "Detector_ID", "type": "Text", "value": detector.detector_id},
            {"name": "Zone_ID", "type": "Text", "value": detector.zone_id},
            {"name": "Coverage_m2", "type": "Number", "value": detector.coverage_m2},
            {"name": "Mounting_Height_m", "type": "Number", "value": detector.mounting_height_m},
            {"name": "Rated_Temp_C", "type": "Number", "value": detector.rated_temp_c or 0},
            {"name": "Standard", "type": "Text", "value": detector.standard_reference},
        ],
        "geometry": {
            "type": "cylinder", "diameter_mm": 100, "height_mm": 50,
        },
        "lod": 300,
    }


def generate_revit_placement(detector: DetectorPlacement) -> dict:
    """Return a Revit placement instance (positioned in model coordinates)."""
    return {
        "family_name": f"Marine_{detector.detector_type.value}",
        "instance_id": detector.detector_id,
        "position_xyz_mm": list(detector.position_xyz_mm),
        "rotation_deg": 0,
    }


def generate_revit_division(spec: FireResistanceSpec) -> dict:
    """Return a Revit wall/floor element for a fire division."""
    return {
        "element_id": spec.division_id,
        "type": "Fire_Rated_Bulkhead" if spec.required_class.value.startswith("A-") else "Non_Combustible_Panel",
        "from_zone": spec.from_zone, "to_zone": spec.to_zone,
        "fire_class": spec.required_class.value,
        "material": spec.material,
        "insulation_material": spec.insulation_material or "none",
        "insulation_thickness_mm": spec.insulation_thickness_mm,
        "standard": spec.standard_reference,
    }


__all__ = [
    "generate_revit_family", "generate_revit_placement", "generate_revit_division",
]
