"""
tests/test_sensor_physics_advisor.py
======================================
Comprehensive test suite for:
  - fireai/core/sensor_physics_advisor.py

SAFETY CRITICAL: This advisory module flags conditions where point-type
detectors may be insufficient. Missing warnings could result in
inadequate detection in high-ceiling or steep-slope environments.

NFPA 72 References:
  §17.7.1 — Spot-type smoke detectors
  §17.7.2 — Projected beam-type smoke detectors
  §17.7.3 — Performance-based design alternative
  §17.6.3.4 — Sloped ceilings
  Table 17.6.3.1.1 — Height-adjusted spacing
"""

from __future__ import annotations

import pytest
from typing import List

from fireai.core.sensor_physics_advisor import (
    SensorAdvisory,
    SensorPhysicsAdvisor,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SensorAdvisory Dataclass Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSensorAdvisory:
    def test_creation(self):
        advisory = SensorAdvisory(
            room_id="R1",
            ceiling_height_m=3.0,
            slope_degrees=0.0,
            detector_type="smoke",
            severity="INFO",
        )
        assert advisory.room_id == "R1"
        assert advisory.ceiling_height_m == 3.0
        assert advisory.severity == "INFO"
        assert advisory.beam_detector_recommended is False
        assert advisory.performance_based_design is False

    def test_defaults(self):
        advisory = SensorAdvisory(room_id="R1", ceiling_height_m=3.0)
        assert advisory.slope_degrees == 0.0
        assert advisory.detector_type == "smoke"
        assert advisory.severity == "INFO"
        assert advisory.recommendations == []
        assert advisory.nfpa_references == []
        assert advisory.beam_detector_recommended is False
        assert advisory.performance_based_design is False

    def test_custom_values(self):
        advisory = SensorAdvisory(
            room_id="R2",
            ceiling_height_m=15.0,
            slope_degrees=20.0,
            detector_type="heat",
            severity="CRITICAL",
            recommendations=["Use beam detectors"],
            nfpa_references=["NFPA 72-2022 §17.7.2"],
            beam_detector_recommended=True,
            performance_based_design=True,
        )
        assert advisory.severity == "CRITICAL"
        assert advisory.beam_detector_recommended is True
        assert advisory.performance_based_design is True
        assert len(advisory.recommendations) == 1

    def test_mutable_defaults_are_independent(self):
        """Two instances should not share mutable default lists."""
        a1 = SensorAdvisory(room_id="R1", ceiling_height_m=3.0)
        a2 = SensorAdvisory(room_id="R2", ceiling_height_m=3.0)
        a1.recommendations.append("test")
        assert len(a2.recommendations) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SensorPhysicsAdvisor Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAdviseBasic:
    """Basic advisory: flat ceiling, normal height — no warnings."""

    def test_normal_office(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=3.0)
        assert advisory.severity == "INFO"
        assert advisory.beam_detector_recommended is False
        assert len(advisory.recommendations) == 0
        assert len(advisory.nfpa_references) == 0

    def test_normal_warehouse(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=6.0)
        # 6.0m is below 9.1m warning threshold
        assert advisory.severity == "INFO"

    def test_heat_detector_normal(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(
            room_id="R1", ceiling_height_m=3.0, detector_type="heat"
        )
        assert advisory.severity == "INFO"
        assert advisory.detector_type == "heat"


class TestAdviseHighCeiling:
    """High ceiling warnings per NFPA 72 §17.7.2."""

    def test_warning_above_9_1m(self):
        """Ceiling > 9.1m → WARNING, beam detectors recommended."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=10.0)
        assert advisory.severity == "WARNING"
        assert advisory.beam_detector_recommended is True
        assert any("§17.7.2" in ref for ref in advisory.nfpa_references)

    def test_critical_beyond_table_max(self):
        """Ceiling > 12.2m → CRITICAL, beam detectors REQUIRED."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=15.0)
        assert advisory.severity == "CRITICAL"
        assert advisory.beam_detector_recommended is True
        assert any("§17.7.2" in ref for ref in advisory.nfpa_references)
        assert any("Table 17.6.3.1.1" in ref for ref in advisory.nfpa_references)

    def test_heat_detector_high_ceiling(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(
            room_id="R1", ceiling_height_m=10.0, detector_type="heat"
        )
        assert advisory.severity == "WARNING"
        assert advisory.beam_detector_recommended is True

    def test_heat_detector_critical_ceiling(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(
            room_id="R1", ceiling_height_m=15.0, detector_type="heat"
        )
        assert advisory.severity == "CRITICAL"

    def test_exactly_at_warning_threshold(self):
        """h = 9.1m exactly should still be INFO (not > 9.1)."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=9.1)
        assert advisory.severity == "INFO"

    def test_just_above_warning_threshold(self):
        """h = 9.2m → WARNING."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=9.2)
        assert advisory.severity == "WARNING"

    def test_exactly_at_table_max(self):
        """h = 12.2m exactly should be WARNING (not > 12.2)."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=12.2)
        assert advisory.severity == "WARNING"

    def test_just_above_table_max(self):
        """h = 12.3m → CRITICAL."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=12.3)
        assert advisory.severity == "CRITICAL"


class TestAdviseSlopedCeiling:
    """Sloped ceiling advisory per NFPA 72 §17.6.3.4."""

    def test_gentle_slope_no_warning(self):
        """Slope ≤ 7.125° → no sloped ceiling advisory."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=3.0, slope_degrees=5.0)
        assert advisory.severity == "INFO"

    def test_moderate_slope_warning(self):
        """Slope > 7.125° → WARNING, ridge zone detectors required."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=3.0, slope_degrees=10.0)
        assert advisory.severity == "WARNING"
        assert any("§17.6.3.4" in ref for ref in advisory.nfpa_references)
        assert any("ridge zone" in r.lower() for r in advisory.recommendations)

    def test_steep_slope_critical(self):
        """Slope > 30° → CRITICAL, performance-based design required."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=3.0, slope_degrees=35.0)
        assert advisory.severity == "CRITICAL"
        assert advisory.performance_based_design is True
        assert any("§17.7.3" in ref for ref in advisory.nfpa_references)

    def test_exactly_at_slope_threshold(self):
        """Slope = 7.125° → no warning (not > threshold)."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=3.0, slope_degrees=7.125)
        assert advisory.severity == "INFO"

    def test_exactly_at_steep_threshold(self):
        """Slope = 30° → no steep warning (not > threshold)."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=3.0, slope_degrees=30.0)
        assert advisory.severity == "WARNING"  # Moderate slope, not steep

    def test_just_above_steep_threshold(self):
        """Slope = 30.1° → CRITICAL."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=3.0, slope_degrees=30.1)
        assert advisory.severity == "CRITICAL"


class TestAdviseCombinedConditions:
    """Combined high ceiling + slope → CRITICAL."""

    def test_high_ceiling_plus_slope(self):
        """High ceiling (>9.1m) + slope (>7.125°) → CRITICAL."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(
            room_id="R1",
            ceiling_height_m=10.0,
            slope_degrees=15.0,
        )
        assert advisory.severity == "CRITICAL"
        assert advisory.beam_detector_recommended is True
        assert advisory.performance_based_design is True
        assert any("CRITICAL COMBINATION" in r for r in advisory.recommendations)

    def test_high_ceiling_plus_steep_slope(self):
        """Both ceiling and slope exceed limits → CRITICAL with multiple warnings."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(
            room_id="R1",
            ceiling_height_m=15.0,
            slope_degrees=35.0,
        )
        assert advisory.severity == "CRITICAL"
        assert len(advisory.recommendations) >= 2


class TestAdviseLowCeiling:
    """Very low ceiling → smoke stratification warning."""

    def test_low_ceiling_stratification_warning(self):
        """Ceiling < 2.4m → stratification risk WARNING."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=2.2, detector_type="smoke")
        assert advisory.severity == "WARNING"
        assert any("stratification" in r.lower() for r in advisory.recommendations)
        assert any("§17.7.3.6" in ref for ref in advisory.nfpa_references)

    def test_low_ceiling_heat_no_warning(self):
        """Low ceiling with heat detector → no stratification warning."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=2.2, detector_type="heat")
        assert advisory.severity == "INFO"

    def test_exactly_2_4m_no_warning(self):
        """2.4m exactly → no stratification warning (not < 2.4)."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=2.4, detector_type="smoke")
        assert advisory.severity == "INFO"

    def test_just_below_2_4m(self):
        """2.3m → stratification WARNING."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=2.3, detector_type="smoke")
        assert advisory.severity == "WARNING"


class TestAdviseRoomDict:
    """Convenience method: advise from room dict."""

    def test_basic_dict(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise_room_dict({
            "room_id": "R1",
            "ceiling_height": 3.0,
            "ceiling_slope_degrees": 0.0,
        })
        assert advisory.room_id == "R1"
        assert advisory.severity == "INFO"

    def test_missing_ceiling_height_default(self):
        """Missing ceiling_height defaults to 3.0."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise_room_dict({"room_id": "R1"})
        assert advisory.ceiling_height_m == 3.0

    def test_none_ceiling_height_default(self):
        """None ceiling_height defaults to 3.0."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise_room_dict({"room_id": "R1", "ceiling_height": None})
        assert advisory.ceiling_height_m == 3.0

    def test_heat_detector_type_detection(self):
        """Detector type with 'heat' → heat advisory."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise_room_dict({
            "room_id": "R1",
            "ceiling_height": 3.0,
            "detector_type": "heat_rate_compensated",
        })
        assert advisory.detector_type == "heat"

    def test_smoke_detector_type_detection(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise_room_dict({
            "room_id": "R1",
            "ceiling_height": 3.0,
            "detector_type": "smoke_photoelectric",
        })
        assert advisory.detector_type == "smoke"

    def test_name_fallback_for_room_id(self):
        """If room_id missing, use 'name' key."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise_room_dict({
            "name": "Office 101",
            "ceiling_height": 3.0,
        })
        assert advisory.room_id == "Office 101"

    def test_unknown_room_id_default(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise_room_dict({"ceiling_height": 3.0})
        assert advisory.room_id == "unknown"

    def test_high_ceiling_dict(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise_room_dict({
            "room_id": "R1",
            "ceiling_height": 15.0,
        })
        assert advisory.severity == "CRITICAL"


class TestSeverityEscalation:
    """Severity should only escalate, never de-escalate."""

    def test_info_to_warning(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=10.0)
        assert advisory.severity == "WARNING"

    def test_warning_to_critical(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=15.0)
        assert advisory.severity == "CRITICAL"

    def test_multiple_warnings_escalate(self):
        """Low ceiling + slope → WARNING should not override to INFO."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(
            room_id="R1", ceiling_height_m=2.2, slope_degrees=10.0, detector_type="smoke"
        )
        assert advisory.severity == "WARNING"


class TestNFPA72References:
    """Verify correct NFPA 72 section references in advisories."""

    def test_beam_detector_references_1772(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=10.0)
        assert any("§17.7.2" in ref for ref in advisory.nfpa_references)

    def test_critical_height_references_table(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=15.0)
        assert any("Table 17.6.3.1.1" in ref for ref in advisory.nfpa_references)

    def test_slope_references_17634(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=3.0, slope_degrees=10.0)
        assert any("§17.6.3.4" in ref for ref in advisory.nfpa_references)

    def test_steep_slope_references_1773(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=3.0, slope_degrees=35.0)
        assert any("§17.7.3" in ref for ref in advisory.nfpa_references)

    def test_stratification_references_17736(self):
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="R1", ceiling_height_m=2.2, detector_type="smoke")
        assert any("§17.7.3.6" in ref for ref in advisory.nfpa_references)


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Scenarios
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegrationScenarios:
    def test_typical_office(self):
        """Normal office: flat ceiling, 3m — no advisory."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="OFFICE-1", ceiling_height_m=3.0)
        assert advisory.severity == "INFO"
        assert advisory.beam_detector_recommended is False

    def test_atrium_beam_detectors(self):
        """Atrium: 15m ceiling → beam detectors required."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="ATRIUM-1", ceiling_height_m=15.0)
        assert advisory.severity == "CRITICAL"
        assert advisory.beam_detector_recommended is True

    def test_cathedral_ceiling(self):
        """Cathedral ceiling: 8m, 25° slope → WARNING for slope."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(
            room_id="CAT-1", ceiling_height_m=8.0, slope_degrees=25.0
        )
        assert advisory.severity == "WARNING"
        assert any("ridge" in r.lower() for r in advisory.recommendations)

    def test_industrial_high_slope(self):
        """Industrial: 12m ceiling + 15° slope → CRITICAL combination."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(
            room_id="IND-1", ceiling_height_m=12.0, slope_degrees=15.0
        )
        assert advisory.severity == "CRITICAL"
        assert advisory.beam_detector_recommended is True
        assert advisory.performance_based_design is True

    def test_corridor_low_ceiling(self):
        """Corridor: 2.3m ceiling → stratification WARNING."""
        advisor = SensorPhysicsAdvisor()
        advisory = advisor.advise(room_id="CORR-1", ceiling_height_m=2.3, detector_type="smoke")
        assert advisory.severity == "WARNING"
        assert any("stratification" in r.lower() for r in advisory.recommendations)
