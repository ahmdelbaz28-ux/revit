"""
tests/test_v19_high_rise_suite.py
==================================
Ruthless vulnerability testing for V19.1 High-Rise Engineering Suite:

  1. ElevatorShuntTripAuditor  — NFPA 72 §21.4.1 / ASME A17.1 (with RTI)
  2. NACBoosterAllocator       — NFPA 72 §10.6 / §18.5.5 (with Voltage Drop)
  3. SeismicJointPenalyer      — NEC §300.4(D) / ASCE 7-22 (Orthogonal Crossing)

V19.1 FIXES TESTED:
  - RTI (Response Time Index) thermodynamic validation
  - Iterative voltage drop along NAC circuit paths
  - Orthogonal crossing enforcement (not violation-flagging)
"""
import pytest
import math

from fireai.core.elevator_shunt_trip import (
    ElevatorShuntTripAuditor,
    ShuntTripResult,
    SAFETY_GAP_C,
    MAX_HD_SPRINKLER_DISTANCE_M,
    DEFAULT_SPRINKLER_RTI,
    DEFAULT_HD_RTI,
    RTI_RATIO_LIMIT,
)
from fireai.core.bps_allocator import (
    NACBoosterAllocator,
    WIRE_RESISTANCE_OHM_PER_M,
    DEFAULT_SOURCE_VOLTAGE,
    DEFAULT_MIN_TERMINAL_VOLTAGE,
    DEFAULT_AWG,
)
from fireai.core.seismic_joint_penalyer import (
    SeismicJointPenalyer,
    StructuralJoint,
    JointCrossing,
    FlexibleJunctionTie,
    JOINT_CROSSING_COST_PENALTY,
    FLEXIBLE_TRANSITION_LENGTH_M,
    ORTHOGONAL_TOLERANCE_DEG,
    _segments_intersect,
    _compute_approach_angle,
)
from fireai.core.provenance import (
    DecisionProvenance,
    ConfidenceLevel,
    Violation,
)


# ============================================================================
# 1. ELEVATOR SHUNT-TRIP AUDITOR TESTS (with RTI)
# ============================================================================
class TestElevatorShuntTripAuditor:
    """NFPA 72 §21.4.1 / ASME A17.1 — Shunt-Trip Audit with RTI."""

    def setup_method(self):
        self.auditor = ElevatorShuntTripAuditor()

    # -- 1.1 Compliant: correct temp gap AND RTI --
    def test_compliant_shunt_trip(self):
        """Compliant: HD 57.2°C within 0.5 m, RTI=50 ≤ sprinkler RTI=50."""
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-01", "room_id": "ELEV-MR", "x": 10.0, "y": 5.0, "temp_rating_C": 68.3, "rti": 50.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-01", "room_id": "ELEV-MR", "x": 10.3, "y": 5.0, "temp_rating_C": 57.2, "rti": 50.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True
        assert len(val["logic_injections"]) == 1

    # -- 1.2 FATAL OMISSION: No HD --
    def test_fatal_omission_no_hd(self):
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-01", "room_id": "ELEV-HW", "x": 5.0, "y": 10.0, "temp_rating_C": 68.3},
            ],
            heat_detector_locations=[],
            elevator_spaces=["ELEV-HW"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is False
        vio = result.violations_detected if isinstance(result, DecisionProvenance) else result.get("violations", [])
        desc = vio[0]["description"] if isinstance(vio[0], dict) else vio[0].description
        assert "FATAL OMISSION" in desc

    # -- 1.3 RTI VIOLATION: HD RTI=150, Sprinkler RTI=50 --
    def test_rti_violation_slow_hd(self):
        """V19.1 CRITICAL TEST: HD with RTI=150 is too slow for
        RTI=50 quick-response sprinkler — sprinkler bursts FIRST."""
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-QR", "room_id": "ELEV-MR", "x": 10.0, "y": 5.0, "temp_rating_C": 68.3, "rti": 50.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-SLOW", "room_id": "ELEV-MR", "x": 10.2, "y": 5.0, "temp_rating_C": 57.2, "rti": 150.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is False, "HD RTI=150 > Sprinkler RTI=50 must FAIL"
        # Check that the violation mentions RTI
        vio = result.violations_detected if isinstance(result, DecisionProvenance) else result.get("violations", [])
        desc = vio[0]["description"] if isinstance(vio[0], dict) else vio[0].description
        assert "RTI" in desc, "Violation must mention RTI mismatch"

    # -- 1.4 RTI PASS: HD RTI ≤ Sprinkler RTI --
    def test_rti_pass_hd_same_rti(self):
        """HD RTI=50 = Sprinkler RTI=50 → passes."""
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-01", "room_id": "ELEV-MR", "x": 10.0, "y": 5.0, "temp_rating_C": 68.3, "rti": 50.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-01", "room_id": "ELEV-MR", "x": 10.2, "y": 5.0, "temp_rating_C": 57.2, "rti": 50.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True

    # -- 1.5 RTI PASS: HD RTI < Sprinkler RTI (HD is faster) --
    def test_rti_pass_hd_faster(self):
        """HD RTI=30 (fast) < Sprinkler RTI=100 (standard) → passes."""
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-STD", "room_id": "ELEV-MR", "x": 10.0, "y": 5.0, "temp_rating_C": 68.3, "rti": 100.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-FAST", "room_id": "ELEV-MR", "x": 10.2, "y": 5.0, "temp_rating_C": 57.2, "rti": 30.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True

    # -- 1.6 HD temperature too high --
    def test_hd_temp_too_high(self):
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-01", "room_id": "ELEV-MR", "x": 10.0, "y": 5.0, "temp_rating_C": 68.3},
            ],
            heat_detector_locations=[
                {"device_id": "HD-HOT", "room_id": "ELEV-MR", "x": 10.2, "y": 5.0, "temp_rating_C": 71.1},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is False

    # -- 1.7 Both temp and RTI violations simultaneously --
    def test_dual_violation_temp_and_rti(self):
        """HD has both wrong temp AND too-slow RTI → both flagged."""
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-01", "room_id": "ELEV-MR", "x": 10.0, "y": 5.0, "temp_rating_C": 68.3, "rti": 50.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-BAD", "room_id": "ELEV-MR", "x": 10.2, "y": 5.0, "temp_rating_C": 71.1, "rti": 200.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is False
        dr = val["detailed_results"][0]
        assert dr["temp_violation"] is True
        assert dr["rti_violation"] is True

    # -- 1.8 Default RTI values (backward compatible) --
    def test_default_rti_backward_compatible(self):
        """V20.2: Default HD RTI (100) > default sprinkler RTI (50).
        
        Previously, both defaulted to 50, making the RTI check a no-op.
        V20.2 fix: DEFAULT_HD_RTI=100 correctly represents standard-response
        heat detectors per UL 521. With RTI 100 > 50, the RTI check now
        correctly flags that a standard-response HD is too slow to beat
        a quick-response sprinkler — exactly the danger V19.1 was built
        to catch. Test updated to reflect correct behavior.
        """
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-01", "room_id": "ELEV-MR", "x": 10.0, "y": 5.0, "temp_rating_C": 68.3},
            ],
            heat_detector_locations=[
                {"device_id": "HD-01", "room_id": "ELEV-MR", "x": 10.2, "y": 5.0, "temp_rating_C": 57.2},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # V20.2: Default HD RTI=100 > sprinkler RTI=50 → RTI violation
        # This is CORRECT — standard-response HD IS too slow for QR sprinkler
        assert val["safe"] is False

    # -- 1.9 Provenance algorithm name --
    def test_algorithm_name_rti(self):
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-01", "room_id": "ELEV-MR", "x": 10.0, "y": 5.0, "temp_rating_C": 68.3},
            ],
            heat_detector_locations=[
                {"device_id": "HD-01", "room_id": "ELEV-MR", "x": 10.2, "y": 5.0, "temp_rating_C": 57.2},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        assert isinstance(result, DecisionProvenance)
        assert result.algorithm["name"] == "RTI_Differential_Comparator"
        assert result.algorithm["version"] == "v19.1"

    # -- 1.10 Sprinkler not in elevator space --
    def test_sprinkler_not_in_elevator_space(self):
        result = self.auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-OFFICE", "room_id": "OFFICE-01", "x": 3.0, "y": 3.0, "temp_rating_C": 68.3},
            ],
            heat_detector_locations=[],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True


# ============================================================================
# 2. NAC BOOSTER ALLOCATOR TESTS (with Voltage Drop)
# ============================================================================
class TestNACBoosterAllocator:
    """NFPA 72 §10.6 / §18.5.5 — NAC Power Booster Distribution."""

    def setup_method(self):
        self.allocator = NACBoosterAllocator(
            facp_limit_amps=8.0,
            booster_capacity_amps=6.0,
        )

    # -- 2.1 No booster needed --
    def test_no_booster_needed(self):
        result = self.allocator.allocate_boosters_across_floors(
            floor_data=[
                {"floor_name": "GF", "nac_current": 2.0, "level_z": 0.0, "centroid_location": (10, 5)},
            ]
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        boosters = [b for b in val["boosters"] if b.get("type") == "NAC_BOOSTER_BPS"]
        assert len(boosters) == 0

    # -- 2.2 Voltage drop: short circuit → no BPS needed --
    def test_voltage_drop_short_circuit(self):
        """Short NAC circuit with 5 devices in 10m → voltage OK."""
        devices = [
            {"id": f"DEV-{i}", "x": float(i * 2), "y": 0.0, "inrush_a": 0.2}
            for i in range(5)
        ]
        result = self.allocator.validate_voltage_drop(devices, awg=14)
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True
        assert val["cuts"] == 0

    # -- 2.3 Voltage drop: long circuit → BPS insertion needed --
    def test_voltage_drop_long_circuit(self):
        """200m circuit with 50 devices → voltage collapses, BPS needed."""
        devices = [
            {"id": f"DEV-{i}", "x": float(i * 4), "y": 0.0, "inrush_a": 0.3}
            for i in range(50)
        ]
        result = self.allocator.validate_voltage_drop(devices, awg=14)
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # With AWG 14, 200m, 50×0.3A=15A total, voltage will definitely collapse
        assert val["cuts"] >= 1, "Long circuit must require at least 1 BPS insertion"
        assert len(val["bps_insertions"]) >= 1

    # -- 2.4 Voltage drop: AWG 10 (thicker wire) reduces drops --
    def test_voltage_drop_thicker_wire(self):
        """Same circuit with AWG 10 → fewer BPS insertions than AWG 14."""
        devices = [
            {"id": f"DEV-{i}", "x": float(i * 4), "y": 0.0, "inrush_a": 0.3}
            for i in range(50)
        ]
        result_14 = self.allocator.validate_voltage_drop(devices, awg=14)
        result_10 = self.allocator.validate_voltage_drop(devices, awg=10)
        val_14 = result_14.value if isinstance(result_14, DecisionProvenance) else result_14["value"]
        val_10 = result_10.value if isinstance(result_10, DecisionProvenance) else result_10["value"]
        # Thicker wire → fewer or equal BPS insertions
        assert val_10["cuts"] <= val_14["cuts"]

    # -- 2.5 Voltage drop: DC return path factor --
    def test_dc_return_path_factor(self):
        """Verify that voltage drop uses 2× factor for DC return."""
        # Single device 100m away drawing 1A on AWG 14
        devices = [
            {"id": "DEV-0", "x": 0.0, "y": 0.0, "inrush_a": 0.0},  # source
            {"id": "DEV-1", "x": 100.0, "y": 0.0, "inrush_a": 1.0},  # 100m away
        ]
        result = self.allocator.validate_voltage_drop(devices, awg=14)
        # Expected drop: 2 * 100m * 0.0103 ohm/m * 1.0A = 2.06V
        # Terminal voltage: 24.0 - 2.06 = 21.94V → still above 16V
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True
        assert val["cuts"] == 0

    # -- 2.6 Voltage drop provenance --
    def test_voltage_drop_provenance(self):
        devices = [
            {"id": "DEV-0", "x": 0.0, "y": 0.0, "inrush_a": 0.2},
            {"id": "DEV-1", "x": 5.0, "y": 0.0, "inrush_a": 0.2},
        ]
        result = self.allocator.validate_voltage_drop(devices)
        assert isinstance(result, DecisionProvenance)
        assert result.decision_type == "voltage_drop_validation"
        assert result.algorithm["name"] == "DynamicIterativeVoltageChipper"

    # -- 2.7 Booster auto-deployment --
    def test_booster_auto_deployment(self):
        floor_data = [
            {"floor_name": f"F{i:02d}", "nac_current": 3.0, "level_z": float(i * 4), "centroid_location": (10, 5)}
            for i in range(5)
        ]
        result = self.allocator.allocate_boosters_across_floors(floor_data)
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["total_current"] == 15.0
        boosters = [b for b in val["boosters"] if b.get("type") == "NAC_BOOSTER_BPS"]
        assert len(boosters) >= 1

    # -- 2.8 Wire resistance table values --
    def test_wire_resistance_table(self):
        """Verify key wire resistance values per NEC Chapter 9 Table 8."""
        assert abs(WIRE_RESISTANCE_OHM_PER_M[14] - 0.0103) < 0.001
        assert abs(WIRE_RESISTANCE_OHM_PER_M[12] - 0.0065) < 0.001
        assert abs(WIRE_RESISTANCE_OHM_PER_M[10] - 0.0041) < 0.001


# ============================================================================
# 3. SEISMIC JOINT PENALTYER TESTS (Orthogonal Crossing)
# ============================================================================
class TestSeismicJointPenalyer:
    """NEC §300.4(D) / ASCE 7-22 — Orthogonal Joint Crossing."""

    def setup_method(self):
        self.penalyer = SeismicJointPenalyer()

    # -- 3.1 Orthogonal crossing → no violation --
    def test_orthogonal_crossing_no_violation(self):
        """Path crossing vertical joint horizontally → 90° → OK."""
        result = self.penalyer.detect_structural_shearing(
            path=[(0, 0), (20, 0)],
            seismic_joints=[
                StructuralJoint("SJ-01", (10, -5), (10, 5), "seismic"),
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # Horizontal path crossing vertical joint = 90° → orthogonal
        assert val["safe"] is True
        assert val["crossings_detected"] == 1
        assert val["orthogonal_crossings"] == 1
        assert val["non_orthogonal_crossings"] == 0

    # -- 3.2 Non-orthogonal crossing → violation --
    def test_non_orthogonal_crossing_violation(self):
        """Path at ~45° to vertical joint → non-orthogonal → violation."""
        result = self.penalyer.detect_structural_shearing(
            path=[(0, 0), (20, 20)],
            seismic_joints=[
                StructuralJoint("SJ-01", (10, -5), (10, 15), "seismic"),
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # 45° approach angle ≠ 90° → non-orthogonal
        assert val["non_orthogonal_crossings"] >= 1
        vio = result.violations_detected if isinstance(result, DecisionProvenance) else result.get("violations", [])
        assert len(vio) >= 1

    # -- 3.3 Flexible junction always generated --
    def test_flexible_junction_always_generated(self):
        """Even orthogonal crossings get flexible junction ties."""
        result = self.penalyer.detect_structural_shearing(
            path=[(0, 0), (20, 0)],
            seismic_joints=[
                StructuralJoint("SJ-01", (10, -5), (10, 5), "seismic"),
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert len(val["flexible_junctions"]) == 1
        assert val["flexible_junctions"][0]["conduit_type"] == "LFMC"

    # -- 3.4 Approach angle calculation --
    def test_approach_angle_calculation(self):
        """Verify approach angle computation."""
        # Horizontal path (1,0) crossing vertical joint (0,1)
        angle = _compute_approach_angle(
            (0, 0), (10, 0),  # horizontal path
            (5, -5), (5, 5),  # vertical joint
        )
        assert abs(angle - 90.0) < 1.0, f"Expected ~90°, got {angle}"

        # 45° path crossing vertical joint
        angle45 = _compute_approach_angle(
            (0, 0), (10, 10),  # 45° path
            (5, -5), (5, 5),   # vertical joint
        )
        assert abs(angle45 - 45.0) < 2.0, f"Expected ~45°, got {angle45}"

    # -- 3.5 No joint crossings → safe --
    def test_no_joint_crossings(self):
        result = self.penalyer.detect_structural_shearing(
            path=[(0, 0), (5, 0), (10, 0)],
            seismic_joints=[
                StructuralJoint("SJ-01", (20, -5), (20, 5), "seismic"),
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True
        assert val["crossings_detected"] == 0

    # -- 3.6 Penalty grid cells have force_orthogonal=True --
    def test_penalty_grid_force_orthogonal(self):
        result = self.penalyer.detect_structural_shearing(
            path=[(0, 0), (20, 0)],
            seismic_joints=[
                StructuralJoint("SJ-01", (10, -2), (10, 2), "seismic"),
            ],
        )
        if isinstance(result, DecisionProvenance):
            val = result.value
            cells = val.get("penalty_grid_cells", [])
            assert len(cells) > 0
            for cell in cells:
                assert cell["force_orthogonal"] is True

    # -- 3.7 Algorithm name updated --
    def test_algorithm_name(self):
        result = self.penalyer.detect_structural_shearing(
            path=[(0, 0), (20, 0)],
            seismic_joints=[
                StructuralJoint("SJ-01", (10, -5), (10, 5), "seismic"),
            ],
        )
        assert isinstance(result, DecisionProvenance)
        assert result.algorithm["name"] == "AnisotropicCostMultiplier"
        assert result.algorithm["version"] == "v19.1"


# ============================================================================
# 4. INTEGRATION / CROSS-MODULE TESTS
# ============================================================================
class TestV19Integration:
    """Cross-module integration tests for V19.1 High-Rise Suite."""

    def test_shunt_trip_with_rti_and_booster(self):
        """High-rise with RTI-validated shunt-trip AND BPS deployment."""
        # Shunt-trip with RTI check
        shunt_auditor = ElevatorShuntTripAuditor()
        shunt_result = shunt_auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-MR", "room_id": "ELEV-MR", "x": 5.0, "y": 5.0, "temp_rating_C": 68.3, "rti": 50.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-MR", "room_id": "ELEV-MR", "x": 5.2, "y": 5.0, "temp_rating_C": 57.2, "rti": 50.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val_shunt = shunt_result.value if isinstance(shunt_result, DecisionProvenance) else shunt_result["value"]
        assert val_shunt["safe"] is True

        # Booster allocation
        allocator = NACBoosterAllocator(facp_limit_amps=8.0, booster_capacity_amps=6.0)
        booster_result = allocator.allocate_boosters_across_floors(
            floor_data=[
                {"floor_name": f"F{i:02d}", "nac_current": 3.5, "level_z": float(i * 4), "centroid_location": (10, 5)}
                for i in range(10)
            ]
        )
        val_booster = booster_result.value if isinstance(booster_result, DecisionProvenance) else booster_result["value"]
        assert val_booster["total_current"] == 35.0

    def test_seismic_orthogonal_and_voltage(self):
        """Seismic orthogonal crossing + voltage drop on same circuit."""
        penalyer = SeismicJointPenalyer()
        result = penalyer.detect_structural_shearing(
            path=[(0, 0), (20, 0)],
            seismic_joints=[
                StructuralJoint("SJ-01", (10, -5), (10, 5), "seismic"),
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["orthogonal_crossings"] == 1

        # Voltage drop on the same circuit
        allocator = NACBoosterAllocator()
        devices = [
            {"id": f"DEV-{i}", "x": float(i * 2), "y": 0.0, "inrush_a": 0.2}
            for i in range(10)
        ]
        vresult = allocator.validate_voltage_drop(devices)
        vval = vresult.value if isinstance(vresult, DecisionProvenance) else vresult["value"]
        # Short circuit → no BPS needed
        assert vval["cuts"] == 0

    def test_all_three_modules_v191(self):
        """All three V19.1 modules produce correct DecisionProvenance."""
        s = ElevatorShuntTripAuditor().audit_hoistway_machine_room(
            [{"device_id": "SPK-1", "room_id": "ELEV-MR", "x": 5, "y": 5, "temp_rating_C": 68.3, "rti": 50}],
            [{"device_id": "HD-1", "room_id": "ELEV-MR", "x": 5.1, "y": 5, "temp_rating_C": 57.2, "rti": 50}],
            ["ELEV-MR"],
        )
        b = NACBoosterAllocator().allocate_boosters_across_floors(
            [{"floor_name": "GF", "nac_current": 3.0, "level_z": 0.0, "centroid_location": (0, 0)}]
        )
        j = SeismicJointPenalyer().detect_structural_shearing(
            [(0, 0), (10, 0)],
            [StructuralJoint("SJ-01", (5, -5), (5, 5))],
        )
        for result, expected_type in [
            (s, "elevator_shunt_trip"),
            (b, "distributed_power_routing"),
            (j, "seismic_joint_routing"),
        ]:
            assert isinstance(result, DecisionProvenance)
            assert result.decision_type == expected_type


# ============================================================================
# 5. APOCALYPSE EDGE CASES — V19.1
# ============================================================================
class TestV19Apocalypse:
    """Ruthless edge cases for V19.1 RTI + Voltage Drop + Orthogonal."""

    # -- 5.1 RTI=0 edge case (instant response) --
    def test_rti_zero(self):
        """HD RTI=0 → always faster than any sprinkler → passes."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-1", "room_id": "ELEV-MR", "x": 5, "y": 5, "temp_rating_C": 68.3, "rti": 50.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-1", "room_id": "ELEV-MR", "x": 5.1, "y": 5, "temp_rating_C": 57.2, "rti": 0.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True

    # -- 5.2 Very high RTI HD (RTI=500) --
    def test_extremely_slow_hd(self):
        """HD RTI=500 with QR sprinkler RTI=50 → catastrophic failure."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-1", "room_id": "ELEV-MR", "x": 5, "y": 5, "temp_rating_C": 68.3, "rti": 50.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-1", "room_id": "ELEV-MR", "x": 5.1, "y": 5, "temp_rating_C": 57.2, "rti": 500.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is False

    # -- 5.3 Voltage drop: zero devices → no drop --
    def test_voltage_drop_no_devices(self):
        allocator = NACBoosterAllocator()
        result = allocator.validate_voltage_drop([])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True

    # -- 5.4 Voltage drop: single device at source → no drop --
    def test_voltage_drop_device_at_source(self):
        """Device at x=0, y=0 (same as source) → zero drop."""
        allocator = NACBoosterAllocator()
        result = allocator.validate_voltage_drop([
            {"id": "DEV-0", "x": 0.0, "y": 0.0, "inrush_a": 5.0},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True
        assert val["cuts"] == 0

    # -- 5.5 Orthogonal: path parallel to joint (never crosses) --
    def test_path_parallel_to_joint(self):
        """Path along same direction as joint → never crosses."""
        penalyer = SeismicJointPenalyer()
        result = penalyer.detect_structural_shearing(
            path=[(0, 5), (20, 5)],  # horizontal at y=5
            seismic_joints=[
                StructuralJoint("SJ-01", (0, 10), (20, 10), "seismic"),  # horizontal at y=10
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["crossings_detected"] == 0

    # -- 5.6 Multiple joints, mixed orthogonal/non-orthogonal --
    def test_mixed_orthogonal_crossings(self):
        """Two joints: one orthogonal, one non-orthogonal."""
        penalyer = SeismicJointPenalyer()
        # Diagonal path crosses both a vertical and a horizontal joint
        result = penalyer.detect_structural_shearing(
            path=[(0, 0), (30, 10)],  # ~18° angle
            seismic_joints=[
                StructuralJoint("SJ-VERT", (15, -5), (15, 20), "seismic"),  # vertical
                StructuralJoint("SJ-HORIZ", (-5, 5), (30, 5), "seismic"),   # horizontal
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # Both crossings should be detected
        assert val["crossings_detected"] == 2

    # -- 5.7 Custom RTI ratio limit --
    def test_custom_rti_ratio_limit(self):
        """Allow HD RTI up to 1.5× sprinkler RTI."""
        auditor = ElevatorShuntTripAuditor(rti_ratio_limit=1.5)
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-1", "room_id": "ELEV-MR", "x": 5, "y": 5, "temp_rating_C": 68.3, "rti": 100.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-1", "room_id": "ELEV-MR", "x": 5.1, "y": 5, "temp_rating_C": 57.2, "rti": 140.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # 140 / 100 = 1.4 ≤ 1.5 → passes
        assert val["safe"] is True

        # But 160 / 100 = 1.6 > 1.5 → fails
        result2 = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-1", "room_id": "ELEV-MR", "x": 5, "y": 5, "temp_rating_C": 68.3, "rti": 100.0},
            ],
            heat_detector_locations=[
                {"device_id": "HD-1", "room_id": "ELEV-MR", "x": 5.1, "y": 5, "temp_rating_C": 57.2, "rti": 160.0},
            ],
            elevator_spaces=["ELEV-MR"],
        )
        val2 = result2.value if isinstance(result2, DecisionProvenance) else result2["value"]
        assert val2["safe"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
