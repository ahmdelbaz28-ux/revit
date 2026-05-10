"""
Revit-to-GeoGraph Semantic Translator.

This module contains the STATIC mapping table and transformation logic
to convert Revit elements into GeoGraph-compatible JSON.

WARNING: The mapping table REVIT_TO_GEOGRAPH is FROZEN.
Any addition or modification requires governance process approval.
"""

import json
import hashlib
from typing import Dict, Any, List, Optional, Tuple

# ============================================================
# FROZEN STATIC MAPPING TABLE
# Do NOT modify without governance approval.
# ============================================================
REVIT_TO_GEOGRAPH: Dict[str, Dict[str, Any]] = {
    # --- Fire Alarm Devices ---
    "Fire_Smoke_Detector": {
        "node_type": "SmokeDetector",
    },
    "Fire_Heat_Detector": {
        "node_type": "HeatDetector",
    },
    "Fire_Alarm_Manual_Pull_Station": {
        "node_type": "ManualCallPoint",
    },
    "Fire_Alarm_Control_Panel": {
        "node_type": "Panel",
    },

    # --- Architectural Elements ---
    "Fire_Rated_Door": {
        "semantics": "FireDoor",
        "is_solid_wall": True,  # Blocks smoke propagation
    },
    "Solid_Wall_Full_Height": {
        "is_solid_wall": True,
    },
    "Partial_Wall": {
        "is_solid_wall": False,  # Doesn't block smoke at ceiling level
    },
}


# ============================================================
# Canonical Coordinate Rounding
# Ensures identical hashes across different CAD platforms.
# ============================================================
CANONICAL_PRECISION = 6


def canonicalize(value: float) -> float:
    """Round to 6 decimal places to prevent floating-point drift."""
    return round(value, CANONICAL_PRECISION)


# ============================================================
# Element Translation
# ============================================================
def translate_element(
    element_family: str,
    x: float,
    y: float,
    element_id: str,
    zone_id: str,
    additional_props: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Convert a Revit element to a GeoGraph-compatible dictionary.
    
    Args:
        element_family: The Revit family name (e.g., "Fire_Smoke_Detector").
        x, y: Canonicalized coordinates.
        element_id: Unique element identifier (from Revit ElementId).
        zone_id: The room/zone this element belongs to.
        additional_props: Any extra properties (e.g., door width).
    
    Returns:
        A dictionary representing the element, or None if the family
        is not recognized in REVIT_TO_GEOGRAPH.
    """
    if element_family not in REVIT_TO_GEOGRAPH:
        # Strict: Unrecognized elements halt the export
        raise ValueError(
            f"UNRECOGNIZED ELEMENT: '{element_family}' (ID: {element_id}). "
            "Cannot proceed with export. Add this family to REVIT_TO_GEOGRAPH "
            "via the governance process."
        )
    
    mapping = REVIT_TO_GEOGRAPH[element_family]
    result: Dict[str, Any] = {
        "id": element_id,
        "x": canonicalize(x),
        "y": canonicalize(y),
        "family": element_family,
    }
    
    # Merge mapped properties
    for key, value in mapping.items():
        result[key] = value
    
    # Merge any additional properties
    if additional_props:
        for key, value in additional_props.items():
            result[key] = canonicalize(value) if isinstance(value, float) else value
    
    return result


def classify_elements(elements: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Classify a list of translated elements into detectors, obstacles, and doors.
    
    Args:
        elements: List of dictionaries from translate_element().
    
    Returns:
        Dictionary with keys 'detectors', 'obstacles', 'doors'.
    """
    classified: Dict[str, List[Dict[str, Any]]] = {
        "detectors": [],
        "obstacles": [],
        "doors": [],
        "unclassified": [],
    }
    
    for elem in elements:
        node_type = elem.get("node_type")
        if node_type in ("SmokeDetector", "HeatDetector", "ManualCallPoint", "Panel"):
            classified["detectors"].append(elem)
        elif elem.get("is_solid_wall") is not None:
            if elem.get("semantics") == "FireDoor":
                classified["doors"].append(elem)
            else:
                classified["obstacles"].append(elem)
        else:
            classified["unclassified"].append(elem)
    
    return classified
