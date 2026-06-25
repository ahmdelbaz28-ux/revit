"""test_v133_phase4_engineering.py — Tests for PHASE 4 Engineering Upgrades.

Validates beam obstruction, BIM unit detection, and Darcy-Weisbach solver.
"""

from __future__ import annotations

import math

import pytest


# ---------------------------------------------------------------------------
# Beam Obstruction Tests (PHASE 4.1)
# ---------------------------------------------------------------------------


class TestBeamObstruction:
    """Tests for NFPA 72 §17.7.3.2.4.2 beam-pocket detection."""

    @pytest.fixture
    def simple_room(self):
        return [(0, 0), (10, 0), (10, 8), (0, 8)]

    def test_no_beams_returns_single_pocket(self, simple_room):
        """Room with no beams should return 1 pocket (whole room)."""
        from fireai.core.spatial_engine.beam_obstruction import (
            calculate_beam_obstruction,
        )
        result = calculate_beam_obstruction(
            room_id="R-001",
            room_polygon=simple_room,
            ceiling_height_m=3.0,
            beams=[],
        )
        assert len(result.pockets) == 1
        assert result.subdivision_applied is False
        assert result.beams_analyzed == 0

    def test_shallow_beams_no_subdivision(self, simple_room):
        """Beams < 10% of ceiling height should NOT subdivide."""
        from fireai.core.spatial_engine.beam_obstruction import (
            Beam,
            calculate_beam_obstruction,
            BEAM_DEPTH_THRESHOLD_RATIO,
        )
        # 3m ceiling → threshold = 0.3m. Beam depth 0.2m < 0.3m → no subdivision.
        beam = Beam(
            id="B1",
            start=(0, 4),
            end=(10, 4),
            depth_m=0.2,  # < 10% of 3.0m
        )
        result = calculate_beam_obstruction(
            room_id="R-001",
            room_polygon=simple_room,
            ceiling_height_m=3.0,
            beams=[beam],
        )
        assert len(result.pockets) == 1
        assert result.subdivision_applied is False
        assert result.significant_beams == 0

    def test_deep_beam_subdivides_room(self, simple_room):
        """Beam depth > 10% of ceiling height should subdivide."""
        from fireai.core.spatial_engine.beam_obstruction import (
            Beam,
            calculate_beam_obstruction,
        )
        # 3m ceiling → threshold = 0.3m. Beam depth 0.5m > 0.3m → subdivide.
        beam = Beam(
            id="B1",
            start=(0, 4),
            end=(10, 4),
            depth_m=0.5,  # > 10% of 3.0m
        )
        result = calculate_beam_obstruction(
            room_id="R-001",
            room_polygon=simple_room,
            ceiling_height_m=3.0,
            beams=[beam],
        )
        assert len(result.pockets) == 2  # Subdivided into 2 pockets
        assert result.subdivision_applied is True
        assert result.significant_beams == 1

    def test_multiple_deep_beams_create_multiple_pockets(self, simple_room):
        """Multiple significant beams should create multiple pockets."""
        from fireai.core.spatial_engine.beam_obstruction import (
            Beam,
            calculate_beam_obstruction,
        )
        beams = [
            Beam(id="B1", start=(0, 2), end=(10, 2), depth_m=0.5),
            Beam(id="B2", start=(0, 4), end=(10, 4), depth_m=0.5),
            Beam(id="B3", start=(0, 6), end=(10, 6), depth_m=0.5),
        ]
        result = calculate_beam_obstruction(
            room_id="R-001",
            room_polygon=simple_room,
            ceiling_height_m=3.0,
            beams=beams,
        )
        assert len(result.pockets) == 4  # 3 beams → 4 pockets

    def test_nan_ceiling_height_rejected(self, simple_room):
        """NaN ceiling height must be rejected (per V57)."""
        from fireai.core.spatial_engine.beam_obstruction import (
            calculate_beam_obstruction,
        )
        with pytest.raises(ValueError, match="positive finite"):
            calculate_beam_obstruction(
                room_id="R-001",
                room_polygon=simple_room,
                ceiling_height_m=float("nan"),
                beams=[],
            )

    def test_negative_ceiling_height_rejected(self, simple_room):
        from fireai.core.spatial_engine.beam_obstruction import (
            calculate_beam_obstruction,
        )
        with pytest.raises(ValueError, match="positive finite"):
            calculate_beam_obstruction(
                room_id="R-001",
                room_polygon=simple_room,
                ceiling_height_m=-3.0,
                beams=[],
            )

    def test_invalid_polygon_rejected(self):
        """Polygon with < 3 points must be rejected."""
        from fireai.core.spatial_engine.beam_obstruction import (
            calculate_beam_obstruction,
        )
        with pytest.raises(ValueError, match="at least 3 points"):
            calculate_beam_obstruction(
                room_id="R-001",
                room_polygon=[(0, 0), (1, 1)],  # Only 2 points
                ceiling_height_m=3.0,
                beams=[],
            )

    def test_beam_with_nan_coordinates_rejected(self, simple_room):
        """Beam with NaN coordinates must be rejected."""
        from fireai.core.spatial_engine.beam_obstruction import (
            Beam,
            calculate_beam_obstruction,
        )
        with pytest.raises(ValueError, match="non-finite"):
            Beam(
                id="B1",
                start=(float("nan"), 4),
                end=(10, 4),
                depth_m=0.5,
            )

    def test_beam_with_negative_depth_rejected(self, simple_room):
        from fireai.core.spatial_engine.beam_obstruction import (
            Beam,
            calculate_beam_obstruction,
        )
        with pytest.raises(ValueError, match="positive finite"):
            Beam(
                id="B1",
                start=(0, 4),
                end=(10, 4),
                depth_m=-0.5,
            )

    def test_low_ceiling_disables_beam_logic(self, simple_room):
        """Ceiling below MIN_CEILING_HEIGHT_FOR_BEAM_LOGIC_M should not subdivide."""
        from fireai.core.spatial_engine.beam_obstruction import (
            Beam,
            calculate_beam_obstruction,
            MIN_CEILING_HEIGHT_FOR_BEAM_LOGIC_M,
        )
        beam = Beam(id="B1", start=(0, 4), end=(10, 4), depth_m=0.3)
        # Ceiling 2.0m < 2.4m minimum → no subdivision
        result = calculate_beam_obstruction(
            room_id="R-001",
            room_polygon=simple_room,
            ceiling_height_m=2.0,
            beams=[beam],
        )
        assert len(result.pockets) == 1
        assert any("below minimum" in w for w in result.warnings)

    def test_result_includes_nfpa_reference(self, simple_room):
        """Result must cite NFPA 72 §17.7.3.2.4.2."""
        from fireai.core.spatial_engine.beam_obstruction import (
            calculate_beam_obstruction,
        )
        result = calculate_beam_obstruction(
            room_id="R-001",
            room_polygon=simple_room,
            ceiling_height_m=3.0,
            beams=[],
        )
        assert "NFPA 72" in result.nfpa_reference
        assert "17.7.3.2.4.2" in result.nfpa_reference


# ---------------------------------------------------------------------------
# BIM Unit Detection Tests (PHASE 4.2)
# ---------------------------------------------------------------------------


class TestBIMUnitDetection:
    """Tests for automated BIM unit detection."""

    def test_unit_system_scale_factors(self):
        """Verify scale-to-metres factors are correct (NIST)."""
        from fireai.bridges.bim_unit_detector import UnitSystem
        assert UnitSystem.METRES.scale_to_metres == 1.0
        assert UnitSystem.CENTIMETRES.scale_to_metres == 0.01
        assert UnitSystem.MILLIMETRES.scale_to_metres == 0.001
        assert UnitSystem.FEET.scale_to_metres == 0.3048
        assert UnitSystem.INCHES.scale_to_metres == 0.0254

    def test_detect_nonexistent_file(self):
        """Non-existent file should return default (metres)."""
        from fireai.bridges.bim_unit_detector import detect_bim_unit, UnitSystem
        result = detect_bim_unit("/nonexistent/file.ifc")
        assert result.unit == UnitSystem.UNKNOWN
        assert result.scale_to_metres == 1.0  # Default to metres

    def test_detect_dxf_with_insunits(self, tmp_path):
        """DXF file with $INSUNITS should be detected correctly."""
        from fireai.bridges.bim_unit_detector import detect_bim_unit, UnitSystem

        # Create a minimal DXF file with $INSUNITS=4 (millimetres)
        dxf_content = """0
SECTION
2
HEADER
9
$INSUNITS
70
4
0
ENDSEC
"""
        dxf_file = tmp_path / "test.dxf"
        dxf_file.write_text(dxf_content)

        result = detect_bim_unit(str(dxf_file))
        assert result.unit == UnitSystem.MILLIMETRES
        assert result.source == "dxf_insunits"
        assert result.confidence == 1.0

    def test_detect_ifc_with_metre_unit(self, tmp_path):
        """IFC file with IFCSIUNIT(.METRE.) should be detected."""
        from fireai.bridges.bim_unit_detector import detect_bim_unit, UnitSystem

        ifc_content = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('test.ifc','2024-01-01T00:00:00',(''),(''),'IFC4','','');
FILE_SCHEMA(('IFC4X3_ADD2'));
ENDSEC;
DATA;
#1 = IFCUNITASSIGNMENT((#2));
#2 = IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
ENDSEC;
END-ISO-10303-21;
"""
        ifc_file = tmp_path / "test.ifc"
        ifc_file.write_text(ifc_content)

        result = detect_bim_unit(str(ifc_file))
        assert result.unit == UnitSystem.METRES
        assert result.source == "ifc_header"
        assert result.confidence == 1.0

    def test_detect_ifc_with_millimetre_unit(self, tmp_path):
        """IFC file with IFCSIUNIT(.MILLI.,.METRE.) should be detected."""
        from fireai.bridges.bim_unit_detector import detect_bim_unit, UnitSystem

        ifc_content = """ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1 = IFCSIUNIT(*,.LENGTHUNIT.,$,.MILLI.,.METRE.);
ENDSEC;
END-ISO-10303-21;
"""
        ifc_file = tmp_path / "test.ifc"
        ifc_file.write_text(ifc_content)

        result = detect_bim_unit(str(ifc_file))
        assert result.unit == UnitSystem.MILLIMETRES


# ---------------------------------------------------------------------------
# Darcy-Weisbach Tests (PHASE 4.3)
# ---------------------------------------------------------------------------


class TestDarcyWeisbach:
    """Tests for Darcy-Weisbach friction loss calculation."""

    def test_water_flow_returns_valid_result(self):
        """Water flow through a pipe should return a valid result."""
        from fireai.core.darcy_weisbach_solver import (
            calculate_darcy_weisbach_friction_loss,
            FluidType,
        )
        result = calculate_darcy_weisbach_friction_loss(
            pipe_length_m=100.0,
            pipe_diameter_m=0.05,  # 50mm
            flow_rate_kg_s=1.0,    # 1 kg/s
            fluid_type=FluidType.WATER,
        )
        assert result.head_loss_m > 0
        assert result.pressure_loss_pa > 0
        assert result.pressure_loss_psi > 0
        assert result.friction_factor > 0
        assert result.reynolds_number > 0

    def test_zero_flow_returns_zero_loss(self):
        """Zero flow rate should return zero friction loss."""
        from fireai.core.darcy_weisbach_solver import (
            calculate_darcy_weisbach_friction_loss,
            FluidType,
        )
        result = calculate_darcy_weisbach_friction_loss(
            pipe_length_m=100.0,
            pipe_diameter_m=0.05,
            flow_rate_kg_s=0.0,
            fluid_type=FluidType.WATER,
        )
        assert result.head_loss_m == 0.0
        assert result.pressure_loss_pa == 0.0
        assert result.flow_regime == "no_flow"

    def test_nan_pipe_length_rejected(self):
        """NaN pipe length must be rejected (per V57)."""
        from fireai.core.darcy_weisbach_solver import (
            calculate_darcy_weisbach_friction_loss,
            FluidType,
        )
        with pytest.raises(ValueError, match="must be finite"):
            calculate_darcy_weisbach_friction_loss(
                pipe_length_m=float("nan"),
                pipe_diameter_m=0.05,
                flow_rate_kg_s=1.0,
                fluid_type=FluidType.WATER,
            )

    def test_negative_pipe_diameter_rejected(self):
        from fireai.core.darcy_weisbach_solver import (
            calculate_darcy_weisbach_friction_loss,
            FluidType,
        )
        with pytest.raises(ValueError):
            calculate_darcy_weisbach_friction_loss(
                pipe_length_m=100.0,
                pipe_diameter_m=-0.05,
                flow_rate_kg_s=1.0,
                fluid_type=FluidType.WATER,
            )

    def test_co2_liquid_supported(self):
        """CO2 liquid should be supported (NFPA 12)."""
        from fireai.core.darcy_weisbach_solver import (
            calculate_darcy_weisbach_friction_loss,
            FluidType,
        )
        result = calculate_darcy_weisbach_friction_loss(
            pipe_length_m=50.0,
            pipe_diameter_m=0.025,
            flow_rate_kg_s=5.0,
            fluid_type=FluidType.CO2_LIQUID,
        )
        assert result.fluid_type == "co2_liquid"
        assert "NFPA 12" in result.nfpa_reference or "NFPA 2001" in result.nfpa_reference or "Darcy-Weisbach" in result.nfpa_reference

    def test_clean_agent_supported(self):
        """FM-200 (clean agent) should be supported (NFPA 2001)."""
        from fireai.core.darcy_weisbach_solver import (
            calculate_darcy_weisbach_friction_loss,
            FluidType,
        )
        result = calculate_darcy_weisbach_friction_loss(
            pipe_length_m=30.0,
            pipe_diameter_m=0.020,
            flow_rate_kg_s=2.0,
            fluid_type=FluidType.FM200,
        )
        assert result.fluid_type == "fm200"

    def test_laminar_flow_friction_factor(self):
        """Laminar flow (Re < 2300) should use f = 64/Re."""
        from fireai.core.darcy_weisbach_solver import (
            calculate_darcy_weisbach_friction_loss,
            FluidType,
        )
        # Very low flow → laminar
        result = calculate_darcy_weisbach_friction_loss(
            pipe_length_m=10.0,
            pipe_diameter_m=0.05,
            flow_rate_kg_s=0.001,  # Very low flow
            fluid_type=FluidType.WATER,
        )
        assert result.flow_regime == "laminar"
        # f = 64/Re for laminar
        expected_f = 64.0 / result.reynolds_number
        assert math.isclose(result.friction_factor, expected_f, rel_tol=0.01)

    def test_turbulent_flow_friction_factor(self):
        """Turbulent flow (Re > 4000) should use Colebrook-White."""
        from fireai.core.darcy_weisbach_solver import (
            calculate_darcy_weisbach_friction_loss,
            FluidType,
        )
        result = calculate_darcy_weisbach_friction_loss(
            pipe_length_m=10.0,
            pipe_diameter_m=0.05,
            flow_rate_kg_s=5.0,  # High flow → turbulent
            fluid_type=FluidType.WATER,
        )
        assert result.flow_regime == "turbulent"
        # Turbulent friction factor should be in range 0.01-0.05 for steel pipe
        assert 0.005 < result.friction_factor < 0.1

    def test_compare_with_hazen_williams(self):
        """Comparison function should return both results."""
        from fireai.core.darcy_weisbach_solver import compare_with_hazen_williams
        result = compare_with_hazen_williams(
            pipe_length_m=100.0,
            pipe_diameter_m=0.05,
            flow_rate_kg_s=1.0,
        )
        assert "darcy_weisbach" in result
        assert "hazen_williams" in result
        assert "difference_percent" in result

    def test_fluid_properties_database_complete(self):
        """All fluid types should have properties defined."""
        from fireai.core.darcy_weisbach_solver import FLUID_PROPERTIES, FluidType
        for fluid in FluidType:
            if fluid == FluidType.CUSTOM:
                continue  # Custom requires user input
            assert fluid in FLUID_PROPERTIES
            props = FLUID_PROPERTIES[fluid]
            assert "density_kg_m3" in props
            assert "viscosity_pa_s" in props
            assert "typical_roughness_m" in props

    def test_result_serializes_to_dict(self):
        from fireai.core.darcy_weisbach_solver import (
            calculate_darcy_weisbach_friction_loss,
            FluidType,
        )
        result = calculate_darcy_weisbach_friction_loss(
            pipe_length_m=100.0,
            pipe_diameter_m=0.05,
            flow_rate_kg_s=1.0,
            fluid_type=FluidType.WATER,
        )
        d = result.to_dict()
        assert "head_loss_m" in d
        assert "pressure_loss_pa" in d
        assert "friction_factor" in d
        assert "reynolds_number" in d
        assert "flow_regime" in d
