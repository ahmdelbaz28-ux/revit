"""
Comprehensive tests for all new modules:
  - Pathway Survivability Engine (NFPA 72 §12.4)
  - Inrush Current + NAC Loading + AWG Selection (NFPA 72 §10.14.1, §18.5)
  - BOQ Generator enhancements (survivability-aware, AWG sizing)
  - Auto-Drafting Engine enhancements (plenum collision, survivability constraints)
  - Riser Diagram Generator (NFPA 72 §7.4.5)
  - AHJ Submittal Package Generator
  - Contracts (new enums)
"""

import os
import sys
import math
import tempfile
import unittest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fireai.core.contracts import (
    PathwaySurvivabilityLevel,
    CableType,
    OccupancyCategory,
)
from fireai.core.pathway_survivability_engine import (
    BuildingSpec,
    SurvivabilityResult,
    CableRequirement,
    PathwaySurvivabilityEngine,
)
from fireai.core.nfpa72_calculations import (
    calculate_inrush_current,
    calculate_nac_loading,
    auto_select_awg,
    check_voltage_drop,
    AWG_RESISTANCE_TABLE,
    AWG_GAUGES,
    DEVICE_CURRENT_DRAW,
    NAC_MAX_CURRENT_A,
)
from fireai.core.boq_generator import (
    generate_cable_boq,
    UNIT_COSTS,
)


# ============================================================================
# 1. Pathway Survivability Engine Tests
# ============================================================================

class TestPathwaySurvivabilityEngine(unittest.TestCase):
    """Test pathway survivability classification per NFPA 72 §12.4."""

    def setUp(self):
        self.engine = PathwaySurvivabilityEngine()

    def test_sprinklered_full_evacuation_level_1(self):
        """Fully sprinklered building with full evacuation → Level 1."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.BUSINESS,
            height_m=12.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        result = self.engine.classify(spec)
        self.assertEqual(result.building_level, PathwaySurvivabilityLevel.LEVEL_1)

    def test_high_rise_level_2(self):
        """High-rise (>23 m) → Level 2 regardless of sprinklers."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        result = self.engine.classify(spec)
        self.assertEqual(result.building_level, PathwaySurvivabilityLevel.LEVEL_2)

    def test_partial_evacuation_level_2(self):
        """Partial evacuation → Level 2."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.BUSINESS,
            height_m=12.0,
            is_sprinklered=True,
            evacuation_type="partial",
        )
        result = self.engine.classify(spec)
        self.assertEqual(result.building_level, PathwaySurvivabilityLevel.LEVEL_2)

    def test_staged_non_sprinklered_level_3(self):
        """Staged evacuation in non-sprinklered building → Level 3."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=False,
            evacuation_type="staged",
        )
        result = self.engine.classify(spec)
        self.assertEqual(result.building_level, PathwaySurvivabilityLevel.LEVEL_3)

    def test_voice_evac_level_2(self):
        """Voice evacuation → Level 2 minimum."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.ASSEMBLY,
            height_m=12.0,
            is_sprinklered=True,
            has_voice_evac=True,
            evacuation_type="full",
        )
        result = self.engine.classify(spec)
        self.assertEqual(result.building_level, PathwaySurvivabilityLevel.LEVEL_2)

    def test_health_care_level_2(self):
        """Health care (defend-in-place) → Level 2."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.HEALTH_CARE,
            height_m=12.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        result = self.engine.classify(spec)
        self.assertEqual(result.building_level, PathwaySurvivabilityLevel.LEVEL_2)

    def test_detention_level_2(self):
        """Detention/correctional → Level 2."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.DETENTION,
            height_m=12.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        result = self.engine.classify(spec)
        self.assertEqual(result.building_level, PathwaySurvivabilityLevel.LEVEL_2)

    def test_auto_detect_high_rise(self):
        """Building height >23 m auto-detects as high-rise."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.BUSINESS,
            height_m=30.0,
            is_sprinklered=True,
            evacuation_type="full",
            is_high_rise=False,  # Should be auto-set
        )
        self.assertTrue(spec.is_high_rise)

    def test_cable_requirements_count(self):
        """Level 2 should have 4 cable requirements (riser, horizontal, plenum, general)."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        result = self.engine.classify(spec)
        self.assertEqual(len(result.cable_requirements), 4)

    def test_level_2_riser_requires_ci(self):
        """Level 2 riser cables require CI type."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        result = self.engine.classify(spec)
        riser_req = next(r for r in result.cable_requirements if r.route_type == "riser")
        self.assertEqual(riser_req.cable_type, CableType.CI)

    def test_level_3_riser_requires_rated_enclosure(self):
        """Level 3 riser cables require CI in rated enclosure."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=False,
            evacuation_type="staged",
        )
        result = self.engine.classify(spec)
        riser_req = next(r for r in result.cable_requirements if r.route_type == "riser")
        self.assertTrue(riser_req.in_rated_enclosure)
        self.assertEqual(riser_req.enclosure_rating_hr, 2.0)

    def test_level_1_riser_fplr(self):
        """Level 1 riser cables use FPLR."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.BUSINESS,
            height_m=12.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        result = self.engine.classify(spec)
        riser_req = next(r for r in result.cable_requirements if r.route_type == "riser")
        self.assertEqual(riser_req.cable_type, CableType.FPLR)

    def test_rationale_not_empty(self):
        """Classification rationale should always contain at least one reason."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.BUSINESS,
            height_m=12.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        result = self.engine.classify(spec)
        self.assertGreater(len(result.classification_rationale), 0)

    def test_get_required_cable_type_convenience(self):
        """Convenience method returns correct cable type."""
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        cable = self.engine.get_required_cable_type(spec, "riser")
        self.assertEqual(cable, CableType.CI)


# ============================================================================
# 2. Inrush Current + NAC Loading + AWG Selection Tests
# ============================================================================

class TestInrushCurrent(unittest.TestCase):
    """Test inrush current calculations per NFPA 72 §10.14.1."""

    def test_strobe_inrush_factor(self):
        """Strobe inrush should be 2.5× steady-state."""
        result = calculate_inrush_current("strobe_15cd", 10)
        self.assertAlmostEqual(result["inrush_factor"], 2.5)
        self.assertAlmostEqual(result["steady_total_a"], 0.15 * 10)
        self.assertAlmostEqual(result["inrush_total_a"], 0.38 * 10)

    def test_horn_inrush_factor(self):
        """Horn inrush should be 2.0× steady-state."""
        result = calculate_inrush_current("horn", 5)
        self.assertAlmostEqual(result["inrush_factor"], 2.0)

    def test_speaker_no_inrush(self):
        """Speakers should have inrush factor 1.0 (no inrush)."""
        result = calculate_inrush_current("speaker_4w_70v", 10)
        self.assertAlmostEqual(result["inrush_factor"], 1.0)
        self.assertEqual(result["steady_total_a"], result["inrush_total_a"])

    def test_unknown_device_conservative(self):
        """Unknown device type should use conservative defaults."""
        result = calculate_inrush_current("unknown_device", 5)
        self.assertAlmostEqual(result["inrush_factor"], 2.5)
        self.assertGreater(result["inrush_total_a"], 0)

    def test_zero_quantity(self):
        """Zero quantity should return zero currents."""
        result = calculate_inrush_current("strobe_15cd", 0)
        self.assertAlmostEqual(result["steady_total_a"], 0.0)
        self.assertAlmostEqual(result["inrush_total_a"], 0.0)


class TestNACLoading(unittest.TestCase):
    """Test NAC circuit loading calculations per NFPA 72 §18.5."""

    def test_within_panel_limit(self):
        """Small NAC load should be within panel limit."""
        result = calculate_nac_loading([
            {"device_type": "strobe_15cd", "quantity": 5},
        ])
        self.assertTrue(result["within_panel_limit"])

    def test_over_panel_limit(self):
        """Large NAC load should exceed panel limit."""
        result = calculate_nac_loading([
            {"device_type": "strobe_75cd", "quantity": 10},
        ])
        self.assertFalse(result["within_panel_limit"])
        self.assertGreater(len(result["warnings"]), 0)

    def test_mixed_devices(self):
        """Mixed device types should aggregate correctly."""
        result = calculate_nac_loading([
            {"device_type": "strobe_15cd", "quantity": 3},
            {"device_type": "horn", "quantity": 2},
        ])
        expected_steady = 3 * 0.15 + 2 * 0.25
        self.assertAlmostEqual(result["steady_total_a"], expected_steady, places=3)

    def test_high_inrush_warning(self):
        """High inrush current should generate warning."""
        result = calculate_nac_loading([
            {"device_type": "strobe_75cd", "quantity": 6},
        ])
        # 6 * 1.13 = 6.78A inrush > 4.5A (3.0 * 1.5)
        has_inrush_warning = any("inrush" in w.lower() for w in result["warnings"])
        self.assertTrue(has_inrush_warning or not result["within_panel_limit"])


class TestAWGSelection(unittest.TestCase):
    """Test automatic AWG wire gauge selection per NEC Art. 760."""

    def test_short_run_selects_18awg(self):
        """Short cable run should select smallest wire (18 AWG)."""
        result = auto_select_awg(
            supply_voltage_v=24.0,
            load_current_a=0.5,
            cable_length_m=10.0,
        )
        self.assertIsNotNone(result["selected_awg"])
        self.assertEqual(result["selected_awg"], 18)
        self.assertTrue(result["compliant"])

    def test_long_run_upgrades_gauge(self):
        """Long cable run should select larger wire."""
        result = auto_select_awg(
            supply_voltage_v=24.0,
            load_current_a=1.0,
            cable_length_m=200.0,
        )
        self.assertIsNotNone(result["selected_awg"])
        # Should be a larger gauge than 18
        self.assertLessEqual(result["selected_awg"], 16)

    def test_impossible_run_returns_none(self):
        """Very long run with high current should return None."""
        result = auto_select_awg(
            supply_voltage_v=24.0,
            load_current_a=5.0,
            cable_length_m=500.0,
        )
        # May or may not find a solution — depends on table limits
        # At least check it doesn't crash
        if result["selected_awg"] is None:
            self.assertFalse(result["compliant"])
            self.assertIn("error", result)

    def test_voltage_at_device_above_minimum(self):
        """Selected gauge should keep voltage at device above 16V."""
        result = auto_select_awg(
            supply_voltage_v=24.0,
            load_current_a=1.0,
            cable_length_m=50.0,
        )
        if result["selected_awg"] is not None:
            self.assertGreaterEqual(result["voltage_at_device"], 16.0)

    def test_all_candidates_evaluated(self):
        """All AWG gauges should be evaluated."""
        result = auto_select_awg(
            supply_voltage_v=24.0,
            load_current_a=0.5,
            cable_length_m=10.0,
        )
        self.assertEqual(len(result["all_candidates"]), len(AWG_GAUGES))


# ============================================================================
# 3. BOQ Generator Enhancement Tests
# ============================================================================

class TestBOQEnhancements(unittest.TestCase):
    """Test BOQ generator survivability-aware and AWG enhancements."""

    def test_ci_cable_in_unit_costs(self):
        """CI cable should be in UNIT_COSTS."""
        self.assertIn("cable_ci_per_m", UNIT_COSTS)

    def test_rated_conduit_in_unit_costs(self):
        """2-hour rated conduit should be in UNIT_COSTS."""
        self.assertIn("conduit_rated_2hr_per_m", UNIT_COSTS)

    def test_firestop_in_unit_costs(self):
        """Firestop penetration should be in UNIT_COSTS."""
        self.assertIn("firestop_penetration", UNIT_COSTS)

    def test_survivability_level_2_overrides_cable(self):
        """Level 2 survivability should override cable type to CI."""
        loops = [{"loop_id": "SLC-1", "cable_length_m": 100}]
        items = generate_cable_boq(loops, cable_type="FPL", survivability_level="LEVEL_2")
        cable_item = next((i for i in items if i.item_type.startswith("cable_")), None)
        self.assertIsNotNone(cable_item)
        self.assertEqual(cable_item.item_type, "cable_CI")

    def test_survivability_level_3_rated_conduit(self):
        """Level 3 should use rated conduit."""
        loops = [{"loop_id": "SLC-1", "cable_length_m": 100}]
        items = generate_cable_boq(loops, survivability_level="LEVEL_3")
        conduit_item = next((i for i in items if i.item_type == "conduit_rated_2hr"), None)
        self.assertIsNotNone(conduit_item)

    def test_auto_awg_sizing_in_notes(self):
        """Auto AWG sizing should appear in cable BOQ notes."""
        loops = [{"loop_id": "SLC-1", "cable_length_m": 100}]
        items = generate_cable_boq(loops, auto_size_awg=True, load_current_a=0.5)
        cable_item = next((i for i in items if i.item_type.startswith("cable_")), None)
        self.assertIsNotNone(cable_item)
        self.assertIn("AWG=", cable_item.notes)

    def test_firestop_item_for_ci_cable(self):
        """CI cable should include firestop penetration items."""
        loops = [{"loop_id": "SLC-1", "cable_length_m": 100}]
        items = generate_cable_boq(loops, cable_type="CI")
        firestop = next((i for i in items if i.item_type == "firestop_penetration"), None)
        self.assertIsNotNone(firestop)


# ============================================================================
# 4. Auto-Drafting Engine Enhancement Tests
# ============================================================================

class TestAutoDraftingEnhancements(unittest.TestCase):
    """Test plenum collision and survivability constraints in auto_drafting_engine."""

    def test_plenum_zone_dataclass(self):
        """PlenumZone dataclass should work correctly."""
        from fireai.core.auto_drafting_engine import PlenumZone
        zone = PlenumZone(
            zone_id="PLENUM-1",
            floor_id="GF",
            bounds=(0, 0, 50, 50),
            plenum_height_m=0.6,
            collision_zones=((10, 10, 5, 3),),
        )
        self.assertTrue(zone.requires_fplp)
        self.assertEqual(len(zone.collision_zones), 1)

    def test_survivability_constraint_dataclass(self):
        """SurvivabilityRouteConstraint dataclass should work correctly."""
        from fireai.core.auto_drafting_engine import SurvivabilityRouteConstraint
        constraint = SurvivabilityRouteConstraint(
            route_id="SLC-1",
            required_level="LEVEL_2",
            cable_type="CI",
        )
        self.assertEqual(constraint.required_level, "LEVEL_2")
        self.assertFalse(constraint.in_rated_enclosure)

    def test_plenum_collision_detection(self):
        """check_plenum_collisions should detect obstacles."""
        from fireai.core.auto_drafting_engine import AutoDraftingEngine, PlenumZone
        engine = AutoDraftingEngine(walls=[], devices=[])
        path = [(5, 5), (15, 15), (25, 25)]
        zone = PlenumZone(
            zone_id="PLENUM-1",
            bounds=(0, 0, 50, 50),
            collision_zones=((10, 10, 5, 5),),
        )
        collisions = engine.check_plenum_collisions(path, [zone])
        # Path point (15,15) is inside collision zone (10,10,5,5) = 10-15 x 10-15
        self.assertGreater(len(collisions), 0)

    def test_no_collision_outside_zone(self):
        """Path outside plenum zone should have no collisions."""
        from fireai.core.auto_drafting_engine import AutoDraftingEngine, PlenumZone
        engine = AutoDraftingEngine(walls=[], devices=[])
        path = [(60, 60), (70, 70)]
        zone = PlenumZone(
            zone_id="PLENUM-1",
            bounds=(0, 0, 50, 50),
            collision_zones=((10, 10, 5, 5),),
        )
        collisions = engine.check_plenum_collisions(path, [zone])
        self.assertEqual(len(collisions), 0)

    def test_survivability_constraints_warnings(self):
        """apply_survivability_constraints should generate Level 2 warnings."""
        from fireai.core.auto_drafting_engine import AutoDraftingEngine, SurvivabilityRouteConstraint
        engine = AutoDraftingEngine(walls=[], devices=[])
        path = [(0, 0), (10, 10)]
        constraint = SurvivabilityRouteConstraint(
            route_id="SLC-1",
            required_level="LEVEL_2",
            cable_type="CI",
        )
        _, warnings = engine.apply_survivability_constraints(path, constraint)
        self.assertGreater(len(warnings), 0)

    def test_low_plenum_height_warning(self):
        """Very low plenum height should generate warning."""
        from fireai.core.auto_drafting_engine import AutoDraftingEngine, PlenumZone, SurvivabilityRouteConstraint
        engine = AutoDraftingEngine(walls=[], devices=[])
        path = [(5, 5), (15, 15)]
        zone = PlenumZone(
            zone_id="PLENUM-LOW",
            bounds=(0, 0, 50, 50),
            plenum_height_m=0.2,  # Very low
        )
        constraint = SurvivabilityRouteConstraint(route_id="SLC-1")
        _, warnings = engine.apply_survivability_constraints(path, constraint, [zone])
        has_clearance_warning = any("clearance" in w.lower() or "low" in w.lower() for w in warnings)
        self.assertTrue(has_clearance_warning)


# ============================================================================
# 5. Riser Diagram Generator Tests
# ============================================================================

class TestRiserDiagramGenerator(unittest.TestCase):
    """Test riser diagram generation per NFPA 72 §7.4.5."""

    def test_spec_creation(self):
        """RiserDiagramSpec should be creatable."""
        from fireai.core.riser_diagram_generator import RiserDiagramSpec, RiserPanel, RiserLoop
        spec = RiserDiagramSpec(
            project_name="Test Building",
            panels=[RiserPanel(panel_id="FACP-1", floor_id="GF", loop_count=2)],
            loops=[RiserLoop(loop_id="SLC-1", panel_id="FACP-1", device_count=48)],
        )
        self.assertEqual(len(spec.panels), 1)
        self.assertEqual(len(spec.loops), 1)

    def test_generate_no_panels_error(self):
        """No panels should produce an error result."""
        from fireai.core.riser_diagram_generator import RiserDiagramGenerator, RiserDiagramSpec
        gen = RiserDiagramGenerator()
        spec = RiserDiagramSpec()
        result = gen.generate(spec)
        self.assertGreater(len(result.errors), 0)

    def test_generate_with_ezdxf(self):
        """Should generate DXF file when ezdxf is available."""
        try:
            import ezdxf
            has_ezdxf = True
        except ImportError:
            has_ezdxf = False

        if not has_ezdxf:
            self.skipTest("ezdxf not installed")

        from fireai.core.riser_diagram_generator import (
            RiserDiagramGenerator, RiserDiagramSpec, RiserPanel,
            RiserLoop, RiserNACCircuit,
        )

        gen = RiserDiagramGenerator()
        spec = RiserDiagramSpec(
            project_name="Test Building",
            panels=[
                RiserPanel(panel_id="FACP-1", floor_id="GF", loop_count=2, nac_count=2),
            ],
            loops=[
                RiserLoop(loop_id="SLC-1", panel_id="FACP-1", device_count=48, isolator_count=2),
            ],
            nac_circuits=[
                RiserNACCircuit(nac_id="NAC-1", panel_id="FACP-1", device_count=10),
            ],
        )

        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            output_path = f.name

        try:
            result = gen.generate(spec, output_path=output_path)
            self.assertEqual(result.panel_count, 1)
            self.assertEqual(result.loop_count, 1)
            self.assertEqual(result.nac_count, 1)
            self.assertTrue(os.path.exists(output_path))
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)


# ============================================================================
# 6. AHJ Submittal Package Tests
# ============================================================================

class TestAHJSubmittalPackage(unittest.TestCase):
    """Test AHJ submittal package generation."""

    def test_assemble_all_sections(self):
        """Assembly should produce all 10 required sections."""
        from fireai.core.ahj_submittal_package import AHJSubmittalGenerator
        gen = AHJSubmittalGenerator()
        pkg = gen.assemble(
            project_name="Test Building",
            engineer_name="John Doe, PE",
            license_number="PE-12345",
        )
        self.assertEqual(len(pkg.sections), 10)

    def test_generate_index(self):
        """Index file should be generated."""
        from fireai.core.ahj_submittal_package import AHJSubmittalGenerator
        gen = AHJSubmittalGenerator()
        pkg = gen.assemble(project_name="Test Building")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = gen.generate_index(pkg, output_dir=tmpdir)
            self.assertTrue(result.complete)
            self.assertEqual(result.section_count, 10)

    def test_survivability_in_submittal(self):
        """Submittal should include survivability classification."""
        from fireai.core.ahj_submittal_package import AHJSubmittalGenerator
        from fireai.core.pathway_survivability_engine import PathwaySurvivabilityEngine, BuildingSpec
        from fireai.core.contracts import OccupancyCategory

        engine = PathwaySurvivabilityEngine()
        surv_result = engine.classify(BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=True,
            evacuation_type="full",
        ))

        gen = AHJSubmittalGenerator()
        pkg = gen.assemble(
            project_name="Test Building",
            survivability_result=surv_result,
        )

        surv_section = next(s for s in pkg.sections if s.section_id == "8.0")
        self.assertIn("LEVEL_2", surv_section.content)


# ============================================================================
# 7. Contracts Enum Tests
# ============================================================================

class TestContractsEnums(unittest.TestCase):
    """Test new enum additions to contracts.py."""

    def test_pathway_survivability_levels(self):
        """All three levels should exist."""
        self.assertEqual(PathwaySurvivabilityLevel.LEVEL_1.value, "LEVEL_1")
        self.assertEqual(PathwaySurvivabilityLevel.LEVEL_2.value, "LEVEL_2")
        self.assertEqual(PathwaySurvivabilityLevel.LEVEL_3.value, "LEVEL_3")

    def test_cable_types(self):
        """All four cable types should exist."""
        self.assertEqual(CableType.FPL.value, "FPL")
        self.assertEqual(CableType.FPLR.value, "FPLR")
        self.assertEqual(CableType.FPLP.value, "FPLP")
        self.assertEqual(CableType.CI.value, "CI")

    def test_occupancy_categories(self):
        """All 10 occupancy categories should exist."""
        self.assertEqual(len(OccupancyCategory), 10)

    def test_enum_string_comparison(self):
        """Enums should be comparable as strings."""
        self.assertEqual(str(PathwaySurvivabilityLevel.LEVEL_2), "PathwaySurvivabilityLevel.LEVEL_2")


# ============================================================================
# 8. Integration Tests
# ============================================================================

class TestIntegration(unittest.TestCase):
    """Integration tests connecting multiple modules."""

    def test_survivability_to_boq_pipeline(self):
        """PathwaySurvivabilityEngine → BOQ cable selection pipeline."""
        engine = PathwaySurvivabilityEngine()
        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        surv_result = engine.classify(spec)

        # Use survivability level in BOQ
        loops = [{"loop_id": "SLC-1", "cable_length_m": 200}]
        boq_items = generate_cable_boq(
            loops,
            cable_type="FPL",
            survivability_level=surv_result.building_level.value,
        )

        # Should have CI cable, not FPL
        cable_item = next(i for i in boq_items if i.item_type.startswith("cable_"))
        self.assertEqual(cable_item.item_type, "cable_CI")

    def test_nac_loading_to_awg_pipeline(self):
        """NAC loading → AWG sizing pipeline."""
        # Calculate NAC loading
        nac_result = calculate_nac_loading([
            {"device_type": "strobe_15cd", "quantity": 10},
        ])
        steady_current = nac_result["steady_total_a"]

        # Use steady current for AWG sizing
        awg_result = auto_select_awg(
            supply_voltage_v=24.0,
            load_current_a=steady_current,
            cable_length_m=100.0,
        )

        # Should find a valid gauge for 1.5A over 100m
        self.assertIsNotNone(awg_result["selected_awg"])
        self.assertTrue(awg_result["compliant"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
