"""
Tests for the Revit-to-GeoGraph translator.

These tests verify:
1. Static mapping table integrity.
2. Coordinate canonicalization.
3. Full export pipeline.
4. Unrecognized element rejection.
"""

import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from translator import (
    REVIT_TO_GEOGRAPH,
    translate_element,
    classify_elements,
    canonicalize,
)
from exporter import export_zone, validate_snapshot


def test_canonicalize():
    """Verify canonical rounding."""
    assert canonicalize(5.0000000001) == 5.0
    assert canonicalize(5.9999999999) == 6.0
    assert canonicalize(3.1415926535) == 3.141593


def test_translate_known_element():
    """Verify a known element translates correctly."""
    result = translate_element(
        element_family="Fire_Smoke_Detector",
        x=5.0000000001,
        y=3.2,
        element_id="DET_01",
        zone_id="Zone_101",
    )
    assert result is not None
    assert result["id"] == "DET_01"
    assert result["x"] == 5.0  # Canonicalized
    assert result["y"] == 3.2
    assert result["node_type"] == "SmokeDetector"


def test_translate_unrecognized_element():
    """Verify an unrecognized element raises ValueError."""
    try:
        translate_element(
            element_family="Mystery_Device",
            x=1.0,
            y=2.0,
            element_id="UNKNOWN_01",
            zone_id="Zone_101",
        )
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "UNRECOGNIZED ELEMENT" in str(e)
        assert "Mystery_Device" in str(e)


def test_classify_elements():
    """Verify element classification."""
    elements = [
        {"id": "D1", "x": 1.0, "y": 2.0, "family": "Fire_Smoke_Detector", "node_type": "SmokeDetector"},
        {"id": "W1", "x": 3.0, "y": 0.0, "family": "Solid_Wall_Full_Height", "is_solid_wall": True},
        {"id": "DR1", "x": 3.0, "y": 5.0, "family": "Fire_Rated_Door", "is_solid_wall": True, "semantics": "FireDoor"},
    ]
    classified = classify_elements(elements)
    assert len(classified["detectors"]) == 1
    assert len(classified["obstacles"]) == 1
    assert len(classified["doors"]) == 1
    assert len(classified["unclassified"]) == 0


def test_export_zone():
    """Verify full export pipeline produces valid JSON."""
    elements = [
        {"family": "Fire_Smoke_Detector", "x": 3.0, "y": 4.0, "id": "DET_A"},
        {"family": "Fire_Smoke_Detector", "x": 7.0, "y": 4.0, "id": "DET_B"},
        {"family": "Solid_Wall_Full_Height", "x": 5.0, "y": 0.0, "id": "WALL_01",
         "props": {"x1": 5.0, "y1": 0.0, "x2": 5.0, "y2": 10.0}},
    ]
    
    result_json = export_zone(
        zone_id="Zone_101",
        width=10.0,
        height=10.0,
        elements=elements,
        source_file_path=None,
    )
    
    data = json.loads(result_json)
    snap = data["snapshot"]
    
    assert snap["zone_id"] == "Zone_101"
    assert len(snap["detectors"]) == 2
    assert len(snap["obstacles"]) == 1
    assert "geo_hash" in data
    assert len(data["geo_hash"]) == 64  # SHA256 hex length


def test_export_rejects_unrecognized():
    """Verify export stops on unrecognized elements."""
    elements = [
        {"family": "Fire_Smoke_Detector", "x": 3.0, "y": 4.0, "id": "DET_A"},
        {"family": "Alien_Device", "x": 1.0, "y": 1.0, "id": "ALIEN_01"},
    ]
    try:
        export_zone("Zone_X", 10.0, 10.0, elements)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unrecognized elements" in str(e)
        assert "Alien_Device" in str(e)


def test_validate_snapshot():
    """Verify snapshot validation catches issues."""
    # Valid snapshot
    elements = [
        {"family": "Fire_Smoke_Detector", "x": 3.0, "y": 4.0, "id": "DET_A"},
    ]
    result_json = export_zone("Zone_OK", 10.0, 10.0, elements)
    issues = validate_snapshot(result_json)
    assert len(issues) == 0, f"Expected 0 issues, got: {issues}"


def test_source_file_hash_present():
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.rvt') as f:
        f.write("Dummy Revit file content")
        temp_path = f.name
    try:
        elements = [{"family": "Fire_Smoke_Detector", "x": 3.0, "y": 4.0, "id": "DET_A"}]
        result_json = export_zone("Zone_Test", 10.0, 10.0, elements, source_file_path=temp_path)
        data = json.loads(result_json)
        assert "source_file_hash" in data
        assert len(data["source_file_hash"]) == 64
        assert data["source_file_hash"] != "FILE_NOT_FOUND"
    finally:
        os.unlink(temp_path)


if __name__ == "__main__":
    # Run all tests manually
    tests = [
        test_canonicalize,
        test_translate_known_element,
        test_translate_unrecognized_element,
        test_classify_elements,
        test_export_zone,
        test_export_rejects_unrecognized,
        test_validate_snapshot,
        test_source_file_hash_present,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            print(f"✅ {test.__name__} passed")
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {test.__name__} ERROR: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*50}")
    
    if failed > 0:
        sys.exit(1)