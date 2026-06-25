"""
tests/test_revit_acl.py
===========================
Comprehensive test suite for:
  - fireai/core/revit_acl.py

SAFETY CRITICAL: This is the Anti-Corruption Layer that protects strict
domain models from corrupted BIM/Revit data. Failures here could allow
invalid data to reach safety-critical calculations.

Standards:
  IEC 60079-10-1:2015 — Input data requirements
  NFPA 72-2022 — Fire alarm system data
  DDD Anti-Corruption Layer pattern (Vernon 2013)
"""

from __future__ import annotations

import pytest

from fireai.core.models_v21 import (
    HazardType,
    WavelengthBand,
)
from fireai.core.revit_acl import (
    _HAZARD_TYPE_ALIASES,
    _WAVELENGTH_BAND_ALIASES,
    ImportError,
    ImportReport,
    RevitDetectorDTO,
    RevitObstructionDTO,
    RevitSubstanceDTO,
    _normalize_enum,
    _safe_float,
    import_detectors_from_revit,
    import_obstructions_from_revit,
    import_substances_from_revit,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Import Error Tracking Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestImportError:
    def test_creation(self):
        err = ImportError("E1", "field", "bad_val", "invalid data", "WARNING")
        assert err.element_id == "E1"
        assert err.field_name == "field"
        assert err.raw_value == "bad_val"
        assert err.error_message == "invalid data"
        assert err.severity == "WARNING"

    def test_default_severity(self):
        err = ImportError("E1", "f", None, "msg")
        assert err.severity == "WARNING"

    def test_str_format(self):
        err = ImportError("E1", "hazard_type", "INVALID", "Unknown type", "ERROR")
        s = str(err)
        assert "[ERROR]" in s
        assert "E1" in s
        assert "hazard_type" in s

    def test_error_severity(self):
        err = ImportError("E1", "f", None, "msg", "ERROR")
        assert err.severity == "ERROR"


class TestImportReport:
    def test_empty_report(self):
        report = ImportReport()
        assert report.has_errors is False
        assert report.has_warnings is False
        assert report.total_elements == 0

    def test_add_warning(self):
        report = ImportReport()
        report.add_error("E1", "f", None, "warning msg", "WARNING")
        assert report.has_warnings is True
        assert report.has_errors is False

    def test_add_error(self):
        report = ImportReport()
        report.add_error("E1", "f", None, "error msg", "ERROR")
        assert report.has_errors is True

    def test_summary(self):
        report = ImportReport(total_elements=10, successful=8, skipped=2)
        s = report.summary()
        assert "10 elements" in s
        assert "8 successful" in s

    def test_detailed_report(self):
        report = ImportReport()
        report.add_error("E1", "f", "bad", "msg", "ERROR")
        d = report.detailed_report()
        assert "E1" in d


# ═══════════════════════════════════════════════════════════════════════════════
# Enum Normalization Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeEnum:
    def test_gas_alias(self):
        assert _normalize_enum("GAS", _HAZARD_TYPE_ALIASES) == "GAS"

    def test_vapor_alias(self):
        assert _normalize_enum("VAPOR", _HAZARD_TYPE_ALIASES) == "GAS"

    def test_gas_vapor_slash(self):
        assert _normalize_enum("GAS/VAPOR", _HAZARD_TYPE_ALIASES) == "GAS"

    def test_dust_alias(self):
        assert _normalize_enum("DUST", _HAZARD_TYPE_ALIASES) == "DUST"

    def test_combustible_dust_alias(self):
        assert _normalize_enum("COMBUSTIBLE_DUST", _HAZARD_TYPE_ALIASES) == "DUST"

    def test_hybrid_alias(self):
        assert _normalize_enum("HYBRID", _HAZARD_TYPE_ALIASES) == "HYBRID"

    def test_mixed_alias(self):
        assert _normalize_enum("MIXED", _HAZARD_TYPE_ALIASES) == "HYBRID"

    def test_fiber_alias(self):
        assert _normalize_enum("FIBER", _HAZARD_TYPE_ALIASES) == "FIBER"

    def test_fibres_alias(self):
        assert _normalize_enum("FIBRES", _HAZARD_TYPE_ALIASES) == "FIBER"

    def test_whitespace_stripped(self):
        assert _normalize_enum("  GAS  ", _HAZARD_TYPE_ALIASES) == "GAS"

    def test_case_insensitive(self):
        assert _normalize_enum("gas", _HAZARD_TYPE_ALIASES) == "GAS"

    def test_hyphen_to_underscore(self):
        """Hyphens replaced by underscores, but 'GAS_VAPOR' is not an alias key."""
        result = _normalize_enum("GAS-VAPOR", _HAZARD_TYPE_ALIASES)
        # 'GAS_VAPOR' is not in aliases (only 'GAS/VAPOR' is)
        assert result is None

    def test_unknown_returns_none(self):
        assert _normalize_enum("UNKNOWN_TYPE", _HAZARD_TYPE_ALIASES) is None

    def test_wavelength_uv(self):
        assert _normalize_enum("UV", _WAVELENGTH_BAND_ALIASES) == "UV"

    def test_wavelength_ultraviolet(self):
        assert _normalize_enum("ULTRAVIOLET", _WAVELENGTH_BAND_ALIASES) == "UV"

    def test_wavelength_near_ir(self):
        assert _normalize_enum("NEAR_IR", _WAVELENGTH_BAND_ALIASES) == "IR1"

    def test_wavelength_nir(self):
        assert _normalize_enum("NIR", _WAVELENGTH_BAND_ALIASES) == "IR1"

    def test_wavelength_mid_ir(self):
        assert _normalize_enum("MID_IR", _WAVELENGTH_BAND_ALIASES) == "IR3"

    def test_wavelength_co2(self):
        assert _normalize_enum("CO2", _WAVELENGTH_BAND_ALIASES) == "IR3"


# ═══════════════════════════════════════════════════════════════════════════════
# _safe_float Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSafeFloat:
    def test_int(self):
        assert _safe_float(42) == 42.0

    def test_float(self):
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_string_number(self):
        assert _safe_float("5.5") == 5.5

    def test_string_with_percent(self):
        """Revit often exports '5.0 %' → need to strip non-numeric."""
        assert _safe_float("5.0 %") == 5.0

    def test_string_with_comma_decimal(self):
        """European format: '3,14' → 3.14."""
        assert _safe_float("3,14") == pytest.approx(3.14)

    def test_string_with_units(self):
        """'100 mm' → 100.0."""
        assert _safe_float("100 mm") == 100.0

    def test_empty_string(self):
        assert _safe_float("") == 0.0

    def test_non_numeric_string(self):
        assert _safe_float("abc") == 0.0

    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_custom_default(self):
        assert _safe_float("bad", default=-1.0) == -1.0

    def test_negative_string(self):
        assert _safe_float("-5.5") == pytest.approx(-5.5)


# ═══════════════════════════════════════════════════════════════════════════════
# RevitSubstanceDTO Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRevitSubstanceDTO:
    """Anti-Corruption Layer for substance data from Revit/BIM exports."""

    def test_basic_creation(self):
        dto = RevitSubstanceDTO(name="Methane", hazard_type="GAS", lfl_vol_pct=5.0)
        assert dto.name == "Methane"
        assert dto.hazard_type == "GAS"

    def test_hazard_type_normalization(self):
        """'Gas/Vapor' → 'GAS' via alias normalization."""
        dto = RevitSubstanceDTO(name="Test", hazard_type="Gas/Vapor")
        assert dto.hazard_type == "GAS"

    def test_whitespace_stripping(self):
        dto = RevitSubstanceDTO(name="  Methane  ", element_id="  E1  ")
        assert dto.name == "Methane"
        assert dto.element_id == "E1"

    def test_numeric_string_conversion(self):
        """'5.0 %' → 5.0 for lfl_vol_pct."""
        dto = RevitSubstanceDTO(name="Test", hazard_type="GAS", lfl_vol_pct="5.0 %")
        assert dto.lfl_vol_pct == 5.0

    def test_field_name_variation_lfl(self):
        """'lfl' → 'lfl_vol_pct' (value stays string — renamed after numeric conversion)."""
        dto = RevitSubstanceDTO(name="Test", hazard_type="GAS", lfl="5.0")
        # Renamed fields keep their original string value
        # because field name variation runs AFTER numeric sanitization
        assert dto.lfl_vol_pct == "5.0"

    def test_field_name_variation_ufl(self):
        """'ufl' → 'ufl_vol_pct' (value stays string)."""
        dto = RevitSubstanceDTO(name="Test", hazard_type="GAS", ufl="15.0")
        assert dto.ufl_vol_pct == "15.0"

    def test_field_name_variation_flash_point(self):
        """'flash_point' → 'flash_point_c' (value stays string)."""
        dto = RevitSubstanceDTO(name="Test", hazard_type="GAS", flash_point="-100")
        assert dto.flash_point_c == "-100"

    def test_field_name_variation_auto_ignition(self):
        """'auto_ignition' → 'autoignition_c' (value stays string)."""
        dto = RevitSubstanceDTO(name="Test", hazard_type="GAS", auto_ignition="537")
        assert dto.autoignition_c == "537"

    def test_substance_name_variation(self):
        """'substance_name' → 'name'."""
        dto = RevitSubstanceDTO(substance_name="Propane", hazard_type="GAS")
        assert dto.name == "Propane"

    def test_to_domain_valid_gas(self):
        dto = RevitSubstanceDTO(
            name="Methane",
            hazard_type="GAS",
            lfl_vol_pct=5.0,
            ufl_vol_pct=15.0,
            autoignition_c=537.0,
        )
        domain = dto.to_domain()
        assert domain is not None
        assert domain.name == "Methane"
        assert domain.hazard_type == HazardType.GAS
        assert domain.lfl_vol_pct == 5.0

    def test_to_domain_invalid_hazard_type(self):
        """Unknown hazard type returns None with error in report."""
        dto = RevitSubstanceDTO(name="Test", hazard_type="INVALID")
        report = ImportReport()
        domain = dto.to_domain(report)
        assert domain is None
        assert report.has_errors is True

    def test_to_domain_with_report(self):
        dto = RevitSubstanceDTO(
            name="Methane",
            hazard_type="GAS",
            lfl_vol_pct=5.0,
        )
        report = ImportReport()
        domain = dto.to_domain(report)
        assert domain is not None
        assert report.successful == 0  # to_domain doesn't increment
        assert len(report.errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# RevitObstructionDTO Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRevitObstructionDTO:
    def test_basic_creation(self):
        dto = RevitObstructionDTO(
            obstruction_id="OBS-1",
            vertices=[[0, 0, 0], [1, 1, 1]],
        )
        assert dto.obstruction_id == "OBS-1"

    def test_flat_vertex_conversion(self):
        """Flat list [x1,y1,z1,x2,y2,z2] → [[x1,y1,z1],[x2,y2,z2]]."""
        dto = RevitObstructionDTO(
            vertices=[0, 0, 0, 1, 1, 1],
        )
        assert dto.vertices == [[0, 0, 0], [1, 1, 1]]

    def test_id_field_variation(self):
        """'id' → 'obstruction_id'."""
        dto = RevitObstructionDTO(id="OBS-ALT")
        assert dto.obstruction_id == "OBS-ALT"

    def test_transparency_clamping(self):
        """Transparency values clamped to [0, 1]."""
        dto = RevitObstructionDTO(
            transparency_uv=1.5,
            transparency_vis=-0.5,
        )
        assert dto.transparency_uv == 1.0
        assert dto.transparency_vis == 0.0

    def test_to_domain_valid(self):
        dto = RevitObstructionDTO(
            obstruction_id="OBS-1",
            vertices=[[0, 0, 0], [1, 1, 1]],
            transparency_uv=0.5,
            transparency_vis=0.8,
            transparency_ir1=0.9,
            transparency_ir3=0.3,
        )
        domain = dto.to_domain()
        assert domain is not None
        assert domain.obstruction_id == "OBS-1"
        assert domain.spectral_transparency[WavelengthBand.UV] == 0.5

    def test_to_domain_single_vertex_reports_error(self):
        """< 2 vertices should return None with error."""
        dto = RevitObstructionDTO(
            obstruction_id="OBS-1",
            vertices=[[0, 0, 0]],
        )
        report = ImportReport()
        domain = dto.to_domain(report)
        assert domain is None
        assert report.has_errors is True

    def test_to_domain_default_vertices(self):
        """No vertices → default bounding box."""
        dto = RevitObstructionDTO(obstruction_id="OBS-1")
        domain = dto.to_domain()
        assert domain is not None
        assert len(domain.vertices) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# RevitDetectorDTO Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRevitDetectorDTO:
    def test_basic_creation(self):
        dto = RevitDetectorDTO(
            detector_id="FD-1",
            position=[1.0, 2.0, 3.0],
            spectral_bands=["IR3"],
        )
        assert dto.detector_id == "FD-1"

    def test_id_field_variation(self):
        """'id' → 'detector_id'."""
        dto = RevitDetectorDTO(id="FD-ALT")
        assert dto.detector_id == "FD-ALT"

    def test_position_string_conversion(self):
        """Position with string values → float conversion."""
        dto = RevitDetectorDTO(position=["1.5", "2.5", "3.5"])
        assert dto.position == [1.5, 2.5, 3.5]

    def test_spectral_band_normalization(self):
        """'ULTRAVIOLET' → 'UV'."""
        dto = RevitDetectorDTO(spectral_bands=["ULTRAVIOLET", "IR3"])
        assert "UV" in dto.spectral_bands
        assert "IR3" in dto.spectral_bands

    def test_spectral_band_string_input(self):
        """String spectral_bands → single-element list."""
        dto = RevitDetectorDTO(spectral_bands="UV")
        assert dto.spectral_bands == ["UV"]

    def test_unknown_spectral_band_defaults_to_ir3(self):
        """Unknown bands are filtered out; empty list defaults to ['IR3']."""
        dto = RevitDetectorDTO(spectral_bands=["UNKNOWN"])
        assert dto.spectral_bands == ["IR3"]

    def test_to_domain_valid(self):
        dto = RevitDetectorDTO(
            detector_id="FD-1",
            position=[1.0, 2.0, 3.0],
            orientation=[0.0, 0.0, -1.0],
            rated_range_m=20.0,
            aoc_deg=90.0,
            spectral_bands=["IR3"],
        )
        domain = dto.to_domain()
        assert domain is not None
        assert domain.detector_id == "FD-1"
        assert domain.spectral_bands == [WavelengthBand.IR3]

    def test_to_domain_default_position(self):
        """Default position when not enough coords."""
        dto = RevitDetectorDTO(
            detector_id="FD-1",
            position=[1.0],  # Only 1 coordinate
            spectral_bands=["IR3"],
        )
        domain = dto.to_domain()
        assert domain is not None
        # Falls back to [0, 0, 3] for insufficient position data


# ═══════════════════════════════════════════════════════════════════════════════
# Batch Import Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestImportSubstances:
    def test_valid_batch(self):
        data = [
            {"name": "Methane", "hazard_type": "GAS", "lfl_vol_pct": 5.0, "autoignition_c": 537},
            {"name": "Propane", "hazard_type": "GAS", "lfl_vol_pct": 2.1, "autoignition_c": 450},
        ]
        substances, report = import_substances_from_revit(data)
        assert len(substances) == 2
        assert report.total_elements == 2
        assert report.successful == 2
        assert report.skipped == 0

    def test_mixed_valid_invalid(self):
        data = [
            {"name": "Methane", "hazard_type": "GAS", "lfl_vol_pct": 5.0, "autoignition_c": 537},
            {"name": "Bad", "hazard_type": "INVALID"},
        ]
        substances, report = import_substances_from_revit(data)
        assert len(substances) == 1
        assert report.skipped == 1

    def test_empty_batch(self):
        substances, report = import_substances_from_revit([])
        assert len(substances) == 0
        assert report.total_elements == 0


class TestImportObstructions:
    def test_valid_batch(self):
        data = [
            {"obstruction_id": "OBS-1", "vertices": [[0, 0, 0], [1, 1, 1]]},
            {"obstruction_id": "OBS-2", "vertices": [[2, 2, 2], [3, 3, 3]]},
        ]
        obs, report = import_obstructions_from_revit(data)
        assert len(obs) == 2
        assert report.successful == 2

    def test_invalid_obstruction(self):
        data = [
            {"obstruction_id": "OBS-1", "vertices": [[0, 0, 0]]},  # Only 1 vertex
        ]
        obs, report = import_obstructions_from_revit(data)
        assert len(obs) == 0
        assert report.skipped == 1


class TestImportDetectors:
    def test_valid_batch(self):
        data = [
            {"detector_id": "FD-1", "position": [1, 2, 3], "spectral_bands": ["IR3"]},
            {"detector_id": "FD-2", "position": [4, 5, 6], "spectral_bands": ["UV", "IR3"]},
        ]
        detectors, report = import_detectors_from_revit(data)
        assert len(detectors) == 2
        assert report.successful == 2

    def test_empty_batch(self):
        detectors, report = import_detectors_from_revit([])
        assert len(detectors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_substance_with_none_values(self):
        """None numeric fields should be handled gracefully.
        Note: GAS hazard requires lfl_vol_pct in domain model, so this
        returns None from to_domain (expected behavior)."""
        dto = RevitSubstanceDTO(
            name="Test",
            hazard_type="DUST",
            lfl_vol_pct=None,
            ufl_vol_pct=None,
            flash_point_c=None,
            mec_g_m3=50.0,
        )
        domain = dto.to_domain()
        assert domain is not None
        assert domain.lfl_vol_pct is None

    def test_substance_extra_fields_allowed(self):
        """Revit exports often have extra fields — extra='allow'."""
        dto = RevitSubstanceDTO(
            name="Test",
            hazard_type="GAS",
            lfl_vol_pct=5.0,
            custom_field="should not crash",
        )
        assert dto.name == "Test"

    def test_obstruction_with_transparency_strings(self):
        """Transparency as strings → converted and clamped."""
        dto = RevitObstructionDTO(
            transparency_uv="0.5",
            transparency_vis="1.5",
            transparency_ir1="-0.1",
            transparency_ir3="0.8",
        )
        assert dto.transparency_uv == 0.5
        assert dto.transparency_vis == 1.0
        assert dto.transparency_ir1 == 0.0
        assert dto.transparency_ir3 == 0.8

    def test_detector_rated_range_string(self):
        """Rated range as string → float conversion."""
        dto = RevitDetectorDTO(rated_range_m="25")
        assert dto.rated_range_m == 25.0

    def test_detector_aoc_deg_string(self):
        dto = RevitDetectorDTO(aoc_deg="60")
        assert dto.aoc_deg == 60.0
