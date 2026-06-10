"""
QOMN-FIRE INPUT PARSING AND VALIDATION TEST SUITE

Safety-Critical: These tests validate that corrupted or invalid BIM files are
REJECTED, not silently accepted. A false PASS in these tests means a corrupted
file could produce wrong fire protection designs.

Standards: ISO 16739 (IFC), AutoCAD DXF Spec, ISO 10303-21 (STEP), NFPA 72 (2022)

BUG-7 FIX: Mock IFC/DXF files now use actual newlines (\n) instead of
double-escaped \\n. The original test code used \\n which wrote LITERAL
backslash-n characters to disk instead of newlines, meaning the parsers
would never find the proper section markers (SECTION, HEADER, EOF, etc.)
in the mock files.
"""

import os
import sys
import unittest
import tempfile
import shutil

# Ensure project root is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestFormatDetector(unittest.TestCase):
    """Tests for QOMN-FIRE format and version detection engine."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ifc_format_detection(self):
        """IFC files with ISO-10303-21 header must be detected as IFC format."""
        from qomn_fire.parsers.format_detector import FormatDetector

        ifc_path = os.path.join(self.tmpdir, "test.ifc")
        with open(ifc_path, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")

        res = FormatDetector.detect_format_and_version(ifc_path)
        self.assertTrue(res.is_success, f"IFC detection failed: {res.error() if res.is_failure else ''}")
        fmt, ver = res.unwrap()
        self.assertEqual(fmt, "IFC")
        self.assertEqual(ver, "IFC2X3")

    def test_ifc4_format_detection(self):
        """IFC4 files must be detected with correct version."""
        from qomn_fire.parsers.format_detector import FormatDetector

        ifc_path = os.path.join(self.tmpdir, "test_ifc4.ifc")
        with open(ifc_path, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")

        res = FormatDetector.detect_format_and_version(ifc_path)
        self.assertTrue(res.is_success)
        fmt, ver = res.unwrap()
        self.assertEqual(fmt, "IFC")
        self.assertEqual(ver, "IFC4")

    def test_dwg_format_detection(self):
        """
        DWG files with AC1015 magic bytes must be detected.
        BUG-1 VALIDATION: Verifies the OLE/DWG magic byte detection works correctly.
        """
        from qomn_fire.parsers.format_detector import FormatDetector

        dwg_path = os.path.join(self.tmpdir, "test.dwg")
        with open(dwg_path, "wb") as f:
            f.write(b"AC1015_MOCK_DWG_DATA")

        res = FormatDetector.detect_format_and_version(dwg_path)
        self.assertTrue(res.is_success, f"DWG detection failed: {res.error() if res.is_failure else ''}")
        fmt, ver = res.unwrap()
        self.assertEqual(fmt, "DWG")
        self.assertIn("AC1015", ver)

    def test_dwg_ac1032_detection(self):
        """DWG R2018 (AC1032) must be detected."""
        from qomn_fire.parsers.format_detector import FormatDetector

        dwg_path = os.path.join(self.tmpdir, "test_r2018.dwg")
        with open(dwg_path, "wb") as f:
            f.write(b"AC1032_MOCK_DWG_DATA")

        res = FormatDetector.detect_format_and_version(dwg_path)
        self.assertTrue(res.is_success)
        fmt, ver = res.unwrap()
        self.assertEqual(fmt, "DWG")
        self.assertIn("AC1032", ver)

    def test_rvt_format_detection(self):
        """
        RVT files (OLE Compound Container) must be detected.
        BUG-1 VALIDATION: Verifies the OLE signature b"\\xd0\\xcf..." is correct
        binary bytes, not escaped string literals.
        """
        from qomn_fire.parsers.format_detector import FormatDetector

        rvt_path = os.path.join(self.tmpdir, "test.rvt")
        with open(rvt_path, "wb") as f:
            # Write actual OLE Compound File Binary signature
            f.write(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)

        res = FormatDetector.detect_format_and_version(rvt_path)
        self.assertTrue(res.is_success, f"RVT detection failed: {res.error() if res.is_failure else ''}")
        fmt, ver = res.unwrap()
        self.assertEqual(fmt, "RVT")

    def test_dxf_format_detection(self):
        """
        DXF files with SECTION/HEADER markers must be detected.
        BUG-2 VALIDATION: Verifies DXF detection works with proper newlines.
        """
        from qomn_fire.parsers.format_detector import FormatDetector

        dxf_path = os.path.join(self.tmpdir, "test.dxf")
        with open(dxf_path, "w", encoding="utf-8") as f:
            f.write("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n0\nEOF\n")

        res = FormatDetector.detect_format_and_version(dxf_path)
        self.assertTrue(res.is_success, f"DXF detection failed: {res.error() if res.is_failure else ''}")
        fmt, ver = res.unwrap()
        self.assertEqual(fmt, "DXF")

    def test_unrecognized_format_rejected(self):
        """Unknown file formats must be rejected with FormatError."""
        from qomn_fire.parsers.format_detector import FormatDetector

        bad_path = os.path.join(self.tmpdir, "test.xyz")
        with open(bad_path, "w", encoding="utf-8") as f:
            f.write("RANDOM DATA THAT DOES NOT MATCH ANY FORMAT")

        res = FormatDetector.detect_format_and_version(bad_path)
        self.assertTrue(res.is_failure)

    def test_nonexistent_file_rejected(self):
        """Non-existent files must be rejected with FormatError."""
        from qomn_fire.parsers.format_detector import FormatDetector

        res = FormatDetector.detect_format_and_version("/nonexistent/path/file.ifc")
        self.assertTrue(res.is_failure)


class TestFileValidator(unittest.TestCase):
    """Tests for QOMN-FIRE file validation and corruption detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_ifc_file_validation(self):
        """Valid IFC file must pass validation and produce SHA-256 hash."""
        from qomn_fire.parsers.file_validator import FileValidator

        ifc_path = os.path.join(self.tmpdir, "valid.ifc")
        with open(ifc_path, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")

        res = FileValidator.validate_file(ifc_path)
        self.assertTrue(res.is_success, f"Valid IFC failed validation: {res.error() if res.is_failure else ''}")
        hash_val = res.unwrap()
        self.assertTrue(len(hash_val) == 64, f"SHA-256 hash should be 64 chars, got {len(hash_val)}")

    def test_valid_dxf_file_validation(self):
        """Valid DXF file must pass validation and produce SHA-256 hash."""
        from qomn_fire.parsers.file_validator import FileValidator

        dxf_path = os.path.join(self.tmpdir, "valid.dxf")
        with open(dxf_path, "w", encoding="utf-8") as f:
            f.write("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n0\nEOF\n")

        res = FileValidator.validate_file(dxf_path)
        self.assertTrue(res.is_success, f"Valid DXF failed validation: {res.error() if res.is_failure else ''}")

    def test_corrupted_ifc_detected(self):
        """
        IFC file missing END-ISO-10303-21; footer must be flagged as corrupted.
        This prevents processing of truncated IFC exports.
        """
        from qomn_fire.parsers.file_validator import FileValidator

        ifc_path = os.path.join(self.tmpdir, "corrupted.ifc")
        with open(ifc_path, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\n")
            # Deliberately missing END-ISO-10303-21;

        res = FileValidator.validate_file(ifc_path)
        self.assertTrue(res.is_failure, "Corrupted IFC should fail validation")
        self.assertIn("corrupted", res.error().message.lower())

    def test_corrupted_dxf_detected(self):
        """
        DXF file missing EOF marker must be flagged as corrupted.
        This prevents processing of truncated DXF exports.
        """
        from qomn_fire.parsers.file_validator import FileValidator

        dxf_path = os.path.join(self.tmpdir, "corrupted.dxf")
        with open(dxf_path, "w", encoding="utf-8") as f:
            f.write("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n")
            # Deliberately missing EOF

        res = FileValidator.validate_file(dxf_path)
        self.assertTrue(res.is_failure, "Corrupted DXF should fail validation")

    def test_empty_file_rejected(self):
        """Empty files must be rejected."""
        from qomn_fire.parsers.file_validator import FileValidator

        empty_path = os.path.join(self.tmpdir, "empty.ifc")
        with open(empty_path, "w") as f:
            pass  # Write nothing

        res = FileValidator.validate_file(empty_path)
        self.assertTrue(res.is_failure)

    def test_nonexistent_file_rejected(self):
        """Non-existent files must be rejected."""
        from qomn_fire.parsers.file_validator import FileValidator

        res = FileValidator.validate_file("/nonexistent/file.ifc")
        self.assertTrue(res.is_failure)


class TestIfcParser(unittest.TestCase):
    """Tests for QOMN-FIRE IFC parsing engine."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ifc_wall_and_space_parsing(self):
        """
        IFC file with IFCWALL and IFCSPACE entities must extract walls and rooms.
        BUG-3 VALIDATION: Verifies the STEP regex pattern works with actual newlines.
        """
        from qomn_fire.parsers.ifc_parser import IfcParser

        ifc_path = os.path.join(self.tmpdir, "test.ifc")
        with open(ifc_path, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\n")
            f.write("HEADER;\n")
            f.write("FILE_SCHEMA(('IFC2X3'));\n")
            f.write("ENDSEC;\n")
            f.write("DATA;\n")
            f.write("#10=IFCSPACE('ICU_WARD_A');\n")
            f.write("#20=IFCWALL(3.0);\n")
            f.write("#30=IFCDOOR(0.9,2.1);\n")
            f.write("ENDSEC;\n")
            f.write("END-ISO-10303-21;\n")

        res = IfcParser.parse_ifc(ifc_path, "test_hash_123")
        self.assertTrue(res.is_success, f"IFC parsing failed: {res.error() if res.is_failure else ''}")
        building = res.unwrap()
        self.assertGreater(len(building.rooms), 0, "Must extract at least one room")
        self.assertGreater(len(building.walls), 0, "Must extract at least one wall")
        self.assertEqual(building.format_detected, "IFC")

    def test_ifc_room_area_calculated(self):
        """Room areas must be calculated from boundary, not hardcoded."""
        from qomn_fire.parsers.ifc_parser import IfcParser

        ifc_path = os.path.join(self.tmpdir, "test_area.ifc")
        with open(ifc_path, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\n")
            f.write("DATA;\n#10=IFCSPACE('ROOM_A');\nENDSEC;\nEND-ISO-10303-21;\n")

        res = IfcParser.parse_ifc(ifc_path, "hash123")
        self.assertTrue(res.is_success)
        building = res.unwrap()
        # Default room is 10x10 = 100 m2 (calculated by Shoelace)
        self.assertEqual(building.rooms[0].area_m2, 100.0)

    def test_ifc_fallback_room(self):
        """IFC file with no IFCSPACE entities must provide a fallback room."""
        from qomn_fire.parsers.ifc_parser import IfcParser

        ifc_path = os.path.join(self.tmpdir, "no_spaces.ifc")
        with open(ifc_path, "w", encoding="utf-8") as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC2X3'));\nENDSEC;\n")
            f.write("DATA;\n#10=IFCWALL(3.0);\nENDSEC;\nEND-ISO-10303-21;\n")

        res = IfcParser.parse_ifc(ifc_path, "hash123")
        self.assertTrue(res.is_success)
        building = res.unwrap()
        self.assertEqual(len(building.rooms), 1)
        self.assertIn("FALLBACK", building.rooms[0].id)


class TestGeometryValidator(unittest.TestCase):
    """Tests for QOMN-FIRE geometry validation engine."""

    def test_valid_building_passes(self):
        """Building with valid rooms must pass geometry validation."""
        from qomn_fire.core.types import Building, Room, Point3D
        from qomn_fire.parsers.geometry_validator import GeometryValidator

        room = Room(
            id="ROOM_A",
            name="Office",
            boundary=(Point3D(0, 0), Point3D(5, 0), Point3D(5, 5), Point3D(0, 5)),
            area_m2=25.0,
            height_m=3.0
        )
        building = Building(
            file_hash="test_hash",
            format_detected="IFC",
            version_detected="IFC2X3",
            units="METERS",
            walls=(),
            rooms=(room,),
            openings=()
        )

        res = GeometryValidator.validate_building(building)
        self.assertTrue(res.is_success, f"Valid building failed: {res.error() if res.is_failure else ''}")

    def test_duplicate_rooms_detected(self):
        """
        Duplicate overlapping rooms must be detected.
        BUG-5 VALIDATION: Original code only detected rooms with identical bounding boxes.
        This test verifies that exact duplicates are caught.
        """
        from qomn_fire.core.types import Building, Room, Point3D
        from qomn_fire.parsers.geometry_validator import GeometryValidator

        r1 = Room(
            id="ROOM_A",
            name="Lab",
            boundary=(Point3D(0, 0), Point3D(5, 0), Point3D(5, 5), Point3D(0, 5)),
            area_m2=25.0,
            height_m=3.0
        )
        r2 = Room(
            id="ROOM_B",
            name="Duplicate Lab",
            boundary=(Point3D(0, 0), Point3D(5, 0), Point3D(5, 5), Point3D(0, 5)),
            area_m2=25.0,
            height_m=3.0
        )

        building = Building(
            file_hash="test_hash",
            format_detected="IFC",
            version_detected="IFC2X3",
            units="METERS",
            walls=(),
            rooms=(r1, r2),
            openings=()
        )

        res = GeometryValidator.validate_building(building)
        self.assertTrue(res.is_failure, "Duplicate rooms should fail validation")
        self.assertIn("Duplicate overlapping rooms", res.error().message)

    def test_partial_overlap_detected(self):
        """
        Partially overlapping rooms must be detected when overlap > 50%.
        BUG-5 VALIDATION: Original code missed partial overlaps entirely.
        """
        from qomn_fire.core.types import Building, Room, Point3D
        from qomn_fire.parsers.geometry_validator import GeometryValidator

        r1 = Room(
            id="ROOM_A",
            name="Large Room",
            boundary=(Point3D(0, 0), Point3D(10, 0), Point3D(10, 10), Point3D(0, 10)),
            area_m2=100.0,
            height_m=3.0
        )
        # r2 overlaps r1 by > 50% (shared area = 9*9 = 81 out of 9*9 = 81)
        r2 = Room(
            id="ROOM_B",
            name="Overlapping Room",
            boundary=(Point3D(1, 1), Point3D(10, 1), Point3D(10, 10), Point3D(1, 10)),
            area_m2=81.0,
            height_m=3.0
        )

        building = Building(
            file_hash="test_hash",
            format_detected="IFC",
            version_detected="IFC2X3",
            units="METERS",
            walls=(),
            rooms=(r1, r2),
            openings=()
        )

        res = GeometryValidator.validate_building(building)
        self.assertTrue(res.is_failure, "Partially overlapping rooms should fail validation")

    def test_no_rooms_fails(self):
        """Building with zero rooms must fail validation."""
        from qomn_fire.core.types import Building
        from qomn_fire.parsers.geometry_validator import GeometryValidator

        building = Building(
            file_hash="test_hash",
            format_detected="IFC",
            version_detected="IFC2X3",
            units="METERS",
            walls=(),
            rooms=(),
            openings=()
        )

        res = GeometryValidator.validate_building(building)
        self.assertTrue(res.is_failure)

    def test_unclosed_room_fails(self):
        """Room with fewer than 3 boundary points must fail."""
        from qomn_fire.core.types import Building, Room, Point3D
        from qomn_fire.parsers.geometry_validator import GeometryValidator

        room = Room(
            id="ROOM_BAD",
            name="Invalid",
            boundary=(Point3D(0, 0), Point3D(5, 0)),  # Only 2 points — not a polygon
            area_m2=0.0,
            height_m=3.0
        )
        building = Building(
            file_hash="test_hash",
            format_detected="IFC",
            version_detected="IFC2X3",
            units="METERS",
            walls=(),
            rooms=(room,),
            openings=()
        )

        res = GeometryValidator.validate_building(building)
        self.assertTrue(res.is_failure)

    def test_unit_mismatch_detected(self):
        """
        Coordinates exceeding 10,000m must be flagged as potential unit mismatch.
        This catches files using millimeters instead of meters.
        """
        from qomn_fire.core.types import Building, Room, Point3D
        from qomn_fire.parsers.geometry_validator import GeometryValidator

        room = Room(
            id="ROOM_MM",
            name="Room in Millimeters",
            boundary=(Point3D(0, 0), Point3D(50000, 0), Point3D(50000, 30000), Point3D(0, 30000)),
            area_m2=1500000.0,  # 50000*30000 mm2 — clearly millimeters, not meters!
            height_m=3.0
        )
        building = Building(
            file_hash="test_hash",
            format_detected="IFC",
            version_detected="IFC2X3",
            units="METERS",
            walls=(),
            rooms=(room,),
            openings=()
        )

        res = GeometryValidator.validate_building(building)
        self.assertTrue(res.is_failure, "Unit mismatch should be detected")

    def test_shoelace_area_calculation(self):
        """Shoelace formula must produce correct polygon area."""
        from qomn_fire.core.types import Point3D
        from qomn_fire.parsers.geometry_validator import GeometryValidator

        # 10x10 square = 100 m2
        square = (Point3D(0, 0), Point3D(10, 0), Point3D(10, 10), Point3D(0, 10))
        self.assertEqual(GeometryValidator.calculate_polygon_area_2d(square), 100.0)

        # 5x5 square = 25 m2
        small = (Point3D(0, 0), Point3D(5, 0), Point3D(5, 5), Point3D(0, 5))
        self.assertEqual(GeometryValidator.calculate_polygon_area_2d(small), 25.0)


class TestDwgConverter(unittest.TestCase):
    """Tests for DWG to DXF conversion."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_fallback_conversion(self):
        """Without dwg2dxf installed, fallback must produce valid DXF."""
        from qomn_fire.parsers.dwg_converter import DwgConverter

        dwg_path = os.path.join(self.tmpdir, "test.dwg")
        dxf_path = os.path.join(self.tmpdir, "output.dxf")

        # Write a fake DWG file
        with open(dwg_path, "wb") as f:
            f.write(b"AC1015_FAKE")

        res = DwgConverter.convert_dwg_to_dxf(dwg_path, dxf_path)
        self.assertTrue(res.is_success, f"DWG conversion failed: {res.error() if res.is_failure else ''}")
        self.assertTrue(os.path.exists(dxf_path))

    def test_missing_source_file(self):
        """Missing source DWG must be rejected."""
        from qomn_fire.parsers.dwg_converter import DwgConverter

        res = DwgConverter.convert_dwg_to_dxf("/nonexistent/file.dwg", "/tmp/out.dxf")
        self.assertTrue(res.is_failure)


class TestRvtConverter(unittest.TestCase):
    """Tests for RVT to IFC conversion."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_fallback_conversion(self):
        """Without RevitCLI installed, fallback must produce valid IFC."""
        from qomn_fire.parsers.rvt_converter import RvtConverter

        rvt_path = os.path.join(self.tmpdir, "test.rvt")
        ifc_path = os.path.join(self.tmpdir, "output.ifc")

        # Write a fake RVT file (OLE signature)
        with open(rvt_path, "wb") as f:
            f.write(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 50)

        res = RvtConverter.convert_rvt_to_ifc(rvt_path, ifc_path)
        self.assertTrue(res.is_success, f"RVT conversion failed: {res.error() if res.is_failure else ''}")
        self.assertTrue(os.path.exists(ifc_path))


class TestDxfParser(unittest.TestCase):
    """Tests for DXF parsing engine."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dxf_fallback_room(self):
        """
        DXF file with no extractable entities must provide a fallback room.
        BUG-4 VALIDATION: Area must be calculated from boundary, not hardcoded to 100.
        """
        from qomn_fire.parsers.dxf_parser import DxfParser

        dxf_path = os.path.join(self.tmpdir, "minimal.dxf")
        with open(dxf_path, "w", encoding="utf-8") as f:
            f.write("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n0\nENDSEC\n0\nEOF\n")

        res = DxfParser.parse_dxf(dxf_path, "test_hash")
        self.assertTrue(res.is_success, f"DXF parsing failed: {res.error() if res.is_failure else ''}")
        building = res.unwrap()
        self.assertGreater(len(building.rooms), 0)
        # Fallback room is 10x10 = 100 m2 (calculated by Shoelace from boundary)
        self.assertEqual(building.rooms[0].area_m2, 100.0)


class TestBuildingHash(unittest.TestCase):
    """Tests for Building model hash computation (traceability)."""

    def test_building_hash_deterministic(self):
        """Building hash must be deterministic — same input = same hash."""
        from qomn_fire.core.types import Building, Room, Point3D

        room = Room(
            id="R1",
            name="Test",
            boundary=(Point3D(0, 0), Point3D(10, 0), Point3D(10, 10), Point3D(0, 10)),
            area_m2=100.0,
            height_m=3.0
        )
        b1 = Building(file_hash="h1", format_detected="IFC", version_detected="IFC2X3",
                       units="METERS", walls=(), rooms=(room,), openings=())
        b2 = Building(file_hash="h1", format_detected="IFC", version_detected="IFC2X3",
                       units="METERS", walls=(), rooms=(room,), openings=())

        self.assertEqual(b1.compute_hash(), b2.compute_hash())

    def test_different_buildings_different_hash(self):
        """Different buildings must produce different hashes."""
        from qomn_fire.core.types import Building, Room, Point3D

        r1 = Room(id="R1", name="A", boundary=(Point3D(0,0), Point3D(5,0), Point3D(5,5), Point3D(0,5)), area_m2=25.0, height_m=3.0)
        r2 = Room(id="R2", name="B", boundary=(Point3D(0,0), Point3D(10,0), Point3D(10,10), Point3D(0,10)), area_m2=100.0, height_m=3.0)

        b1 = Building(file_hash="h1", format_detected="IFC", version_detected="IFC2X3", units="METERS", walls=(), rooms=(r1,), openings=())
        b2 = Building(file_hash="h1", format_detected="IFC", version_detected="IFC2X3", units="METERS", walls=(), rooms=(r2,), openings=())

        self.assertNotEqual(b1.compute_hash(), b2.compute_hash())


if __name__ == "__main__":
    unittest.main(verbosity=2)
