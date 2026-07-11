"""
test_v214_cable_sizing_report.py — V214 regression tests for cable sizing
report with real NEC ampacity verification.

Verifies that _generate_cable_sizing_report() now:
  1. Maps cable sizes to AWG gauges
  2. Looks up NEC ampacity (§310.16, 60°C column)
  3. Computes load current (P=VI)
  4. Applies NEC 125% derating for continuous loads (§210.19)
  5. Reports is_adequate per connection
  6. Counts adequate/inadequate/skipped connections
"""

from __future__ import annotations

import pytest

from backend.routers.reports import _generate_cable_sizing_report, _cable_size_to_awg


class TestV214CableSizingRealAmpacity:
    """V214: cable_sizing report must verify NEC ampacity, not just list cables."""

    def test_cable_sizing_returns_adequate_inadequate_counts(self):
        """The report must include adequateConnections, inadequateConnections,
        and skippedConnections summary fields (V214).
        """
        connections = [
            {
                "id": "c1",
                "fromId": "d1",
                "toId": "d2",
                "cableSize": "1.5mm²",  # maps to AWG 16, ampacity 13A
                "length": 30.0,
                "type": "power",
            },
        ]
        devices = [
            {"id": "d1", "name": "Panel", "voltage": 24.0, "current": 2.0, "load": 2.0},
            {"id": "d2", "name": "Detector", "voltage": 24.0, "current": 0.1, "load": 0.1},
        ]
        result = _generate_cable_sizing_report(connections, devices, "2026-01-01T00:00:00Z")

        assert "adequateConnections" in result
        assert "inadequateConnections" in result
        assert "skippedConnections" in result
        assert result["totalConnections"] == 1

    def test_cable_sizing_verifies_ampacity_for_adequate_cable(self):
        """A 1.5mm² cable (AWG 16, 13A) feeding a 0.1A device at 24V
        must be reported as adequate (ampacity 13A >> derated current 0.125A).
        """
        connections = [
            {
                "id": "c1",
                "fromId": "d1",
                "toId": "d2",
                "cableSize": "1.5mm²",
                "length": 30.0,
                "type": "power",
            },
        ]
        devices = [
            {"id": "d1", "name": "Panel", "voltage": 24.0, "current": 2.0, "load": 2.0},
            {"id": "d2", "name": "Detector", "voltage": 24.0, "current": 0.1, "load": 0.1},
        ]
        result = _generate_cable_sizing_report(connections, devices, "2026-01-01")
        conn = result["connections"][0]

        assert conn["verification"] == "computed"
        assert conn["awg_gauge"] == "16"
        assert conn["nec_ampacity_a"] == 13.0
        assert conn["is_adequate"] is True
        # 0.1A × 1.25 = 0.125A derated
        assert conn["derated_current_a"] == 0.125
        assert result["adequateConnections"] == 1
        assert result["inadequateConnections"] == 0

    def test_cable_sizing_flags_inadequate_cable(self):
        """An AWG 18 cable (7A ampacity) feeding a 10A device must be
        reported as inadequate (10A × 1.25 = 12.5A > 7A).
        """
        connections = [
            {
                "id": "c1",
                "fromId": "d1",
                "toId": "d2",
                "cableSize": "18",  # AWG 18, ampacity 7A
                "length": 10.0,
                "type": "power",
            },
        ]
        devices = [
            {"id": "d1", "name": "Panel", "voltage": 24.0, "current": 10.0, "load": 10.0},
            {"id": "d2", "name": "Heavy Device", "voltage": 24.0, "current": 10.0, "load": 10.0},
        ]
        result = _generate_cable_sizing_report(connections, devices, "2026-01-01")
        conn = result["connections"][0]

        assert conn["verification"] == "computed"
        assert conn["awg_gauge"] == "18"
        assert conn["nec_ampacity_a"] == 7.0
        assert conn["is_adequate"] is False
        # 10A × 1.25 = 12.5A derated > 7A ampacity
        assert conn["derated_current_a"] == 12.5
        assert result["inadequateConnections"] == 1
        assert result["adequateConnections"] == 0

    def test_cable_sizing_derives_current_from_pvi_when_missing(self):
        """When device current is 0 but load (W) + voltage are present,
        the report must derive current = load / voltage.
        """
        connections = [
            {
                "id": "c1",
                "fromId": "d1",
                "toId": "d2",
                "cableSize": "2.5mm²",  # AWG 14, ampacity 15A
                "length": 20.0,
                "type": "power",
            },
        ]
        devices = [
            {"id": "d1", "name": "Panel", "voltage": 24.0, "current": 5.0, "load": 5.0},
            # Device with current=0 but load=12W, voltage=24V → 0.5A
            {"id": "d2", "name": "Detector", "voltage": 24.0, "current": 0, "load": 12.0},
        ]
        result = _generate_cable_sizing_report(connections, devices, "2026-01-01")
        conn = result["connections"][0]

        assert conn["verification"] == "computed"
        # 12W / 24V = 0.5A; 0.5A × 1.25 = 0.625A derated
        assert conn["load_current_a"] == 0.5
        assert conn["derated_current_a"] == 0.625
        assert conn["is_adequate"] is True  # 15A >> 0.625A

    def test_cable_sizing_skips_unmappable_cable(self):
        """Connections with exotic cable sizes must be skipped (not crash)."""
        connections = [
            {
                "id": "c1",
                "fromId": "d1",
                "toId": "d2",
                "cableSize": "exotic_unknown_format",
                "length": 20.0,
                "type": "power",
            },
        ]
        devices = [
            {"id": "d1", "name": "Panel", "voltage": 24.0, "current": 1.0, "load": 1.0},
            {"id": "d2", "name": "Detector", "voltage": 24.0, "current": 0.1, "load": 0.1},
        ]
        result = _generate_cable_sizing_report(connections, devices, "2026-01-01")
        conn = result["connections"][0]

        assert conn["verification"] == "skipped"
        assert "could not be mapped" in conn["verification_note"]
        assert result["skippedConnections"] == 1

    def test_cable_sizing_skips_when_device_not_found(self):
        """When the receiving device is not in the devices list, the
        connection must be skipped (not crash).
        """
        connections = [
            {
                "id": "c1",
                "fromId": "d1",
                "toId": "nonexistent",
                "cableSize": "1.5mm²",
                "length": 20.0,
                "type": "power",
            },
        ]
        devices = [
            {"id": "d1", "name": "Panel", "voltage": 24.0, "current": 1.0, "load": 1.0},
        ]
        result = _generate_cable_sizing_report(connections, devices, "2026-01-01")
        conn = result["connections"][0]

        assert conn["verification"] == "skipped"
        assert "not found" in conn["verification_note"]
        assert result["skippedConnections"] == 1

    def test_cable_sizing_includes_nec_section_reference(self):
        """The report must include NEC section references for traceability."""
        connections = [
            {
                "id": "c1",
                "fromId": "d1",
                "toId": "d2",
                "cableSize": "1.5mm²",
                "length": 30.0,
                "type": "power",
            },
        ]
        devices = [
            {"id": "d1", "name": "Panel", "voltage": 24.0, "current": 2.0, "load": 2.0},
            {"id": "d2", "name": "Detector", "voltage": 24.0, "current": 0.1, "load": 0.1},
        ]
        result = _generate_cable_sizing_report(connections, devices, "2026-01-01")

        assert "NEC" in result["standard"]
        assert "310.16" in result["standard"]  # ampacity table
        assert "210.19" in result["standard"]  # continuous load derating
        assert result["deratingFactor"] == 1.25
        assert "continuous" in result["deratingRationale"].lower()

    def test_cable_sizing_includes_utilization_pct(self):
        """Each computed connection must include utilization_pct
        (derated_current / ampacity × 100).
        """
        connections = [
            {
                "id": "c1",
                "fromId": "d1",
                "toId": "d2",
                "cableSize": "1.5mm²",  # AWG 16, 13A
                "length": 30.0,
                "type": "power",
            },
        ]
        devices = [
            {"id": "d1", "name": "Panel", "voltage": 24.0, "current": 2.0, "load": 2.0},
            {"id": "d2", "name": "Detector", "voltage": 24.0, "current": 1.0, "load": 1.0},
        ]
        result = _generate_cable_sizing_report(connections, devices, "2026-01-01")
        conn = result["connections"][0]

        # 1.0A × 1.25 = 1.25A derated; 1.25 / 13 × 100 = 9.615%
        assert conn["utilization_pct"] == pytest.approx(9.615, rel=0.01)
