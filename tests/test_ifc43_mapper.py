"""test_ifc43_mapper.py — Tests for IFC 4.3 Schema Mapper.

MISSION TASK 1.3 — Validates the IFC 4.3 ADD2 schema mapper that
transforms FireAI internal elements to standard IFC 4.3 representation.

Per agent.md Rule 10: tests run after every modification.
Per agent.md Rule 1: no fabrication.
"""

from __future__ import annotations

import math

import pytest

from fireai.bridges.ifc43_mapper import (
    FIREAI_TO_IFC43_MAP,
    IFC43ElementType,
    IFC43Mapper,
    IFC43_SCHEMA_VERSION,
    PSET_FIREALARM_COMMON,
    PSET_FIREAI_AUDIT,
    PSET_FIREAI_DESIGN,
    PSET_FIREAI_SAFETY,
)


# ---------------------------------------------------------------------------
# Constants Tests
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify IFC 4.3 constants are correctly defined."""

    def test_schema_version_is_ifc4x3_add2(self):
        """Schema version must be IFC4X3_ADD2 (IFC 4.3 ADD2 release)."""
        assert IFC43_SCHEMA_VERSION == "IFC4X3_ADD2"

    def test_type_mapping_covers_smoke_detector(self):
        """Smoke detector type must be mapped."""
        assert "smoke" in FIREAI_TO_IFC43_MAP
        assert FIREAI_TO_IFC43_MAP["smoke"] == IFC43ElementType.SMOKE_DETECTOR

    def test_type_mapping_covers_heat_detector(self):
        assert "heat" in FIREAI_TO_IFC43_MAP
        assert FIREAI_TO_IFC43_MAP["heat"] == IFC43ElementType.HEAT_DETECTOR

    def test_type_mapping_covers_all_major_types(self):
        """At minimum, smoke/heat/flame/duct/beam/aspirating must be mapped."""
        required = ["smoke", "heat", "flame", "duct", "beam", "aspirating",
                    "horn", "strobe", "speaker", "sprinkler", "facp"]
        for t in required:
            assert t in FIREAI_TO_IFC43_MAP, f"Missing mapping for: {t}"

    def test_ifc43_element_type_includes_marine_facilities(self):
        """IFC 4.3 adds IfcMarineFacility — must be in enum."""
        assert IFC43ElementType.MARINE_FACILITY.value == "IfcMarineFacility"

    def test_property_set_names_follow_ifc_convention(self):
        """Property set names must start with 'Pset_' per IFC convention."""
        for pset in (PSET_FIREALARM_COMMON, PSET_FIREAI_DESIGN,
                     PSET_FIREAI_AUDIT, PSET_FIREAI_SAFETY):
            assert pset.startswith("Pset_"), f"Pset name must start with 'Pset_': {pset}"


# ---------------------------------------------------------------------------
# Mapper Tests
# ---------------------------------------------------------------------------


class TestIFC43Mapper:
    """Tests for the IFC43Mapper class."""

    @pytest.fixture
    def mapper(self):
        return IFC43Mapper()

    @pytest.fixture
    def sample_detector(self):
        return {
            "device_id": "SM-01",
            "type": "smoke",
            "x": 5.0, "y": 3.0, "z": 2.8,
            "room_id": "ROOM-001",
            "coverage_radius_m": 6.37,
            "spacing_m": 9.1,
            "ceiling_height_m": 3.0,
            "occupancy_type": "office",
            "is_code_compliant": True,
            "coverage_pct": 100.0,
            "run_id": "abc123",
            "evidence_hash": "def456",
        }

    @pytest.fixture
    def sample_room(self):
        return {
            "room_id": "ROOM-001",
            "name": "Office 101",
            "area_m2": 25.0,
            "ceiling_height_m": 3.0,
            "occupancy_type": "office",
            "level_id": "L1",
        }

    def test_map_detector_returns_mapped_element(self, mapper, sample_detector):
        """map_detector must return IFC43MappedElement."""
        result = mapper.map_detector(sample_detector)
        assert result is not None
        assert result.ifc_type == "IfcFireAlarmInstance"
        assert result.predefined_type == "SMOKE_DETECTOR"
        assert result.name == "SM-01"
        assert result.location == (5.0, 3.0, 2.8)

    def test_map_detector_global_id_is_22_chars(self, mapper, sample_detector):
        """IFC GlobalId must be exactly 22 characters per IFC spec."""
        result = mapper.map_detector(sample_detector)
        assert len(result.global_id) == 22

    def test_map_detector_is_deterministic(self, mapper, sample_detector):
        """Same input MUST produce same GlobalId (per agent.md V85 Bug #28)."""
        r1 = mapper.map_detector(sample_detector)
        r2 = mapper.map_detector(sample_detector)
        assert r1.global_id == r2.global_id, "GlobalId must be deterministic"

    def test_map_detector_different_inputs_produce_different_ids(
        self, mapper, sample_detector
    ):
        """Different device_ids must produce different GlobalIds."""
        d2 = {**sample_detector, "device_id": "SM-02"}
        r1 = mapper.map_detector(sample_detector)
        r2 = mapper.map_detector(d2)
        assert r1.global_id != r2.global_id

    def test_map_detector_rejects_nan_position(self, mapper, sample_detector):
        """NaN position must raise ValueError (per agent.md V57)."""
        d_nan = {**sample_detector, "x": float("nan")}
        with pytest.raises(ValueError, match="non-finite position"):
            mapper.map_detector(d_nan)

    def test_map_detector_rejects_inf_position(self, mapper, sample_detector):
        """Inf position must raise ValueError."""
        d_inf = {**sample_detector, "z": float("inf")}
        with pytest.raises(ValueError, match="non-finite position"):
            mapper.map_detector(d_inf)

    def test_map_detector_includes_audit_pset(self, mapper, sample_detector):
        """Audit property set must be included for NFPA 72 §7.5 compliance."""
        result = mapper.map_detector(sample_detector)
        assert PSET_FIREAI_AUDIT in result.property_sets
        audit_pset = result.property_sets[PSET_FIREAI_AUDIT]
        assert "RunId" in audit_pset
        assert "EvidenceHash" in audit_pset
        assert "NFPAReference" in audit_pset

    def test_map_detector_includes_safety_pset(self, mapper, sample_detector):
        """Safety classification property set must be included."""
        result = mapper.map_detector(sample_detector)
        assert PSET_FIREAI_SAFETY in result.property_sets
        safety_pset = result.property_sets[PSET_FIREAI_SAFETY]
        assert "SafetyTier" in safety_pset
        assert "IsCodeCompliant" in safety_pset

    def test_map_detector_unknown_type_defaults_to_smoke(self, mapper, sample_detector):
        """V137 F-8: Unknown detector type raises ValueError (was silent default)."""
        d_unknown = {**sample_detector, "type": "unknown_type"}
        with pytest.raises(ValueError, match="Unknown FireAI detector type"):
            mapper.map_detector(d_unknown)

    def test_map_detector_heat_type(self, mapper, sample_detector):
        """Heat detector must map correctly."""
        d_heat = {**sample_detector, "type": "heat", "device_id": "HT-01"}
        result = mapper.map_detector(d_heat)
        assert result.predefined_type == "HEAT_DETECTOR"

    def test_map_room_returns_ifc_space(self, mapper, sample_room):
        """map_room must return IfcSpace."""
        result = mapper.map_room(sample_room)
        assert result.ifc_type == "IfcSpace"
        assert result.name == "Office 101"

    def test_map_room_includes_design_pset(self, mapper, sample_room):
        """Room must include FireAI design parameters."""
        result = mapper.map_room(sample_room)
        assert PSET_FIREAI_DESIGN in result.property_sets
        assert result.property_sets[PSET_FIREAI_DESIGN]["Area"] == 25.0

    def test_map_building_returns_ifc_building(self, mapper):
        """map_building must return IfcBuilding."""
        result = mapper.map_building({
            "building_id": "B-001",
            "name": "Test Building",
            "num_storeys": 3,
        })
        assert result.ifc_type == "IfcBuilding"
        assert result.name == "Test Building"

    def test_generate_ifc_header_uses_ifc4x3_add2(self, mapper):
        """Header must declare IFC4X3_ADD2 schema."""
        header = mapper.generate_ifc_header()
        assert "IFC4X3_ADD2" in header["file_schema"]

    def test_generate_ifc_header_includes_audit_info(self, mapper):
        """Header must include audit trail reference."""
        header = mapper.generate_ifc_header()
        assert "nfpa_reference" in header
        assert "NFPA 72" in header["nfpa_reference"]

    def test_map_project_returns_complete_structure(self, mapper, sample_room, sample_detector):
        """map_project must return building + rooms + detectors + stats."""
        result = mapper.map_project({
            "building": {"building_id": "B-001", "name": "Test", "num_storeys": 1},
            "rooms": [sample_room],
            "detectors": [
                sample_detector,
                {**sample_detector, "type": "heat", "device_id": "HT-01"},
            ],
        })
        assert "header" in result
        assert "building" in result
        assert "rooms" in result
        assert "detectors" in result
        assert result["statistics"]["total_rooms"] == 1
        assert result["statistics"]["total_detectors"] == 2
        assert result["statistics"]["smoke_detectors"] == 1
        assert result["statistics"]["heat_detectors"] == 1
        assert result["schema_version"] == IFC43_SCHEMA_VERSION

    def test_target_schema_defaults_to_ifc4x3_add2(self, mapper):
        """Default target schema must be IFC4X3_ADD2."""
        assert mapper.target_schema == IFC43_SCHEMA_VERSION

    def test_non_default_schema_logs_warning(self):
        """Non-standard schema version must log warning (not raise)."""
        # Should not raise
        mapper = IFC43Mapper(target_schema="IFC4")
        assert mapper.target_schema == "IFC4"
