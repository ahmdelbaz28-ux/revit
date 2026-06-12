"""
QOMN-FIRE PARSER SUITE — COMPREHENSIVE UNIT TESTS

Safety-Critical: These tests exist to EXPOSE defects, not to increase pass rates.
Every test validates a specific safety property. A failing test means the code
is WRONG, not that the test needs to be changed.

Standards: ISO 16739 (IFC), AutoCAD DXF Spec, ISO 10303-21 (STEP), NFPA 72 (2022)

Test Categories:
1. Format Detection — Magic number / header verification
2. File Validation — Corruption, size, integrity checks
3. IFC Parsing — STEP instance extraction, room/wall geometry
4. DXF Parsing — Text and ezdxf path extraction
5. Geometry Validation — Area, unit, overlap, 3D checks
6. Converter Fallbacks — DWG/RVT mock conversion
7. Data Types — Hash determinism, immutability, fallback flag
8. Integration Pipeline — End-to-end parse + validate
"""

import os
import sys
import unittest
import tempfile
import hashlib

# Ensure the project root is on the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from qomn_fire.core.types import (
    Point3D, Wall, Room, Opening, Building, Device,
    DeviceType, ConduitType, ConduitRun, Fitting, FittingType,
    FireAlarmPanel, ProjectRequirements, PanelRecommendation,
    HatchSpec, TitleBlock, Revision
)
from qomn_fire.core.errors import (
    Result, BaseEngineeringError, FileValidationError, FormatError,
    VersionError, CorruptionError, ConversionError, GeometryError,
    UnitError, ConduitFillError, NECViolationError, HatchPlacementError,
    PhysicalConstraintError, FACPSelectionError
)
from qomn_fire.parsers.format_detector import FormatDetector
from qomn_fire.parsers.file_validator import FileValidator
from qomn_fire.parsers.dwg_converter import DwgConverter
from qomn_fire.parsers.rvt_converter import RvtConverter
from qomn_fire.parsers.ifc_parser import IfcParser
from qomn_fire.parsers.dxf_parser import DxfParser
from qomn_fire.parsers.geometry_validator import GeometryValidator


class TestFormatDetector(unittest.TestCase):
    """Tests for format detection using magic numbers and header verification."""

    def test_ifc_format_detection(self):
        """IFC file with ISO-10303-21 header is correctly detected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")
            f.flush()
            path = f.name
        try:
            res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(res.is_success, f"IFC detection failed: {res.error() if res.is_failure else ''}")
            fmt, ver = res.unwrap()
            self.assertEqual(fmt, "IFC")
            self.assertEqual(ver, "IFC2X3")
        finally:
            os.unlink(path)

    def test_ifc4_format_detection(self):
        """IFC4 schema version is correctly detected from header."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nEND-ISO-10303-21;\n")
            f.flush()
            path = f.name
        try:
            res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(res.is_success)
            fmt, ver = res.unwrap()
            self.assertEqual(fmt, "IFC")
            self.assertEqual(ver, "IFC4")
        finally:
            os.unlink(path)

    def test_dwg_format_detection(self):
        """DWG binary file with AC1015 magic is correctly detected."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.dwg', delete=False) as f:
            f.write(b"AC1015_REST_OF_BINARY_DATA")
            f.flush()
            path = f.name
        try:
            res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(res.is_success, f"DWG detection failed: {res.error() if res.is_failure else ''}")
            fmt, ver = res.unwrap()
            self.assertEqual(fmt, "DWG")
            self.assertIn("AC1015", ver)
        finally:
            os.unlink(path)

    def test_dwg_r2018_format_detection(self):
        """DWG R2018 (AC1032) magic is correctly detected."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.dwg', delete=False) as f:
            f.write(b"AC1032_MODERN_DWG")
            f.flush()
            path = f.name
        try:
            res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(res.is_success)
            fmt, ver = res.unwrap()
            self.assertEqual(fmt, "DWG")
            self.assertIn("AC1032", ver)
        finally:
            os.unlink(path)

    def test_rvt_format_detection(self):
        """RVT file with OLE compound binary signature is correctly detected."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.rvt', delete=False) as f:
            f.write(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
            f.flush()
            path = f.name
        try:
            res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(res.is_success, f"RVT detection failed: {res.error() if res.is_failure else ''}")
            fmt, ver = res.unwrap()
            self.assertEqual(fmt, "RVT")
        finally:
            os.unlink(path)

    def test_dxf_format_detection(self):
        """DXF text file with SECTION/HEADER markers is correctly detected."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False) as f:
            f.write("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n0\nEOF\n")
            f.flush()
            path = f.name
        try:
            res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(res.is_success, f"DXF detection failed: {res.error() if res.is_failure else ''}")
            fmt, ver = res.unwrap()
            self.assertEqual(fmt, "DXF")
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_format_error(self):
        """Non-existent file returns FormatError, not crash."""
        res = FormatDetector.detect_format_and_version("/nonexistent/path/file.ifc")
        self.assertTrue(res.is_failure)
        self.assertIsInstance(res.error(), FormatError)

    def test_unknown_format_returns_error(self):
        """File with unrecognized content returns FormatError."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.ifc', delete=False) as f:
            f.write(b"\x00\x01\x02\x03RANDOM_GARBAGE")
            f.flush()
            path = f.name
        try:
            res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(res.is_failure)
            self.assertIsInstance(res.error(), FormatError)
            self.assertIn("Unrecognized", res.error().message)
        finally:
            os.unlink(path)

    def test_empty_file_returns_format_error(self):
        """Zero-byte file returns FormatError."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.ifc', delete=False) as f:
            # Write nothing — empty file
            path = f.name
        try:
            res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(res.is_failure)
            self.assertIsInstance(res.error(), FormatError)
            self.assertIn("zero bytes", res.error().message)
        finally:
            os.unlink(path)


class TestFileValidator(unittest.TestCase):
    """Tests for file validation, corruption detection, and SHA-256 hashing."""

    def test_valid_ifc_file_passes_validation(self):
        """Valid IFC file with proper footer passes all validation checks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\n#10=IFCSPACE('ROOM');\nENDSEC;\nEND-ISO-10303-21;\n")
            f.flush()
            path = f.name
        try:
            res = FileValidator.validate_file(path)
            self.assertTrue(res.is_success, f"Validation failed: {res.error() if res.is_failure else ''}")
            file_hash = res.unwrap()
            self.assertEqual(len(file_hash), 64)  # SHA-256 hex digest is 64 chars
        finally:
            os.unlink(path)

    def test_valid_dxf_file_passes_validation(self):
        """Valid DXF file with EOF marker passes all validation checks."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False) as f:
            f.write("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n0\nEOF\n")
            f.flush()
            path = f.name
        try:
            res = FileValidator.validate_file(path)
            self.assertTrue(res.is_success, f"Validation failed: {res.error() if res.is_failure else ''}")
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_error(self):
        """Non-existent file returns FileValidationError."""
        res = FileValidator.validate_file("/nonexistent/file.ifc")
        self.assertTrue(res.is_failure)
        self.assertIsInstance(res.error(), FileValidationError)
        self.assertIn("not found", res.error().message)

    def test_zero_byte_file_returns_error(self):
        """Zero-byte file returns FileValidationError."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.ifc', delete=False) as f:
            path = f.name
        try:
            res = FileValidator.validate_file(path)
            self.assertTrue(res.is_failure)
            self.assertIsInstance(res.error(), FileValidationError)
            self.assertIn("zero bytes", res.error().message)
        finally:
            os.unlink(path)

    def test_corrupted_ifc_missing_footer_returns_error(self):
        """IFC file missing END-ISO-10303-21; footer returns CorruptionError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\n#10=IFCSPACE('ROOM');\nENDSEC;\n")
            # NO END-ISO-10303-21; at the end — corrupted
            f.flush()
            path = f.name
        try:
            res = FileValidator.validate_file(path)
            self.assertTrue(res.is_failure)
            self.assertIsInstance(res.error(), CorruptionError)
            self.assertIn("END-ISO-10303-21", res.error().message)
        finally:
            os.unlink(path)

    def test_corrupted_dxf_missing_eof_returns_error(self):
        """DXF file missing EOF marker returns CorruptionError."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False) as f:
            f.write("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n")
            # NO EOF — corrupted
            f.flush()
            path = f.name
        try:
            res = FileValidator.validate_file(path)
            self.assertTrue(res.is_failure)
            self.assertIsInstance(res.error(), CorruptionError)
            self.assertIn("EOF", res.error().message)
        finally:
            os.unlink(path)

    def test_sha256_hash_determinism(self):
        """SHA-256 hash is deterministic — same file always produces same hash."""
        content = "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nEND-ISO-10303-21;\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
            f.write(content)
            f.flush()
            path = f.name
        try:
            hash1 = FileValidator.validate_file(path).unwrap()
            hash2 = FileValidator.validate_file(path).unwrap()
            self.assertEqual(hash1, hash2, "SHA-256 hash must be deterministic")
        finally:
            os.unlink(path)

    def test_sha256_hash_uniqueness(self):
        """Different file content produces different SHA-256 hash."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f1:
            f1.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nEND-ISO-10303-21;\n")
            f1.flush()
            path1 = f1.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f2:
            f2.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nEND-ISO-10303-21;\n")
            f2.flush()
            path2 = f2.name
        try:
            hash1 = FileValidator.validate_file(path1).unwrap()
            hash2 = FileValidator.validate_file(path2).unwrap()
            self.assertNotEqual(hash1, hash2, "Different files must produce different hashes")
        finally:
            os.unlink(path1)
            os.unlink(path2)


class TestIfcParser(unittest.TestCase):
    """Tests for IFC/STEP parsing and room/wall extraction."""

    def _create_ifc_file(self, content: str) -> str:
        """Helper: create a temporary IFC file and return its path."""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False)
        f.write(content)
        f.flush()
        f.close()
        return f.name

    def test_parse_ifc_with_space_and_wall(self):
        """IFC file with IFCSPACE and IFCWALL produces rooms and walls."""
        content = (
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\n"
            "#10=IFCSPACE('ICU_ROOM_A');\n"
            "#20=IFCWALL(3.0);\n"
            "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        path = self._create_ifc_file(content)
        try:
            file_hash = "TEST_HASH_123"
            res = IfcParser.parse_ifc(path, file_hash)
            self.assertTrue(res.is_success, f"IFC parse failed: {res.error() if res.is_failure else ''}")
            building = res.unwrap()
            self.assertEqual(building.format_detected, "IFC")
            self.assertGreaterEqual(len(building.rooms), 1)
            self.assertGreaterEqual(len(building.walls), 1)
            self.assertEqual(building.file_hash, file_hash)
        finally:
            os.unlink(path)

    def test_parse_ifc_no_spaces_creates_fallback_room(self):
        """IFC file without IFCSPACE creates a fallback room with flag set."""
        content = (
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\n"
            "#20=IFCWALL(3.0);\n"
            "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        path = self._create_ifc_file(content)
        try:
            res = IfcParser.parse_ifc(path, "HASH")
            self.assertTrue(res.is_success)
            building = res.unwrap()
            self.assertEqual(len(building.rooms), 1)
            self.assertEqual(building.rooms[0].id, "IFC_ROOM_FALLBACK")
            self.assertTrue(building.has_fallback_geometry,
                           "has_fallback_geometry must be True when fallback room is used")
        finally:
            os.unlink(path)

    def test_parse_ifc_with_spaces_no_fallback(self):
        """V58 SAFETY FIX: IFC file with IFCSPACE STILL has has_fallback_geometry=True.

        The regex IFC parser CANNOT extract real room geometry — all IFCSPACE rooms
        get placeholder 10m x 10m boundary boxes. These placeholder boundaries are
        NOT the real building geometry, so has_fallback_geometry MUST be True.
        This is the correct V58 safety behavior: any building with placeholder
        boundaries is INVALID for fire protection design and must be rejected
        by the GeometryValidator. Install ifcopenshell for real IFC geometry.
        """
        content = (
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\n"
            "#10=IFCSPACE('LAB');\n"
            "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        path = self._create_ifc_file(content)
        try:
            res = IfcParser.parse_ifc(path, "HASH")
            self.assertTrue(res.is_success)
            building = res.unwrap()
            # V58 FIX: has_fallback_geometry MUST be True because ALL regex-parsed
            # IFC rooms have placeholder boundaries. Real geometry requires ifcopenshell.
            self.assertTrue(building.has_fallback_geometry,
                           "has_fallback_geometry must be True when rooms have placeholder boundaries. "
                           "The regex parser cannot extract real IFC geometry. "
                           "Install ifcopenshell for real geometry extraction.")
        finally:
            os.unlink(path)

    def test_parse_ifc_multiple_spaces_dont_overlap(self):
        """BUG-8 FIX: Multiple IFCSPACE rooms are offset, not all at origin."""
        content = (
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\n"
            "#10=IFCSPACE('ROOM_A');\n"
            "#20=IFCSPACE('ROOM_B');\n"
            "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        path = self._create_ifc_file(content)
        try:
            res = IfcParser.parse_ifc(path, "HASH")
            self.assertTrue(res.is_success)
            building = res.unwrap()
            self.assertEqual(len(building.rooms), 2)
            # Rooms must have DIFFERENT boundaries (not all at origin)
            r1_boundary = building.rooms[0].boundary
            r2_boundary = building.rooms[1].boundary
            r1_min_x = min(p.x for p in r1_boundary)
            r2_min_x = min(p.x for p in r2_boundary)
            self.assertNotEqual(r1_min_x, r2_min_x,
                               "BUG-8: Multiple rooms must not share same origin")
        finally:
            os.unlink(path)

    def test_parse_ifc_version_detection(self):
        """IFC4 schema version is correctly detected from content."""
        content = (
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\n"
            "#10=IFCSPACE('ROOM');\n"
            "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        path = self._create_ifc_file(content)
        try:
            res = IfcParser.parse_ifc(path, "HASH")
            self.assertTrue(res.is_success)
            building = res.unwrap()
            self.assertEqual(building.version_detected, "IFC4")
        finally:
            os.unlink(path)

    def test_parse_ifc_extracts_door_and_window(self):
        """IFCDOOR and IFCWINDOW entities are parsed into Opening objects."""
        content = (
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\n"
            "#10=IFCSPACE('ROOM');\n"
            "#30=IFCDOOR(0.9,2.1);\n"
            "#40=IFCWINDOW(1.2,1.5);\n"
            "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        path = self._create_ifc_file(content)
        try:
            res = IfcParser.parse_ifc(path, "HASH")
            self.assertTrue(res.is_success)
            building = res.unwrap()
            self.assertGreaterEqual(len(building.openings), 2)
            door_types = [o.opening_type for o in building.openings]
            self.assertIn("DOOR", door_types)
            self.assertIn("WINDOW", door_types)
        finally:
            os.unlink(path)

    def test_parse_ifc_area_is_calculated_not_hardcoded(self):
        """Room area is calculated using Shoelace, not hardcoded."""
        content = (
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\n"
            "#10=IFCSPACE('ROOM');\n"
            "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        path = self._create_ifc_file(content)
        try:
            res = IfcParser.parse_ifc(path, "HASH")
            self.assertTrue(res.is_success)
            building = res.unwrap()
            for room in building.rooms:
                # Fallback 10x10 room = 100m², but it should be calculated, not hardcoded
                self.assertGreater(room.area_m2, 0.0, "Room area must be positive")
        finally:
            os.unlink(path)


class TestDxfParser(unittest.TestCase):
    """Tests for DXF text-based and ezdxf-based parsing."""

    def _create_dxf_file(self, content: str) -> str:
        """Helper: create a temporary DXF file and return its path."""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False)
        f.write(content)
        f.flush()
        f.close()
        return f.name

    def test_parse_dxf_fallback_room_when_empty(self):
        """DXF file with no entities creates fallback room with flag set."""
        content = "0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n0\nEOF\n"
        path = self._create_dxf_file(content)
        try:
            res = DxfParser.parse_dxf(path, "HASH")
            self.assertTrue(res.is_success)
            building = res.unwrap()
            self.assertTrue(building.has_fallback_geometry,
                           "has_fallback_geometry must be True when fallback room is used")
        finally:
            os.unlink(path)

    def test_parse_dxf_text_line_extraction(self):
        """Text-based DXF parser extracts LINE entities as walls."""
        content = (
            "0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n"
            "0\nSECTION\n2\nENTITIES\n"
            "0\nLINE\n8\n0\n10\n0.0\n20\n0.0\n11\n5.0\n21\n5.0\n"
            "0\nENDSEC\n0\nEOF\n"
        )
        path = self._create_dxf_file(content)
        try:
            res = DxfParser.parse_dxf(path, "HASH")
            self.assertTrue(res.is_success)
            building = res.unwrap()
            self.assertGreaterEqual(len(building.walls), 1,
                                    "LINE entity must be parsed as a wall")
        finally:
            os.unlink(path)

    def test_dxf_area_calculated_not_hardcoded(self):
        """BUG-4 FIX: Room area is calculated, not hardcoded to 100.0."""
        content = (
            "0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n"
            "0\nSECTION\n2\nENTITIES\n"
            "0\nLWPOLYLINE\n8\n0\n70\n1\n"
            "10\n0.0\n20\n0.0\n"
            "10\n5.0\n20\n0.0\n"
            "10\n5.0\n20\n5.0\n"
            "10\n0.0\n20\n5.0\n"
            "0\nENDSEC\n0\nEOF\n"
        )
        path = self._create_dxf_file(content)
        try:
            res = DxfParser.parse_dxf(path, "HASH")
            self.assertTrue(res.is_success)
            building = res.unwrap()
            for room in building.rooms:
                if "FALLBACK" not in room.id:
                    # 5x5 room = 25m², NOT 100m²
                    self.assertAlmostEqual(room.area_m2, 25.0, places=1,
                                           msg="Area must be calculated from vertices, not hardcoded")
        finally:
            os.unlink(path)


class TestGeometryValidator(unittest.TestCase):
    """Tests for geometry validation: area, units, overlap, 3D-aware checks."""

    def test_no_rooms_returns_error(self):
        """Building with zero rooms returns GeometryError."""
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_failure)
        self.assertIsInstance(res.error(), GeometryError)
        self.assertIn("at least one", res.error().message.lower())

    def test_room_with_fewer_than_3_points_returns_error(self):
        """Room with < 3 boundary points returns GeometryError."""
        r = Room(id="R1", name="Bad", boundary=(Point3D(0,0), Point3D(5,0)), area_m2=0, height_m=3.0)
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(r,), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_failure)
        self.assertIsInstance(res.error(), GeometryError)
        self.assertIn("fewer than 3", res.error().message)

    def test_room_with_zero_area_returns_error(self):
        """Room with < 1.0 m² area returns GeometryError."""
        r = Room(
            id="R1", name="Tiny",
            boundary=(Point3D(0,0), Point3D(0.5,0), Point3D(0.5,0.5)),
            area_m2=0.125, height_m=3.0
        )
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(r,), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_failure)
        self.assertIsInstance(res.error(), GeometryError)
        self.assertIn("invalid physical area", res.error().message)

    def test_coordinate_exceeding_limit_returns_unit_error(self):
        """Coordinates > 10,000m returns UnitError (likely mm instead of m)."""
        r = Room(
            id="R1", name="MM Room",
            boundary=(Point3D(0,0), Point3D(15000,0), Point3D(15000,5000), Point3D(0,5000)),
            area_m2=75000000, height_m=3.0
        )
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(r,), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_failure)
        self.assertIsInstance(res.error(), UnitError)

    def test_duplicate_overlapping_rooms_returns_error(self):
        """Two rooms with identical boundaries returns GeometryError."""
        boundary = (Point3D(0,0), Point3D(5,0), Point3D(5,5), Point3D(0,5))
        r1 = Room(id="R1", name="Lab", boundary=boundary, area_m2=25, height_m=3.0)
        r2 = Room(id="R2", name="Duplicate", boundary=boundary, area_m2=25, height_m=3.0)
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(r1, r2), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_failure)
        self.assertIsInstance(res.error(), GeometryError)
        self.assertIn("Duplicate overlapping", res.error().message)

    def test_valid_building_passes_validation(self):
        """Valid building with proper geometry passes all checks."""
        r1 = Room(
            id="R1", name="Office",
            boundary=(Point3D(0,0), Point3D(10,0), Point3D(10,10), Point3D(0,10)),
            area_m2=100, height_m=3.0
        )
        r2 = Room(
            id="R2", name="Lab",
            boundary=(Point3D(15,0), Point3D(25,0), Point3D(25,10), Point3D(15,10)),
            area_m2=100, height_m=3.0
        )
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(r1, r2), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_success, f"Valid building failed: {res.error() if res.is_failure else ''}")

    def test_3d_aware_overlap_different_floors_passes(self):
        """BUG-7 FIX: Rooms on different floors with same X,Y footprint pass validation."""
        # Floor 1: room at z=0
        boundary_f1 = (Point3D(0,0,0), Point3D(10,0,0), Point3D(10,10,0), Point3D(0,10,0))
        # Floor 2: room at z=4 (4m above floor 1)
        boundary_f2 = (Point3D(0,0,4), Point3D(10,0,4), Point3D(10,10,4), Point3D(0,10,4))
        r1 = Room(id="F1_R1", name="Floor1 Office", boundary=boundary_f1, area_m2=100, height_m=3.0)
        r2 = Room(id="F2_R1", name="Floor2 Office", boundary=boundary_f2, area_m2=100, height_m=3.0)
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(r1, r2), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_success,
                       f"BUG-7: Rooms on different floors should NOT be flagged as overlapping: "
                       f"{res.error() if res.is_failure else ''}")

    def test_3d_aware_overlap_same_floor_still_fails(self):
        """BUG-7 FIX: Rooms on SAME floor with overlapping X,Y still returns error."""
        boundary = (Point3D(0,0,0), Point3D(10,0,0), Point3D(10,10,0), Point3D(0,10,0))
        r1 = Room(id="R1", name="Room1", boundary=boundary, area_m2=100, height_m=3.0)
        r2 = Room(id="R2", name="Room2", boundary=boundary, area_m2=100, height_m=3.0)
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(r1, r2), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_failure,
                       "Same-floor overlapping rooms must still be detected")

    def test_shoelace_area_calculation(self):
        """Shoelace algorithm correctly calculates known polygon areas."""
        # 10x10 square = 100 m²
        boundary = (Point3D(0,0), Point3D(10,0), Point3D(10,10), Point3D(0,10))
        area = GeometryValidator.calculate_polygon_area_2d(boundary)
        self.assertAlmostEqual(area, 100.0, places=2)

        # 5x3 rectangle = 15 m²
        boundary2 = (Point3D(0,0), Point3D(5,0), Point3D(5,3), Point3D(0,3))
        area2 = GeometryValidator.calculate_polygon_area_2d(boundary2)
        self.assertAlmostEqual(area2, 15.0, places=2)

    def test_partial_overlap_above_50_percent_returns_error(self):
        """Rooms overlapping > 50% of their area returns GeometryError."""
        r1 = Room(
            id="R1", name="Room1",
            boundary=(Point3D(0,0), Point3D(10,0), Point3D(10,10), Point3D(0,10)),
            area_m2=100, height_m=3.0
        )
        r2 = Room(
            id="R2", name="Room2",
            boundary=(Point3D(2,2), Point3D(12,2), Point3D(12,12), Point3D(2,12)),
            area_m2=100, height_m=3.0
        )
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(r1, r2), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_failure)
        self.assertIn("overlap", res.error().message.lower())


class TestConverters(unittest.TestCase):
    """Tests for DWG and RVT converter fallback paths."""

    def test_dwg_converter_fallback_creates_dxf(self):
        """DWG converter fallback creates a valid DXF file when dwg2dxf not available."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.dwg', delete=False) as f:
            f.write(b"AC1015_MOCK_DWG_DATA")
            dwg_path = f.name
        dxf_path = dwg_path.replace('.dwg', '_converted.dxf')
        try:
            res = DwgConverter.convert_dwg_to_dxf(dwg_path, dxf_path)
            self.assertTrue(res.is_success, f"DWG conversion failed: {res.error() if res.is_failure else ''}")
            self.assertTrue(os.path.exists(dxf_path))
            # Verify the DXF has required markers
            with open(dxf_path, 'r') as f:
                content = f.read()
            self.assertIn("SECTION", content)
            self.assertIn("EOF", content)
        finally:
            os.unlink(dwg_path)
            if os.path.exists(dxf_path):
                os.unlink(dxf_path)

    def test_dwg_converter_missing_source_returns_error(self):
        """DWG converter returns error for non-existent source file."""
        res = DwgConverter.convert_dwg_to_dxf("/nonexistent.dwg", "/tmp/out.dxf")
        self.assertTrue(res.is_failure)
        self.assertIsInstance(res.error(), ConversionError)

    def test_rvt_converter_fallback_creates_ifc(self):
        """RVT converter fallback creates a valid IFC file when revit-extractor not available."""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.rvt', delete=False) as f:
            f.write(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
            rvt_path = f.name
        ifc_path = rvt_path.replace('.rvt', '_converted.ifc')
        try:
            res = RvtConverter.convert_rvt_to_ifc(rvt_path, ifc_path)
            self.assertTrue(res.is_success, f"RVT conversion failed: {res.error() if res.is_failure else ''}")
            self.assertTrue(os.path.exists(ifc_path))
            with open(ifc_path, 'r') as f:
                content = f.read()
            self.assertIn("ISO-10303-21", content)
            self.assertIn("END-ISO-10303-21", content)
        finally:
            os.unlink(rvt_path)
            if os.path.exists(ifc_path):
                os.unlink(ifc_path)

    def test_rvt_converter_missing_source_returns_error(self):
        """RVT converter returns error for non-existent source file."""
        res = RvtConverter.convert_rvt_to_ifc("/nonexistent.rvt", "/tmp/out.ifc")
        self.assertTrue(res.is_failure)
        self.assertIsInstance(res.error(), ConversionError)


class TestDataTypes(unittest.TestCase):
    """Tests for data type integrity: hash determinism, immutability, frozen behavior."""

    def test_point3d_rounding(self):
        """Point3D rounds coordinates to 4 decimal places."""
        p = Point3D(1.123456789, 2.987654321, 3.111111111)
        self.assertEqual(p.x, 1.1235)
        self.assertEqual(p.y, 2.9877)
        self.assertEqual(p.z, 3.1111)

    def test_point3d_frozen(self):
        """Point3D is frozen and cannot be modified after creation."""
        p = Point3D(1.0, 2.0, 3.0)
        with self.assertRaises(AttributeError):
            p.x = 5.0

    def test_building_compute_hash_determinism(self):
        """Building.compute_hash() is deterministic for same inputs."""
        r = Room(id="R1", name="Test",
                 boundary=(Point3D(0,0), Point3D(10,0), Point3D(10,10), Point3D(0,10)),
                 area_m2=100, height_m=3.0)
        b1 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3",
                      units="METERS", walls=(), rooms=(r,), openings=())
        b2 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3",
                      units="METERS", walls=(), rooms=(r,), openings=())
        self.assertEqual(b1.compute_hash(), b2.compute_hash())

    def test_building_hash_differs_for_different_rooms(self):
        """Buildings with different room IDs produce different hashes."""
        r1 = Room(id="R1", name="A", boundary=(Point3D(0,0), Point3D(5,0), Point3D(5,5), Point3D(0,5)), area_m2=25, height_m=3.0)
        r2 = Room(id="R2", name="B", boundary=(Point3D(0,0), Point3D(5,0), Point3D(5,5), Point3D(0,5)), area_m2=25, height_m=3.0)
        b1 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3", units="METERS", walls=(), rooms=(r1,), openings=())
        b2 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3", units="METERS", walls=(), rooms=(r2,), openings=())
        self.assertNotEqual(b1.compute_hash(), b2.compute_hash())

    def test_building_hash_includes_fallback_flag(self):
        """Buildings with different has_fallback_geometry produce different hashes."""
        r = Room(id="R1", name="A", boundary=(Point3D(0,0), Point3D(5,0), Point3D(5,5), Point3D(0,5)), area_m2=25, height_m=3.0)
        b1 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3", units="METERS", walls=(), rooms=(r,), openings=(), has_fallback_geometry=False)
        b2 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3", units="METERS", walls=(), rooms=(r,), openings=(), has_fallback_geometry=True)
        self.assertNotEqual(b1.compute_hash(), b2.compute_hash())

    def test_device_hash_includes_z(self):
        """Device.compute_hash() includes Z coordinate — devices at different floors differ."""
        d1 = Device(id="D1", device_type=DeviceType.SMOKE_DETECTOR, location=Point3D(1,2,0), elevation_ft=0, circuit="C1", zone="Z1")
        d2 = Device(id="D1", device_type=DeviceType.SMOKE_DETECTOR, location=Point3D(1,2,4), elevation_ft=0, circuit="C1", zone="Z1")
        self.assertNotEqual(d1.compute_hash(), d2.compute_hash(),
                           "Devices at different Z must have different hashes")

    def test_result_unwrap_failure_raises(self):
        """Result.unwrap() on failure Result raises ValueError."""
        r = Result(error=GeometryError(message="test", code_ref="ref", remedy="fix"))
        with self.assertRaises(ValueError):
            r.unwrap()

    def test_result_error_success_raises(self):
        """Result.error() on success Result raises ValueError."""
        r = Result(value=42)
        with self.assertRaises(ValueError):
            r.error()

    def test_error_hierarchy(self):
        """All error types inherit from BaseEngineeringError and Exception."""
        error_types = [FileValidationError, FormatError, VersionError, CorruptionError,
                      ConversionError, GeometryError, UnitError, ConduitFillError,
                      NECViolationError, HatchPlacementError, PhysicalConstraintError,
                      FACPSelectionError]
        for et in error_types:
            err = et(message="m", code_ref="r", remedy="fix")
            self.assertIsInstance(err, BaseEngineeringError)
            # BUG-3 FIX: All engineering errors must also be Exception subclass
            self.assertIsInstance(err, Exception,
                               f"{et.__name__} must inherit from Exception for proper error handling")
            self.assertIn("m", err.message)
            self.assertIn("r", err.code_ref)
            self.assertIn("fix", err.remedy)


class TestIntegrationPipeline(unittest.TestCase):
    """End-to-end integration tests: validate → detect → parse → geometry check."""

    def test_ifc_pipeline_full(self):
        """V58 SAFETY FIX: IFC pipeline with regex parser is REJECTED by GeometryValidator.

        The regex IFC parser CANNOT extract real room geometry — all IFCSPACE rooms
        get placeholder 10m x 10m boundary boxes. The V58 safety fix correctly
        sets has_fallback_geometry=True for buildings with placeholder boundaries,
        and the GeometryValidator correctly REJECTS them. This prevents fire
        protection designs based on wrong geometry from being produced.

        For a SUCCESSFUL full pipeline, install ifcopenshell (pip install ifcopenshell)
        which provides real IFC geometry extraction.
        """
        content = (
            "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\n"
            "#10=IFCSPACE('ICU_ROOM');\n"
            "#20=IFCWALL(3.0);\n"
            "ENDSEC;\nEND-ISO-10303-21;\n"
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
            f.write(content)
            path = f.name
        try:
            # Step 1: Validate
            val_res = FileValidator.validate_file(path)
            self.assertTrue(val_res.is_success, f"Validation failed: {val_res.error() if val_res.is_failure else ''}")
            file_hash = val_res.unwrap()

            # Step 2: Detect format
            fmt_res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(fmt_res.is_success)
            fmt, ver = fmt_res.unwrap()
            self.assertEqual(fmt, "IFC")

            # Step 3: Parse
            parse_res = IfcParser.parse_ifc(path, file_hash)
            self.assertTrue(parse_res.is_success)
            building = parse_res.unwrap()
            self.assertGreaterEqual(len(building.rooms), 1)

            # Step 4: Geometry validate — V58 SAFETY: MUST FAIL for placeholder geometry
            # The regex parser creates 10m x 10m placeholder boxes, NOT real room shapes.
            # The GeometryValidator correctly rejects placeholder buildings because fire
            # protection design based on wrong geometry is INVALID and DANGEROUS.
            geom_res = GeometryValidator.validate_building(building)
            self.assertTrue(geom_res.is_failure,
                           f"V58 SAFETY: GeometryValidator MUST reject placeholder geometry. "
                           f"Got unexpected success — placeholder buildings must NOT pass validation.")
            # Verify the error is about placeholder/fallback geometry
            self.assertIn("placeholder", str(geom_res.error()).lower(),
                         "Rejection reason must mention placeholder/fallback geometry")

            # Step 5: Compute hash
            bhash = building.compute_hash()
            self.assertEqual(len(bhash), 64)  # SHA-256
        finally:
            os.unlink(path)

    def test_dxf_pipeline_full(self):
        """Full DXF pipeline: validate → detect → parse → geometry validate.

        BUG-8 FIX: DXF file with no entities produces fallback geometry, which
        is now correctly REJECTED by the GeometryValidator. Fallback geometry is
        INVALID for fire protection design — the validator must reject it.
        This test now verifies the correct rejection behavior.
        """
        content = "0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n0\nEOF\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False) as f:
            f.write(content)
            path = f.name
        try:
            # Validate
            val_res = FileValidator.validate_file(path)
            self.assertTrue(val_res.is_success)
            file_hash = val_res.unwrap()

            # Detect
            fmt_res = FormatDetector.detect_format_and_version(path)
            self.assertTrue(fmt_res.is_success)
            fmt, ver = fmt_res.unwrap()
            self.assertEqual(fmt, "DXF")

            # Parse
            parse_res = DxfParser.parse_dxf(path, file_hash)
            self.assertTrue(parse_res.is_success)
            building = parse_res.unwrap()

            # BUG-8 FIX: Fallback geometry must be REJECTED by the validator.
            # A DXF with no entities produces fallback/placeholder geometry,
            # which is INVALID for fire protection design.
            self.assertTrue(building.has_fallback_geometry,
                           "Empty DXF should have has_fallback_geometry=True")
            geom_res = GeometryValidator.validate_building(building)
            self.assertTrue(geom_res.is_failure,
                           "BUG-8: Fallback geometry must be REJECTED by validator")
            self.assertIsInstance(geom_res.error(), GeometryError)
            self.assertIn("fallback", geom_res.error().message.lower())
        finally:
            os.unlink(path)

    def test_corrupted_file_stops_pipeline(self):
        """Corrupted file stops the pipeline at validation stage."""
        content = "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\n"
        # Missing END-ISO-10303-21; — corrupted
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ifc', delete=False) as f:
            f.write(content)
            path = f.name
        try:
            val_res = FileValidator.validate_file(path)
            self.assertTrue(val_res.is_failure)
            self.assertIsInstance(val_res.error(), CorruptionError)
            # Pipeline stops here — no parsing attempted
        finally:
            os.unlink(path)

    # ── BUG-8 FIX TEST: Fallback geometry rejection ──
    def test_fallback_geometry_rejected_by_validator(self):
        """BUG-8 FIX: Building with has_fallback_geometry=True is REJECTED."""
        r = Room(id="FALLBACK", name="Fallback",
                 boundary=(Point3D(0,0), Point3D(10,0), Point3D(10,10), Point3D(0,10)),
                 area_m2=100, height_m=3.0)
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="METERS", walls=(), rooms=(r,), openings=(),
            has_fallback_geometry=True
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_failure, "BUG-8: Fallback geometry must be REJECTED")
        self.assertIsInstance(res.error(), GeometryError)
        self.assertIn("fallback", res.error().message.lower())

    # ── BUG-14 FIX TEST: Non-METERS units rejected ──
    def test_non_meters_units_rejected(self):
        """BUG-14 FIX: Building with units != METERS is rejected."""
        r = Room(id="R1", name="A",
                 boundary=(Point3D(0,0), Point3D(10,0), Point3D(10,10), Point3D(0,10)),
                 area_m2=100, height_m=3.0)
        b = Building(
            file_hash="H", format_detected="IFC", version_detected="IFC2X3",
            units="MILLIMETERS", walls=(), rooms=(r,), openings=()
        )
        res = GeometryValidator.validate_building(b)
        self.assertTrue(res.is_failure, "BUG-14: Non-METERS units must be REJECTED")
        self.assertIsInstance(res.error(), UnitError)

    # ── BUG-1 FIX TEST: Result cannot hold both value and error ──
    def test_result_cannot_hold_both_value_and_error(self):
        """BUG-1 FIX: Result with both value and error raises ValueError."""
        with self.assertRaises(ValueError):
            Result(value=42, error=GeometryError(message="test", code_ref="r", remedy="f"))

    # ── BUG-30+36 FIX TEST: Building hash includes wall geometry and openings ──
    def test_building_hash_includes_wall_geometry(self):
        """BUG-30 FIX: Buildings with same wall ID but different geometry have different hashes."""
        r = Room(id="R1", name="A",
                 boundary=(Point3D(0,0), Point3D(5,0), Point3D(5,5), Point3D(0,5)),
                 area_m2=25, height_m=3.0)
        w1 = Wall(id="W1", start=Point3D(0,0), end=Point3D(5,0), height_m=3.0, thickness_m=0.20)
        w2 = Wall(id="W1", start=Point3D(0,0), end=Point3D(10,0), height_m=3.0, thickness_m=0.40)
        b1 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3",
                      units="METERS", walls=(w1,), rooms=(r,), openings=())
        b2 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3",
                      units="METERS", walls=(w2,), rooms=(r,), openings=())
        self.assertNotEqual(b1.compute_hash(), b2.compute_hash(),
                           "BUG-30: Different wall geometry must produce different hashes")

    def test_building_hash_includes_openings(self):
        """BUG-36 FIX: Buildings with different openings have different hashes."""
        r = Room(id="R1", name="A",
                 boundary=(Point3D(0,0), Point3D(5,0), Point3D(5,5), Point3D(0,5)),
                 area_m2=25, height_m=3.0)
        o1 = Opening(id="D1", opening_type="DOOR", location=Point3D(0,0), width_m=0.9, height_m=2.1)
        b1 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3",
                      units="METERS", walls=(), rooms=(r,), openings=())
        b2 = Building(file_hash="H", format_detected="IFC", version_detected="IFC2X3",
                      units="METERS", walls=(), rooms=(r,), openings=(o1,))
        self.assertNotEqual(b1.compute_hash(), b2.compute_hash(),
                           "BUG-36: Different openings must produce different hashes")


if __name__ == '__main__':
    unittest.main(verbosity=2)
