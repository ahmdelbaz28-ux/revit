"""
Zone Exporter for GeoGraph-compatible snapshots.

Takes translated elements and produces a CanonicalGeoSnapshot
in the exact JSON format expected by the Governance Engine and
the Standalone Verifier.
"""

import json
import hashlib
from typing import Dict, Any, List, Optional
from translator import (
    translate_element,
    classify_elements,
    canonicalize,
    CANONICAL_PRECISION,
)


def export_zone(
    zone_id: str,
    width: float,
    height: float,
    elements: List[Dict[str, Any]],
    ceiling_slope: float = 0.0,
) -> str:
    """
    Export a single zone (room) to a CanonicalGeoSnapshot JSON string.
    
    Args:
        zone_id: Unique identifier for the zone (e.g., "Room_101").
        width: Zone width in meters.
        height: Zone height in meters.
        elements: List of raw elements (before translation).
            Each element must have keys: family, x, y, id.
        ceiling_slope: Ceiling slope in degrees (0 = flat).
    
    Returns:
        JSON string of the CanonicalGeoSnapshot.
    """
    # Translate all elements
    translated = []
    unrecognized = []
    
    for elem in elements:
        try:
            t = translate_element(
                element_family=elem["family"],
                x=elem["x"],
                y=elem["y"],
                element_id=elem["id"],
                zone_id=zone_id,
                additional_props=elem.get("props"),
            )
            if t:
                translated.append(t)
        except ValueError as e:
            unrecognized.append(str(e))
    
    # If any unrecognized elements exist, fail the export
    if unrecognized:
        raise ValueError(
            f"Cannot export zone '{zone_id}'. Unrecognized elements:\n" +
            "\n".join(unrecognized)
        )
    
    # Classify elements
    classified = classify_elements(translated)
    
    # Warn if no detectors in zone
    if not classified["detectors"]:
        print(f"WARNING: Zone '{zone_id}' has no fire detectors!")
    
    # Build the snapshot
    snapshot: Dict[str, Any] = {
        "zone_id": zone_id,
        "width": canonicalize(width),
        "height": canonicalize(height),
        "ceiling_slope": canonicalize(ceiling_slope),
        "detectors": [
            {
                "id": d["id"],
                "x": d["x"],
                "y": d["y"],
            }
            for d in classified["detectors"]
        ],
        "obstacles": [
            {
                "x1": o.get("x1", o["x"]),
                "y1": o.get("y1", o["y"]),
                "x2": o.get("x2", o["x"]),
                "y2": o.get("y2", o["y"]),
                "is_solid_wall": o["is_solid_wall"],
            }
            for o in classified["obstacles"]
        ],
        "doors": [
            {
                "x1": d.get("x1", d["x"]),
                "y1": d.get("y1", d["y"]),
                "x2": d.get("x2", d["x"]),
                "y2": d.get("y2", d["y"]),
                "semantics": d.get("semantics", "FireDoor"),
            }
            for d in classified["doors"]
        ],
    }
    
    # Compute hash immediately for integrity
    snapshot_str = json.dumps(snapshot, sort_keys=True, separators=(',', ':'))
    geo_hash = hashlib.sha256(snapshot_str.encode('utf-8')).hexdigest()
    
    result = {
        "snapshot": snapshot,
        "geo_hash": geo_hash,
    }
    
    return json.dumps(result, sort_keys=True, separators=(',', ':'), indent=2)


# ============================================================
# Pre-submission Checks
# ============================================================
def validate_snapshot(snapshot_json: str) -> List[str]:
    """
    Validate a generated snapshot before submission.
    
    Returns:
        List of validation warnings/errors. Empty list means valid.
    """
    issues = []
    data = json.loads(snapshot_json)
    snap = data.get("snapshot", {})
    
    # Check all coordinates are rounded to precision
    for det in snap.get("detectors", []):
        if round(det["x"], CANONICAL_PRECISION) != det["x"]:
            issues.append(f"Detector {det['id']} x-coordinate not canonicalized: {det['x']}")
        if round(det["y"], CANONICAL_PRECISION) != det["y"]:
            issues.append(f"Detector {det['id']} y-coordinate not canonicalized: {det['y']}")
    
    # Check no empty zone without detectors
    if not snap.get("detectors"):
        issues.append(f"Zone '{snap.get('zone_id')}' has no detectors. Coverage may be insufficient.")
    return issues
