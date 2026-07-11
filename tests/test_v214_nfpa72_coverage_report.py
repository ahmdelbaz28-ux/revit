"""
test_v214_nfpa72_coverage_report.py — V214 regression tests for NFPA 72
coverage report with real detector spacing verification.

Verifies that _generate_nfpa72_coverage_report() now:
  1. Classifies devices into smoke/heat/notification/manual/other
  2. Reports per-type counts with NFPA 72 section references
  3. Includes spacing constants (smoke=9.1m, heat=6.1m) from qomn_kernel
  4. Computes coverage radius (R = 0.7 × S) and area per detector
  5. Flags devices missing coordinates
  6. Warns when notification appliances or manual stations are absent
"""

from __future__ import annotations

import pytest

from backend.routers.reports import _generate_nfpa72_coverage_report


class TestV214Nfpa72CoverageRealSpacing:
    """V214: nfpa72_coverage report must verify detector spacing, not just
    count devices.
    """

    def test_coverage_report_includes_detector_summary(self):
        """The report must include a detectorSummary field with per-type
        breakdown (smoke, heat, notification, manual, other).
        """
        devices = [
            {"id": "d1", "type": "FA_SMOKE", "category": "FIRE_ALARM", "x": 0, "y": 0},
            {"id": "d2", "type": "FA_HEAT", "category": "FIRE_ALARM", "x": 5, "y": 5},
            {"id": "d3", "type": "FA_SOUND_STROBE", "category": "FIRE_ALARM", "x": 10, "y": 10},
            {"id": "d4", "type": "FA_MANUAL_PULL", "category": "FIRE_ALARM", "x": 15, "y": 15},
        ]
        result = _generate_nfpa72_coverage_report(devices, "2026-01-01")

        assert "detectorSummary" in result
        summary = result["detectorSummary"]
        assert summary["smokeDetectors"]["count"] == 1
        assert summary["heatDetectors"]["count"] == 1
        assert summary["notificationAppliances"]["count"] == 1
        assert summary["manualPullStations"]["count"] == 1
        assert summary["otherDevices"]["count"] == 0

    def test_coverage_report_includes_smoke_spacing_from_qomn(self):
        """Smoke detector spacing must be 9.1m flat per NFPA 72 §17.7.3.2.3,
        sourced from qomn_kernel.
        """
        devices = [{"id": "d1", "type": "FA_SMOKE", "category": "FIRE_ALARM", "x": 0, "y": 0}]
        result = _generate_nfpa72_coverage_report(devices, "2026-01-01")

        smoke = result["detectorSummary"]["smokeDetectors"]
        assert smoke["maxSpacingM"] == 9.1
        assert "§17.7.3.2.3" in smoke["nfpaSection"]
        # Coverage radius = 0.7 × 9.1 = 6.37m
        assert smoke["coverageRadiusM"] == 6.37
        # Coverage area = π × 6.37² ≈ 127.4 m²
        assert smoke["coverageAreaPerDetectorM2"] > 127
        assert smoke["coverageAreaPerDetectorM2"] < 128

    def test_coverage_report_includes_heat_spacing_from_qomn(self):
        """Heat detector spacing must be 6.1m per NFPA 72 §17.6.3.5.1."""
        devices = [{"id": "d1", "type": "FA_HEAT", "category": "FIRE_ALARM", "x": 0, "y": 0}]
        result = _generate_nfpa72_coverage_report(devices, "2026-01-01")

        heat = result["detectorSummary"]["heatDetectors"]
        assert heat["maxSpacingM"] == 6.1
        assert "§17.6.3.5.1" in heat["nfpaSection"]
        # Coverage radius = 0.7 × 6.1 = 4.27m
        assert heat["coverageRadiusM"] == 4.27

    def test_coverage_report_flags_devices_missing_coordinates(self):
        """Devices with x=None or y=None must be counted as
        devicesMissingCoordinates.
        """
        devices = [
            {"id": "d1", "type": "FA_SMOKE", "category": "FIRE_ALARM", "x": 0, "y": 0},
            {"id": "d2", "type": "FA_SMOKE", "category": "FIRE_ALARM", "x": None, "y": None},
            {"id": "d3", "type": "FA_SMOKE", "category": "FIRE_ALARM"},  # no x/y keys
        ]
        result = _generate_nfpa72_coverage_report(devices, "2026-01-01")

        smoke = result["detectorSummary"]["smokeDetectors"]
        assert smoke["count"] == 3
        assert smoke["devicesWithCoordinates"] == 1
        assert smoke["devicesMissingCoordinates"] == 2

    def test_coverage_report_warns_when_no_notification_appliances(self):
        """When there are detectors but no notification appliances, the
        report must include a warning about NFPA 72 §18.4.
        """
        devices = [
            {"id": "d1", "type": "FA_SMOKE", "category": "FIRE_ALARM", "x": 0, "y": 0},
            {"id": "d2", "type": "FA_HEAT", "category": "FIRE_ALARM", "x": 5, "y": 5},
        ]
        result = _generate_nfpa72_coverage_report(devices, "2026-01-01")

        notes = result["complianceNotes"]
        notification_warning = [n for n in notes if "notification" in n.lower() or "§18.4" in n]
        assert len(notification_warning) > 0, (
            f"Must warn about missing notification appliances, notes: {notes}"
        )

    def test_coverage_report_warns_when_no_manual_stations(self):
        """When there are devices but no manual pull stations, the report
        must include a warning about NFPA 72 §17.14.
        """
        devices = [
            {"id": "d1", "type": "FA_SMOKE", "category": "FIRE_ALARM", "x": 0, "y": 0},
        ]
        result = _generate_nfpa72_coverage_report(devices, "2026-01-01")

        notes = result["complianceNotes"]
        manual_warning = [n for n in notes if "manual" in n.lower() or "§17.14" in n]
        assert len(manual_warning) > 0, (
            f"Must warn about missing manual pull stations, notes: {notes}"
        )

    def test_coverage_report_includes_spacing_constants(self):
        """The report must include a spacingConstants field with the source
        (qomn_kernel or fallback).
        """
        devices = []
        result = _generate_nfpa72_coverage_report(devices, "2026-01-01")

        assert "spacingConstants" in result
        sc = result["spacingConstants"]
        assert sc["smokeMaxSpacingM"] == 9.1
        assert sc["heatMaxSpacingM"] == 6.1
        assert sc["coverageRadiusFactor"] == 0.7
        assert "source" in sc

    def test_coverage_report_includes_disclaimer(self):
        """The report must include a disclaimer explaining that this is a
        placement adequacy check, not a full coverage simulation.
        """
        devices = [{"id": "d1", "type": "FA_SMOKE", "category": "FIRE_ALARM", "x": 0, "y": 0}]
        result = _generate_nfpa72_coverage_report(devices, "2026-01-01")

        assert "disclaimer" in result
        assert "spatial_engine" in result["disclaimer"] or "place-detectors" in result["disclaimer"]

    def test_coverage_report_handles_empty_device_list(self):
        """An empty device list must not crash the report."""
        result = _generate_nfpa72_coverage_report([], "2026-01-01")

        assert result["totalDevices"] == 0
        assert result["detectorSummary"]["smokeDetectors"]["count"] == 0
        assert result["detectorSummary"]["heatDetectors"]["count"] == 0

    def test_coverage_report_includes_nfpa_section_references(self):
        """Each detector type summary must include the NFPA 72 section
        reference for traceability.
        """
        devices = [
            {"id": "d1", "type": "FA_SMOKE", "category": "FIRE_ALARM", "x": 0, "y": 0},
            {"id": "d2", "type": "FA_HEAT", "category": "FIRE_ALARM", "x": 5, "y": 5},
            {"id": "d3", "type": "FA_SOUND_STROBE", "category": "FIRE_ALARM", "x": 10, "y": 10},
            {"id": "d4", "type": "FA_MANUAL_PULL", "category": "FIRE_ALARM", "x": 15, "y": 15},
        ]
        result = _generate_nfpa72_coverage_report(devices, "2026-01-01")

        summary = result["detectorSummary"]
        assert "§17.7.3.2.3" in summary["smokeDetectors"]["nfpaSection"]
        assert "§17.6.3.5.1" in summary["heatDetectors"]["nfpaSection"]
        assert "§18.4" in summary["notificationAppliances"]["nfpaSection"]
        assert "§17.14" in summary["manualPullStations"]["nfpaSection"]
