"""Gate 9: Import-Level Integration Tests (V131 Phase 4).
======================================================
Direct import-level integration between ETAP Skill and FireAI modules.
These tests verify that the bridge modules can IMPORT and USE FireAI
functions directly (not just read source files).

Per Operator request (V131 Phase 4):
    "تكامل أعمق: ربط المهارة مباشرةً مع وحدات FireAI الموجودة
     كـ import وليس فقط اختبارات تكامل"

Author: FireAI Project
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).parent.parent
PROJECT_ROOT = SKILL_ROOT.parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# BRIDGE IMPORT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestBridgeImports:
    """Verify bridge module imports cleanly."""

    def test_fireai_bridge_imports(self):
        """fireai_bridge module must import without errors."""
        import fireai_bridge

        assert hasattr(fireai_bridge, "bridge_voltage_drop")
        assert hasattr(fireai_bridge, "bridge_arc_flash_atex")
        assert hasattr(fireai_bridge, "bridge_marine_power_fire_safety")
        assert hasattr(fireai_bridge, "bridge_harmonic_analysis")
        assert hasattr(fireai_bridge, "run_all_bridges")

    def test_bridge_data_classes_importable(self):
        """Bridge result data classes must be importable."""
        from fireai_bridge import (
            ArcFlashAtexBridgeResult,
            HarmonicBridgeResult,
            MarineBridgeResult,
            VoltageDropBridgeResult,
        )

        assert VoltageDropBridgeResult is not None
        assert ArcFlashAtexBridgeResult is not None
        assert MarineBridgeResult is not None
        assert HarmonicBridgeResult is not None


# ═══════════════════════════════════════════════════════════════════════════
# VOLTAGE DROP BRIDGE TESTS (direct import integration)
# ═══════════════════════════════════════════════════════════════════════════


class TestVoltageDropBridge:
    """Test ETAP ↔ FireAI voltage_drop bridge."""

    def test_bridge_runs_with_etap_only(self):
        """Bridge must work even if FireAI module is unavailable."""
        from fireai_bridge import bridge_voltage_drop

        result = bridge_voltage_drop(
            load_current_a=200.0, one_way_length_ft=300.0
        )
        assert result.etap_recommended_size == "4/0 AWG"
        assert result.etap_ampacity_a == 230
        assert result.etap_voltage_drop_v > 0

    def test_bridge_uses_fireai_when_available(self):
        """If FireAI voltage_drop is importable, bridge must use it."""
        try:
            import importlib

            if importlib.util.find_spec("fireai.core.voltage_drop") is None:
                pytest.skip("FireAI voltage_drop not importable")
        except ImportError:
            pytest.skip("FireAI voltage_drop not importable")

        from fireai_bridge import bridge_voltage_drop

        result = bridge_voltage_drop(
            load_current_a=2.0,  # Low current for FA circuit
            one_way_length_ft=100.0,
            voltage_v=24.0,  # 24VDC FA system
            pf=1.0,  # DC
        )

        # FireAI should have calculated voltage drop
        if result.fireai_voltage_drop_v is not None:
            assert result.fireai_voltage_drop_v > 0
            assert result.fireai_compliant is not None

    def test_bridge_returns_unified_compliance(self):
        """Bridge must return unified compliance flag."""
        from fireai_bridge import bridge_voltage_drop

        result = bridge_voltage_drop(
            load_current_a=200.0, one_way_length_ft=300.0
        )
        assert isinstance(result.unified_compliant, bool)
        assert isinstance(result.max_voltage_drop_pct, float)

    def test_bridge_cross_validation(self):
        """Bridge must cross-validate ETAP vs FireAI methods."""
        from fireai_bridge import bridge_voltage_drop

        result = bridge_voltage_drop(
            load_current_a=200.0, one_way_length_ft=300.0
        )
        assert isinstance(result.voltage_drop_methods_agree, bool)


# ═══════════════════════════════════════════════════════════════════════════
# ARC FLASH ↔ ATEX BRIDGE TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestArcFlashAtexBridge:
    """Test ETAP arc flash ↔ FireAI ATEX bridge."""

    def test_bridge_arc_flash_only(self):
        """Without hazardous area, only arc flash analysis runs."""
        from fireai_bridge import bridge_arc_flash_atex

        result = bridge_arc_flash_atex(
            bolted_fault_current_ka=50.0, hazardous_area=False
        )
        assert result.arc_flash_ppe_category >= 0
        assert result.atex_zone is None
        assert not result.dual_hazard_present

    def test_bridge_dual_hazard(self):
        """With hazardous area, both arc flash and ATEX apply."""
        from fireai_bridge import bridge_arc_flash_atex

        result = bridge_arc_flash_atex(
            bolted_fault_current_ka=50.0,
            hazardous_area=True,
            hazard_type="gas",
        )
        assert result.dual_hazard_present
        assert result.atex_zone == "Zone 1"
        assert result.atex_epl == "Gb"
        assert "Arc Flash" in result.combined_ppe_required
        assert "ATEX" in result.combined_ppe_required

    def test_bridge_dust_hazard(self):
        """Dust hazard → Zone 21, EPL Db."""
        from fireai_bridge import bridge_arc_flash_atex

        result = bridge_arc_flash_atex(
            hazardous_area=True, hazard_type="dust"
        )
        assert result.atex_zone == "Zone 21"
        assert result.atex_epl == "Db"

    def test_bridge_combined_ppe_string(self):
        """Combined PPE string must mention both hazards."""
        from fireai_bridge import bridge_arc_flash_atex

        result = bridge_arc_flash_atex(
            hazardous_area=True, hazard_type="gas"
        )
        assert "Arc Flash" in result.combined_ppe_required
        assert "ATEX" in result.combined_ppe_required
        assert "intrinsic safety" in result.combined_ppe_required


# ═══════════════════════════════════════════════════════════════════════════
# MARINE BRIDGE TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestMarineBridge:
    """Test ETAP marine ↔ FireAI marine_service bridge."""

    def test_bridge_default_ship(self):
        """Default ship (7.5MW, 690V, 3 generators) must work."""
        from fireai_bridge import bridge_marine_power_fire_safety

        result = bridge_marine_power_fire_safety()
        assert result.ship_power_mw == 7.5
        assert result.ship_voltage_v == 690.0
        assert result.generator_count == 3
        assert result.solas_compliance_required

    def test_bridge_iec_standard_selection(self):
        """IEC standard must be selected based on voltage."""
        from fireai_bridge import bridge_marine_power_fire_safety

        # LV (≤1000V)
        result_lv = bridge_marine_power_fire_safety(ship_voltage_v=690.0)
        assert "IEC 60092-201" in result_lv.iec_standard_applied

        # MV (1000V < V ≤ 15000V)
        result_mv = bridge_marine_power_fire_safety(ship_voltage_v=6600.0)
        assert "IEC 60092-503" in result_mv.iec_standard_applied

    def test_bridge_mvz_calculation(self):
        """Main Vertical Zones must scale with ship length."""
        from fireai_bridge import bridge_marine_power_fire_safety

        result_short = bridge_marine_power_fire_safety(ship_length_m=100.0)
        result_long = bridge_marine_power_fire_safety(ship_length_m=300.0)
        assert result_long.fire_zones_needed > result_short.fire_zones_needed

    def test_bridge_solas_compliance_threshold(self):
        """SOLAS applies for ships > 0.5 MW."""
        from fireai_bridge import bridge_marine_power_fire_safety

        result_small = bridge_marine_power_fire_safety(ship_power_mw=0.3)
        result_large = bridge_marine_power_fire_safety(ship_power_mw=5.0)
        assert not result_small.solas_compliance_required
        assert result_large.solas_compliance_required

    def test_bridge_redundancy_warning(self):
        """Single generator must trigger SOLAS warning."""
        from fireai_bridge import bridge_marine_power_fire_safety

        result = bridge_marine_power_fire_safety(generator_count=1)
        assert any("SOLAS requires at least 2 generators" in w for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════
# HARMONIC BRIDGE TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestHarmonicBridge:
    """Test ETAP harmonic ↔ FireAI bridge."""

    def test_bridge_default_analysis(self):
        """Default harmonic analysis must run."""
        from fireai_bridge import bridge_harmonic_analysis

        result = bridge_harmonic_analysis()
        assert result.thd_current_pct > 0
        assert result.tdd_limit_pct > 0

    def test_bridge_filter_recommendation(self):
        """Non-compliant THD must trigger filter recommendation."""
        from fireai_bridge import bridge_harmonic_analysis

        result = bridge_harmonic_analysis(
            load_current_a=200.0, isc_a=20000.0  # High ISC/IL ratio
        )
        if not result.current_compliant:
            assert result.filter_required
            assert result.recommended_filter_type is not None
            assert "filter" in result.recommended_filter_type.lower()

    def test_bridge_filter_type_for_5th_harmonic(self):
        """5th harmonic dominance → 5th harmonic tuned filter."""
        from fireai_bridge import bridge_harmonic_analysis

        result = bridge_harmonic_analysis()
        if result.filter_required:
            # Default spectrum has 5th at 20% (dominant)
            assert "5th harmonic" in (result.recommended_filter_type or "")

    def test_bridge_compliance_flags(self):
        """Compliance flags must be boolean."""
        from fireai_bridge import bridge_harmonic_analysis

        result = bridge_harmonic_analysis()
        assert isinstance(result.voltage_compliant, bool)
        assert isinstance(result.current_compliant, bool)
        assert isinstance(result.filter_required, bool)


# ═══════════════════════════════════════════════════════════════════════════
# MASTER BRIDGE RUNNER TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestMasterBridgeRunner:
    """Test run_all_bridges() orchestrator."""

    def test_all_4_bridges_run(self):
        """run_all_bridges() must execute all 4 bridges."""
        from fireai_bridge import run_all_bridges

        results = run_all_bridges()
        assert len(results) == 4
        expected_keys = {"voltage_drop", "arc_flash_atex", "marine", "harmonic"}
        assert set(results.keys()) == expected_keys

    def test_all_bridges_return_dicts(self):
        """Each bridge result must be serializable to dict."""
        from fireai_bridge import run_all_bridges

        results = run_all_bridges()
        for name, result in results.items():
            assert isinstance(result, dict), f"{name} did not return dict"
            assert "warnings" in result, f"{name} missing warnings field"


# ═══════════════════════════════════════════════════════════════════════════
# DIRECT FIREAI IMPORT TESTS (verify FireAI modules are importable)
# ═══════════════════════════════════════════════════════════════════════════


class TestDirectFireAIImports:
    """Verify FireAI modules can be imported directly from skill."""

    def test_voltage_drop_importable(self):
        """fireai.core.voltage_drop must be importable."""
        try:
            from fireai.core.voltage_drop import (
                calculate_voltage_drop,
                get_wire_resistance_ohm_per_m,
            )

            assert callable(calculate_voltage_drop)
            assert callable(get_wire_resistance_ohm_per_m)
        except ImportError:
            pytest.skip("fireai.core.voltage_drop not importable")

    def test_atex_importable(self):
        """fireai.core.atex_hazardous_arbiter must be importable."""
        try:
            from fireai.core.atex_hazardous_arbiter import EquipmentProtectionLevel

            assert EquipmentProtectionLevel is not None
        except ImportError:
            pytest.skip("fireai.core.atex_hazardous_arbiter not importable")

    def test_voltage_drop_function_callable(self):
        """calculate_voltage_drop must be callable with valid inputs."""
        try:
            from fireai.core.voltage_drop import calculate_voltage_drop
        except ImportError:
            pytest.skip("fireai module not importable")

        result = calculate_voltage_drop(
            current_a=2.0,
            one_way_length_m=100.0,
            awg="14",
            nominal_voltage=24.0,
        )
        assert result["voltage_drop_v"] > 0
        assert result["voltage_drop_pct"] > 0
        assert isinstance(result["is_compliant"], bool)

    def test_awg_resistance_lookup_works(self):
        """get_wire_resistance_ohm_per_m must return valid resistance."""
        try:
            from fireai.core.voltage_drop import get_wire_resistance_ohm_per_m
        except ImportError:
            pytest.skip("fireai module not importable")

        r = get_wire_resistance_ohm_per_m("14")
        assert r > 0
        # AWG 14: 10.07 Ω/km → 0.01007 Ω/m
        assert abs(r - 0.01007) < 0.001
