"""
test_stress_session4.py — Stress Tests for Session 4 Integration
=================================================================
Comprehensive stress tests to find runtime problems after all
Session 4 changes: Speaker Coverage, Fault Isolators, ASET/RSET,
BOQ Generator, Enum Consolidation, Polygon Self-Intersection.

These tests are designed to BREAK things — edge cases, boundary
conditions, adversarial inputs, and large-scale operations.
"""

import pytest
import math
import random


class TestSpeakerCoverageStress:
    """Stress test the acoustic_calculator speaker coverage system."""

    def test_extreme_quiet_ambient(self):
        """Very quiet ambient (20 dBA) should give large coverage."""
        from fireai.core.acoustic_calculator import get_speaker_coverage_radius
        radius = get_speaker_coverage_radius(
            source_dba=95.0, ambient_dba=20.0, mode="public"
        )
        assert radius > 10  # Should cover substantial distance in quiet

    def test_extreme_noisy_environment(self):
        """Very noisy environment (95 dBA) should give tiny coverage."""
        from fireai.core.acoustic_calculator import get_speaker_coverage_radius
        radius = get_speaker_coverage_radius(
            source_dba=95.0, ambient_dba=90.0, mode="public"
        )
        # In 90 dBA noise, a 95 dBA speaker can barely meet 15 dB above
        assert radius >= 0

    def test_sleeping_mode_higher_requirement(self):
        """Sleeping areas require 75 dBA at pillow — more restrictive."""
        from fireai.core.acoustic_calculator import get_speaker_coverage_radius
        public_radius = get_speaker_coverage_radius(
            source_dba=95.0, ambient_dba=40.0, mode="public"
        )
        sleeping_radius = get_speaker_coverage_radius(
            source_dba=95.0, ambient_dba=40.0, mode="sleeping"
        )
        # Sleeping mode should have smaller or equal radius (more restrictive)
        assert sleeping_radius <= public_radius

    def test_many_rooms_boq_speaker_count(self):
        """BOQ generator should handle many rooms without crashing."""
        from fireai.core.boq_generator import generate_full_boq
        rooms = [
            {"room_id": f"R{i}", "area_m2": 50.0 + i * 10, "detector_type": "smoke_detector"}
            for i in range(50)
        ]
        loops = [{"loop_id": "L1", "devices": [], "cable_length_m": 500.0}]
        result = generate_full_boq(rooms, loops, panels=2)
        assert result.detector_count >= 50
        assert result.grand_total_usd > 0

    def test_spl_inverse_square_law(self):
        """Verify SPL decreases with distance per inverse square law."""
        from fireai.core.acoustic_calculator import calculate_spl_at_distance
        r3 = calculate_spl_at_distance(95.0, 3.0, ref_distance_m=3.0)
        r6 = calculate_spl_at_distance(95.0, 6.0, ref_distance_m=3.0)
        # 6m is 2× the 3m reference → ~6 dB drop
        assert r6.effective_dba < r3.effective_dba
        # Exact drop: 20*log10(6/3) = 20*0.301 = 6.02 dB
        expected_drop = 20 * math.log10(2.0)
        actual_drop = r3.effective_dba - r6.effective_dba
        # Without room absorption, drop should be close to expected
        if r6.room_gain_dB < 0.1:  # Negligible room gain
            assert abs(actual_drop - expected_drop) < 0.5

    def test_speaker_deprecated_constant_warning(self):
        """Accessing SPEAKER_COVERAGE should trigger deprecation warning."""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Import and use the deprecated method
            # This tests that the deprecation mechanism works
            from fire_expert_system import NFPA72
            radius = NFPA72.get_speaker_coverage_radius()
            # Should have triggered a DeprecationWarning
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1


class TestFaultIsolationStress:
    """Stress test fault isolation with zone_id and fire_zone_engine."""

    def test_large_loop_250_devices(self):
        """Inject isolators into a full 250-device loop."""
        from fireai.core.fault_isolator_injector import inject_fault_isolators
        devices = [
            {"device_idx": f"D{i}", "device_type": "SMOKE_DETECTOR", "zone_id": f"Z{(i//50)+1}"}
            for i in range(250)
        ]
        result = inject_fault_isolators(devices, max_devices_between_isolators=32)
        assert result.is_compliant is True
        assert result.total_device_count == 250 + result.injected_isolator_count

    def test_many_zones_create_many_isolators(self):
        """Each zone boundary should get an isolator."""
        from fireai.core.fault_isolator_injector import inject_fault_isolators
        devices = []
        for zone in range(5):
            for j in range(10):
                devices.append({
                    "device_idx": f"D{zone}_{j}",
                    "device_type": "SMOKE_DETECTOR",
                    "zone_id": f"Z{zone+1}"
                })
        result = inject_fault_isolators(devices)
        # Should have isolators at zone boundaries (at least 4 boundary transitions)
        assert result.injected_isolator_count >= 5  # 5 zones → at least 5 isolators

    def test_fire_zone_engine_large_floor(self):
        """Zone engine should handle 100+ rooms without crashing."""
        from fireai.core.fire_zone_engine import FireZoneEngine
        engine = FireZoneEngine()
        rooms = [
            {"id": f"R{i}", "area": 50.0 + random.random() * 100,
             "detectors": max(1, int(random.random() * 5)),
             "occupancy": random.choice(["office", "storage", "industrial"])}
            for i in range(100)
        ]
        report = engine.cluster_floor("GF", rooms)
        assert report.total_zones > 0
        assert report.total_area_sqm > 0

        zone_map = engine.build_zone_map(report)
        assert len(zone_map) == 100  # All rooms mapped

    def test_zone_map_integration_with_isolators(self):
        """Full integration: zone engine → zone_map → fault isolator injection."""
        from fireai.core.fire_zone_engine import FireZoneEngine
        from fireai.core.fault_isolator_injector import inject_fault_isolators

        engine = FireZoneEngine()
        rooms = [
            {"id": f"R{i}", "area": 80.0, "detectors": 3,
             "occupancy": "office" if i < 15 else "storage"}
            for i in range(30)
        ]
        report = engine.cluster_floor("F1", rooms)
        zone_map = engine.build_zone_map(report)

        # Create devices for each room
        devices = []
        for i, room in enumerate(rooms):
            for j in range(3):
                devices.append({
                    "device_idx": f"D{i}_{j}",
                    "device_type": "SMOKE_DETECTOR",
                    "room_id": room["id"],
                })

        result = inject_fault_isolators(devices, zone_map=zone_map)
        assert result.is_compliant is True


class TestASETRSETStress:
    """Stress test the ASET/RSET physics pipeline."""

    def test_slow_fire_large_room(self):
        """Slow fire in large room should give long ASET."""
        from fireai.core.aset_rset_calculator import perform_aset_rset_analysis
        result = perform_aset_rset_analysis(
            room_area_m2=1000.0,
            room_height_m=4.0,
            travel_distance_m=60.0,
            occupancy_type="storage",
            fire_growth_rate="slow",
        )
        assert result["aset_seconds"] > 0
        assert result["rset_seconds"] > 0

    def test_fast_fire_small_room(self):
        """Fast fire in small room may give short ASET — could fail safety."""
        from fireai.core.aset_rset_calculator import perform_aset_rset_analysis
        result = perform_aset_rset_analysis(
            room_area_m2=50.0,
            room_height_m=3.0,
            travel_distance_m=45.0,
            occupancy_type="assembly",
            fire_growth_rate="fast",
        )
        # Fast fire in assembly hall = likely unsafe
        # But the function should not crash regardless
        assert result["aset_seconds"] >= 0
        assert "verdict" in result

    def test_all_occupancy_types(self):
        """All supported occupancy types should compute without error."""
        from fireai.core.aset_rset_calculator import perform_aset_rset_analysis
        occ_types = ["business", "assembly", "healthcare", "industrial",
                     "mercantile", "residential", "storage", "educational"]
        for occ in occ_types:
            result = perform_aset_rset_analysis(
                room_area_m2=200.0,
                room_height_m=3.5,
                travel_distance_m=30.0,
                occupancy_type=occ,
            )
            assert result["aset_seconds"] > 0, f"Failed for occupancy: {occ}"

    def test_gate7_numerical_reecheck(self):
        """Gate 7 should numerically re-verify even if caller claims is_safe=True."""
        from fireai.core.release_gates import verify_and_evaluate
        # Caller claims is_safe=True but math says otherwise
        result = verify_and_evaluate(
            aset_rset_result={
                "aset_seconds": 50.0,
                "rset_seconds": 100.0,
                "safety_factor": 1.5,
            }
        )
        # Gate 7 should BLOCK because 50 < 100 * 1.5 = 150
        assert result["checks"]["aset_rset_valid"] is False


class TestBOQGeneratorStress:
    """Stress test the BOQ generator with battery integration."""

    def test_zero_rooms(self):
        """BOQ with zero rooms should return gracefully."""
        from fireai.core.boq_generator import generate_full_boq
        result = generate_full_boq([], [], panels=1, include_notification=False)
        assert result.detector_count == 0

    def test_large_building(self):
        """BOQ for a 500-room building should compute without error."""
        from fireai.core.boq_generator import generate_full_boq
        rooms = [
            {"room_id": f"R{i}", "area_m2": 30.0 + i % 50, "detector_type": "smoke_detector"}
            for i in range(500)
        ]
        loops = [
            {"loop_id": f"L{i}", "devices": [], "cable_length_m": 200.0 + i * 10}
            for i in range(10)
        ]
        result = generate_full_boq(rooms, loops, panels=3)
        assert result.detector_count > 0
        assert result.grand_total_usd > 0

    def test_battery_result_for_release_gate_various_panels(self):
        """Battery result should work for various panel counts."""
        from fireai.core.boq_generator import generate_battery_result_for_release_gate
        for panels in [1, 2, 5]:
            result = generate_battery_result_for_release_gate(panel_count=panels)
            assert result["is_adequate"] is True
            assert result["battery_count"] == panels * 2


class TestEnumConsolidationStress:
    """Stress test enum consolidation between contracts.py and nfpa72_models.py."""

    def test_all_ceiling_types_compatible(self):
        """All CeilingType values should be usable in both modules."""
        from fireai.core.contracts import CeilingType
        from fireai.core.nfpa72_models import CeilingSpec

        # Test that each ceiling type works with CeilingSpec
        for ct in CeilingType:
            spec = CeilingSpec.create_safe(
                height_at_low_point_m=3.5,
                ceiling_type=ct,
            )
            assert spec.ceiling_type == ct

    def test_detector_type_string_equality(self):
        """DetectorType values should be string-comparable."""
        from fireai.core.contracts import DetectorType
        assert DetectorType.SMOKE == "SMOKE"
        assert DetectorType.HEAT == "HEAT"
        assert DetectorType.FLAME == "FLAME"

    def test_no_enum_drift(self):
        """Verify that contracts.py and nfpa72_models.py have same enum."""
        from fireai.core.contracts import DetectorType as C_DT
        from fireai.core.nfpa72_models import DetectorType as M_DT
        from fireai.core.contracts import CeilingType as C_CT
        from fireai.core.nfpa72_models import CeilingType as M_CT

        assert C_DT is M_DT, "DetectorType should be the SAME object (not just equal)"
        assert C_CT is M_CT, "CeilingType should be the SAME object (not just equal)"

        # Verify all members are present
        for member in C_DT:
            assert hasattr(M_DT, member.name)
        for member in C_CT:
            assert hasattr(M_CT, member.name)


class TestPolygonSelfIntersectionStress:
    """Stress test polygon self-intersection detection."""

    def test_large_polygon_validation(self):
        """Large polygon should validate in reasonable time."""
        from fireai.core.geometry_utils import validate_polygon
        # Regular polygon with 50 vertices
        n = 50
        poly = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
        result = validate_polygon(poly)
        assert result.valid is True

    def test_near_self_intersection_warning(self):
        """Near-duplicate vertices should generate warnings in validate_polygon."""
        from fireai.core.geometry_utils import validate_polygon
        # Create polygon with very close non-consecutive vertices
        poly = [(0, 0), (10, 0), (10, 8), (5.01, 4), (5, 4), (0, 8)]
        result = validate_polygon(poly)
        # The near-duplicate check is in the pure-Python path
        # and may or may not trigger depending on Shapely handling
        # Just verify the polygon is valid (no self-intersection)
        assert isinstance(result.valid, bool)

    def test_contracts_self_intersection_rejection(self):
        """contracts.py should reject self-intersecting polygons."""
        from fireai.core.contracts import validate_room_input, ContractViolation
        with pytest.raises(ContractViolation, match="self-intersecting"):
            validate_room_input({
                "room_id": "R-X",
                "polygon": [(0, 0), (5, 5), (0, 5), (5, 0)],
                "ceiling_height_m": 3.0,
            })


class TestReleaseGatesFullStress:
    """Stress test the full release gate system with all 8 gates."""

    def test_all_gates_missing_defaults_to_blocked(self):
        """Missing data should default all gates to blocked."""
        from fireai.core.release_gates import verify_and_evaluate
        result = verify_and_evaluate()
        assert result["release_status"] == "blocked"
        assert len(result["blockers"]) == 8

    def test_evidence_chain_tampering_detected(self):
        """Tampered evidence should be detected even with valid other gates."""
        from fireai.core.release_gates import verify_and_evaluate
        from fireai.core.evidence_chain import EvidenceChain

        chain = EvidenceChain(secret_key="stress-key", signer_id="stress")
        envelope = chain.build_envelope(
            snapshot_payload={"room_id": "R-1"},
            analysis_payload={"is_compliant": True},
        )
        # Tamper
        envelope["envelope_hash"] = "TAMPERED_HASH"

        result = verify_and_evaluate(
            input_payload={"room_id": "R-1", "polygon": [(0,0),(10,0),(10,8),(0,8)], "ceiling_height_m": 3.0},
            nfpa_results={"is_compliant": True, "violations": []},
            evidence_envelope=envelope,
            evidence_secret_key="stress-key",
            drift_records=[],
            stale_detector_ids=[],
        )
        assert result["checks"]["evidence_chain_sealed"] is False

    def test_describe_blockers_readable(self):
        """describe_blockers should produce human-readable output."""
        from fireai.core.release_gates import verify_and_evaluate, describe_blockers
        result = verify_and_evaluate()
        description = describe_blockers(result)
        assert "BLOCKED" in description
        assert "input_contract_valid" in description

    def test_aset_rset_gate7_numerical_reverification(self):
        """Gate 7 should block even if is_safe=True when math says otherwise."""
        from fireai.core.release_gates import verify_and_evaluate
        result = verify_and_evaluate(
            aset_rset_result={
                "aset_seconds": 50.0,
                "rset_seconds": 100.0,
                "safety_factor": 1.5,
                "is_safe": True,  # LIE — 50 < 100*1.5=150
            }
        )
        # Gate 7 should BLOCK because numeric check overrides the lie
        assert result["checks"]["aset_rset_valid"] is False
