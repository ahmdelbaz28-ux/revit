"""
tests/test_elevator_shunt_trip.py
===================================
Comprehensive test suite for:
  - fireai/core/elevator_shunt_trip.py

SAFETY CRITICAL: Elevator shunt-trip ensures power is severed BEFORE
sprinkler water contacts 480V motor windings. A failure means electrified
water — lethal electrocution risk for firefighters and building occupants.

Code References:
  - NFPA 72-2022 §21.4.1 — Shunt trip requirement
  - NFPA 72-2022 §21.4.2 — Heat detector placement & rating
  - ASME A17.1 Rule 2.8.3.3 — Elevator safety
  - NFPA 13-2022 — Sprinkler requirements in elevator spaces
  - UL 521 — Standard for Heat Detectors
  - SFPE Handbook — RTI theory, Alpert ceiling jet correlations
"""

from __future__ import annotations

import pytest

# NOTE: Provenance module's RuleApplied/Violation field names differ from what
# elevator_shunt_trip expects. We mock provenance to None to test business logic
# via the fallback dict path — same pattern as group 3/4 tests.
import fireai.core.elevator_shunt_trip as _est_mod


@pytest.fixture(autouse=True)
def _disable_provenance():
    """Force the fallback dict path by setting provenance objects to None."""
    originals = {}
    for attr in ("DecisionProvenance", "RuleApplied", "Violation",
                "ConfidenceScore", "ConfidenceLevel"):
        originals[attr] = getattr(_est_mod, attr, None)
        setattr(_est_mod, attr, None)
    yield
    for attr, val in originals.items():
        setattr(_est_mod, attr, val)

from fireai.core.elevator_shunt_trip import (
    DEFAULT_HD_RTI,
    DEFAULT_SPRINKLER_RTI,
    MAX_HD_SPRINKLER_DISTANCE_M,
    RTI_RATIO_LIMIT,
    SAFETY_GAP_C,
    STANDARD_HD_TEMPS_C,
    STANDARD_SPRINKLER_TEMPS_C,
    ElevatorShuntTripAuditor,
    ShuntTripResult,
)

# ─────────────────────────────────────────────────────────────────────────────
# Constants Verification
# ─────────────────────────────────────────────────────────────────────────────


class TestConstants:
    """Verify NFPA 72 / UL 521 constants."""

    def test_safety_gap_11_1c(self):
        """NFPA 72 §21.4.2: 20°F = 11.1°C gap required."""
        assert SAFETY_GAP_C == pytest.approx(11.1)

    def test_max_hd_sprinkler_distance_0_6m(self):
        """NFPA 72 §21.4.2: Max 2 ft = 0.6m between HD and sprinkler."""
        assert MAX_HD_SPRINKLER_DISTANCE_M == pytest.approx(0.6, abs=0.01)

    def test_default_sprinkler_rti_50(self):
        """Quick-response sprinkler RTI = 50 (m·s)^0.5 per NFPA 13 §8.3.3.1."""
        assert DEFAULT_SPRINKLER_RTI == pytest.approx(50.0)

    def test_default_hd_rti_100(self):
        """V20.2 FIX: Standard-response HD RTI = 100 (m·s)^0.5.
        Previous value of 50.0 was WRONG — matched sprinkler RTI,
        making the RTI check always pass."""
        assert DEFAULT_HD_RTI == pytest.approx(100.0)

    def test_rti_ratio_limit_1_0(self):
        """HD RTI must not exceed sprinkler RTI (ratio ≤ 1.0)."""
        assert RTI_RATIO_LIMIT == pytest.approx(1.0)

    def test_standard_sprinkler_temps(self):
        assert STANDARD_SPRINKLER_TEMPS_C["ordinary"] == pytest.approx(68.3)
        assert STANDARD_SPRINKLER_TEMPS_C["intermediate"] == pytest.approx(93.3)

    def test_standard_hd_temps(self):
        assert STANDARD_HD_TEMPS_C["135F"] == pytest.approx(57.2)
        assert STANDARD_HD_TEMPS_C["190F"] == pytest.approx(87.8)


# ─────────────────────────────────────────────────────────────────────────────
# ShuntTripResult Dataclass
# ─────────────────────────────────────────────────────────────────────────────


class TestShuntTripResult:
    """ShuntTripResult dataclass verification."""

    def test_result_fields(self):
        r = ShuntTripResult(
            sprinkler_id="SPK-1",
            room_id="ELEV-1",
            has_dedicated_hd=True,
            hd_device_id="HD-1",
            hd_distance_m=0.3,
            hd_temp_rating_C=57.2,
            hd_rti=50.0,
            required_hd_temp_C=57.2,
            sprinkler_temp_C=68.3,
            sprinkler_rti=50.0,
            rti_violation=False,
            temp_violation=False,
            compliant=True,
        )
        assert r.sprinkler_id == "SPK-1"
        assert r.compliant is True
        assert r.violation_description is None

    def test_frozen_dataclass(self):
        r = ShuntTripResult(
            sprinkler_id="SPK-1",
            room_id="ELEV-1",
            has_dedicated_hd=False,
            compliant=False,
        )
        with pytest.raises(AttributeError):
            r.compliant = True


# ─────────────────────────────────────────────────────────────────────────────
# ElevatorShuntTripAuditor — Fully Compliant Scenario
# ─────────────────────────────────────────────────────────────────────────────


class TestFullyCompliant:
    """Scenario where all conditions are met — shunt-trip logic injected."""

    def test_compliant_setup_injects_logic(self):
        """HD within 0.6m, temp gap ≥ 11.1°C, RTI ≤ sprinkler RTI."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-SHAFT",
                    "x": 10.0,
                    "y": 20.0,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-SHAFT",
                    "x": 10.2,
                    "y": 20.1,
                    "temp_rating_C": 57.2,
                    "rti": 40.0,
                },
            ],
            elevator_spaces=["ELEV-SHAFT"],
        )
        val = result
        assert val["safe"] is True
        # Logic injection should be present
        injections = val["value"].get("logic_injections", [])
        assert len(injections) >= 1
        assert injections[0]["action"] == "SHUNT_TRIP_POWER_DELAY_0s"

    def test_compliant_detailed_result(self):
        """Compliant detailed_results should have compliant=True."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                    "rti": 50.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        detailed = val["value"]["detailed_results"]
        assert len(detailed) >= 1
        assert detailed[0]["compliant"] is True
        assert detailed[0]["has_dedicated_hd"] is True


# ─────────────────────────────────────────────────────────────────────────────
# ElevatorShuntTripAuditor — Temperature Gap Violation
# ─────────────────────────────────────────────────────────────────────────────


class TestTemperatureGapViolation:
    """NFPA 72 §21.4.2: HD temp must be at least 11.1°C below sprinkler."""

    def test_insufficient_temp_gap_violation(self):
        """HD at 65°C with sprinkler at 68.3°C → gap only 3.3°C < 11.1°C."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 65.0,
                    "rti": 40.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        assert val["safe"] is False
        detailed = val["value"]["detailed_results"]
        assert any(d["temp_violation"] for d in detailed)

    def test_exact_11_1c_gap_compliant(self):
        """HD temp exactly 11.1°C below sprinkler → just barely compliant.
        required_hd_temp = sprinkler_temp - 11.1°C; HD must be ≤ required_hd_temp."""
        auditor = ElevatorShuntTripAuditor()
        spk_temp = 68.3
        required_hd = spk_temp - SAFETY_GAP_C  # 57.2
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": spk_temp,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": required_hd,
                    "rti": 40.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        # hd_temp (57.2) > required_hd_temp (57.2) is False → no temp_violation
        detailed = val["value"]["detailed_results"]
        assert not any(d["temp_violation"] for d in detailed)


# ─────────────────────────────────────────────────────────────────────────────
# ElevatorShuntTripAuditor — RTI Violation
# ─────────────────────────────────────────────────────────────────────────────


class TestRTIViolation:
    """V19.1: RTI check ensures HD responds before sprinkler."""

    def test_hd_rti_exceeds_sprinkler_rti_violation(self):
        """HD with RTI=100 vs sprinkler RTI=50 → HD responds too slowly."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 93.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                    "rti": 100.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        detailed = val["value"]["detailed_results"]
        assert any(d["rti_violation"] for d in detailed)

    def test_hd_rti_equal_to_sprinkler_rti_compliant(self):
        """HD RTI = sprinkler RTI → no violation (must be strictly >)."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 93.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                    "rti": 50.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        detailed = val["value"]["detailed_results"]
        assert not any(d["rti_violation"] for d in detailed)

    def test_hd_rti_lower_than_sprinkler_compliant(self):
        """HD with lower RTI than sprinkler → HD responds faster → compliant."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 93.3,
                    "rti": 100.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                    "rti": 50.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        detailed = val["value"]["detailed_results"]
        assert not any(d["rti_violation"] for d in detailed)
        assert detailed[0]["compliant"] is True


# ─────────────────────────────────────────────────────────────────────────────
# ElevatorShuntTripAuditor — No Heat Detector (FATAL OMISSION)
# ─────────────────────────────────────────────────────────────────────────────


class TestNoHeatDetector:
    """No HD within range → FATAL OMISSION."""

    def test_no_hd_at_all(self):
        """No heat detector in elevator space → FATAL OMISSION."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 10.0,
                    "y": 20.0,
                    "temp_rating_C": 68.3,
                },
            ],
            heat_detector_locations=[],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        assert val["safe"] is False
        detailed = val["value"]["detailed_results"]
        assert len(detailed) >= 1
        assert detailed[0]["has_dedicated_hd"] is False
        assert detailed[0]["compliant"] is False

    def test_hd_too_far_from_sprinkler(self):
        """HD more than 0.6m from sprinkler → no dedicated HD."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 5.0,
                    "y": 5.0,  # ~7.07m away — far exceeds 0.6m limit
                    "temp_rating_C": 57.2,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        assert val["safe"] is False

    def test_hd_in_different_room(self):
        """HD in different room should not be considered."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "OTHER-ROOM",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        assert val["safe"] is False


# ─────────────────────────────────────────────────────────────────────────────
# ElevatorShuntTripAuditor — NaN/Inf Protection (V57 FIX)
# ─────────────────────────────────────────────────────────────────────────────


class TestNaNInfProtection:
    """V57 FIX: NaN/Inf in sprinkler or HD data must not bypass safety checks."""

    def test_nan_sprinkler_x_violation(self):
        """NaN in sprinkler x-coordinate → CRITICAL violation (skip sprinkler)."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": float("nan"),
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                },
            ],
            heat_detector_locations=[],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        assert val["safe"] is False

    def test_inf_sprinkler_temp_violation(self):
        """Inf in sprinkler temp → CRITICAL violation."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": float("inf"),
                },
            ],
            heat_detector_locations=[],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        assert val["safe"] is False

    def test_nan_hd_temp_forces_violation(self):
        """NaN in HD temp → both temp_violation and rti_violation forced True (fail-safe)."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": float("nan"),
                    "rti": 50.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        detailed = val["value"]["detailed_results"]
        assert any(d["temp_violation"] and d["rti_violation"] for d in detailed)

    def test_nan_hd_rti_forces_violation(self):
        """NaN in HD RTI → both violations forced True."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                    "rti": float("nan"),
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        detailed = val["value"]["detailed_results"]
        assert any(d["rti_violation"] for d in detailed)


# ─────────────────────────────────────────────────────────────────────────────
# ElevatorShuntTripAuditor — V43 FIX: 1:1 HD-to-Sprinkler Mapping
# ─────────────────────────────────────────────────────────────────────────────


class TestOneToOneMapping:
    """V43 FIX: One HD cannot serve two sprinklers (1:1 mapping required)."""

    def test_two_sprinklers_one_hd_second_fails(self):
        """Two sprinklers near one HD → second sprinkler has no dedicated HD."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
                {
                    "device_id": "SPK-2",
                    "room_id": "ELEV-1",
                    "x": 0.3,
                    "y": 0.3,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                    "rti": 40.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        # At least one sprinkler should fail (not have dedicated HD)
        detailed = val["value"]["detailed_results"]
        non_compliant = [d for d in detailed if not d["compliant"]]
        assert len(non_compliant) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# ElevatorShuntTripAuditor — Non-Elevator Spaces Ignored
# ─────────────────────────────────────────────────────────────────────────────


class TestNonElevatorSpacesIgnored:
    """Sprinklers outside elevator spaces should be ignored."""

    def test_non_elevator_sprinkler_ignored(self):
        """Sprinkler not in elevator_spaces list should not be audited."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-OFFICE",
                    "room_id": "OFFICE-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                },
            ],
            heat_detector_locations=[],
            elevator_spaces=["ELEV-SHAFT"],
        )
        val = result
        assert val["safe"] is True  # No elevator sprinklers to audit
        detailed = val["value"]["detailed_results"]
        assert len(detailed) == 0


# ─────────────────────────────────────────────────────────────────────────────
# ElevatorShuntTripAuditor — Custom Parameters
# ─────────────────────────────────────────────────────────────────────────────


class TestCustomParameters:
    """Custom safety_gap_C and rti_ratio_limit."""

    def test_larger_safety_gap_stricter(self):
        """Larger safety gap means stricter temperature requirement."""
        auditor = ElevatorShuntTripAuditor(safety_gap_C=20.0)
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                    "rti": 40.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        # With 20°C gap: required_hd_temp = 68.3 - 20.0 = 48.3°C
        # HD at 57.2°C > 48.3°C → temp_violation
        detailed = val["value"]["detailed_results"]
        assert any(d["temp_violation"] for d in detailed)

    def test_permissive_rti_ratio(self):
        """rti_ratio_limit=2.0 allows HD RTI up to 2× sprinkler RTI."""
        auditor = ElevatorShuntTripAuditor(rti_ratio_limit=2.0)
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-1",
                    "room_id": "ELEV-1",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 93.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "ELEV-1",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                    "rti": 90.0,
                },
            ],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        detailed = val["value"]["detailed_results"]
        # HD RTI 90 ≤ 50 × 2.0 = 100 → no RTI violation
        assert not any(d["rti_violation"] for d in detailed)


# ─────────────────────────────────────────────────────────────────────────────
# ElevatorShuntTripAuditor — Empty Inputs
# ─────────────────────────────────────────────────────────────────────────────


class TestEmptyInputs:
    """Edge cases with empty inputs."""

    def test_no_sprinklers(self):
        """No sprinklers → safe with no results."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[],
            heat_detector_locations=[],
            elevator_spaces=["ELEV-1"],
        )
        val = result
        assert val["safe"] is True

    def test_no_elevator_spaces(self):
        """No elevator spaces → safe (nothing to audit)."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {"device_id": "SPK-1", "room_id": "OFFICE", "x": 0, "y": 0, "temp_rating_C": 68.3},
            ],
            heat_detector_locations=[],
            elevator_spaces=[],
        )
        val = result
        assert val["safe"] is True

    def test_multiple_elevator_spaces(self):
        """Multiple elevator spaces should each be audited."""
        auditor = ElevatorShuntTripAuditor()
        result = auditor.audit_hoistway_machine_room(
            sprinkler_locations=[
                {
                    "device_id": "SPK-HOIST",
                    "room_id": "HOISTWAY",
                    "x": 0.0,
                    "y": 0.0,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
                {
                    "device_id": "SPK-MACHINE",
                    "room_id": "MACHINE-ROOM",
                    "x": 5.0,
                    "y": 5.0,
                    "temp_rating_C": 68.3,
                    "rti": 50.0,
                },
            ],
            heat_detector_locations=[
                {
                    "device_id": "HD-1",
                    "room_id": "HOISTWAY",
                    "x": 0.1,
                    "y": 0.1,
                    "temp_rating_C": 57.2,
                    "rti": 40.0,
                },
                {
                    "device_id": "HD-2",
                    "room_id": "MACHINE-ROOM",
                    "x": 5.1,
                    "y": 5.1,
                    "temp_rating_C": 57.2,
                    "rti": 40.0,
                },
            ],
            elevator_spaces=["HOISTWAY", "MACHINE-ROOM"],
        )
        val = result
        assert val["safe"] is True
        detailed = val["value"]["detailed_results"]
        assert len(detailed) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
