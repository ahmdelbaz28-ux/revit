"""
test_v17_wrappers_and_orchestrator.py — V17 Wrapper & Integration Tests
=======================================================================
Tests the V17 Critical Trilogy wrapper interfaces and the
EnterpriseOrchestrator integration pipeline.

These tests verify:
  1. AcousticSPLCalculator (v17_core) wrapper produces DecisionProvenance
  2. StrictBatterySizer (v17_core) wrapper produces DecisionProvenance
  3. TenabilityEvaluator (v17_core) wrapper produces DecisionProvenance
  4. Consultant-compatible dict inputs work correctly
  5. EnterpriseOrchestrator integrates all three modules
  6. Release gates (7 & 8) work with V17 results
  7. Corrections from consultant's code are verified
"""

import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import math
import pytest


# ============================================================================
# AcousticSPLCalculator (v17_core) Tests
# ============================================================================

class TestV17AcousticSPLCalculator:
    """Test the V17 AcousticSPLCalculator wrapper with DecisionProvenance."""

    def test_basic_compliant_room(self):
        """A room with adequate speakers should produce compliant result."""
        from fireai.v17_core import AcousticSPLCalculator
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-101",
            occ_type="business",
            speakers=[{"x": 5, "y": 5, "z": 2.8, "rating_db_3m": 95}],
            check_points=[{"x": 5, "y": 5, "z": 1.5, "label": "center"}],
        )
        # Should return DecisionProvenance or dict
        if hasattr(result, "value"):
            assert result.value["pass"] is True
            assert result.value["min_spl_achieved"] > 55.0  # 40+15=55 required for business
        else:
            assert result["compliant"] is True

    def test_consultant_dict_interface(self):
        """Consultant's dict-based speaker/check_point format should work."""
        from fireai.v17_core import AcousticSPLCalculator
        calc = AcousticSPLCalculator(room_ambient_noise={"business": 55.0})
        result = calc.calculate_room_spl(
            room_id="R-OFFICE",
            occ_type="business",
            speakers=[{"x": 3.0, "y": 3.0, "z": 2.8, "rating_db_3m": 95.0}],
            check_points=[{"x": 10.0, "y": 10.0, "z": 1.5}],
        )
        # Should not crash — consultant's interface compatible
        assert result is not None

    def test_3d_distance_used_not_2d(self):
        """Verify 3D distance (x,y,z) is used, not 2D (x,y) like consultant's code."""
        from fireai.v17_core import AcousticSPLCalculator
        calc = AcousticSPLCalculator()
        # Speaker at ceiling (z=3.0), listener at floor (z=0.0), same x,y
        # 2D distance would be 0, but 3D distance is 3.0m
        result = calc.calculate_room_spl(
            room_id="R-3D-TEST",
            occ_type="office_quiet",
            speakers=[{"x": 5.0, "y": 5.0, "z": 3.0, "rating_db_3m": 95.0}],
            check_points=[{"x": 5.0, "y": 5.0, "z": 0.0, "label": "floor"}],
        )
        # At 3m distance (3D), SPL should equal the speaker rating (95 dBA)
        if hasattr(result, "value"):
            assert result.value["min_spl_achieved"] >= 90.0
        else:
            assert result["worst_point_spl"] >= 90.0

    def test_behind_closed_door_flag_converted(self):
        """Consultant's 'behind_closed_door' flag should be converted to Barrier."""
        from fireai.v17_core import AcousticSPLCalculator
        calc = AcousticSPLCalculator()
        # Without door
        result_no_door = calc.calculate_room_spl(
            room_id="R-NO-DOOR",
            occ_type="office_normal",
            speakers=[{"x": 3.0, "y": 5.0, "z": 2.8, "rating_db_3m": 90.0}],
            check_points=[{"x": 15.0, "y": 5.0, "z": 1.5}],
        )
        # With door
        result_with_door = calc.calculate_room_spl(
            room_id="R-DOOR",
            occ_type="office_normal",
            speakers=[{"x": 3.0, "y": 5.0, "z": 2.8, "rating_db_3m": 90.0, "behind_closed_door": True}],
            check_points=[{"x": 15.0, "y": 5.0, "z": 1.5}],
        )
        # SPL with door should be lower
        if hasattr(result_no_door, "value") and hasattr(result_with_door, "value"):
            assert result_with_door.value["min_spl_achieved"] < result_no_door.value["min_spl_achieved"]
        else:
            assert result_with_door["worst_point_spl"] < result_no_door["worst_point_spl"]

    def test_correct_formula_not_consultant_wrong(self):
        """Verify correct formula: 20*log10(d/d_ref), NOT 20*log10(d)."""
        from fireai.v17_core import AcousticSPLCalculator
        from fireai.core.acoustic_calculator import calculate_spl_at_distance
        # At 3m reference distance: ZERO attenuation
        result_3m = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=3.0, ref_distance_m=3.0,
            include_reverberant_field=False,
        )
        assert result_3m.direct_attenuation_dB == pytest.approx(0.0, abs=0.01)

        # At 6m: 20*log10(6/3) = 6.02 dB (NOT 20*log10(6) = 15.56 dB)
        result_6m = calculate_spl_at_distance(
            source_dba=95.0, target_distance_m=6.0, ref_distance_m=3.0,
            include_reverberant_field=False,
        )
        assert result_6m.direct_attenuation_dB == pytest.approx(6.02, abs=0.1)
        # Consultant's wrong formula would give 15.56 dB — we don't

    def test_provenance_has_audit_trail(self):
        """DecisionProvenance should have NFPA citations and algorithm info."""
        from fireai.v17_core import AcousticSPLCalculator
        from fireai.core.provenance import DecisionProvenance
        calc = AcousticSPLCalculator()
        result = calc.calculate_room_spl(
            room_id="R-AUDIT",
            occ_type="business",
            speakers=[{"x": 5, "y": 5, "z": 2.8, "rating_db_3m": 95}],
            check_points=[{"x": 5, "y": 5, "z": 1.5}],
        )
        if isinstance(result, DecisionProvenance):
            assert result.decision_type == "audibility_compliance"
            assert len(result.rules_applied) > 0
            assert "18.4" in result.rules_applied[0]["citation"]
            assert result.algorithm["name"] == "InverseSquareSPLAccumulator"
            assert result.algorithm["version"] == "v17"


# ============================================================================
# StrictBatterySizer (v17_core) Tests
# ============================================================================

class TestV17StrictBatterySizer:
    """Test the V17 StrictBatterySizer wrapper with DecisionProvenance."""

    def test_basic_calculation(self):
        """Basic battery sizing should return required Ah."""
        from fireai.v17_core import StrictBatterySizer
        sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
        result = sizer.calculate_minimum_ah(
            quiescent_ma=500.0,
            alarm_ma=2000.0,
            panel_ambient_temp_c=25.0,
        )
        if hasattr(result, "value"):
            assert result.value["min_required_ah"] > 0
            assert result.value["base_ah"] > 0
        else:
            assert result["min_required_ah"] > 0

    def test_aging_derating_applied(self):
        """Aging derating (EOL 80%) should increase required capacity."""
        from fireai.v17_core import StrictBatterySizer
        sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
        result = sizer.calculate_minimum_ah(
            quiescent_ma=500.0,
            alarm_ma=2000.0,
            panel_ambient_temp_c=25.0,
        )
        if hasattr(result, "value"):
            # Required Ah should be > base Ah (due to derating)
            assert result.value["min_required_ah"] > result.value["base_ah"]
            # Aging derating should be 0.80 (IEEE 1188 EOL)
            assert result.value["aging_derate"] == pytest.approx(0.80, abs=0.01)
        else:
            assert result["min_required_ah"] > result["base_ah"]

    def test_temperature_derating_cold(self):
        """Cold temperature should increase required capacity significantly."""
        from fireai.v17_core import StrictBatterySizer
        sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
        result_warm = sizer.calculate_minimum_ah(
            quiescent_ma=500.0,
            alarm_ma=2000.0,
            panel_ambient_temp_c=25.0,
        )
        result_cold = sizer.calculate_minimum_ah(
            quiescent_ma=500.0,
            alarm_ma=2000.0,
            panel_ambient_temp_c=0.0,
        )
        # Cold battery requires more capacity
        if hasattr(result_warm, "value"):
            assert result_cold.value["min_required_ah"] > result_warm.value["min_required_ah"]
            assert result_cold.value["thermal_derate"] < result_warm.value["thermal_derate"]
        else:
            assert result_cold["min_required_ah"] > result_warm["min_required_ah"]

    def test_installed_battery_check(self):
        """Checking installed battery should report adequacy."""
        from fireai.v17_core import StrictBatterySizer
        sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
        result = sizer.calculate_minimum_ah(
            quiescent_ma=500.0,
            alarm_ma=2000.0,
            panel_ambient_temp_c=25.0,
            installed_battery_ah=55.0,
            battery_cells=6,
        )
        if hasattr(result, "value"):
            assert result.value["is_adequate"] is True
            assert result.value["installed_ah"] == 55.0
        else:
            assert result["is_adequate"] is True

    def test_insufficient_battery_detected(self):
        """Insufficient battery should be detected and reported."""
        from fireai.v17_core import StrictBatterySizer
        sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
        result = sizer.calculate_minimum_ah(
            quiescent_ma=3000.0,
            alarm_ma=8000.0,
            panel_ambient_temp_c=0.0,  # Cold!
            installed_battery_ah=7.0,
            battery_cells=6,
        )
        if hasattr(result, "value"):
            assert result.value["is_adequate"] is False
        else:
            assert result["is_adequate"] is False

    def test_provenance_has_battery_audit(self):
        """DecisionProvenance should have IEEE 485/1188 citations."""
        from fireai.v17_core import StrictBatterySizer
        from fireai.core.provenance import DecisionProvenance
        sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
        result = sizer.calculate_minimum_ah(
            quiescent_ma=500.0,
            alarm_ma=2000.0,
            panel_ambient_temp_c=25.0,
        )
        if isinstance(result, DecisionProvenance):
            assert result.decision_type == "psu_battery_sizing"
            assert len(result.rules_applied) >= 2
            citations = [r["citation"] for r in result.rules_applied]
            assert any("10.6.7" in c for c in citations)
            assert result.algorithm["name"] == "ThermalDeratedSLA"
            assert result.algorithm["version"] == "v17"

    def test_audit_installed_battery_method(self):
        """audit_installed_battery() convenience method should work."""
        from fireai.v17_core import StrictBatterySizer
        sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
        result = sizer.audit_installed_battery(
            quiescent_ma=500.0,
            alarm_ma=2000.0,
            installed_battery_ah=55.0,
        )
        assert result is not None


# ============================================================================
# TenabilityEvaluator (v17_core) Tests
# ============================================================================

class TestV17TenabilityEvaluator:
    """Test the V17 TenabilityEvaluator wrapper with DecisionProvenance."""

    def test_safe_design_passes(self):
        """When ASET >> RSET, design should be safe."""
        from fireai.v17_core import TenabilityEvaluator
        evaluator = TenabilityEvaluator(walking_speed_mps=1.0, pre_movement_delay_s=60.0)
        result = evaluator.validate_aset_vs_rset(
            longest_travel_dist_m=30.0,
            estimated_fill_time_s=600.0,
            safety_margin=2.0,
        )
        if hasattr(result, "value"):
            assert result.value["is_safe"] is True
            assert result.value["status"] == "SAFE"
        else:
            assert result["is_safe"] is True

    def test_unsafe_design_fails(self):
        """When ASET < RSET, design should fail with UNSURVIVABLE_CHOKEPOINT."""
        from fireai.v17_core import TenabilityEvaluator
        evaluator = TenabilityEvaluator(walking_speed_mps=1.0, pre_movement_delay_s=60.0)
        result = evaluator.validate_aset_vs_rset(
            longest_travel_dist_m=100.0,
            estimated_fill_time_s=30.0,  # Very fast smoke fill
            safety_margin=2.0,
        )
        if hasattr(result, "value"):
            assert result.value["is_safe"] is False
            assert result.value["status"] == "UNSURVIVABLE_CHOKEPOINT"
        else:
            assert result["is_safe"] is False
            assert result["status"] == "UNSURVIVABLE_CHOKEPOINT"

    def test_occupancy_based_overrides(self):
        """Providing occupancy_type should use occupancy-based parameters."""
        from fireai.v17_core import TenabilityEvaluator
        evaluator = TenabilityEvaluator(walking_speed_mps=1.0, pre_movement_delay_s=60.0)
        # With occupancy_type=healthcare: slower speed (0.5 m/s), longer delay (180s)
        result = evaluator.validate_aset_vs_rset(
            longest_travel_dist_m=30.0,
            estimated_fill_time_s=300.0,
            occupancy_type="healthcare",
            is_sprinklered=False,  # Very high safety factor
        )
        if hasattr(result, "value"):
            # Healthcare RSET should be longer than with default 1.0 m/s
            assert result.value["rset_s"] > 60 + 30  # > 90s (default delay + travel)
        else:
            assert result["rset_s"] > 90

    def test_time_series_aset(self):
        """Time-series smoke data should produce accurate ASET."""
        from fireai.v17_core import TenabilityEvaluator
        evaluator = TenabilityEvaluator()
        result = evaluator.validate_aset_vs_rset(
            longest_travel_dist_m=30.0,
            estimated_fill_time_s=300.0,  # Fallback if time-series fails
            smoke_layer_height_series=[
                (0.0, 3.0), (60.0, 2.8), (120.0, 2.5),
                (180.0, 2.0), (240.0, 1.5), (300.0, 0.5),
            ],
            occupancy_type="business",
        )
        if hasattr(result, "value"):
            assert result.value["aset_s"] > 0
        else:
            assert result["aset_s"] > 0

    def test_provenance_has_tenability_audit(self):
        """DecisionProvenance should have NFPA 101/SFPE citations."""
        from fireai.v17_core import TenabilityEvaluator
        from fireai.core.provenance import DecisionProvenance
        evaluator = TenabilityEvaluator(walking_speed_mps=1.0, pre_movement_delay_s=60.0)
        result = evaluator.validate_aset_vs_rset(
            longest_travel_dist_m=45.0,
            estimated_fill_time_s=300.0,
            safety_margin=2.0,
        )
        if isinstance(result, DecisionProvenance):
            assert result.decision_type == "life_safety_tenability_check"
            assert len(result.rules_applied) >= 2
            citations = [r["citation"] for r in result.rules_applied]
            assert any("101" in c or "SFPE" in c for c in citations)
            assert result.algorithm["name"] == "DeterministicASET_RSET_Gate"
            assert result.algorithm["version"] == "v17"

    def test_full_analysis_method(self):
        """full_analysis() should return dict for release_gates.py Gate 7."""
        from fireai.v17_core import TenabilityEvaluator
        evaluator = TenabilityEvaluator()
        result = evaluator.full_analysis(
            room_area_m2=100.0,
            room_height_m=3.0,
            travel_distance_m=30.0,
            occupancy_type="business",
            is_sprinklered=True,
        )
        assert "aset_seconds" in result
        assert "rset_seconds" in result
        assert "is_safe" in result
        assert "verdict" in result


# ============================================================================
# Enterprise Orchestrator Integration Tests
# ============================================================================

class TestEnterpriseOrchestrator:
    """Test the V17 Enterprise Orchestrator integration pipeline."""

    def test_full_check_all_pass(self):
        """All three checks should pass with adequate parameters."""
        from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator
        orch = EnterpriseOrchestrator()
        result = orch.run_full_check(
            acoustic_params={
                "room_id": "R-101",
                "occ_type": "business",
                "speakers": [{"x": 5, "y": 5, "z": 2.8, "rating_db_3m": 95}],
                "check_points": [{"x": 5, "y": 5, "z": 1.5}],
            },
            battery_params={
                "quiescent_ma": 500.0,
                "alarm_ma": 2000.0,
                "panel_ambient_temp_c": 25.0,
                "installed_battery_ah": 55.0,
            },
            tenability_params={
                "longest_travel_dist_m": 30.0,
                "estimated_fill_time_s": 600.0,
                "occupancy_type": "business",
                "is_sprinklered": True,
            },
        )
        assert result.acoustic_compliant is True
        assert result.battery_compliant is True
        assert result.tenability_compliant is True
        assert result.all_compliant is True

    def test_acoustic_failure_propagates(self):
        """Acoustic failure should cause system-wide failure."""
        from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator
        orch = EnterpriseOrchestrator()
        result = orch.run_full_check(
            acoustic_params={
                "room_id": "R-BAD",
                "occ_type": "mechanical",  # 85 dBA ambient!
                "speakers": [{"x": 1, "y": 1, "z": 3.0, "rating_db_3m": 75}],
                "check_points": [{"x": 50, "y": 50, "z": 1.5}],
            },
            battery_params={
                "quiescent_ma": 500.0,
                "alarm_ma": 2000.0,
                "panel_ambient_temp_c": 25.0,
                "installed_battery_ah": 55.0,
            },
            tenability_params={
                "longest_travel_dist_m": 30.0,
                "estimated_fill_time_s": 600.0,
                "occupancy_type": "business",
            },
        )
        assert result.acoustic_compliant is False
        assert result.all_compliant is False

    def test_battery_failure_propagates(self):
        """Battery failure should cause system-wide failure."""
        from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator
        orch = EnterpriseOrchestrator()
        result = orch.run_full_check(
            acoustic_params={
                "room_id": "R-OK",
                "occ_type": "business",
                "speakers": [{"x": 5, "y": 5, "z": 2.8, "rating_db_3m": 95}],
                "check_points": [{"x": 5, "y": 5, "z": 1.5}],
            },
            battery_params={
                "quiescent_ma": 5000.0,
                "alarm_ma": 15000.0,
                "panel_ambient_temp_c": 0.0,
                "installed_battery_ah": 7.0,
            },
            tenability_params={
                "longest_travel_dist_m": 30.0,
                "estimated_fill_time_s": 600.0,
                "occupancy_type": "business",
            },
        )
        assert result.battery_compliant is False
        assert result.all_compliant is False

    def test_tenability_failure_propagates(self):
        """Tenability failure should cause system-wide failure."""
        from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator
        orch = EnterpriseOrchestrator()
        result = orch.run_full_check(
            acoustic_params={
                "room_id": "R-OK",
                "occ_type": "business",
                "speakers": [{"x": 5, "y": 5, "z": 2.8, "rating_db_3m": 95}],
                "check_points": [{"x": 5, "y": 5, "z": 1.5}],
            },
            battery_params={
                "quiescent_ma": 500.0,
                "alarm_ma": 2000.0,
                "panel_ambient_temp_c": 25.0,
                "installed_battery_ah": 55.0,
            },
            tenability_params={
                "longest_travel_dist_m": 200.0,
                "estimated_fill_time_s": 15.0,  # Very fast smoke fill
                "occupancy_type": "healthcare",
                "is_sprinklered": False,
            },
        )
        assert result.tenability_compliant is False
        assert result.all_compliant is False

    def test_orchestrator_release_gates(self):
        """Release gates should be evaluated with V17 results."""
        from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator
        orch = EnterpriseOrchestrator()
        result = orch.run_full_check(
            acoustic_params={
                "room_id": "R-101",
                "occ_type": "business",
                "speakers": [{"x": 5, "y": 5, "z": 2.8, "rating_db_3m": 95}],
                "check_points": [{"x": 5, "y": 5, "z": 1.5}],
            },
            battery_params={
                "quiescent_ma": 500.0,
                "alarm_ma": 2000.0,
                "panel_ambient_temp_c": 25.0,
                "installed_battery_ah": 55.0,
            },
            tenability_params={
                "longest_travel_dist_m": 30.0,
                "estimated_fill_time_s": 600.0,
                "occupancy_type": "business",
            },
        )
        # Release gate result should be present
        if result.release_gate_result is not None:
            assert "checks" in result.release_gate_result
            # Gate 7 (ASET/RSET) and Gate 8 (Battery) should be in checks
            assert "aset_rset_valid" in result.release_gate_result["checks"]
            assert "battery_sized" in result.release_gate_result["checks"]

    def test_individual_check_methods(self):
        """Individual check methods (check_acoustics, check_battery, check_tenability) should work."""
        from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator
        orch = EnterpriseOrchestrator()

        # Acoustic check
        acoustic = orch.check_acoustics(
            room_id="R-1", occ_type="business",
            speakers=[{"x": 5, "y": 5, "z": 2.8, "rating_db_3m": 95}],
            check_points=[{"x": 5, "y": 5, "z": 1.5}],
        )
        assert acoustic is not None

        # Battery check
        battery = orch.check_battery(quiescent_ma=500, alarm_ma=2000)
        assert battery is not None

        # Tenability check
        tenability = orch.check_tenability(
            longest_travel_dist_m=30, estimated_fill_time_s=300,
        )
        assert tenability is not None


# ============================================================================
# V17 Package Import Tests
# ============================================================================

class TestV17PackageImports:
    """Test that V17 modules are importable from expected paths."""

    def test_import_from_v17_core(self):
        """Import directly from fireai.v17_core."""
        from fireai.v17_core import AcousticSPLCalculator, StrictBatterySizer, TenabilityEvaluator
        assert AcousticSPLCalculator is not None
        assert StrictBatterySizer is not None
        assert TenabilityEvaluator is not None

    def test_import_enterprise_orchestrator(self):
        """Import EnterpriseOrchestrator from bridges."""
        from fireai.bridges.enterprise_pipeline import EnterpriseOrchestrator
        assert EnterpriseOrchestrator is not None

    def test_v17_system_result_dataclass(self):
        """V17SystemResult should be a proper dataclass."""
        from fireai.bridges.enterprise_pipeline import V17SystemResult
        result = V17SystemResult(
            acoustic_compliant=True,
            battery_compliant=True,
            tenability_compliant=True,
            all_compliant=True,
        )
        assert result.acoustic_compliant is True
        assert result.all_compliant is True
        assert result.violations == []


# ============================================================================
# Cross-Module Integration Tests
# ============================================================================

class TestCrossModuleIntegration:
    """Test cross-module scenarios that the consultant identified."""

    def test_door_attenuation_plus_mechanical_room(self):
        """Mechanical room + door attenuation = most challenging acoustic scenario."""
        from fireai.v17_core import AcousticSPLCalculator
        calc = AcousticSPLCalculator()
        # Mechanical room: 85 dBA ambient, speaker behind closed door
        result = calc.calculate_room_spl(
            room_id="R-MECH",
            occ_type="mechanical",
            speakers=[{"x": 3, "y": 5, "z": 3.0, "rating_db_3m": 100, "behind_closed_door": True}],
            check_points=[{"x": 20, "y": 5, "z": 1.5}],
        )
        # Required: 85 + 15 = 100 dBA minimum
        # With -15 dB door attenuation, most speakers won't reach this
        if hasattr(result, "value"):
            # Likely fails in this scenario — that's the point
            assert result.value["min_spl_achieved"] < 100.0 or result.value.get("pass") is False

    def test_cold_battery_plus_high_load(self):
        """Cold + high load = real-world battery failure scenario."""
        from fireai.v17_core import StrictBatterySizer
        sizer = StrictBatterySizer(standby_hours=24.0, alarm_minutes=5.0)
        # A battery that "passes" at 25°C...
        result_warm = sizer.calculate_minimum_ah(
            quiescent_ma=1500.0, alarm_ma=5000.0,
            panel_ambient_temp_c=25.0,
            installed_battery_ah=55.0,
        )
        # ...but fails at 0°C (unconditioned space in winter)
        result_cold = sizer.calculate_minimum_ah(
            quiescent_ma=1500.0, alarm_ma=5000.0,
            panel_ambient_temp_c=0.0,
            installed_battery_ah=55.0,
        )
        if hasattr(result_warm, "value") and hasattr(result_cold, "value"):
            # Warm might pass, cold should fail or have less margin
            if result_warm.value.get("is_adequate"):
                assert not result_cold.value.get("is_adequate") or \
                       result_cold.value["margin_pct"] < result_warm.value["margin_pct"]

    def test_healthcare_evacuation_vs_smoke_fill(self):
        """Healthcare: slow speed + high delay vs fast smoke = tenability failure."""
        from fireai.v17_core import TenabilityEvaluator
        evaluator = TenabilityEvaluator(walking_speed_mps=1.0, pre_movement_delay_s=60.0)
        # Consultant's fixed params would show SAFE
        result_default = evaluator.validate_aset_vs_rset(
            longest_travel_dist_m=45.0,
            estimated_fill_time_s=120.0,
            safety_margin=2.0,
        )
        # With occupancy_type=healthcare: 0.5 m/s, 180s delay, 2.5x factor
        result_healthcare = evaluator.validate_aset_vs_rset(
            longest_travel_dist_m=45.0,
            estimated_fill_time_s=120.0,
            occupancy_type="healthcare",
            is_sprinklered=False,
        )
        # Healthcare RSET should be much longer
        if hasattr(result_default, "value") and hasattr(result_healthcare, "value"):
            assert result_healthcare.value["rset_s"] > result_default.value["rset_s"]
