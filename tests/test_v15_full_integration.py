"""
tests/test_v15_full_integration.py
===================================
V15 Full Integration Tests — FACP Capacity Auditor, As-Built Reconciliator,
Orchestrator integration, FirestoppingAnnotator, Pathway Survivability,
and Duct Detector pipeline connectivity.
"""
import pytest
import math
import sys
import os

sys.path.insert(0, '/home/z/my-project/revit')


# ═══════════════════════════════════════════════════════════════════════
# FACP Capacity Auditor Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFACPCapacityAuditor:
    """V15: FACP Global Capacity Auditor — PSU burnout + protocol limits."""

    def test_notifier_profile_defaults(self):
        """Notifier FlashScan profile has correct limits."""
        from fireai.core.facp_capacity_auditor import get_default_profile
        profile = get_default_profile("notifier")
        assert profile.max_detectors_per_slc == 159
        assert profile.max_modules_per_slc == 159
        assert profile.max_total_nac_amps == 10.0
        assert profile.max_amps_per_nac == 3.0

    def test_simplex_profile_defaults(self):
        """Simplex profile has correct limits."""
        from fireai.core.facp_capacity_auditor import get_default_profile
        profile = get_default_profile("simplex")
        assert profile.max_detectors_per_slc == 250
        assert profile.max_total_nac_amps == 10.0

    def test_siemens_profile_defaults(self):
        """Siemens profile has correct limits."""
        from fireai.core.facp_capacity_auditor import get_default_profile
        profile = get_default_profile("siemens")
        assert profile.max_total_nac_amps == 8.0
        assert profile.max_amps_per_nac == 2.5

    def test_unknown_manufacturer_raises(self):
        """Unknown manufacturer should raise ValueError."""
        from fireai.core.facp_capacity_auditor import get_default_profile
        with pytest.raises(ValueError, match="Unknown manufacturer"):
            get_default_profile("honeywell")

    def test_safe_nac_inrush(self):
        """NAC circuits within limits → SAFE."""
        from fireai.core.facp_capacity_auditor import FACPCapacityAuditor, get_default_profile
        profile = get_default_profile("notifier")
        auditor = FACPCapacityAuditor(profile)

        nacs = [
            {"id": "NAC-1", "total_inrush_amps": 2.0},
            {"id": "NAC-2", "total_inrush_amps": 2.5},
        ]
        result = auditor.audit_global_inrush(nacs)
        assert result["status"] == "SAFE"
        assert result["total_inrush_a"] == 4.5
        assert len(result["violations"]) == 0

    def test_per_nac_overload(self):
        """Single NAC exceeding per-circuit limit → CRITICAL violation."""
        from fireai.core.facp_capacity_auditor import FACPCapacityAuditor, get_default_profile
        profile = get_default_profile("notifier")
        auditor = FACPCapacityAuditor(profile)

        nacs = [{"id": "NAC-1", "total_inrush_amps": 5.0}]  # > 3.0A per NAC
        result = auditor.audit_global_inrush(nacs)
        assert result["status"] == "CATASTROPHIC_OVERLOAD"
        assert any("NAC-1" in v["message"] for v in result["violations"])

    def test_aggregate_psu_overload(self):
        """Total inrush exceeding PSU capacity → CRITICAL violation."""
        from fireai.core.facp_capacity_auditor import FACPCapacityAuditor, get_default_profile
        profile = get_default_profile("notifier")
        auditor = FACPCapacityAuditor(profile)

        nacs = [
            {"id": "NAC-1", "total_inrush_amps": 3.0},  # at limit
            {"id": "NAC-2", "total_inrush_amps": 3.0},
            {"id": "NAC-3", "total_inrush_amps": 5.0},  # pushes total to 11A > 10A
        ]
        result = auditor.audit_global_inrush(nacs)
        assert result["status"] == "CATASTROPHIC_OVERLOAD"
        assert result["total_inrush_a"] == 11.0
        # Should have both per-NAC and aggregate violations
        assert len(result["violations"]) >= 1

    def test_slc_loop_within_limits(self):
        """SLC loop within device limits → all_pass."""
        from fireai.core.facp_capacity_auditor import FACPCapacityAuditor, get_default_profile
        profile = get_default_profile("notifier")
        auditor = FACPCapacityAuditor(profile)

        # 100 detectors + 50 modules — within Notifier 159/159
        devices = (
            [{"device_type": "SMOKE_PHOTOELECTRIC"} for _ in range(100)]
            + [{"device_type": "MANUAL_PULL_STATION"} for _ in range(50)]
        )
        slc_loops = [{"loop_id": "SLC-01", "devices": devices}]
        result = auditor.audit_slc_protocol_limits(slc_loops)

        assert result["all_pass"] is True
        assert len(result["loops_passing"]) == 1
        assert len(result["loops_failing"]) == 0

    def test_slc_loop_exceeds_detector_limit(self):
        """SLC loop exceeding detector limit → FAIL."""
        from fireai.core.facp_capacity_auditor import FACPCapacityAuditor, get_default_profile
        profile = get_default_profile("notifier")
        auditor = FACPCapacityAuditor(profile)

        # 200 detectors — exceeds 159 limit
        devices = [{"device_type": "SMOKE_PHOTOELECTRIC"} for _ in range(200)]
        slc_loops = [{"loop_id": "SLC-01", "devices": devices}]
        result = auditor.audit_slc_protocol_limits(slc_loops)

        assert result["all_pass"] is False
        assert len(result["loops_failing"]) == 1

    def test_device_classification_by_type_field(self):
        """Device classification uses device_type field, NOT string matching in ID."""
        from fireai.core.facp_capacity_auditor import _classify_device, DETECTOR_DEVICE_TYPES

        # Exact match detectors
        assert _classify_device("SMOKE_PHOTOELECTRIC") == "detector"
        assert _classify_device("HEAT_FIXED") == "detector"
        assert _classify_device("HEAT_RATE_OF_RISE") == "detector"

        # Exact match modules
        assert _classify_device("MANUAL_PULL_STATION") == "module"
        assert _classify_device("DUCT_SMOKE") == "module"

        # Substring match modules
        assert _classify_device("RELAY_MODULE_01") == "module"
        assert _classify_device("MONITOR_MODULE") == "module"
        assert _classify_device("OUTPUT_CIRCUIT") == "module"

        # Unknown → conservative default (module)
        assert _classify_device("UNKNOWN_TYPE") == "module"

    def test_case_insensitive_manufacturer(self):
        """Manufacturer lookup is case-insensitive."""
        from fireai.core.facp_capacity_auditor import get_default_profile
        assert get_default_profile("Notifier").manufacturer == "Notifier FlashScan"
        assert get_default_profile("NOTIFIER").manufacturer == "Notifier FlashScan"
        assert get_default_profile("notifier").manufacturer == "Notifier FlashScan"

    def test_inrush_result_has_rules_applied(self):
        """Audit result includes rules_applied for traceability."""
        from fireai.core.facp_capacity_auditor import FACPCapacityAuditor, get_default_profile
        profile = get_default_profile("notifier")
        auditor = FACPCapacityAuditor(profile)

        nacs = [{"id": "NAC-1", "total_inrush_amps": 1.0}]
        result = auditor.audit_global_inrush(nacs)
        assert "rules_applied" in result
        assert len(result["rules_applied"]) >= 2  # per-NAC + aggregate


# ═══════════════════════════════════════════════════════════════════════
# As-Built Reconciliator Tests
# ═══════════════════════════════════════════════════════════════════════

class TestAsBuiltReconciliator:
    """V15: 3D As-Built Reconciliator — design vs. field comparison."""

    def _make_design(self):
        """Create a sample design manifest."""
        return {
            "devices": [
                {"id": "S1", "x": 10.0, "y": 20.0, "z": 3.0, "device_type": "SMOKE"},
                {"id": "H1", "x": 30.0, "y": 40.0, "z": 3.0, "device_type": "HEAT"},
                {"id": "MCP1", "x": 50.0, "y": 60.0, "z": 1.2, "device_type": "MANUAL_PULL_STATION"},
                {"id": "D1", "x": 70.0, "y": 80.0, "z": 2.5, "device_type": "DUCT_SMOKE"},
            ]
        }

    def test_all_devices_verified(self):
        """All as-built devices within tolerance → VERIFIED."""
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator

        design = self._make_design()
        reconciliator = AsBuiltReconciliator(design)

        as_built = [
            {"id": "S1", "x": 10.1, "y": 20.1, "z": 3.0, "device_type": "SMOKE"},
            {"id": "H1", "x": 30.0, "y": 40.2, "z": 3.0, "device_type": "HEAT"},
            {"id": "MCP1", "x": 50.05, "y": 60.05, "z": 1.2, "device_type": "MANUAL_PULL_STATION"},
            {"id": "D1", "x": 70.2, "y": 80.2, "z": 2.5, "device_type": "DUCT_SMOKE"},
        ]

        result = reconciliator.reconcile(as_built)
        assert result.status == "VERIFIED"
        assert result.verified_count == 4
        assert len(result.rogue_devices) == 0
        assert len(result.missing_devices) == 0
        assert len(result.drifted_devices) == 0

    def test_drifted_device_detected(self):
        """Device beyond tolerance → DEVIATION_DETECTED."""
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator

        design = self._make_design()
        reconciliator = AsBuiltReconciliator(design)

        # S1 drifted by 1.0m in x — exceeds 0.3m tolerance for SMOKE
        as_built = [
            {"id": "S1", "x": 11.0, "y": 20.0, "z": 3.0, "device_type": "SMOKE"},
            {"id": "H1", "x": 30.0, "y": 40.0, "z": 3.0, "device_type": "HEAT"},
            {"id": "MCP1", "x": 50.0, "y": 60.0, "z": 1.2, "device_type": "MANUAL_PULL_STATION"},
            {"id": "D1", "x": 70.0, "y": 80.0, "z": 2.5, "device_type": "DUCT_SMOKE"},
        ]

        result = reconciliator.reconcile(as_built)
        assert result.status == "DEVIATION_DETECTED"
        assert len(result.drifted_devices) == 1
        assert result.drifted_devices[0][0] == "S1"

    def test_rogue_device_detected(self):
        """Device in as-built but NOT in design → rogue."""
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator

        design = self._make_design()
        reconciliator = AsBuiltReconciliator(design)

        as_built = [
            {"id": "S1", "x": 10.0, "y": 20.0, "z": 3.0, "device_type": "SMOKE"},
            {"id": "ROGUE1", "x": 100.0, "y": 100.0, "z": 3.0, "device_type": "SMOKE"},
            {"id": "H1", "x": 30.0, "y": 40.0, "z": 3.0, "device_type": "HEAT"},
            {"id": "MCP1", "x": 50.0, "y": 60.0, "z": 1.2, "device_type": "MANUAL_PULL_STATION"},
            {"id": "D1", "x": 70.0, "y": 80.0, "z": 2.5, "device_type": "DUCT_SMOKE"},
        ]

        result = reconciliator.reconcile(as_built)
        assert result.status == "DEVIATION_DETECTED"
        assert len(result.rogue_devices) == 1
        assert result.rogue_devices[0][0] == "ROGUE1"

    def test_missing_device_detected(self):
        """Device in design but NOT in as-built → missing (contractor omission)."""
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator

        design = self._make_design()
        reconciliator = AsBuiltReconciliator(design)

        # D1 is missing from as-built
        as_built = [
            {"id": "S1", "x": 10.0, "y": 20.0, "z": 3.0, "device_type": "SMOKE"},
            {"id": "H1", "x": 30.0, "y": 40.0, "z": 3.0, "device_type": "HEAT"},
            {"id": "MCP1", "x": 50.0, "y": 60.0, "z": 1.2, "device_type": "MANUAL_PULL_STATION"},
            # D1 deliberately omitted
        ]

        result = reconciliator.reconcile(as_built)
        assert result.status == "DEVIATION_DETECTED"
        assert len(result.missing_devices) == 1
        assert result.missing_devices[0][0] == "D1"

    def test_3d_drift_includes_z_axis(self):
        """Drift calculation is truly 3D — z-axis deviation counts."""
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator

        design = {"devices": [
            {"id": "S1", "x": 10.0, "y": 20.0, "z": 3.0, "device_type": "SMOKE"},
        ]}
        reconciliator = AsBuiltReconciliator(design)

        # Same x,y but z shifted by 1.0m — should trigger drift
        as_built = [
            {"id": "S1", "x": 10.0, "y": 20.0, "z": 4.0, "device_type": "SMOKE"},
        ]

        result = reconciliator.reconcile(as_built)
        assert result.status == "DEVIATION_DETECTED"
        assert len(result.drifted_devices) == 1
        # Drift should be 1.0m (z-axis only)
        assert abs(result.drifted_devices[0][1] - 1.0) < 0.01

    def test_pull_station_tight_tolerance(self):
        """MANUAL_PULL_STATION has 0.15m tolerance (ADA §309)."""
        from fireai.core.as_built_reconciliator import DEVICE_TOLERANCES
        assert DEVICE_TOLERANCES["MANUAL_PULL_STATION"] == 0.15

    def test_no_merkle_root_skips_integrity(self):
        """No merkle_root → integrity_verified is None (not False)."""
        from fireai.core.as_built_reconciliator import AsBuiltReconciliator

        design = {"devices": [
            {"id": "S1", "x": 10.0, "y": 20.0, "z": 3.0, "device_type": "SMOKE"},
        ]}
        reconciliator = AsBuiltReconciliator(design, merkle_root=None)
        assert reconciliator._integrity_verified is None

    def test_total_deviations_property(self):
        """total_deviations counts rogue + missing + drifted."""
        from fireai.core.as_built_reconciliator import ReconciliationResult

        result = ReconciliationResult(
            status="DEVIATION_DETECTED",
            verified_count=0,
            rogue_devices=[("R1", "rogue")],
            missing_devices=[("M1", "missing"), ("M2", "missing")],
            drifted_devices=[("D1", 1.0, 0.3, "drifted")],
            summary="test",
        )
        assert result.total_deviations == 4  # 1 + 2 + 1


# ═══════════════════════════════════════════════════════════════════════
# Orchestrator Integration Tests
# ═══════════════════════════════════════════════════════════════════════

class TestOrchestratorV15Integration:
    """V15: Orchestrator now integrates FACP, pathway survivability, and ducts."""

    def test_orchestrator_accepts_facp_manufacturer(self):
        """run_full_design() has facp_manufacturer parameter."""
        from bridges.orchestrator import run_full_design
        import inspect

        sig = inspect.signature(run_full_design)
        assert "facp_manufacturer" in sig.parameters

    def test_orchestrator_accepts_ducts(self):
        """run_full_design() has ducts parameter."""
        from bridges.orchestrator import run_full_design
        import inspect

        sig = inspect.signature(run_full_design)
        assert "ducts" in sig.parameters

    def test_orchestrator_accepts_building_spec(self):
        """run_full_design() has building_spec parameter."""
        from bridges.orchestrator import run_full_design
        import inspect

        sig = inspect.signature(run_full_design)
        assert "building_spec" in sig.parameters

    def test_full_design_result_has_facp_audit(self):
        """FullDesignResult has facp_audit field."""
        from bridges.orchestrator import FullDesignResult
        result = FullDesignResult(project_name="test", input_file="test.dxf")
        assert hasattr(result, 'facp_audit')
        assert isinstance(result.facp_audit, dict)

    def test_full_design_result_has_pathway_survivability(self):
        """FullDesignResult has pathway_survivability field."""
        from bridges.orchestrator import FullDesignResult
        result = FullDesignResult(project_name="test", input_file="test.dxf")
        assert hasattr(result, 'pathway_survivability')
        assert isinstance(result.pathway_survivability, dict)


# ═══════════════════════════════════════════════════════════════════════
# Pathway Survivability Integration Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPathwaySurvivabilityIntegration:
    """V15: Pathway survivability engine connected to orchestrator."""

    def test_high_rise_requires_level_2(self):
        """High-rise building (>23m) requires Level 2 survivability."""
        from fireai.core.pathway_survivability_engine import (
            PathwaySurvivabilityEngine, BuildingSpec,
        )
        from fireai.core.contracts import OccupancyCategory, PathwaySurvivabilityLevel

        spec = BuildingSpec(
            occupancy=OccupancyCategory.RESIDENTIAL,
            height_m=50.0,
            is_sprinklered=True,
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)

        assert result.building_level >= PathwaySurvivabilityLevel.LEVEL_2

    def test_sprinklered_low_rise_level_1(self):
        """Fully sprinklered low-rise with full evacuation → Level 1."""
        from fireai.core.pathway_survivability_engine import (
            PathwaySurvivabilityEngine, BuildingSpec,
        )
        from fireai.core.contracts import OccupancyCategory, PathwaySurvivabilityLevel

        spec = BuildingSpec(
            occupancy=OccupancyCategory.BUSINESS,
            height_m=10.0,
            is_sprinklered=True,
            evacuation_type="full",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)

        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_1

    def test_staged_evacuation_non_sprinklered_level_3(self):
        """Staged evacuation in non-sprinklered → Level 3 (highest)."""
        from fireai.core.pathway_survivability_engine import (
            PathwaySurvivabilityEngine, BuildingSpec,
        )
        from fireai.core.contracts import OccupancyCategory, PathwaySurvivabilityLevel

        spec = BuildingSpec(
            occupancy=OccupancyCategory.BUSINESS,
            height_m=10.0,
            is_sprinklered=False,
            evacuation_type="staged",
        )
        engine = PathwaySurvivabilityEngine()
        result = engine.classify(spec)

        assert result.building_level == PathwaySurvivabilityLevel.LEVEL_3


# ═══════════════════════════════════════════════════════════════════════
# Duct Detector Integration Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDuctDetectorIntegration:
    """V15: Duct detector module connected to pipeline."""

    def test_supply_duct_requires_detector(self):
        """Supply duct >1m and >0.2m wide requires detector."""
        from fireai.core.duct_detector import analyse_duct, DuctSpec

        duct = DuctSpec(
            duct_id="AHU-1-S",
            length_m=10.0,
            width_m=0.5,
            duct_type="supply",
        )
        result = analyse_duct(duct)
        assert not result.exempt
        assert result.detector_count >= 1

    def test_exhaust_duct_exempt(self):
        """Exhaust ducts are exempt from detector requirements."""
        from fireai.core.duct_detector import analyse_duct, DuctSpec

        duct = DuctSpec(
            duct_id="EX-1",
            length_m=10.0,
            width_m=0.5,
            duct_type="exhaust",
        )
        result = analyse_duct(duct)
        assert result.exempt is True
        assert result.detector_count == 0

    def test_narrow_duct_exempt(self):
        """Ducts narrower than 0.20m are exempt."""
        from fireai.core.duct_detector import analyse_duct, DuctSpec

        duct = DuctSpec(
            duct_id="NARROW-1",
            length_m=10.0,
            width_m=0.15,
        )
        result = analyse_duct(duct)
        assert result.exempt is True

    def test_total_duct_detectors(self):
        """total_duct_detectors sums across all results."""
        from fireai.core.duct_detector import analyse_ducts, total_duct_detectors, DuctSpec

        ducts = [
            DuctSpec(duct_id="D1", length_m=10.0, width_m=0.5),
            DuctSpec(duct_id="D2", length_m=5.0, width_m=0.3),
        ]
        results = analyse_ducts(ducts)
        total = total_duct_detectors(results)
        assert total >= 2  # at least 1 per duct


# ═══════════════════════════════════════════════════════════════════════
# FirestoppingAnnotator Integration Tests
# ═══════════════════════════════════════════════════════════════════════

class TestFirestoppingAnnotatorIntegration:
    """V15: FirestoppingAnnotator detection works and is connected."""

    def test_penetration_at_wall_crossing(self):
        """Cable crossing fire-rated wall produces penetration point."""
        from fireai.core.firestop_annotator import FirestoppingAnnotator

        walls = [((5.0, 0.0), (5.0, 10.0))]
        annotator = FirestoppingAnnotator(walls)

        cable = [(0.0, 5.0), (10.0, 5.0)]
        penetrations = annotator.locate_penetrations(cable)

        assert len(penetrations) >= 1
        assert abs(penetrations[0][0] - 5.0) < 0.1

    def test_no_penetration_when_parallel(self):
        """Cable running parallel to wall → no penetration."""
        from fireai.core.firestop_annotator import FirestoppingAnnotator

        walls = [((5.0, 0.0), (5.0, 10.0))]
        annotator = FirestoppingAnnotator(walls)

        # Cable runs parallel at x=2.0
        cable = [(2.0, 0.0), (2.0, 10.0)]
        penetrations = annotator.locate_penetrations(cable)

        assert len(penetrations) == 0

    def test_dxf_callout_generation(self):
        """draft_callouts_to_dxf generates DXF entities."""
        import ezdxf
        from fireai.core.firestop_annotator import FirestoppingAnnotator

        doc = ezdxf.new("R2018")
        msp = doc.modelspace()

        walls = [((5.0, 0.0), (5.0, 10.0))]
        annotator = FirestoppingAnnotator(walls)

        cable = [(0.0, 5.0), (10.0, 5.0)]
        count = annotator.draft_callouts_to_dxf(msp, cable)

        assert count >= 1, "Should generate at least one callout"

    def test_output_bridge_firestopping_via_check(self):
        """output_bridge _check_firestopping marks segments crossing walls."""
        from bridges.output_bridge import CableSegment, _check_firestopping
        from shapely.geometry import LineString

        fire_walls = [LineString([(5000, 0), (5000, 10000)])]
        seg = CableSegment(start=(0, 5000), end=(10000, 5000), length_m=10.0)

        _check_firestopping(seg, (0, 5000), (10000, 5000), fire_walls)

        assert seg.firestopping is True
        assert seg.firestopping_ref == "IBC S714"


# ═══════════════════════════════════════════════════════════════════════
# Regression Tests — Existing V13/V14 functionality preserved
# ═══════════════════════════════════════════════════════════════════════

class TestV15Regression:
    """V15 regression: all V13/V14 functionality still works."""

    def test_provenance_shim(self):
        """Provenance shim still re-exports correctly."""
        from fireai.core.provenance import DecisionProvenance, RuleApplied
        assert DecisionProvenance is not None
        assert RuleApplied is not None

    def test_daisy_chain_routing(self):
        """V14 daisy-chain routing still works."""
        from fireai.core.routing_engine_v10 import EliteClassARouter

        router = EliteClassARouter(width=20.0, length=20.0, resolution=0.5)
        facp = (10.0, 1.0)
        devices = [(5.0, 10.0), (15.0, 10.0), (10.0, 18.0)]

        result = router.generate_class_a_loop(facp, devices)

        assert "outgoing_class_a" in result
        assert "return_class_a" in result
        assert len(result["outgoing_class_a"].path) >= 2
        assert len(result["return_class_a"].path) >= 2

    def test_blockchain_readiness_gate(self):
        """Blockchain readiness gate still works."""
        from fireai.core.blockchain_readiness_gate import BlockchainReadinessGate

        artifacts = ["artifact_1", "artifact_2", "artifact_3"]
        gate = BlockchainReadinessGate(artifacts)

        assert gate.merkle_root != "0" * 64
        assert gate.artifact_count == 3

        proof = gate.get_proof(1)
        assert proof.verify() is True
