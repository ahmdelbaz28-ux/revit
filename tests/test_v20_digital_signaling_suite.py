"""
tests/test_v20_digital_signaling_suite.py
==========================================
Ruthless vulnerability testing for V20 Digital Signaling & Master Network:

  1. SLCCapacitanceAuditor       — UL 864 / NFPA 72 §12.2
  2. StairwellSmokeControlIntegrator — NFPA 92 §6.1 / NFPA 101 §7.2.3.9
  3. NetworkTopologyAuditor      — NFPA 72 §23.8 / §12.3
"""
import pytest

from fireai.core.slc_capacitance import (
    SLCCapacitanceAuditor,
    SLCLoopSpec,
    CABLE_CAPACITANCE_PF_PER_M,
    SLC_MAX_CAPACITANCE_UF,
    DEFAULT_MAX_CAP_UF,
)
from fireai.core.stairwell_smoke_control import (
    StairwellSmokeControlIntegrator,
    StairwellZone,
    MIN_HEIGHT_FOR_PRESSURIZATION_M,
    MIN_POSITIVE_PRESSURE_PA,
    MAX_POSITIVE_PRESSURE_PA,
)
from fireai.core.network_topology import (
    NetworkTopologyAuditor,
    PanelNode,
    NetworkLink,
    REQUIRED_TOPOLOGY,
)
from fireai.core.provenance import DecisionProvenance, ConfidenceLevel, Violation


# ============================================================================
# 1. SLC CAPACITANCE AUDITOR TESTS
# ============================================================================
class TestSLCCapacitanceAuditor:

    def setup_method(self):
        self.auditor = SLCCapacitanceAuditor(manufacturer="notifier")

    def test_compliant_short_loop(self):
        """100m FPLP Shielded loop → 16.4 nF << 0.5 µF → PASS."""
        result = self.auditor.audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 100.0, "wire_type": "FPLP_Shielded"},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True
        assert val["loops_compliant"] == 1

    def test_failing_long_loop(self):
        """2500m FPLP Shielded → 410 nF = 0.41 µF < 0.5 µF → PASS
        (but close). 4000m → 656 nF = 0.656 µF > 0.5 µF → FAIL."""
        # Near limit but passes
        result = self.auditor.audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 2500.0, "wire_type": "FPLP_Shielded"},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True

        # Exceeds limit
        result2 = self.auditor.audit_slc_loops([
            {"loop_id": "SLC-02", "total_length_m": 4000.0, "wire_type": "FPLP_Shielded"},
        ])
        val2 = result2.value if isinstance(result2, DecisionProvenance) else result2["value"]
        assert val2["safe"] is False
        vio = result2.violations_detected if isinstance(result2, DecisionProvenance) else result2.get("violations", [])
        desc = vio[0]["description"] if isinstance(vio[0], dict) else vio[0].description
        assert "COMMUNICATION LOSS" in desc

    def test_unshielded_lower_capacitance(self):
        """Unshielded cable has lower capacitance per metre → longer loop OK."""
        auditor = SLCCapacitanceAuditor(manufacturer="notifier")
        # FPLR_Solid: 60 pF/m → 3000m = 180 nF = 0.18 µF → PASS
        result = auditor.audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 3000.0, "wire_type": "FPLR_Solid"},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True

    def test_fiber_optic_immune(self):
        """Fiber optic has 0 pF/m → any length passes."""
        result = self.auditor.audit_slc_loops([
            {"loop_id": "SLC-FIBER", "total_length_m": 50000.0, "wire_type": "Fiber_Optic"},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True
        dr = val["detailed_results"][0]
        assert dr["capacitance_uf"] == 0.0

    def test_manufacturer_simplex_higher_limit(self):
        """Simplex allows 0.75 µF → longer loop allowed."""
        auditor = SLCCapacitanceAuditor(manufacturer="simplex")
        # 0.65 µF would fail on Notifier (0.5) but pass on Simplex (0.75)
        result = auditor.audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 4000.0, "wire_type": "FPLP_Shielded",
             "manufacturer": "simplex"},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # 4000m × 164 pF/m = 656,000 pF = 0.656 µF < 0.75 µF → PASS
        assert val["safe"] is True

    def test_capacitance_calculation_accuracy(self):
        """Verify capacitance math: 1000m × 164 pF/m = 164,000 pF = 0.164 µF."""
        result = self.auditor.audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 1000.0, "wire_type": "FPLP_Shielded"},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        dr = val["detailed_results"][0]
        assert abs(dr["capacitance_pf"] - 164000.0) < 1.0
        assert abs(dr["capacitance_uf"] - 0.164) < 0.001

    def test_multiple_loops_mixed_compliance(self):
        """2 loops: 1 compliant, 1 failing."""
        result = self.auditor.audit_slc_loops([
            {"loop_id": "SLC-GOOD", "total_length_m": 500.0, "wire_type": "FPLP_Shielded"},
            {"loop_id": "SLC-BAD", "total_length_m": 5000.0, "wire_type": "FPLP_Shielded"},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is False
        assert val["loops_compliant"] == 1
        assert val["loops_failing"] == 1

    def test_provenance_structure(self):
        result = self.auditor.audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 100.0, "wire_type": "FPLP_Shielded"},
        ])
        assert isinstance(result, DecisionProvenance)
        assert result.decision_type == "slc_capacitance_audit"
        assert result.algorithm["name"] == "CapacitanceWaveformGuard"

    def test_cable_capacitance_table_values(self):
        """Verify key cable capacitance values."""
        assert CABLE_CAPACITANCE_PF_PER_M["FPLP_Shielded"] == 164.0
        assert CABLE_CAPACITANCE_PF_PER_M["FPLR_Solid"] == 60.0
        assert CABLE_CAPACITANCE_PF_PER_M["Fiber_Optic"] == 0.0


# ============================================================================
# 2. STAIRWELL SMOKE CONTROL INTEGRATOR TESTS
# ============================================================================
class TestStairwellSmokeControlIntegrator:

    def test_low_rise_no_pressurization_needed(self):
        """Building 15m < 22.86m → pressurization NOT required."""
        integrator = StairwellSmokeControlIntegrator(building_height_m=15.0)
        result = integrator.generate_active_smoke_defense(
            stairwells=[
                {"zone_id": "STAIR-A", "name": "Stair A", "floors_served": ["F01", "F02"]},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["pressurization_required"] is False
        assert val["safe"] is True

    def test_high_rise_pressurization_required(self):
        """Building 60m > 22.86m → pressurization IS required."""
        integrator = StairwellSmokeControlIntegrator(building_height_m=60.0)
        result = integrator.generate_active_smoke_defense(
            stairwells=[
                {
                    "zone_id": "STAIR-A", "name": "Stair A",
                    "floors_served": ["F01", "F02", "F03"],
                    "roof_vent_location": (10.0, 5.0),
                    "landing_locations": {"F01": (10, 2), "F02": (10, 6), "F03": (10, 10)},
                },
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["pressurization_required"] is True
        # Missing fan → violation + injection
        assert val["safe"] is False
        assert val["fan_controls"] == 1
        assert val["pressure_monitors"] == 3  # 3 floors

    def test_high_rise_with_existing_fan(self):
        """High-rise with fan already present → no violation."""
        integrator = StairwellSmokeControlIntegrator(building_height_m=60.0)
        result = integrator.generate_active_smoke_defense(
            stairwells=[
                {
                    "zone_id": "STAIR-A", "name": "Stair A",
                    "floors_served": ["F01", "F02"],
                    "has_pressurization_fan": True,
                    "has_pressure_switches": True,
                },
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True
        assert val["fan_controls"] == 0  # Already exists

    def test_injection_device_types(self):
        """Verify injection device types."""
        integrator = StairwellSmokeControlIntegrator(building_height_m=40.0)
        result = integrator.generate_active_smoke_defense(
            stairwells=[
                {
                    "zone_id": "STAIR-A", "name": "Stair A",
                    "floors_served": ["F01", "F02"],
                    "roof_vent_location": (5.0, 5.0),
                    "landing_locations": {"F01": (5, 3), "F02": (5, 7)},
                },
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        injections = val["defense_injections"]
        fan_injections = [i for i in injections if i["device_type"] == "CTRL_PRESSURIZATION_FAN"]
        mon_injections = [i for i in injections if i["device_type"] == "MON_PRESSURE_SWITCH"]
        assert len(fan_injections) == 1
        assert len(mon_injections) == 2

    def test_height_threshold_boundary(self):
        """Building exactly at 22.86m → pressurization required."""
        integrator = StairwellSmokeControlIntegrator(
            building_height_m=22.86,
        )
        result = integrator.generate_active_smoke_defense(
            stairwells=[
                {"zone_id": "STAIR-A", "name": "Stair A", "floors_served": ["F01"]},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["pressurization_required"] is True

    def test_provenance_structure(self):
        integrator = StairwellSmokeControlIntegrator(building_height_m=30.0)
        result = integrator.generate_active_smoke_defense(
            stairwells=[
                {"zone_id": "STAIR-A", "name": "Stair A", "floors_served": ["F01"],
                 "has_pressurization_fan": True, "has_pressure_switches": True},
            ],
        )
        assert isinstance(result, DecisionProvenance)
        assert result.decision_type == "stairwell_smoke_control"
        assert result.algorithm["name"] == "ActiveSmokeDefenseGenerator"


# ============================================================================
# 3. NETWORK TOPOLOGY AUDITOR TESTS
# ============================================================================
class TestNetworkTopologyAuditor:

    def setup_method(self):
        self.auditor = NetworkTopologyAuditor()

    def test_ring_topology_compliant(self):
        """3 panels in a ring → Class X compliant."""
        result = self.auditor.audit_network_topology(
            panels=[
                {"panel_id": "FACP-01", "is_master": True},
                {"panel_id": "FACP-02"},
                {"panel_id": "FACP-03"},
            ],
            links=[
                {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True},
                {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03", "is_class_x": True},
                {"link_id": "L3", "from_panel": "FACP-03", "to_panel": "FACP-01", "is_class_x": True},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["topology_type"] == "ring"
        assert val["is_class_x_compliant"] is True
        assert val["safe"] is True

    def test_star_topology_non_compliant(self):
        """Star topology → single point of failure at master."""
        result = self.auditor.audit_network_topology(
            panels=[
                {"panel_id": "FACP-01", "is_master": True},
                {"panel_id": "FACP-02"},
                {"panel_id": "FACP-03"},
            ],
            links=[
                {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": False},
                {"link_id": "L2", "from_panel": "FACP-01", "to_panel": "FACP-03", "is_class_x": False},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["topology_type"] == "star"
        # FACP-02 and FACP-03 have only 1 connection → violation
        assert val["safe"] is False

    def test_daisy_chain_non_compliant(self):
        """Daisy-chain: mid-chain cut isolates downstream."""
        result = self.auditor.audit_network_topology(
            panels=[
                {"panel_id": "FACP-01", "is_master": True},
                {"panel_id": "FACP-02"},
                {"panel_id": "FACP-03"},
            ],
            links=[
                {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02"},
                {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03"},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # FACP-03 has only 1 connection → violation
        assert val["safe"] is False

    def test_fiber_recommendations_for_copper(self):
        """Non-Class-X copper links should get fiber recommendations."""
        result = self.auditor.audit_network_topology(
            panels=[
                {"panel_id": "FACP-01", "is_master": True},
                {"panel_id": "FACP-02"},
                {"panel_id": "FACP-03"},
            ],
            links=[
                {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02",
                 "is_class_x": True, "link_type": "fiber_dual"},
                {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03",
                 "is_class_x": True, "link_type": "fiber_dual"},
                {"link_id": "L3", "from_panel": "FACP-03", "to_panel": "FACP-01",
                 "is_class_x": False, "link_type": "copper"},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # L3 is copper and not Class X → fiber recommendation
        assert len(val["fiber_recommendations"]) == 1
        assert val["fiber_recommendations"][0]["link_id"] == "L3"

    def test_single_panel_system(self):
        """Single panel → no network topology needed."""
        result = self.auditor.audit_network_topology(
            panels=[{"panel_id": "FACP-01", "is_master": True}],
            links=[],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["topology_type"] == "single_panel"
        assert val["safe"] is True

    def test_master_with_single_connection(self):
        """Master with only 1 connection → single point of failure."""
        result = self.auditor.audit_network_topology(
            panels=[
                {"panel_id": "FACP-01", "is_master": True},
                {"panel_id": "FACP-02"},
            ],
            links=[
                {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is False  # Both panels have only 1 connection

    def test_provenance_structure(self):
        result = self.auditor.audit_network_topology(
            panels=[
                {"panel_id": "FACP-01", "is_master": True},
                {"panel_id": "FACP-02"},
            ],
            links=[
                {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True},
                {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-01", "is_class_x": True},
            ],
        )
        assert isinstance(result, DecisionProvenance)
        assert result.decision_type == "network_topology_audit"
        assert result.algorithm["name"] == "RedundantPathFinder"

    def test_mesh_topology_compliant(self):
        """Mesh with >2 connections per panel → Class X compliant."""
        result = self.auditor.audit_network_topology(
            panels=[
                {"panel_id": "FACP-01", "is_master": True},
                {"panel_id": "FACP-02"},
                {"panel_id": "FACP-03"},
                {"panel_id": "FACP-04"},
            ],
            links=[
                {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02", "is_class_x": True},
                {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03", "is_class_x": True},
                {"link_id": "L3", "from_panel": "FACP-03", "to_panel": "FACP-04", "is_class_x": True},
                {"link_id": "L4", "from_panel": "FACP-04", "to_panel": "FACP-01", "is_class_x": True},
                {"link_id": "L5", "from_panel": "FACP-01", "to_panel": "FACP-03", "is_class_x": True},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["topology_type"] == "mesh"
        assert val["is_class_x_compliant"] is True


# ============================================================================
# 4. INTEGRATION TESTS
# ============================================================================
class TestV20Integration:

    def test_all_three_v20_modules(self):
        """All three V20 modules produce correct DecisionProvenance."""
        s = SLCCapacitanceAuditor().audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 100.0},
        ])
        sc = StairwellSmokeControlIntegrator(building_height_m=10.0).generate_active_smoke_defense(
            [{"zone_id": "STAIR-A", "name": "Stair A", "floors_served": ["F01"],
              "has_pressurization_fan": True, "has_pressure_switches": True}],
        )
        n = NetworkTopologyAuditor().audit_network_topology(
            panels=[{"panel_id": "FACP-01", "is_master": True}],
            links=[],
        )
        for result, expected_type in [
            (s, "slc_capacitance_audit"),
            (sc, "stairwell_smoke_control"),
            (n, "network_topology_audit"),
        ]:
            assert isinstance(result, DecisionProvenance)
            assert result.decision_type == expected_type


# ============================================================================
# 5. APOCALYPSE EDGE CASES
# ============================================================================
class TestV20Apocalypse:

    def test_slc_zero_length_loop(self):
        """Zero-length loop → invalid (V20.2 FIX) → FAIL.
        V20.2 FIX: Zero-length SLC loops are physically meaningless and
        likely indicate a data-entry error. Previously this trivially
        passed, masking missing data. Now correctly flagged as invalid."""
        auditor = SLCCapacitanceAuditor()
        result = auditor.audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 0.0},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is False

    def test_slc_unknown_wire_type(self):
        """Unknown wire type uses conservative fallback (V20.2 FIX: 164 pF/m, not 100 pF/m).
        V20.2 FIX: Unknown wire types now use the HIGHEST known value (164 pF/m
        for FPLP_Shielded) as a conservative default, not 100 pF/m which could
        approve an overloaded shielded-cable loop."""
        auditor = SLCCapacitanceAuditor()
        result = auditor.audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 1000.0, "wire_type": "UNKNOWN_CABLE"},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # V20.2 FIX: 1000m × 164 pF/m = 164,000 pF = 0.164 µF → PASS
        # (was 1000m × 100 pF/m = 0.1 µF before)
        assert val["safe"] is True

    def test_stairwell_zero_building_height(self):
        """Zero-height building → no pressurization needed."""
        integrator = StairwellSmokeControlIntegrator(building_height_m=0.0)
        result = integrator.generate_active_smoke_defense(
            [{"zone_id": "STAIR-A", "name": "Stair A", "floors_served": ["GF"]}],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["pressurization_required"] is False

    def test_stairwell_no_stairwells(self):
        """No stairwells → trivially safe."""
        integrator = StairwellSmokeControlIntegrator(building_height_m=60.0)
        result = integrator.generate_active_smoke_defense(stairwells=[])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        assert val["safe"] is True

    def test_network_unknown_topology(self):
        """Complex topology that doesn't fit star/ring/mesh."""
        result = NetworkTopologyAuditor().audit_network_topology(
            panels=[
                {"panel_id": "FACP-01", "is_master": True},
                {"panel_id": "FACP-02"},
                {"panel_id": "FACP-03"},
                {"panel_id": "FACP-04"},
            ],
            links=[
                {"link_id": "L1", "from_panel": "FACP-01", "to_panel": "FACP-02"},
                {"link_id": "L2", "from_panel": "FACP-02", "to_panel": "FACP-03"},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # Multiple panels with <2 connections → not safe
        assert val["safe"] is False

    def test_slc_capacitance_near_limit_warning(self):
        """Loop at 90% of limit → passes but should log warning."""
        # Notifier limit: 0.5 µF. FPLP_Shielded: 164 pF/m
        # 90% of 0.5 µF = 0.45 µF = 450,000 pF
        # 450,000 / 164 = 2743.9 m
        auditor = SLCCapacitanceAuditor(manufacturer="notifier")
        result = auditor.audit_slc_loops([
            {"loop_id": "SLC-01", "total_length_m": 2744.0, "wire_type": "FPLP_Shielded"},
        ])
        val = result.value if isinstance(result, DecisionProvenance) else result["value"]
        # Should pass but be near limit
        assert val["safe"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
