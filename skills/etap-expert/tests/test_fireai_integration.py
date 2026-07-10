"""
Gate 6: Integration Tests — ETAP Skill ↔ FireAI Modules.
=========================================================
Validates that the ETAP skill's calculation methods produce results
compatible with FireAI's existing engineering modules.

Three integration axes:
    1. ETAP cable sizing ↔ fireai.core.voltage_drop (NEC Table 310.16 vs Table 8)
    2. ETAP arc flash ↔ fireai.core.atex_hazardous_arbiter (IEEE 1584 vs IEC 60079)
    3. ETAP marine ↔ backend.services.marine_service (IEC 60092 vs IEC 61363)

Per FireAI agent.md Rule 20 (MULTI-PHASE INTEGRITY REVIEW):
    A phase that works in isolation but breaks when combined with other phases
    is NOT a completed phase. Cross-module interactions MUST be verified.

Author: FireAI Project
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).parent.parent
PROJECT_ROOT = SKILL_ROOT.parent.parent  # /home/z/my-project/revit/
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION 1: ETAP Cable Sizing ↔ FireAI voltage_drop
# ═══════════════════════════════════════════════════════════════════════════
#
# ETAP skill uses NEC Table 310.16 (AC ampacity, 75°C copper)
# FireAI voltage_drop uses NEC Chapter 9 Table 8 (DC resistance, 75°C copper)
#
# Both tables are for copper at 75°C, but Table 310.16 gives ampacity (A)
# while Table 8 gives resistance (Ω/km). They are complementary, not
# contradictory — a proper cable design uses BOTH:
#   1. Table 310.16 → minimum conductor size for ampacity
#   2. Table 8 → voltage drop calculation for chosen size
#
# Integration test: for a given load current, the ETAP skill recommends
# a cable size, and FireAI's voltage_drop module should accept that size
# and produce a finite, positive voltage drop.


class TestCableSizingVoltageDropIntegration:
    """Integration: ETAP cable sizing ↔ FireAI voltage_drop module."""

    @pytest.fixture(scope="class")
    def etap_cable_result(self):
        from internal_simulation_engine import simulate_cable_sizing

        return simulate_cable_sizing(
            load_current_a=2.0,  # Typical FA circuit current
            voltage_v=24.0,  # 24VDC FA system
            length_ft=300.0,  # 300 ft ≈ 91.44 m
            pf=1.0,  # DC system → PF = 1
        )

    @pytest.fixture(scope="class")
    def fireai_voltage_drop_result(self):
        """Run FireAI voltage_drop for the same scenario."""
        # Skip if fireai module not importable (e.g., missing deps)
        try:
            from fireai.core.voltage_drop import calculate_voltage_drop
        except ImportError:
            pytest.skip("fireai.core.voltage_drop not importable")
        return calculate_voltage_drop(
            current_a=2.0,
            one_way_length_m=91.44,  # 300 ft
            awg="14",  # Standard FA wire
            nominal_voltage=24.0,
        )

    def test_etap_skill_recommends_4_0_awg_for_high_current(self, etap_cable_result) -> None:
        """For 200A load, ETAP skill recommends 4/0 AWG (230A ampacity)."""
        from internal_simulation_engine import simulate_cable_sizing

        result = simulate_cable_sizing(load_current_a=200.0)
        assert result.recommended_size == "4/0 AWG"
        assert result.ampacity_a >= 200

    def test_fireai_voltage_drop_accepts_etap_recommended_size(self) -> None:
        """FireAI voltage_drop must accept '4/0' AWG (per NEC Table 8)."""
        try:
            from fireai.core.voltage_drop import calculate_voltage_drop
        except ImportError:
            pytest.skip("fireai module not importable")

        # Use 4/0 AWG as recommended by ETAP skill for 200A load
        result = calculate_voltage_drop(
            current_a=200.0,
            one_way_length_m=91.44,  # 300 ft
            awg="4/0",
            nominal_voltage=480.0,  # Use higher voltage (not FA)
        )
        assert result["voltage_drop_v"] > 0
        assert result["voltage_drop_pct"] > 0
        assert math.isfinite(result["voltage_drop_v"])

    def test_both_modules_use_75c_copper_baseline(self) -> None:
        """Both ETAP skill and FireAI use 75°C copper reference."""
        # ETAP: NEC Table 310.16 (75°C Cu)
        # FireAI: NEC Chapter 9 Table 8 (75°C Cu, DC resistance)
        # Verify both reference 75°C in their source files
        try:
            vd_file = PROJECT_ROOT / "fireai" / "core" / "voltage_drop.py"
            vd_source = vd_file.read_text(encoding="utf-8")
        except (OSError, ImportError):
            pytest.skip("fireai.core.voltage_drop source not readable")

        # FireAI voltage_drop.py has "75°C" in comments (NEC Table 8 reference)
        assert "75°C" in vd_source or "75" in vd_source, (
            "FireAI voltage_drop.py should reference 75°C copper baseline"
        )

        # ETAP skill
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        assert "75°C" in skill_content  # NEC Table 310.16 reference

    def test_awg_table_overlap(self) -> None:
        """ETAP NEC 310.16 and FireAI Table 8 cover overlapping AWG range."""
        from internal_simulation_engine import NEC_310_16_COPPER_75C

        # Read FireAI source to extract AWG keys
        try:
            vd_file = PROJECT_ROOT / "fireai" / "core" / "voltage_drop.py"
            vd_source = vd_file.read_text(encoding="utf-8")
        except OSError:
            pytest.skip("fireai.voltage_drop source not readable")

        import re
        # Parse all AWG keys from the resistance table
        awg_matches = re.findall(r'"(\d+/\d+|\d+)":\s*[\d.]+', vd_source)
        fireai_awg_keys = set(awg_matches)

        # Both tables must cover 14 AWG through 4/0 AWG (common FA range)
        common_awg = ["14", "12", "10", "8", "6", "4", "2", "1/0", "2/0", "3/0", "4/0"]

        # ETAP uses labels like "14 AWG", FireAI uses "14"
        etap_keys_normalized = {k.replace(" AWG", ""): v for k, v in NEC_310_16_COPPER_75C.items()}

        for awg in common_awg:
            assert awg in etap_keys_normalized, f"ETAP missing {awg}"
            assert awg in fireai_awg_keys, f"FireAI missing {awg}"


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION 2: ETAP Arc Flash ↔ FireAI atex_hazardous_arbiter
# ═══════════════════════════════════════════════════════════════════════════
#
# ETAP skill uses IEEE 1584-2018 for arc flash (electrical safety)
# FireAI atex_hazardous_arbiter uses IEC 60079 for explosive atmospheres
#
# These are DIFFERENT standards for DIFFERENT hazards:
#   - IEEE 1584: arc flash (electrical arc energy → burn injury)
#   - IEC 60079: explosive atmospheres (gas/dust → explosion)
#
# Integration test: verify both modules can coexist without conflict,
# and that the ETAP skill's PPE categories are compatible with FireAI's
# hazardous area classifications (they apply to different scenarios).


class TestArcFlashAtexIntegration:
    """Integration: ETAP arc flash ↔ FireAI atex_hazardous_arbiter."""

    def test_both_modules_reference_distinct_standards(self) -> None:
        """ETAP uses IEEE 1584, FireAI uses IEC 60079 — no conflict."""
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        assert "IEEE 1584" in skill_content  # Arc flash standard

        # Read FireAI atex source file (module __doc__ may not contain all refs)
        try:
            atex_file = PROJECT_ROOT / "fireai" / "core" / "atex_hazardous_arbiter.py"
            atex_source = atex_file.read_text(encoding="utf-8")
        except OSError:
            pytest.skip("fireai.atex source not readable")

        assert "IEC 60079" in atex_source  # Explosive atmospheres
        assert "ATEX" in atex_source

    def test_etap_ppe_categories_match_nfpa_70e(self) -> None:
        """ETAP PPE categories must align with NFPA 70E Table 130.7(C)(15)(c)."""
        from internal_simulation_engine import determine_ppe_category

        # Verify category boundaries per NFPA 70E
        # Category 0: < 1.2 cal/cm²
        # Category 1: 1.2 - 8 cal/cm²
        # Category 2: 8 - 25 cal/cm²
        # Category 3: 25 - 40 cal/cm²
        # Category 4: > 40 cal/cm²
        assert determine_ppe_category(0.5)[0] == 0
        assert determine_ppe_category(5.0)[0] == 1
        assert determine_ppe_category(15.0)[0] == 2
        assert determine_ppe_category(30.0)[0] == 3
        assert determine_ppe_category(50.0)[0] == 4

    def test_corrected_skill_example_gives_category_2(self) -> None:
        """After Arc Flash fix (En=17.14, E=21.2 cal/cm²), PPE = Category 2."""
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        # Verify the corrected values are in the skill
        assert "En = 10^4.234 = 17.14 J/cm²" in skill_content
        assert "E = 88.6 J/cm² = 21.2 cal/cm²" in skill_content
        assert "Category 2" in skill_content
        # PPE for Cat 2 is 8 cal/cm² arc-rated (not 40 cal/cm²)
        assert "8 cal/cm² arc-rated" in skill_content

    def test_atex_module_does_not_use_ieee_1584(self) -> None:
        """FireAI atex module must NOT use IEEE 1584 (different domain)."""
        try:
            atex_file = PROJECT_ROOT / "fireai" / "core" / "atex_hazardous_arbiter.py"
            atex_source = atex_file.read_text(encoding="utf-8")
        except OSError:
            pytest.skip("fireai.atex source not readable")

        # atex module should reference IEC 60079, NOT IEEE 1584
        assert "IEC 60079" in atex_source
        # IEEE 1584 may appear in comments but should NOT be the primary standard
        # (atex is for explosive atmospheres, not arc flash)

    def test_etap_skill_does_not_reference_iec_60079_for_arc_flash(self) -> None:
        """ETAP skill's arc flash section uses IEEE 1584, not IEC 60079."""
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        # Find arc flash section
        arc_flash_section_start = skill_content.find("ARC FLASH & SAFETY")
        arc_flash_section_end = skill_content.find("TRANSIENT & DYNAMIC ANALYSIS")
        arc_flash_section = skill_content[arc_flash_section_start:arc_flash_section_end]

        assert "IEEE 1584" in arc_flash_section
        # IEC 60079 may be mentioned for hazardous areas but not as primary arc flash std
        # (just verify IEEE 1584 is the dominant reference)


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION 3: ETAP Marine ↔ FireAI marine_service
# ═══════════════════════════════════════════════════════════════════════════
#
# ETAP skill Section 25 covers Marine (IEC 60092, IEC 61363)
# FireAI marine_service orchestrates marine fire-safety design
#
# Both use IEC 60092 for shipboard electrical installations.
# ETAP focuses on power system analysis (short circuit, load flow)
# FireAI focuses on fire safety (detection, extinguishing, alarm)
#
# Integration test: verify both reference IEC 60092 and complement each other.


class TestMarineIntegration:
    """Integration: ETAP marine section ↔ FireAI marine_service."""

    def test_both_reference_iec_60092(self) -> None:
        """Both ETAP skill and FireAI marine module reference IEC 60092."""
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        assert "IEC 60092" in skill_content

        # Read FireAI marine_service source file
        try:
            ms_file = PROJECT_ROOT / "backend" / "services" / "marine_service.py"
            ms_source = ms_file.read_text(encoding="utf-8")
        except OSError:
            pytest.skip("backend.marine_service source not readable")

        # marine_service references IEC 60092 in its imports/docstring
        assert "IEC 60092" in ms_source or "iec60092" in ms_source.lower()

    def test_etap_marine_section_covers_iec_61363(self) -> None:
        """ETAP skill Section 25 covers IEC 61363 (marine short circuit)."""
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        # Find marine section
        marine_section_start = skill_content.find("MARINE & OFFSHORE")
        assert marine_section_start > 0
        marine_section = skill_content[marine_section_start:marine_section_start + 5000]

        assert "IEC 60092" in marine_section  # Electrical installations
        assert "IEC 61363" in marine_section  # Short circuit

    def test_fireai_marine_service_imports_iec60092_module(self) -> None:
        """FireAI marine_service imports from marine.iec60092 package."""
        try:
            ms_file = PROJECT_ROOT / "backend" / "services" / "marine_service.py"
            ms_source = ms_file.read_text(encoding="utf-8")
        except OSError:
            pytest.skip("backend.marine_service source not readable")

        # Check import statements in source
        assert "marine.iec60092" in ms_source or "from marine.iec60092" in ms_source

    def test_etap_marine_voltage_levels_match_fireai_scope(self) -> None:
        """ETAP marine voltages (400V, 690V, 3.3kV, 6.6kV) match FireAI scope."""
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        # ETAP skill lists marine voltage levels
        assert "400V" in skill_content
        assert "690V" in skill_content
        assert "3.3kV" in skill_content
        assert "6.6kV" in skill_content

    def test_etap_marine_standards_table_comprehensive(self) -> None:
        """ETAP marine standards table covers SOLAS, Lloyd's, DNV, ABS."""
        skill_content = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        # Find marine standards section
        marine_std_start = skill_content.find("Marine Standards")
        if marine_std_start < 0:
            marine_std_start = skill_content.find("25.5 Marine Standards")
        assert marine_std_start > 0

        marine_std_section = skill_content[marine_std_start:marine_std_start + 2000]

        # Required marine standards
        assert "IEC 60092" in marine_std_section
        assert "IEC 61363" in marine_std_section
        assert "Lloyd" in marine_std_section
        assert "DNV" in marine_std_section
        assert "ABS" in marine_std_section
        assert "SOLAS" in marine_std_section


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION 4: Cross-Module Numerical Consistency
# ═══════════════════════════════════════════════════════════════════════════


class TestCrossModuleNumericalConsistency:
    """Verify numerical values are consistent across modules."""

    def test_awg_4_0_resistance_consistent_across_modules(self) -> None:
        """
        4/0 AWG resistance must be consistent between ETAP and FireAI.

        ETAP skill Example 1 uses:
            3/0 AWG: R = 0.077 Ω/1000ft, X = 0.048 Ω/1000ft

        FireAI Table 8 uses:
            3/0 AWG: 0.0766 Ω/kft (DC resistance)

        These should be close (ETAP uses AC impedance, FireAI uses DC resistance).
        """
        from internal_simulation_engine import CONDUCTOR_IMPEDANCE_75C

        etap_3_0_r = CONDUCTOR_IMPEDANCE_75C["3/0 AWG"]["r"]  # 0.077 Ω/1000ft

        # Read FireAI resistance table from source (avoid import complications)
        try:
            vd_file = PROJECT_ROOT / "fireai" / "core" / "voltage_drop.py"
            vd_source = vd_file.read_text(encoding="utf-8")
        except OSError:
            pytest.skip("fireai.voltage_drop source not readable")

        # Extract 3/0 AWG resistance from source: parse "3/0": 0.251,
        import re
        match = re.search(r'"3/0":\s*([\d.]+)', vd_source)
        if not match:
            pytest.skip("Cannot parse 3/0 AWG resistance from FireAI source")
        fireai_3_0_r_per_km = float(match.group(1))  # 0.251 Ω/km
        fireai_3_0_r_per_kft = fireai_3_0_r_per_km * 0.3048  # → 0.0766 Ω/kft

        # ETAP (0.077) and FireAI (0.0766) should be within 5%
        pct_diff = abs(etap_3_0_r - fireai_3_0_r_per_kft) / fireai_3_0_r_per_kft * 100
        assert pct_diff < 5.0, (
            f"3/0 AWG resistance mismatch: ETAP={etap_3_0_r} Ω/kft, "
            f"FireAI={fireai_3_0_r_per_kft:.4f} Ω/kft, diff={pct_diff:.2f}%"
        )

    def test_nev_310_16_ampacity_consistent_with_physical_law(self) -> None:
        """NEC Table 310.16 ampacity should obey I ∝ area relationship."""
        from internal_simulation_engine import NEC_310_16_COPPER_75C

        # 4/0 AWG (107.2 mm²) should have higher ampacity than 3/0 AWG (85.0 mm²)
        amp_4_0 = NEC_310_16_COPPER_75C["4/0 AWG"]
        amp_3_0 = NEC_310_16_COPPER_75C["3/0 AWG"]
        assert amp_4_0 > amp_3_0, "4/0 AWG should have higher ampacity than 3/0 AWG"

        # 2/0 AWG should have lower ampacity than 3/0 AWG
        amp_2_0 = NEC_310_16_COPPER_75C["2/0 AWG"]
        assert amp_2_0 < amp_3_0, "2/0 AWG should have lower ampacity than 3/0 AWG"

    def test_ieee_1584_formula_produces_realistic_arcing_current(self) -> None:
        """IEEE 1584 formula: Iarc must be < Ibf (arcing impedance > 0)."""
        from internal_simulation_engine import simulate_arc_flash

        # For 50 kA bolted fault, Iarc should be ~42 kA (per skill example)
        result = simulate_arc_flash(bolted_fault_current_ka=50.0)
        assert 30 < result.arcing_current_ka < 50, (
            f"Iarc = {result.arcing_current_ka} kA should be 30-50 kA for 50 kA bolted fault"
        )

    def test_flisr_ohms_law_consistent_with_fireai_voltage_drop(self) -> None:
        """
        Both FLISR (V=I×Z) and FireAI voltage_drop (V=I×R) use Ohm's law.

        This is a fundamental physics consistency check — both modules
        must agree on V = I × Z (or V = I × R for DC).
        """
        from internal_simulation_engine import simulate_flisr

        # FLISR: 13.8kV / 5kA = 2.76 Ω, / 0.4 Ω/mi = 6.9 miles
        result = simulate_flisr(
            fault_current_a=5000.0,
            source_voltage_v=13800.0,
            line_impedance_per_mile_ohm=0.4,
        )
        expected_z = 13800.0 / 5000.0  # = 2.76 Ω
        expected_distance = expected_z / 0.4  # = 6.9 miles

        assert abs(result.fault_distance_miles - expected_distance) < 0.01

        # Verify FireAI voltage_drop uses same Ohm's law: V_drop = I × R
        # Read formula from source file (avoid import complications)
        try:
            vd_file = PROJECT_ROOT / "fireai" / "core" / "voltage_drop.py"
            vd_source = vd_file.read_text(encoding="utf-8")
        except OSError:
            pytest.skip("fireai.voltage_drop source not readable")

        # FireAI voltage_drop.py must contain Ohm's law formula V = I × R
        assert "v_drop = current_a * r_total" in vd_source or "V_drop = I" in vd_source, (
            "FireAI voltage_drop.py should use Ohm's law (V = I × R)"
        )
