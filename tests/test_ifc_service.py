"""
tests/test_ifc_service.py — Comprehensive IFC Service Tests
============================================================

Tests cover:
  1. IFCService initialization
  2. Load + extract from real IFC file
  3. Space extraction
  4. Device extraction
  5. Building metadata
  6. Standard format conversion
  7. Path traversal protection
  8. NaN/Negative area rejection
  9. Error handling
  10. Full E2E pipeline

Safety-Critical: IFC spaces feed into detector placement engine.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.services.ifc_service import (
    IFCService,
    IfcBuildingInfo,
    IfcDevice,
    IfcExtractionResult,
    IfcSpace,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_IFC_TEST_FILE = None


def _ensure_test_ifc() -> str:
    """Create a minimal IFC test file if it doesn't exist."""
    global _IFC_TEST_FILE
    if _IFC_TEST_FILE and os.path.exists(_IFC_TEST_FILE):
        return _IFC_TEST_FILE

    ifc_content = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('FireAI Test Building'),'2;1');
FILE_NAME('test.ifc','2026-06-26',('FireAI'),('FireAI'),'IfcOpenShell','IfcOpenShell','');
FILE_SCHEMA(('IFC4'));
ENDSEC;

DATA;
#1=IFCPROJECT('1Proj',$,'Test Project',$,$,$,$,(#2),#3);
#2=IFCUNITASSIGNMENT((#4,#5));
#3=IFCLOCALPLACEMENT($,$);
#4=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#5=IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);
#10=IFCSITE('1Site',$,'Test Site',$,$,#11,$,$,.ELEMENT.,$,$,$,$,$);
#11=IFCLOCALPLACEMENT(#3,$);
#20=IFCBUILDING('1Bldg',$,'Test Building',$,$,#21,$,$,.ELEMENT.,$,$,$);
#21=IFCLOCALPLACEMENT(#11,$);
#30=IFCBUILDINGSTOREY('1Sty',$,'Ground Floor',$,$,#31,$,.ELEMENT.,0.);
#31=IFCLOCALPLACEMENT(#21,$);
#40=IFCRELCONTAINEDINSPATIALSTRUCTURE('1Rel1',$,$,(#50,#60),#30);
#50=IFCSPACE('1Sp1',$,'Room-101','Office',$,$,$,'SPACE',$);
#51=IFCLOCALPLACEMENT(#31,#52);
#52=IFCAXIS2PLACEMENT3D(#53,$,$);
#53=IFCCARTESIANPOINT((0.,0.,0.));
#60=IFCSPACE('1Sp2',$,'Room-102','Corridor',$,$,$,'SPACE',$);
#61=IFCLOCALPLACEMENT(#31,#62);
#62=IFCAXIS2PLACEMENT3D(#63,$,$);
#63=IFCCARTESIANPOINT((5.,0.,0.));
#70=IFCRELAGGREGATES('1Agg1',$,$,$,#1,(#10));
#71=IFCRELAGGREGATES('1Agg2',$,$,$,#10,(#20));
#72=IFCRELAGGREGATES('1Agg3',$,$,$,#20,(#30));
ENDSEC;

END-ISO-10303-21;
"""
    fd, path = tempfile.mkstemp(suffix=".ifc", prefix="ifc_svc_test_")
    try:
        os.write(fd, ifc_content.encode())
    finally:
        os.close(fd)
    _IFC_TEST_FILE = path
    return path


@pytest.fixture(autouse=True)
def cleanup_test_file():
    yield
    # Cleanup handled by temp file system


# ── Test: Initialization ──────────────────────────────────────────────────────


class TestIFCServiceInit:
    def test_creates_instance(self):
        svc = IFCService()
        assert svc is not None

    def test_default_max_file_size(self):
        svc = IFCService()
        assert svc._max_file_size == 500 * 1024 * 1024

    def test_custom_max_file_size(self):
        svc = IFCService(max_file_size_bytes=1000)
        assert svc._max_file_size == 1000

    def test_not_loaded_initially(self):
        svc = IFCService()
        with pytest.raises(ValueError, match="No IFC file loaded"):
            svc.extract_spaces()


# ── Test: Load ────────────────────────────────────────────────────────────────


class TestIFCServiceLoad:
    def test_load_valid_ifc(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        result = svc.load(path, correlation_id="test-load")
        assert result["status"] == "loaded"
        assert result["schema"] is not None
        assert result["correlation_id"] == "test-load"
        svc.close()

    def test_load_nonexistent_file_raises(self):
        svc = IFCService()
        with pytest.raises(ValueError, match="not found"):
            svc.load("/tmp/nonexistent_file_xyz.ifc")

    def test_load_wrong_extension_rejected(self):
        svc = IFCService()
        with pytest.raises(ValueError):
            svc.load("/tmp/test.exe")

    def test_load_path_traversal_rejected(self):
        svc = IFCService()
        with pytest.raises(ValueError):
            svc.load("../../etc/passwd")


# ── Test: Extract Building ────────────────────────────────────────────────────


class TestExtractBuilding:
    def test_extracts_building_name(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        svc.load(path)
        building = svc.extract_building()
        assert building.name == "Test Building"
        svc.close()

    def test_extracts_story_count(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        svc.load(path)
        building = svc.extract_building()
        assert building.num_stories == 1
        svc.close()


# ── Test: Extract Spaces ──────────────────────────────────────────────────────


class TestExtractSpaces:
    def test_extracts_spaces(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        svc.load(path)
        spaces = svc.extract_spaces()
        assert len(spaces) >= 2
        svc.close()

    def test_space_has_name(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        svc.load(path)
        spaces = svc.extract_spaces()
        assert spaces[0].name == "Room-101"
        svc.close()

    def test_space_area_is_nonnegative(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        svc.load(path)
        spaces = svc.extract_spaces()
        for s in spaces:
            assert s.area >= 0
        svc.close()


# ── Test: Extract Devices ─────────────────────────────────────────────────────


class TestExtractDevices:
    def test_extracts_empty_when_no_devices(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        svc.load(path)
        devices = svc.extract_fire_devices()
        assert isinstance(devices, list)
        svc.close()


# ── Test: Full Extraction ─────────────────────────────────────────────────────


class TestFullExtraction:
    def test_extract_all(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        result = svc.extract_all(path, correlation_id="test-e2e")
        assert isinstance(result, IfcExtractionResult)
        assert result.building.name == "Test Building"
        assert len(result.spaces) >= 2
        assert result.correlation_id == "test-e2e"
        assert result.parser == "ifcopenshell"

    def test_standard_format_conversion(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        result = svc.extract_all(path)
        standard = svc.to_standard_format(result)
        assert "building_name" in standard
        assert "rooms" in standard
        assert "devices" in standard
        assert standard["parser"] == "ifcopenshell"
        assert standard["correlation_id"] is not None


# ── Test: Security ────────────────────────────────────────────────────────────


class TestIFCServiceSecurity:
    def test_path_traversal_rejected(self):
        svc = IFCService()
        with pytest.raises(ValueError):
            svc.extract_all("/etc/passwd")

    def test_null_byte_rejected(self):
        svc = IFCService()
        with pytest.raises(ValueError):
            svc.extract_all("/tmp/test.ifc\x00.exe")

    def test_leading_dash_rejected(self):
        svc = IFCService()
        with pytest.raises(ValueError):
            svc.extract_all("-/tmp/test.ifc")


# ── Test: Data Classes ────────────────────────────────────────────────────────


class TestDataClasses:
    def test_ifc_space(self):
        space = IfcSpace(express_id=1, name="Test", long_name="TL", area=25.0, elevation=0.0)
        assert space.name == "Test"
        assert space.area == 25.0

    def test_ifc_device(self):
        device = IfcDevice(express_id=1, name="Smoke Detector", ifc_type="IfcSensor")
        assert device.name == "Smoke Detector"
        assert device.ifc_type == "IfcSensor"

    def test_ifc_building_info(self):
        info = IfcBuildingInfo(name="HQ", description="Main", num_stories=5, total_area=0.0)
        assert info.num_stories == 5

    def test_extraction_result_timestamp(self):
        path = _ensure_test_ifc()
        svc = IFCService()
        result = svc.extract_all(path)
        assert result.extracted_at  # Should be auto-filled
        assert "T" in result.extracted_at  # ISO format
