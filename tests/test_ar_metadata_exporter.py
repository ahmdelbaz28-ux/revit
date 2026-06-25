"""test_ar_metadata_exporter.py — Tests for AR Metadata Exporter.

MISSION TASK 4.2 — Validates GLB/USDZ export with behind-the-wall metadata.
"""

from __future__ import annotations

import io
import struct
import zipfile

import pytest

from fireai.integration.ar_metadata_exporter import (
    ARExportFormat,
    ARMetadataExporter,
    ARSceneNode,
    ARSnapshot,
    ARVisibilityMode,
    GLB_CHUNK_BIN,
    GLB_CHUNK_JSON,
    GLTF_MAGIC,
    GLTF_VERSION,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def exporter():
    return ARMetadataExporter()


@pytest.fixture
def sample_snapshot():
    return ARSnapshot(
        building_id="B-001",
        nodes=[
            ARSceneNode(
                id="SM-01", name="Smoke Detector 01", node_type="detector",
                position=(5.0, 3.0, 2.8),
                is_behind_wall=False,
                inspection_critical=True,
            ),
            ARSceneNode(
                id="SM-02", name="Smoke Detector 02", node_type="detector",
                position=(8.0, 3.0, 2.8),
                is_behind_wall=True,
            ),
            ARSceneNode(
                id="WALL-01", name="Wall 01", node_type="wall",
                position=(5.0, 5.0, 1.5),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Scene Node Tests
# ---------------------------------------------------------------------------


class TestARSceneNode:
    def test_node_creation_default_x_ray_off(self):
        """SAFETY-R3: x_ray_enabled MUST default to False."""
        node = ARSceneNode(id="test", name="test", node_type="detector")
        assert node.x_ray_enabled is False

    def test_node_nan_position_rejected(self):
        with pytest.raises(ValueError, match="not finite"):
            ARSceneNode(id="test", name="test", node_type="detector",
                        position=(float("nan"), 0, 0))

    def test_node_nan_rotation_rejected(self):
        with pytest.raises(ValueError, match="not finite"):
            ARSceneNode(id="test", name="test", node_type="detector",
                        rotation=(float("nan"), 0, 0, 1))

    def test_to_gltf_dict_includes_extras(self):
        node = ARSceneNode(
            id="test", name="Test", node_type="detector",
            is_behind_wall=True,
            inspection_critical=True,
        )
        d = node.to_gltf_dict()
        assert "extras" in d
        assert d["extras"]["is_behind_wall"] is True
        assert d["extras"]["inspection_critical"] is True
        assert d["extras"]["x_ray_enabled"] is False
        assert d["extras"]["safety_classification"] == "TIER_2"

    def test_to_gltf_dict_includes_translation(self):
        node = ARSceneNode(
            id="test", name="Test", node_type="detector",
            position=(1.0, 2.0, 3.0),
        )
        d = node.to_gltf_dict()
        assert d["translation"] == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# Snapshot Tests
# ---------------------------------------------------------------------------


class TestARSnapshot:
    def test_node_count(self, sample_snapshot):
        assert sample_snapshot.node_count == 3

    def test_behind_wall_count(self, sample_snapshot):
        assert sample_snapshot.behind_wall_count == 1

    def test_inspection_critical_count(self, sample_snapshot):
        assert sample_snapshot.inspection_critical_count == 1

    def test_to_dict_serializes_all_nodes(self, sample_snapshot):
        d = sample_snapshot.to_dict()
        assert d["node_count"] == 3
        assert len(d["nodes"]) == 3
        assert d["nodes"][0]["id"] == "SM-01"


# ---------------------------------------------------------------------------
# GLB Export Tests
# ---------------------------------------------------------------------------


class TestGLBExport:
    def test_glb_starts_with_magic(self, exporter, sample_snapshot):
        glb = exporter.export_glb(sample_snapshot)
        magic = struct.unpack("<I", glb[0:4])[0]
        assert magic == GLTF_MAGIC

    def test_glb_version_is_2(self, exporter, sample_snapshot):
        glb = exporter.export_glb(sample_snapshot)
        version = struct.unpack("<I", glb[4:8])[0]
        assert version == GLTF_VERSION

    def test_glb_total_length_matches_actual(self, exporter, sample_snapshot):
        glb = exporter.export_glb(sample_snapshot)
        declared_length = struct.unpack("<I", glb[8:12])[0]
        assert declared_length == len(glb)

    def test_glb_has_json_chunk(self, exporter, sample_snapshot):
        glb = exporter.export_glb(sample_snapshot)
        # After 12-byte header, chunk header is 8 bytes
        chunk_length = struct.unpack("<I", glb[12:16])[0]
        chunk_type = struct.unpack("<I", glb[16:20])[0]
        assert chunk_type == GLB_CHUNK_JSON
        assert chunk_length > 0

    def test_glb_has_bin_chunk(self, exporter, sample_snapshot):
        glb = exporter.export_glb(sample_snapshot)
        # Parse JSON chunk first
        json_length = struct.unpack("<I", glb[12:16])[0]
        # Bin chunk starts after header (12) + json chunk header (8) + json data
        bin_offset = 12 + 8 + json_length
        bin_length = struct.unpack("<I", glb[bin_offset:bin_offset+4])[0]
        bin_type = struct.unpack("<I", glb[bin_offset+4:bin_offset+8])[0]
        assert bin_type == GLB_CHUNK_BIN

    def test_glb_is_valid_bytes(self, exporter, sample_snapshot):
        """GLB must be non-empty bytes."""
        glb = exporter.export_glb(sample_snapshot)
        assert isinstance(glb, bytes)
        assert len(glb) > 0


# ---------------------------------------------------------------------------
# USDZ Export Tests
# ---------------------------------------------------------------------------


class TestUSDZExport:
    def test_usdz_is_valid_zip(self, exporter, sample_snapshot):
        """USDZ must be a valid zip archive."""
        usdz = exporter.export_usdz(sample_snapshot)
        assert isinstance(usdz, bytes)
        # Zip files start with PK (0x50 0x4B)
        assert usdz[:2] == b"PK"

        # Verify it can be opened as a zip
        zf = zipfile.ZipFile(io.BytesIO(usdz))
        assert len(zf.namelist()) > 0

    def test_usdz_first_file_is_usda(self, exporter, sample_snapshot):
        """USDZ spec: first file must be the .usda scene file."""
        usdz = exporter.export_usdz(sample_snapshot)
        zf = zipfile.ZipFile(io.BytesIO(usdz))
        first_file = zf.namelist()[0]
        assert first_file.endswith(".usda")

    def test_usdz_uses_no_compression(self, exporter, sample_snapshot):
        """USDZ spec: files must be stored (no compression)."""
        usdz = exporter.export_usdz(sample_snapshot)
        zf = zipfile.ZipFile(io.BytesIO(usdz))
        for info in zf.infolist():
            assert info.compress_type == zipfile.ZIP_STORED, (
                f"File {info.filename} uses compression {info.compress_type}, "
                "USDZ requires ZIP_STORED (no compression)"
            )

    def test_usda_starts_with_usda_header(self, exporter, sample_snapshot):
        """USDA file must start with '#usda 1.0'."""
        usdz = exporter.export_usdz(sample_snapshot)
        zf = zipfile.ZipFile(io.BytesIO(usdz))
        usda_content = zf.read(zf.namelist()[0]).decode("utf-8")
        assert usda_content.startswith("#usda 1.0")

    def test_usda_includes_building_id(self, exporter, sample_snapshot):
        usdz = exporter.export_usdz(sample_snapshot)
        zf = zipfile.ZipFile(io.BytesIO(usdz))
        usda_content = zf.read(zf.namelist()[0]).decode("utf-8")
        assert "B-001" in usda_content

    def test_usda_includes_behind_wall_metadata(self, exporter, sample_snapshot):
        """USDA must include is_behind_wall attribute on nodes."""
        usdz = exporter.export_usdz(sample_snapshot)
        zf = zipfile.ZipFile(io.BytesIO(usdz))
        usda_content = zf.read(zf.namelist()[0]).decode("utf-8")
        assert "is_behind_wall" in usda_content

    def test_usda_includes_x_ray_metadata(self, exporter, sample_snapshot):
        """USDA must include x_ray_enabled attribute (default False per SAFETY-R3)."""
        usdz = exporter.export_usdz(sample_snapshot)
        zf = zipfile.ZipFile(io.BytesIO(usdz))
        usda_content = zf.read(zf.namelist()[0]).decode("utf-8")
        assert "x_ray_enabled" in usda_content
        # Verify default is false
        assert "x_ray_enabled = false" in usda_content


# ---------------------------------------------------------------------------
# Combined Export Tests
# ---------------------------------------------------------------------------


class TestCombinedExport:
    def test_export_both_returns_both_formats(self, exporter, sample_snapshot):
        result = exporter.export(sample_snapshot, ARExportFormat.BOTH)
        assert "glb" in result
        assert "usdz" in result

    def test_export_glb_only(self, exporter, sample_snapshot):
        result = exporter.export(sample_snapshot, ARExportFormat.GLB)
        assert "glb" in result
        assert "usdz" not in result

    def test_export_usdz_only(self, exporter, sample_snapshot):
        result = exporter.export(sample_snapshot, ARExportFormat.USDZ)
        assert "usdz" in result
        assert "glb" not in result


# ---------------------------------------------------------------------------
# Safety Tests (SAFETY-R3)
# ---------------------------------------------------------------------------


class TestSafetyR3:
    """Per VERIFY-TASK4 SAFETY-R3: x-ray must NEVER default ON."""

    def test_default_x_ray_is_false(self):
        node = ARSceneNode(id="t", name="t", node_type="detector")
        assert node.x_ray_enabled is False

    def test_exporter_default_x_ray_is_false(self):
        e = ARMetadataExporter()
        assert e.default_x_ray is False

    def test_exporter_warns_when_x_ray_enabled(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            ARMetadataExporter(default_x_ray=True)
        assert any("SAFETY-R3" in r.message for r in caplog.records)

    def test_all_nodes_have_x_ray_off_by_default(self, exporter, sample_snapshot):
        for node in sample_snapshot.nodes:
            assert node.x_ray_enabled is False, (
                f"Node {node.id} has x_ray_enabled=True by default — SAFETY-R3 violation"
            )


# ---------------------------------------------------------------------------
# DigitalTwin Adapter Tests
# ---------------------------------------------------------------------------


class TestDigitalTwinAdapter:
    def test_from_digital_twin_with_empty_twin(self, exporter):
        """Empty DigitalTwin should produce empty snapshot."""
        class FakeTwin:
            building_id = "B-TEST"
            _detectors = {}
            _room_ids = set()

        snapshot = exporter.from_digital_twin(FakeTwin())
        assert snapshot.building_id == "B-TEST"
        assert snapshot.node_count == 0

    def test_from_digital_twin_with_detectors(self, exporter):
        class FakeDetectorState:
            # V134 F-4: Use correct field names (x, y, z — not x_m, y_m, z_m)
            x = 5.0
            y = 3.0
            z = 2.8
            detector_type = "smoke"
            # V134 F-4: AR exporter now reads metadata dict (not direct attrs)
            metadata = {
                "is_concealed": False,
                "safety_tier": "TIER_1",
                "requires_inspection": True,
            }
            room_id = "R-001"
            status = "OK"  # DetectorStatus.OK equivalent

        class FakeTwin:
            building_id = "B-TEST"
            _detectors = {"SM-01": FakeDetectorState()}
            _room_ids = {"R-001"}

        snapshot = exporter.from_digital_twin(FakeTwin())
        assert snapshot.node_count == 2  # 1 detector + 1 wall

        detector_node = next(n for n in snapshot.nodes if n.node_type == "detector")
        assert detector_node.id == "SM-01"
        # V134 F-4: Position now correctly extracted (was (0,0,0) before fix)
        assert detector_node.position == (5.0, 3.0, 2.8)
        assert detector_node.inspection_critical is True
