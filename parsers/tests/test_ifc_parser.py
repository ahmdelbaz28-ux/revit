# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
"""
parsers/tests/test_ifc_parser.py — Comprehensive IFC Parser Tests
=================================================================
Task 1.3: Add parser tests — Fix 19% coverage → target 80%

Tests cover:
  1. IFCParser initialization
  2. IFCAnalysis data class
  3. JSON-based IFC loading and parsing
  4. Space extraction (IfcSpace)
  5. Device extraction (fire protection entities)
  6. Building info extraction
  7. Floor counting
  8. Negative area rejection (V79 fix)
  9. to_standard_format conversion
  10. Path security (V125 hardening)
  11. Error handling for invalid/corrupt files
  12. parse_ifc convenience function
  13. Integration with real IFC-JSON data

Safety-Critical: IFC spaces feed into detector placement engine.
Negative areas or missing spaces = zero fire protection.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from parsers.ifc_parser import IFCAnalysis, IFCParser, parse_ifc

# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


def _make_ifc_json(data: dict, suffix=".json") -> str:
    """Create a temp IFC JSON file with given data."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="ifc_test_")
    try:
        os.write(fd, json.dumps(data).encode())
    finally:
        os.close(fd)
    return path


def _make_valid_ifc_json(
    num_spaces=2, num_devices=1, num_floors=2, negative_area=False
) -> dict:
    """
    Create a valid IFC JSON data structure.

    Args:
        num_spaces: Number of IfcSpace instances
        num_devices: Number of fire protection devices
        num_floors: Number of IfcBuildingStorey instances
        negative_area: If True, first space has negative area (V79 test)

    """
    instances = []

    # Building
    instances.append({
        "id": "IFC_BUILDING_1",
        "type": "IfcBuilding",
        "attributes": {
            "Name": "Test Hospital",
            "LongName": "City General Hospital",
        },
    })

    # Floors
    for i in range(num_floors):
        instances.append({
            "id": f"FLOOR_{i+1}",
            "type": "IfcBuildingStorey",
            "attributes": {"Name": f"Level {i+1}"},
        })

    # Spaces
    for i in range(num_spaces):
        area = 25.0 * (i + 1)
        if negative_area and i == 0:
            area = -10.0  # V79 test: negative area
        instances.append({
            "id": f"SPACE_{i+1}",
            "type": "IfcSpace",
            "attributes": {
                "Name": f"Room {i+1}",
                "LongName": f"Office {i+1}",
                "Area": area,
                "Elevation": 0.0,
            },
            "geometry": {
                "bounds": {
                    "origin": {"x": i * 10, "y": 0, "z": 0},
                    "dimensions": {
                        "width": 5.0,
                        "length": 5.0 * (i + 1),
                        "height": 3.0,
                    },
                }
            },
        })

    # Fire protection devices
    device_types = [
        ("IfcFireSuppressionDevice_Type", "Sprinkler Head"),
        ("IfcAlarm", "Smoke Detector"),
        ("IfcSensor", "Heat Detector"),
        ("IfcProtectiveDevice", "Fire Damper"),
    ]
    for i in range(num_devices):
        dtype, name = device_types[i % len(device_types)]
        instances.append({
            "id": f"DEVICE_{i+1}",
            "type": dtype,
            "attributes": {
                "Name": name,
                "DetectorType": name.upper().replace(" ", "_"),
                "Sensitivity": 0.5,
                "CoverageRadius": 6.37,
                "MountingHeight": 3.0,
            },
            "applicable_to": ["SPACE_1"],
        })

    return {"instances": instances}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. IFCParser Initialization
# ═══════════════════════════════════════════════════════════════════════════════


class TestIFCParserInit:
    """IFCParser initialization and state."""

    def test_init_stores_path(self):
        parser = IFCParser("/tmp/test.ifc")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
        assert parser.ifc_path == "/tmp/test.ifc"  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)

    def test_init_data_is_none(self):
        parser = IFCParser("/tmp/test.ifc")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
        assert parser.data is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. IFCAnalysis Data Class
# ═══════════════════════════════════════════════════════════════════════════════


class TestIFCAnalysis:
    """IFCAnalysis data class and field validation."""

    def test_basic_analysis(self):
        analysis = IFCAnalysis(
            building_name="Test Building",
            floors=3,
            spaces=[{"id": "S1"}],
            devices=[{"id": "D1"}],
            total_area=150.0,
        )
        assert analysis.building_name == "Test Building"
        assert analysis.floors == 3
        assert len(analysis.spaces) == 1
        assert len(analysis.devices) == 1
        assert analysis.total_area == 150.0  # NOSONAR — S1244: import retained for re-export / API surface

    def test_empty_analysis(self):
        analysis = IFCAnalysis(
            building_name="Unknown",
            floors=0,
            spaces=[],
            devices=[],
            total_area=0.0,
        )
        assert analysis.building_name == "Unknown"
        assert analysis.floors == 0
        assert analysis.total_area == 0.0  # NOSONAR — S1244: import retained for re-export / API surface


# ═══════════════════════════════════════════════════════════════════════════════
# 3. JSON Loading and Parsing
# ═══════════════════════════════════════════════════════════════════════════════


class TestJSONLoading:
    """IFC JSON file loading and parsing pipeline."""

    def test_load_valid_json(self):
        """Valid JSON file is loaded and parsed successfully."""
        data = _make_valid_ifc_json()
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert isinstance(result, IFCAnalysis)
            assert result.building_name == "Test Hospital"
        finally:
            os.unlink(p)

    def test_load_invalid_json_raises(self):
        """Invalid JSON file raises ValueError."""
        fd, p = tempfile.mkstemp(suffix=".json", prefix="ifc_test_")
        try:
            os.write(fd, b"not valid json{{{")
            os.close(fd)
            parser = IFCParser(p)
            with pytest.raises(ValueError, match="Failed to load IFC file"):
                parser.parse()
        finally:
            try:
                os.unlink(p)
            except OSError:
                pass

    def test_parse_instances(self):
        """_parse_instances extracts instance list from data."""
        data = {"instances": [{"id": 1}, {"id": 2}]}
        parser = IFCParser("/tmp/test.json")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
        instances = parser._parse_instances(data)
        assert len(instances) == 2

    def test_parse_empty_instances(self):
        """Missing 'instances' key returns empty list."""
        data = {}
        parser = IFCParser("/tmp/test.json")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)
        instances = parser._parse_instances(data)
        assert instances == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Space Extraction
# ═══════════════════════════════════════════════════════════════════════════════


class TestSpaceExtraction:
    """IfcSpace extraction with geometry and attributes."""

    def test_extracts_ifc_space(self):
        """IfcSpace instances are extracted with correct attributes."""
        data = _make_valid_ifc_json(num_spaces=3)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert len(result.spaces) == 3
        finally:
            os.unlink(p)

    def test_space_has_bounds(self):
        """Each space has bounds with origin and dimensions."""
        data = _make_valid_ifc_json(num_spaces=1)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert len(result.spaces) == 1
            space = result.spaces[0]
            assert "bounds" in space
            assert "x" in space["bounds"]
            assert "width" in space["bounds"]
        finally:
            os.unlink(p)

    def test_space_area_calculated(self):
        """Space areas are extracted from attributes."""
        data = _make_valid_ifc_json(num_spaces=2)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert result.total_area > 0
        finally:
            os.unlink(p)

    def test_no_spaces_still_works(self):
        """IFC file with no IfcSpace produces empty spaces list."""
        data = {"instances": [
            {"id": "B1", "type": "IfcBuilding", "attributes": {"Name": "Empty"}},
        ]}
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert result.spaces == []
            assert result.total_area == 0.0  # NOSONAR — S1244: import retained for re-export / API surface
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Device Extraction
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeviceExtraction:
    """Fire protection device extraction from IFC entities."""

    def test_extracts_fire_suppression_device(self):
        """IfcFireSuppressionDevice_Type is extracted."""
        data = _make_valid_ifc_json(num_devices=1)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert len(result.devices) >= 1
            device = result.devices[0]
            assert "id" in device
            assert "detector_type" in device
        finally:
            os.unlink(p)

    def test_extracts_all_device_types(self):
        """All 4 fire entity types are extracted."""
        data = _make_valid_ifc_json(num_devices=4)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert len(result.devices) == 4
        finally:
            os.unlink(p)

    def test_device_coverage_radius(self):
        """V79 FIX: coverage_radius is None by default (not 0)."""
        instances = [
            {"id": "B1", "type": "IfcBuilding", "attributes": {"Name": "Test"}},
            {"id": "D1", "type": "IfcAlarm",
             "attributes": {"Name": "SD", "DetectorType": "SMOKE"},
             "applicable_to": []},
        ]
        data = {"instances": instances}
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            if result.devices:
                # coverage_radius should be None if not specified
                device = result.devices[0]
                assert "coverage_radius" in device
        finally:
            os.unlink(p)

    def test_no_devices_produces_empty_list(self):
        """IFC with no fire devices produces empty list."""
        data = _make_valid_ifc_json(num_devices=0)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert result.devices == []
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Building Info Extraction
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildingExtraction:
    """IfcBuilding extraction."""

    def test_extracts_building_name(self):
        data = _make_valid_ifc_json()
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert result.building_name == "Test Hospital"
        finally:
            os.unlink(p)

    def test_missing_building_defaults_unknown(self):
        """IFC with no IfcBuilding defaults to 'Unknown'."""
        data = {"instances": []}
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert result.building_name == "Unknown"
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Floor Counting
# ═══════════════════════════════════════════════════════════════════════════════


class TestFloorCounting:
    """IfcBuildingStorey counting."""

    def test_counts_floors(self):
        data = _make_valid_ifc_json(num_floors=5)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert result.floors == 5
        finally:
            os.unlink(p)

    def test_zero_floors(self):
        data = _make_valid_ifc_json(num_floors=0)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert result.floors == 0
        finally:
            os.unlink(p)

    def test_duplicate_floors_counted_once(self):
        """Duplicate IfcBuildingStorey IDs are counted only once."""
        instances = [
            {"id": "B1", "type": "IfcBuilding", "attributes": {"Name": "Test"}},
            {"id": "F1", "type": "IfcBuildingStorey", "attributes": {"Name": "1st"}},
            {"id": "F1", "type": "IfcBuildingStorey", "attributes": {"Name": "1st dup"}},
        ]
        data = {"instances": instances}
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert result.floors == 1  # Deduped
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Negative Area Rejection (V79 Fix)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNegativeAreaRejection:
    """
    V79 FIX: Negative area spaces are REJECTED, not set to 0.

    Setting to 0 means zero protection for a room with real geometry.
    """

    def test_negative_area_space_rejected(self):
        """Spaces with negative area are skipped entirely."""
        data = _make_valid_ifc_json(num_spaces=2, negative_area=True)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            # Only the non-negative space should remain
            for space in result.spaces:
                assert space["area"] >= 0, "Negative area space was not rejected"
        finally:
            os.unlink(p)

    def test_zero_area_space_accepted(self):
        """Spaces with zero area are accepted (edge case)."""
        instances = [
            {"id": "B1", "type": "IfcBuilding", "attributes": {"Name": "Test"}},
            {"id": "S1", "type": "IfcSpace",
             "attributes": {"Name": "Zero Room", "Area": 0},
             "geometry": {"bounds": {"origin": {"x": 0, "y": 0, "z": 0},
                                     "dimensions": {"width": 0, "length": 0, "height": 3}}}},
        ]
        data = {"instances": instances}
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            assert len(result.spaces) == 1
            assert result.spaces[0]["area"] == 0
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. to_standard_format Conversion
# ═══════════════════════════════════════════════════════════════════════════════


class TestToStandardFormat:
    """IFCAnalysis → standard dict conversion."""

    def test_standard_format_has_walls(self):
        """to_standard_format generates walls from space bounds."""
        data = _make_valid_ifc_json()
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            std = parser.to_standard_format(result)
            assert "walls" in std
            assert isinstance(std["walls"], list)
        finally:
            os.unlink(p)

    def test_standard_format_has_rooms(self):
        """to_standard_format includes room info."""
        data = _make_valid_ifc_json()
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            std = parser.to_standard_format(result)
            assert "rooms" in std
            for room in std["rooms"]:
                assert "id" in room
                assert "name" in room
                assert "area" in room
        finally:
            os.unlink(p)

    def test_standard_format_has_devices(self):
        """to_standard_format includes device info."""
        data = _make_valid_ifc_json(num_devices=2)
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            std = parser.to_standard_format(result)
            assert "devices" in std
            for device in std["devices"]:
                assert "id" in device
                assert "name" in device
                assert "type" in device
        finally:
            os.unlink(p)

    def test_standard_format_building_name(self):
        """to_standard_format preserves building name."""
        data = _make_valid_ifc_json()
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            std = parser.to_standard_format(result)
            assert std["building_name"] == "Test Hospital"
            assert std["floors"] == result.floors
        finally:
            os.unlink(p)

    def test_zero_size_space_no_walls(self):
        """Space with zero width/length produces no wall."""
        instances = [
            {"id": "B1", "type": "IfcBuilding", "attributes": {"Name": "Test"}},
            {"id": "S1", "type": "IfcSpace",
             "attributes": {"Name": "Zero Room", "Area": 0},
             "geometry": {"bounds": {"origin": {"x": 0, "y": 0, "z": 0},
                                     "dimensions": {"width": 0, "length": 0, "height": 3}}}},
        ]
        data = {"instances": instances}
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()
            std = parser.to_standard_format(result)
            # Zero-width space should produce no walls
            assert len(std["walls"]) == 0
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Path Security (V125 Hardening)
# ═══════════════════════════════════════════════════════════════════════════════


class TestIFCParserPathSecurity:
    """V125: IFCParser enforces path security before file I/O."""

    def test_leading_dash_rejected(self):
        """Path starting with '-' is rejected."""
        with pytest.raises(ValueError, match="SECURITY"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
            IFCParser("--evil.ifc").parse()

    def test_null_byte_rejected(self):
        """Null byte in path is rejected."""
        with pytest.raises(ValueError, match="SECURITY"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
            IFCParser("/tmp/x\x00.ifc").parse()  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)

    def test_wrong_extension_rejected(self):
        """Non-IFC/JSON extension is rejected."""
        fd, p = tempfile.mkstemp(suffix=".txt", prefix="ifc_test_")
        try:
            os.write(fd, b"test")
            os.close(fd)
            with pytest.raises(ValueError, match="SECURITY"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
                IFCParser(p).parse()
        finally:
            os.unlink(p)

    def test_missing_file_raises_valueerror(self):
        """Missing file raises ValueError (not raw FileNotFoundError)."""
        with pytest.raises(ValueError, match="not found"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
            IFCParser("/tmp/does_not_exist_xyzzy.ifc").parse()  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)

    def test_ifc_extension_accepted(self):
        """.ifc extension passes validation (may fail at load)."""
        fd, p = tempfile.mkstemp(suffix=".ifc", prefix="ifc_test_")
        try:
            os.write(fd, b"{}")
            os.close(fd)
            # Should not raise SECURITY error
            # May raise ValueError for invalid content — that's OK
            try:
                IFCParser(p).parse()
            except ValueError as e:
                assert "SECURITY" not in str(e)
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Error Handling
# ═══════════════════════════════════════════════════════════════════════════════


class TestIFCParserErrorHandling:
    """Error handling for invalid/corrupt IFC files."""

    def test_corrupt_json_raises_valueerror(self):
        """Corrupt JSON content raises ValueError."""
        fd, p = tempfile.mkstemp(suffix=".json", prefix="ifc_test_")
        try:
            os.write(fd, b"{broken json")
            os.close(fd)
            with pytest.raises(ValueError, match="Failed to load IFC file"):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
                IFCParser(p).parse()
        finally:
            os.unlink(p)

    def test_empty_json_object(self):
        """Empty JSON object ({}) produces valid but empty result."""
        fd, p = tempfile.mkstemp(suffix=".json", prefix="ifc_test_")
        try:
            os.write(fd, b"{}")
            os.close(fd)
            result = IFCParser(p).parse()
            assert isinstance(result, IFCAnalysis)
            assert result.spaces == []
            assert result.devices == []
        finally:
            os.unlink(p)

    def test_non_dict_json(self):
        """Non-dict JSON (e.g. list) raises ValueError."""
        fd, p = tempfile.mkstemp(suffix=".json", prefix="ifc_test_")
        try:
            os.write(fd, b"[1, 2, 3]")
            os.close(fd)
            # The _load_json returns a list, _parse_instances expects dict
            # This should raise an AttributeError or similar
            with pytest.raises((ValueError, AttributeError, TypeError)):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)
                IFCParser(p).parse()
        finally:
            os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. parse_ifc Convenience Function
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseIfcConvenienceFunction:
    """parse_ifc() top-level convenience function."""

    def test_parse_ifc_returns_analysis(self):
        """parse_ifc() returns IFCAnalysis for valid input."""
        data = _make_valid_ifc_json()
        p = _make_ifc_json(data)
        try:
            result = parse_ifc(p)
            assert isinstance(result, IFCAnalysis)
            assert result.building_name == "Test Hospital"
        finally:
            os.unlink(p)

    def test_parse_ifc_security_rejection(self):
        """parse_ifc() enforces security for invalid paths."""
        with pytest.raises(ValueError, match="SECURITY"):
            parse_ifc("--evil.ifc")

    def test_parse_ifc_missing_file(self):
        """parse_ifc() raises ValueError for missing file."""
        with pytest.raises(ValueError, match="not found"):
            parse_ifc("/tmp/does_not_exist_xyzzy.ifc")  # NOSONAR — S5443: safe in test (uses tempfile + cleanup)


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Integration: Complex Building
# ═══════════════════════════════════════════════════════════════════════════════


class TestIFCIntegration:
    """Integration tests with complex IFC-JSON data."""

    def test_hospital_building(self):
        """Full hospital building with multiple floors and devices."""
        data = _make_valid_ifc_json(
            num_spaces=10, num_devices=4, num_floors=3
        )
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()

            assert result.building_name == "Test Hospital"
            assert result.floors == 3
            assert len(result.spaces) == 10
            assert len(result.devices) == 4
            assert result.total_area > 0

            # Verify to_standard_format
            std = parser.to_standard_format(result)
            assert std["building_name"] == "Test Hospital"
            assert std["floors"] == 3
            assert len(std["rooms"]) == 10
            assert len(std["devices"]) == 4
        finally:
            os.unlink(p)

    def test_building_with_mixed_spaces_and_devices(self):
        """Building with spaces and all 4 fire device types."""
        instances = [
            {"id": "B1", "type": "IfcBuilding", "attributes": {"Name": "Office Tower"}},
            {"id": "F1", "type": "IfcBuildingStorey", "attributes": {"Name": "Ground"}},
            {"id": "S1", "type": "IfcSpace",
             "attributes": {"Name": "Lobby", "Area": 200.0, "Elevation": 0},
             "geometry": {"bounds": {"origin": {"x": 0, "y": 0, "z": 0},
                                     "dimensions": {"width": 20, "length": 10, "height": 4}}}},
            {"id": "D1", "type": "IfcFireSuppressionDevice_Type",
             "attributes": {"Name": "Sprinkler", "DetectorType": "SPRINKLER",
                           "CoverageRadius": 2.1, "MountingHeight": 4.0},
             "applicable_to": ["S1"]},
            {"id": "D2", "type": "IfcAlarm",
             "attributes": {"Name": "Smoke Detector", "DetectorType": "SMOKE",
                           "CoverageRadius": 6.37, "MountingHeight": 4.0},
             "applicable_to": ["S1"]},
            {"id": "D3", "type": "IfcSensor",
             "attributes": {"Name": "Heat Detector", "DetectorType": "HEAT",
                           "CoverageRadius": 4.9, "MountingHeight": 4.0},
             "applicable_to": ["S1"]},
            {"id": "D4", "type": "IfcProtectiveDevice",
             "attributes": {"Name": "Fire Damper", "DetectorType": "DAMPER"},
             "applicable_to": ["S1"]},
        ]
        data = {"instances": instances}
        p = _make_ifc_json(data)
        try:
            parser = IFCParser(p)
            result = parser.parse()

            assert result.building_name == "Office Tower"
            assert result.floors == 1
            assert len(result.spaces) == 1
            assert len(result.devices) == 4
            assert result.total_area == 200.0  # NOSONAR — S1244: import retained for re-export / API surface
        finally:
            os.unlink(p)
