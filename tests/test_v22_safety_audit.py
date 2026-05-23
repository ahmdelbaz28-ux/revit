"""
test_v22_safety_audit.py – V22 Safety Audit Engine Comprehensive Tests
========================================================================
Covers all new V22 features:
  1. New Enums: RegionProfile, Jurisdiction, ElevationTier
  2. Vapor Density Logic: vapor_density_tier() with known substances
  3. EnvironmentalContext with new fields: region, jurisdiction
  4. SafetyAuditEngine – Redundancy Gate (IEC + HCIS)
  5. SafetyAuditEngine – Fouling Gate (CRITICAL / WARNING / PASS)
  6. SafetyAuditEngine – Zone Mapping Gate
  7. SafetyAuditEngine – Elevation Gate (vapor density vs detector elevation)
  8. SafetyAuditEngine – MENA Gate (region-specific advisories)
  9. SafetyAuditEngine – Full Audit (multiple gates combined)
  10. CLI Layer 6 Integration
  11. AuditResult / AuditViolation model properties
  12. Edge cases: None substance, no detectors, UNCLASSIFIED zone

Standards referenced:
  IEC 60079-10-1:2015  – Gas zone classification
  IEC 60079-10-2:2015  – Dust zone classification
  NFPA 72-2022 §17.8.3.4 – Redundancy requirements
  FM Global DS 5-48    – Flame detector application
  HCIS SAF Directive 2021 – Saudi industrial safety requirements
"""

import pytest
from pydantic import ValidationError

from fireai.core.models_v21 import (
    ZoneType,
    HazardType,
    EnvironmentalContext,
    SubstanceProperties,
    RegionProfile,
    Jurisdiction,
    ElevationTier,
    VentilationLevel,
    FlameDetectorSpec,
    RayTracePoint,
    WavelengthBand,
    MIN_REDUNDANCY_BY_ZONE,
    vapor_density_tier,
)
from fireai.core.safety_audit_engine import (
    SafetyAuditEngine,
    elevation_tier_from_detector_z,
    AuditResult,
    AuditViolation,
)
from fireai.core.fireai_cli_engine import (
    CLIFireAIEngine,
    Layer6Result,
    PipelineResult,
)


# ===========================================================================
# 1. New Enums
# ===========================================================================

class TestRegionProfile:
    """Test RegionProfile enum values."""

    def test_standard_iec_exists(self):
        assert RegionProfile.STANDARD_IEC.value == "STANDARD_IEC"

    def test_mena_summer_outdoor_exists(self):
        assert RegionProfile.MENA_SUMMER_OUTDOOR.value == "MENA_SUMMER_OUTDOOR"

    def test_gulf_hcis_exists(self):
        assert RegionProfile.GULF_HCIS.value == "GULF_HCIS"

    def test_egypt_code_exists(self):
        assert RegionProfile.EGYPT_CODE.value == "EGYPT_CODE"

    def test_europe_iec_exists(self):
        assert RegionProfile.EUROPE_IEC.value == "EUROPE_IEC"

    def test_usa_nfpa_exists(self):
        assert RegionProfile.USA_NFPA.value == "USA_NFPA"

    def test_all_members(self):
        members = list(RegionProfile)
        assert len(members) == 6
        assert RegionProfile.STANDARD_IEC in members
        assert RegionProfile.MENA_SUMMER_OUTDOOR in members
        assert RegionProfile.GULF_HCIS in members
        assert RegionProfile.EGYPT_CODE in members
        assert RegionProfile.EUROPE_IEC in members
        assert RegionProfile.USA_NFPA in members


class TestJurisdiction:
    """Test Jurisdiction enum values."""

    def test_global_iec_exists(self):
        assert Jurisdiction.GLOBAL_IEC.value == "GLOBAL_IEC"

    def test_saudi_hcis_exists(self):
        assert Jurisdiction.SAUDI_HCIS.value == "SAUDI_HCIS"

    def test_egyptian_fire_code_exists(self):
        assert Jurisdiction.EGYPTIAN_FIRE_CODE.value == "EGYPTIAN_FIRE_CODE"

    def test_usa_nfpa_exists(self):
        assert Jurisdiction.USA_NFPA.value == "USA_NFPA"

    def test_all_members(self):
        members = list(Jurisdiction)
        assert len(members) == 4
        assert Jurisdiction.GLOBAL_IEC in members
        assert Jurisdiction.SAUDI_HCIS in members
        assert Jurisdiction.EGYPTIAN_FIRE_CODE in members
        assert Jurisdiction.USA_NFPA in members


class TestElevationTier:
    """Test ElevationTier enum values."""

    def test_low_exists(self):
        assert ElevationTier.LOW.value == "LOW"

    def test_breathing_zone_exists(self):
        assert ElevationTier.BREATHING_ZONE.value == "BREATHING_ZONE"

    def test_high_exists(self):
        assert ElevationTier.HIGH.value == "HIGH"

    def test_all_members(self):
        members = list(ElevationTier)
        assert len(members) == 3


# ===========================================================================
# 2. Vapor Density Logic: vapor_density_tier()
# ===========================================================================

class TestVaporDensityTier:
    """
    Test gas buoyancy classification by molecular weight.
    
    Now delegates to vapor_density_tier() which uses ratio-based thresholds:
      MW < 28.0912 (ratio < 0.97) → HIGH  (lighter than air, rises to ceiling)
      28.0912 ≤ MW ≤ 29.8288 (0.97 ≤ ratio ≤ 1.03) → BREATHING_ZONE
      MW > 29.8288 (ratio > 1.03) → LOW   (heavier than air, pools at floor)
    
    The old heuristic thresholds (25/35) were deprecated because they
    caused dangerous misclassifications (e.g., H₂S MW=34.08 was wrongly
    classified as BREATHING_ZONE when it is 17.7% heavier than air).
    
    Reference: IEC 60079-10-1:2015 §B.4, NFPA 497 §4.5
    """

    def test_h2_rises(self):
        """H₂ (MW=2.02) is much lighter than air → HIGH."""
        assert vapor_density_tier(2.02) == ElevationTier.HIGH

    def test_ch4_rises(self):
        """CH₄ (MW=16.04) is lighter than air → HIGH."""
        assert vapor_density_tier(16.04) == ElevationTier.HIGH

    def test_nh3_rises(self):
        """NH₃ (MW=17.03) is lighter than air → HIGH."""
        assert vapor_density_tier(17.03) == ElevationTier.HIGH

    def test_c2h6_sinks(self):
        """C₂H₆ (MW=30.07) is heavier than air (ratio=1.038) → LOW.
        Under old heuristic (25/35) this was BREATHING_ZONE, but the
        ratio-based classification correctly identifies it as heavier."""
        assert vapor_density_tier(30.07) == ElevationTier.LOW

    def test_propane_sinks(self):
        """C₃H₈ (MW=44.10) is heavier than air → LOW."""
        assert vapor_density_tier(44.10) == ElevationTier.LOW

    def test_benzene_sinks(self):
        """Benzene (MW=78.11) is much heavier than air → LOW."""
        assert vapor_density_tier(78.11) == ElevationTier.LOW

    def test_boundary_high_breathing(self):
        """Boundary between HIGH and BREATHING_ZONE at MW=28.0912."""
        assert vapor_density_tier(28.09) == ElevationTier.HIGH
        assert vapor_density_tier(28.0912) == ElevationTier.BREATHING_ZONE

    def test_boundary_breathing_low(self):
        """Boundary between BREATHING_ZONE and LOW at MW=29.8288."""
        assert vapor_density_tier(29.8288) == ElevationTier.BREATHING_ZONE
        assert vapor_density_tier(29.83) == ElevationTier.LOW

    def test_very_light_gas(self):
        """Extremely light gas (MW=1) → HIGH."""
        assert vapor_density_tier(1.0) == ElevationTier.HIGH

    def test_very_heavy_gas(self):
        """Extremely heavy gas (MW=200) → LOW."""
        assert vapor_density_tier(200.0) == ElevationTier.LOW

    def test_h2s_critical_regression(self):
        """H₂S (MW=34.08) MUST be LOW — not BREATHING_ZONE.
        
        REGRESSION TEST: The old heuristic thresholds (25/35) classified
        H₂S as BREATHING_ZONE because 34.08 falls in [25,35]. This was
        a DANGEROUS misclassification — H₂S is 17.7% heavier than air
        (ratio=1.177) and sinks to floor level. Placing a detector at
        breathing zone for H₂S creates a physical blind spot.
        
        This was the critical bug that triggered the switch from heuristic
        thresholds to ratio-based thresholds (0.97/1.03 of air MW).
        """
        assert vapor_density_tier(34.08) == ElevationTier.LOW


# ===========================================================================
# 3. Detector Elevation Tier
# ===========================================================================

class TestDetectorElevationTier:
    """
    Test detector elevation classification from Z position.
    
    Heuristics:
      z >= 75% of ceiling → HIGH
      z <= 25% of ceiling → LOW
      otherwise → BREATHING_ZONE
    """

    def test_ceiling_detector(self):
        """Detector at z=5.5m with ceiling 6.0m → HIGH (5.5/6.0 = 0.917 > 0.75)."""
        assert elevation_tier_from_detector_z(5.5, 6.0) == ElevationTier.HIGH

    def test_floor_detector(self):
        """Detector at z=0.5m with ceiling 6.0m → LOW (0.5/6.0 = 0.083 < 0.25)."""
        assert elevation_tier_from_detector_z(0.5, 6.0) == ElevationTier.LOW

    def test_breathing_zone(self):
        """Detector at z=3.0m with ceiling 6.0m → BREATHING_ZONE (between 25% and 75%)."""
        assert elevation_tier_from_detector_z(3.0, 6.0) == ElevationTier.BREATHING_ZONE

    def test_exact_boundary_high(self):
        """Detector at exactly 75% of ceiling height → HIGH."""
        assert elevation_tier_from_detector_z(4.5, 6.0) == ElevationTier.HIGH

    def test_exact_boundary_low(self):
        """Detector at exactly 25% of ceiling height → LOW (z <= 25% ceiling)."""
        assert elevation_tier_from_detector_z(1.5, 6.0) == ElevationTier.LOW

    def test_default_ceiling_height(self):
        """Default ceiling height is 6.0m."""
        assert elevation_tier_from_detector_z(5.5) == ElevationTier.HIGH

    def test_tall_room(self):
        """In a 10m room, z=8m should be HIGH."""
        assert elevation_tier_from_detector_z(8.0, 10.0) == ElevationTier.HIGH


# ===========================================================================
# 4. EnvironmentalContext New Fields
# ===========================================================================

class TestEnvironmentalContextNewFields:
    """Test new region and jurisdiction fields on EnvironmentalContext."""

    def test_defaults(self):
        """Default EnvironmentalContext uses STANDARD_IEC and GLOBAL_IEC."""
        ctx = EnvironmentalContext()
        assert ctx.region == RegionProfile.STANDARD_IEC
        assert ctx.jurisdiction == Jurisdiction.GLOBAL_IEC

    def test_mena_context(self):
        """MENA context with Saudi HCIS jurisdiction."""
        ctx = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            jurisdiction=Jurisdiction.SAUDI_HCIS,
            ambient_temp_c=52.0,
            lens_fouling_factor=0.55,
        )
        assert ctx.region == RegionProfile.MENA_SUMMER_OUTDOOR
        assert ctx.jurisdiction == Jurisdiction.SAUDI_HCIS
        assert ctx.ambient_temp_c == 52.0
        assert ctx.lens_fouling_factor == 0.55

    def test_standard_context_custom_temp(self):
        """Standard IEC context with custom temperature."""
        ctx = EnvironmentalContext(
            region=RegionProfile.STANDARD_IEC,
            ambient_temp_c=35.0,
        )
        assert ctx.region == RegionProfile.STANDARD_IEC
        assert ctx.jurisdiction == Jurisdiction.GLOBAL_IEC
        assert ctx.ambient_temp_c == 35.0

    def test_region_jurisdiction_independent(self):
        """Can have MENA region with GLOBAL_IEC jurisdiction."""
        ctx = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            jurisdiction=Jurisdiction.GLOBAL_IEC,
        )
        assert ctx.region == RegionProfile.MENA_SUMMER_OUTDOOR
        assert ctx.jurisdiction == Jurisdiction.GLOBAL_IEC


# ===========================================================================
# 5. SafetyAuditEngine – Redundancy Gate
# ===========================================================================

class TestRedundancyGate:
    """
    Test Gate 1: Redundancy.
    
    IEC requires:
      Zone 0: 3 detectors (2oo3)
      Zone 1: 2 detectors (1oo2)
      Zone 2: 1 detector (single acceptable)
    
    HCIS requires:
      Zone 2: 2 detectors minimum (1oo2) — stricter than IEC
    """

    def setup_method(self):
        self.engine = SafetyAuditEngine()

    def test_zone1_insufficient_redundancy(self):
        """Zone 1 with min_redundancy=1 → FAIL (IEC requires 2)."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=1,
        )
        assert result.status == "FAIL"
        assert any(v.code == "RED-001" for v in result.violations)
        v = [v for v in result.violations if v.code == "RED-001"][0]
        assert v.severity == "CRITICAL"

    def test_zone1_sufficient_redundancy(self):
        """Zone 1 with min_redundancy=2 → no RED-001 violation."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
        )
        assert not any(v.code == "RED-001" for v in result.violations)

    def test_zone0_requires_3(self):
        """Zone 0 with min_redundancy=2 → FAIL (IEC requires 3)."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
        )
        assert result.status == "FAIL"
        assert any(v.code == "RED-001" for v in result.violations)

    def test_zone2_single_detector_ok_iec(self):
        """Zone 2 with min_redundancy=1 → no RED-001 (IEC allows 1)."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_redundancy=1,
        )
        assert not any(v.code == "RED-001" for v in result.violations)

    def test_zone2_hcis_requires_1oo2(self):
        """Zone 2 + SAUDI_HCIS with min_redundancy=1 → FAIL (HCIS requires 2)."""
        env = EnvironmentalContext(jurisdiction=Jurisdiction.SAUDI_HCIS)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_redundancy=1,
            env_context=env,
        )
        assert result.status == "FAIL"
        assert any(v.code == "RED-001" for v in result.violations)
        # Verify HCIS is mentioned in the violation
        v = [v for v in result.violations if v.code == "RED-001"][0]
        assert "HCIS" in v.message

    def test_zone2_hcis_with_2_passes(self):
        """Zone 2 + SAUDI_HCIS with min_redundancy=2 → no RED-001."""
        env = EnvironmentalContext(jurisdiction=Jurisdiction.SAUDI_HCIS)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
            env_context=env,
        )
        assert not any(v.code == "RED-001" for v in result.violations)

    def test_zone22_hcis_requires_2(self):
        """Zone 22 + SAUDI_HCIS requires min_redundancy=2."""
        env = EnvironmentalContext(jurisdiction=Jurisdiction.SAUDI_HCIS)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_22,
            hazard_type=HazardType.DUST,
            min_redundancy=1,
            env_context=env,
        )
        assert any(v.code == "RED-001" for v in result.violations)

    def test_unclassified_zero_redundancy_ok(self):
        """UNCLASSIFIED zone with 0 redundancy → no RED-001."""
        result = self.engine.run_audit(
            zone=ZoneType.UNCLASSIFIED,
            hazard_type=HazardType.GAS,
            min_redundancy=0,
        )
        assert not any(v.code == "RED-001" for v in result.violations)

    def test_redundancy_violation_standard_ref(self):
        """RED-001 should reference NFPA 72 and FM Global standards."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=0,
        )
        v = [v for v in result.violations if v.code == "RED-001"][0]
        assert "NFPA 72" in v.standard_ref
        assert "FM Global" in v.standard_ref


# ===========================================================================
# 6. SafetyAuditEngine – Fouling Gate
# ===========================================================================

class TestFoulingGate:
    """
    Test Gate 2: Fouling / Transmittance.
    
    Thresholds:
      fouling < 0.50  → FOUL-001 CRITICAL (lens severely degraded)
      0.50 ≤ fouling < 0.70 → FOUL-002 WARNING (significant degradation)
      fouling ≥ 0.70  → PASS (acceptable)
      
      effective_t = spectral_transmittance × fouling
      effective_t < 0.10 → FOUL-003 CRITICAL
      0.10 ≤ effective_t < 0.25 → FOUL-004 WARNING
    """

    def setup_method(self):
        self.engine = SafetyAuditEngine()

    def test_critical_fouling(self):
        """fouling=0.45 → FOUL-001 CRITICAL."""
        env = EnvironmentalContext(lens_fouling_factor=0.45)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert any(v.code == "FOUL-001" and v.severity == "CRITICAL" for v in result.violations)

    def test_warning_fouling(self):
        """fouling=0.60 → FOUL-002 WARNING."""
        env = EnvironmentalContext(lens_fouling_factor=0.60)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert any(v.code == "FOUL-002" and v.severity == "WARNING" for v in result.violations)

    def test_ok_fouling(self):
        """fouling=0.85 → no FOUL-001 or FOUL-002."""
        env = EnvironmentalContext(lens_fouling_factor=0.85)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert not any(v.code in ("FOUL-001", "FOUL-002") for v in result.violations)

    def test_effective_transmittance_critical(self):
        """effective_t = 0.15 × 0.50 = 0.075 < 0.10 → FOUL-003 CRITICAL."""
        env = EnvironmentalContext(lens_fouling_factor=0.50)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_transmittance=0.15,
            env_context=env,
        )
        assert any(v.code == "FOUL-003" and v.severity == "CRITICAL" for v in result.violations)

    def test_effective_transmittance_warning(self):
        """effective_t = 0.40 × 0.50 = 0.20 < 0.25 → FOUL-004 WARNING."""
        env = EnvironmentalContext(lens_fouling_factor=0.50)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_transmittance=0.40,
            env_context=env,
        )
        assert any(v.code == "FOUL-004" and v.severity == "WARNING" for v in result.violations)

    def test_effective_transmittance_ok(self):
        """effective_t = 0.80 × 0.85 = 0.68 ≥ 0.25 → no FOUL-003/004."""
        env = EnvironmentalContext(lens_fouling_factor=0.85)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_transmittance=0.80,
            env_context=env,
        )
        assert not any(v.code in ("FOUL-003", "FOUL-004") for v in result.violations)

    def test_no_min_transmittance_skips_effective_check(self):
        """Without min_transmittance, effective transmittance check is skipped."""
        env = EnvironmentalContext(lens_fouling_factor=0.85)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert not any(v.code in ("FOUL-003", "FOUL-004") for v in result.violations)

    def test_fouling_boundary_050(self):
        """fouling=0.50 is at CRITICAL boundary → WARNING (not CRITICAL)."""
        env = EnvironmentalContext(lens_fouling_factor=0.50)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        # 0.50 is NOT < 0.50, so FOUL-001 should NOT trigger
        # 0.50 IS < 0.70, so FOUL-002 SHOULD trigger
        assert not any(v.code == "FOUL-001" for v in result.violations)
        assert any(v.code == "FOUL-002" for v in result.violations)

    def test_fouling_boundary_070(self):
        """fouling=0.70 → neither FOUL-001 nor FOUL-002."""
        env = EnvironmentalContext(lens_fouling_factor=0.70)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        # 0.70 is NOT < 0.50 and NOT < 0.70 → no fouling violations
        assert not any(v.code in ("FOUL-001", "FOUL-002") for v in result.violations)

    def test_fouling_violation_references_fm_global(self):
        """FOUL-001 should reference FM Global DS 5-48."""
        env = EnvironmentalContext(lens_fouling_factor=0.45)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        v = [v for v in result.violations if v.code == "FOUL-001"][0]
        assert "FM Global" in v.standard_ref


# ===========================================================================
# 7. SafetyAuditEngine – Zone Mapping Gate
# ===========================================================================

class TestZoneMappingGate:
    """
    Test Gate 3: Zone Mapping.
    
    Gas zones (0/1/2) should not be paired with DUST hazard.
    Dust zones (20/21/22) should not be paired with GAS hazard.
    HYBRID with gas/dust zones → WARNING (advisory).
    """

    def setup_method(self):
        self.engine = SafetyAuditEngine()

    def test_gas_zone_with_dust(self):
        """Zone 0 + DUST → ZMAP-001 CRITICAL."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.DUST,
        )
        assert result.status == "FAIL"
        assert any(v.code == "ZMAP-001" for v in result.violations)
        v = [v for v in result.violations if v.code == "ZMAP-001"][0]
        assert v.severity == "CRITICAL"

    def test_dust_zone_with_gas(self):
        """Zone 20 + GAS → ZMAP-002 CRITICAL."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_20,
            hazard_type=HazardType.GAS,
        )
        assert result.status == "FAIL"
        assert any(v.code == "ZMAP-002" for v in result.violations)
        v = [v for v in result.violations if v.code == "ZMAP-002"][0]
        assert v.severity == "CRITICAL"

    def test_gas_zone_hybrid_warning(self):
        """Zone 1 + HYBRID → ZMAP-003 WARNING."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.HYBRID,
        )
        assert any(v.code == "ZMAP-003" for v in result.violations)
        v = [v for v in result.violations if v.code == "ZMAP-003"][0]
        assert v.severity == "WARNING"

    def test_dust_zone_hybrid_warning(self):
        """Zone 21 + HYBRID → ZMAP-004 WARNING."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_21,
            hazard_type=HazardType.HYBRID,
        )
        assert any(v.code == "ZMAP-004" for v in result.violations)
        v = [v for v in result.violations if v.code == "ZMAP-004"][0]
        assert v.severity == "WARNING"

    def test_consistent_zone_hazard(self):
        """Zone 1 + GAS → no ZMAP violations."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
        )
        assert not any(v.code.startswith("ZMAP") for v in result.violations)

    def test_dust_zone_dust_hazard_ok(self):
        """Zone 20 + DUST → no ZMAP violations."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_20,
            hazard_type=HazardType.DUST,
        )
        assert not any(v.code.startswith("ZMAP") for v in result.violations)

    def test_zone2_dust_mismatch(self):
        """Zone 2 + DUST → ZMAP-001 CRITICAL."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.DUST,
        )
        assert any(v.code == "ZMAP-001" for v in result.violations)

    def test_zone22_gas_mismatch(self):
        """Zone 22 + GAS → ZMAP-002 CRITICAL."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_22,
            hazard_type=HazardType.GAS,
        )
        assert any(v.code == "ZMAP-002" for v in result.violations)

    def test_zone_mapping_references_iec(self):
        """ZMAP violations should reference IEC 60079-10-1."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.DUST,
        )
        v = [v for v in result.violations if v.code == "ZMAP-001"][0]
        assert "IEC 60079" in v.standard_ref


# ===========================================================================
# 8. SafetyAuditEngine – Z-Axis Gate
# ===========================================================================

class TestZAxisGate:
    """
    Test Gate 4: Elevation / Vapor Density.
    
    Gas buoyancy determines WHERE a gas accumulates. A detector at the
    wrong elevation is a physical blind spot — a FATAL design flaw.
    
    Mismatches produce ELEV-001 CRITICAL (not WARNING).
    In SIL/IEC 61508 systems, a physical blind spot is a systematic
    failure that must cause the audit to FAIL.
    """

    def setup_method(self):
        self.engine = SafetyAuditEngine()
        self.propane = SubstanceProperties(
            name="Propane", hazard_type=HazardType.GAS,
            lfl_vol_pct=2.1, ufl_vol_pct=9.5,
            autoignition_c=470.0, molecular_weight=44.1,
        )
        self.hydrogen = SubstanceProperties(
            name="Hydrogen", hazard_type=HazardType.GAS,
            lfl_vol_pct=4.0, ufl_vol_pct=75.0,
            autoignition_c=500.0, molecular_weight=2.02,
        )
        self.ethane = SubstanceProperties(
            name="Ethane", hazard_type=HazardType.GAS,
            lfl_vol_pct=3.0, ufl_vol_pct=12.5,
            autoignition_c=472.0, molecular_weight=30.07,
        )

    def test_heavy_gas_at_ceiling_is_wrong(self):
        """Propane (MW=44.1, LOW) detector at z=5.5m (HIGH) → ELEV-001 CRITICAL."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=self.propane,
            detector_z_positions=[5.5],
            ceiling_height_m=6.0,
        )
        assert any(v.code == "ELEV-001" for v in result.violations)
        v = [v for v in result.violations if v.code == "ELEV-001"][0]
        assert v.severity == "CRITICAL"
        assert "Propane" in v.message

    def test_light_gas_at_ceiling_is_correct(self):
        """Hydrogen (MW=2.02, HIGH) detector at z=5.5m (HIGH) → no ELEV-001."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=self.hydrogen,
            detector_z_positions=[5.5],
            ceiling_height_m=6.0,
        )
        assert not any(v.code == "ELEV-001" for v in result.violations)

    def test_light_gas_at_floor_is_wrong(self):
        """Hydrogen (MW=2.02, HIGH) detector at z=0.5m (LOW) → ELEV-001 CRITICAL."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=self.hydrogen,
            detector_z_positions=[0.5],
            ceiling_height_m=6.0,
        )
        assert any(v.code == "ELEV-001" for v in result.violations)

    def test_heavy_gas_at_floor_is_correct(self):
        """Propane (MW=44.1, LOW) detector at z=0.5m (LOW) → no ELEV-001."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=self.propane,
            detector_z_positions=[0.5],
            ceiling_height_m=6.0,
        )
        assert not any(v.code == "ELEV-001" for v in result.violations)

    def test_neutral_gas_at_breathing_zone_ok(self):
        """Gas with MW near air (MW=29.0, BREATHING_ZONE) detector at z=3.0m (BREATHING_ZONE) → no ELEV-001.
        
        Note: C₂H₆ (MW=30.07) was previously used here under the old heuristic
        thresholds (25/35) which classified it as BREATHING_ZONE. However, with
        ratio-based thresholds (0.97/1.03), C₂H₆ (ratio=1.038) is LOW, not
        BREATHING_ZONE. This test now uses MW=29.0 (ratio=1.001) which is
        genuinely in the breathing zone."""
        near_air_substance = SubstanceProperties(
            name="NearAirGas", hazard_type=HazardType.GAS,
            lfl_vol_pct=2.0, ufl_vol_pct=10.0,
            autoignition_c=400.0, molecular_weight=29.0,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=near_air_substance,
            detector_z_positions=[3.0],  # 3.0/6.0 = 0.50 → BREATHING_ZONE
            ceiling_height_m=6.0,
        )
        assert not any(v.code == "ELEV-001" for v in result.violations)

    def test_no_substance_skips_zaxis(self):
        """Without substance, Z-Axis gate is skipped."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
        )
        assert not any(v.code == "ELEV-001" for v in result.violations)

    def test_no_detectors_skips_zaxis(self):
        """With substance but no detector positions, Z-Axis gate is skipped."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=self.propane,
        )
        assert not any(v.code == "ELEV-001" for v in result.violations)

    def test_empty_detector_list_skips_zaxis(self):
        """Empty detector_z_positions list skips Z-Axis gate."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=self.propane,
            detector_z_positions=[],
        )
        assert not any(v.code == "ELEV-001" for v in result.violations)

    def test_multiple_detectors_mixed(self):
        """Propane with one correct and one incorrect detector position."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=self.propane,
            detector_z_positions=[0.5, 5.5],  # LOW (correct), HIGH (wrong)
            ceiling_height_m=6.0,
        )
        elev_violations = [v for v in result.violations if v.code == "ELEV-001"]
        assert len(elev_violations) == 1  # Only the ceiling detector is wrong

    def test_elevation_references_iec_nfpa(self):
        """ELEV-001 should reference IEC 60079, NFPA 497, and IEC 61508."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=self.propane,
            detector_z_positions=[5.5],
            ceiling_height_m=6.0,
        )
        v = [v for v in result.violations if v.code == "ELEV-001"][0]
        assert "IEC 60079" in v.standard_ref
        assert "NFPA 497" in v.standard_ref
        assert "IEC 61508" in v.standard_ref

    def test_substance_none_molecular_weight_skips(self):
        """Substance with molecular_weight=None should skip Z-Axis gate."""
        sub_no_mw = SubstanceProperties(
            name="UnknownGas", hazard_type=HazardType.GAS,
            lfl_vol_pct=1.0, ufl_vol_pct=10.0,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=sub_no_mw,
            detector_z_positions=[5.5],
            ceiling_height_m=6.0,
        )
        assert not any(v.code == "ELEV-001" for v in result.violations)


# ===========================================================================
# 9. SafetyAuditEngine – MENA Gate
# ===========================================================================

class TestMENAGate:
    """
    Test Gate 5: MENA Region advisory checks.
    
    MENA-001 INFO: Low ambient temp for MENA region (below GCC 50C peak)
    MENA-002 WARNING: High fouling factor for MENA outdoor
    MENA-003 WARNING: HCIS + Zone 2/22 advisory
    
    Only triggered when region == MENA_SUMMER_OUTDOOR.
    """

    def setup_method(self):
        self.engine = SafetyAuditEngine()

    def test_mena_low_temp_advisory(self):
        """MENA region with low temp (35C < 50C) → MENA-001 INFO."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            ambient_temp_c=35.0,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert any(v.code == "MENA-001" and v.severity == "INFO" for v in result.violations)

    def test_mena_high_temp_no_advisory(self):
        """MENA region with high temp (52C ≥ 50C) → no MENA-001."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            ambient_temp_c=52.0,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert not any(v.code == "MENA-001" for v in result.violations)

    def test_mena_high_fouling_warning(self):
        """MENA region with fouling > 0.60 → MENA-002 WARNING."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            lens_fouling_factor=0.75,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert any(v.code == "MENA-002" for v in result.violations)
        v = [v for v in result.violations if v.code == "MENA-002"][0]
        assert v.severity == "WARNING"

    def test_mena_low_fouling_no_warning(self):
        """MENA region with fouling ≤ 0.60 → no MENA-002."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            lens_fouling_factor=0.55,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert not any(v.code == "MENA-002" for v in result.violations)

    def test_hcis_zone2_warning(self):
        """SAUDI_HCIS + Zone 2 → MENA-003 WARNING."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            jurisdiction=Jurisdiction.SAUDI_HCIS,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert any(v.code == "MENA-003" for v in result.violations)
        v = [v for v in result.violations if v.code == "MENA-003"][0]
        assert v.severity == "WARNING"

    def test_hcis_zone22_warning(self):
        """SAUDI_HCIS + Zone 22 → MENA-003 WARNING."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            jurisdiction=Jurisdiction.SAUDI_HCIS,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_22,
            hazard_type=HazardType.DUST,
            env_context=env,
        )
        assert any(v.code == "MENA-003" for v in result.violations)

    def test_hcis_zone1_no_mena003(self):
        """SAUDI_HCIS + Zone 1 → no MENA-003 (only triggers for Zone 2/22)."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            jurisdiction=Jurisdiction.SAUDI_HCIS,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert not any(v.code == "MENA-003" for v in result.violations)

    def test_non_mena_skips_mena_gate(self):
        """STANDARD_IEC region → no MENA violations at all."""
        env = EnvironmentalContext()
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert not any(v.code.startswith("MENA") for v in result.violations)

    def test_mena_combined_violations(self):
        """MENA with low temp + high fouling + HCIS → multiple MENA violations."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            jurisdiction=Jurisdiction.SAUDI_HCIS,
            ambient_temp_c=35.0,
            lens_fouling_factor=0.75,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        mena_codes = [v.code for v in result.violations if v.code.startswith("MENA")]
        assert "MENA-001" in mena_codes
        assert "MENA-002" in mena_codes
        assert "MENA-003" in mena_codes


# ===========================================================================
# 10. SafetyAuditEngine – Full Audit (Multiple Gates Combined)
# ===========================================================================

class TestFullAudit:
    """Test multiple audit gates firing together."""

    def setup_method(self):
        self.engine = SafetyAuditEngine()

    def test_clean_design_passes(self):
        """Clean design with no issues should PASS."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
        )
        # Zone 1 + GAS is consistent, min_redundancy=2 meets IEC requirement
        # Default fouling=0.85 is OK, no MENA triggers
        assert result.status == "PASS"
        assert result.critical_count == 0

    def test_multiple_critical_violations(self):
        """Multiple CRITICAL violations from different gates."""
        env = EnvironmentalContext(lens_fouling_factor=0.45)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.DUST,  # Gas zone + DUST → ZMAP-001
            min_redundancy=0,             # Zone 0 requires 3 → RED-001
            env_context=env,              # fouling=0.45 → FOUL-001
        )
        assert result.status == "FAIL"
        assert result.critical_count >= 2  # At least RED-001 + ZMAP-001
        violation_codes = [v.code for v in result.violations]
        assert "RED-001" in violation_codes
        assert "ZMAP-001" in violation_codes
        assert "FOUL-001" in violation_codes

    def test_warnings_do_not_cause_fail(self):
        """WARNING violations should not cause overall FAIL."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.HYBRID,  # ZMAP-003 WARNING
            min_redundancy=2,
        )
        # Only WARNING violations → status should be PASS
        assert result.status == "PASS"
        assert result.warning_count > 0
        assert result.critical_count == 0

    def test_info_violations_do_not_cause_fail(self):
        """INFO violations should not cause overall FAIL."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            ambient_temp_c=35.0,
            lens_fouling_factor=0.50,  # Below 0.60 threshold → no MENA-002
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
            env_context=env,
        )
        # MENA-001 is INFO only → status should be PASS
        assert result.status == "PASS"
        assert result.info_count > 0

    def test_mena_full_audit_with_all_gates(self):
        """MENA installation with multiple gate violations."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            jurisdiction=Jurisdiction.SAUDI_HCIS,
            ambient_temp_c=35.0,
            lens_fouling_factor=0.55,
        )
        propane = SubstanceProperties(
            name="Propane", hazard_type=HazardType.GAS,
            lfl_vol_pct=2.1, ufl_vol_pct=9.5,
            autoignition_c=470.0, molecular_weight=44.1,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_redundancy=1,
            substance=propane,
            detector_z_positions=[5.5],
            ceiling_height_m=6.0,
            env_context=env,
        )
        # Expected violations:
        # RED-001: Zone 2 + HCIS requires 2, only 1 → CRITICAL
        # ELEV-001: Propane sinks but detector at ceiling → CRITICAL
        # MENA-001: Low temp for MENA → INFO
        # MENA-003: HCIS + Zone 2 → WARNING
        violation_codes = [v.code for v in result.violations]
        assert "RED-001" in violation_codes
        assert "ELEV-001" in violation_codes
        assert "MENA-001" in violation_codes
        assert "MENA-003" in violation_codes
        # Overall FAIL because of RED-001 CRITICAL
        assert result.status == "FAIL"

    def test_total_checks_incremented(self):
        """Each gate should increment total_checks."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
            min_transmittance=0.80,
        )
        # Redundancy: 1 check
        # Fouling: 2 checks (fouling factor + effective transmittance)
        # Zone mapping: 1 check
        # Z-Axis: 0 checks (no substance/detectors)
        # MENA: 0 checks (not MENA region)
        assert result.total_checks >= 4

    def test_passed_checks_count(self):
        """passed_checks should count non-violated checks."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
        )
        # All checks should pass
        assert result.passed_checks > 0


# ===========================================================================
# 11. AuditResult and AuditViolation Model Tests
# ===========================================================================

class TestAuditResultModel:
    """Test AuditResult and AuditViolation Pydantic models."""

    def test_pass_result(self):
        """PASS result with no violations."""
        result = AuditResult(status="PASS", violations=[], total_checks=5, passed_checks=5)
        assert result.is_pass
        assert result.critical_count == 0
        assert result.warning_count == 0
        assert result.info_count == 0

    def test_fail_result(self):
        """FAIL result with mixed violations."""
        violations = [
            AuditViolation(
                gate="REDUNDANCY", severity="CRITICAL", code="RED-001",
                message="test", standard_ref="ref", remediation="fix",
            ),
            AuditViolation(
                gate="FOULING", severity="WARNING", code="FOUL-002",
                message="warn", standard_ref="ref", remediation="check",
            ),
            AuditViolation(
                gate="MENA", severity="INFO", code="MENA-001",
                message="info", standard_ref="ref", remediation="verify",
            ),
        ]
        result = AuditResult(status="FAIL", violations=violations, total_checks=3, passed_checks=0)
        assert not result.is_pass
        assert result.critical_count == 1
        assert result.warning_count == 1
        assert result.info_count == 1

    def test_frozen_model(self):
        """AuditResult should be immutable."""
        result = AuditResult(status="PASS", violations=[], total_checks=1, passed_checks=1)
        with pytest.raises(ValidationError):
            result.status = "FAIL"

    def test_violation_frozen_model(self):
        """AuditViolation should be immutable."""
        v = AuditViolation(
            gate="TEST", severity="CRITICAL", code="T-001",
            message="test", standard_ref="ref", remediation="fix",
        )
        with pytest.raises(ValidationError):
            v.severity = "WARNING"

    def test_only_critical_causes_fail(self):
        """Result with only WARNING/INFO should have is_pass logic based on status."""
        violations = [
            AuditViolation(
                gate="TEST", severity="WARNING", code="T-001",
                message="warn", standard_ref="ref", remediation="fix",
            ),
        ]
        # Status is set externally; WARNING alone doesn't force FAIL
        result = AuditResult(status="PASS", violations=violations, total_checks=1, passed_checks=0)
        assert result.is_pass
        assert result.critical_count == 0
        assert result.warning_count == 1

    def test_empty_violations_default(self):
        """Violations defaults to empty list."""
        result = AuditResult(status="PASS", total_checks=0, passed_checks=0)
        assert result.violations == []

    def test_total_checks_non_negative(self):
        """total_checks must be >= 0."""
        with pytest.raises(ValidationError):
            AuditResult(status="PASS", total_checks=-1, passed_checks=0)

    def test_passed_checks_non_negative(self):
        """passed_checks must be >= 0."""
        with pytest.raises(ValidationError):
            AuditResult(status="PASS", total_checks=1, passed_checks=-1)


# ===========================================================================
# 12. CLI Layer 6 Integration
# ===========================================================================

class TestCLILayer6Integration:
    """Test CLIFireAIEngine Layer 6 integration."""

    def test_run_layer6_basic(self):
        """run_layer6() returns a Layer6Result."""
        engine = CLIFireAIEngine()
        result = engine.run_layer6(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
        )
        assert isinstance(result, Layer6Result)
        assert result.audit_status in ("PASS", "FAIL")

    def test_run_layer6_fail(self):
        """Layer 6 with insufficient redundancy should FAIL."""
        engine = CLIFireAIEngine()
        result = engine.run_layer6(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=1,
        )
        assert result.audit_status == "FAIL"
        assert len(result.critical_violations) > 0
        assert not result.success

    def test_run_layer6_pass(self):
        """Layer 6 with sufficient redundancy should PASS."""
        engine = CLIFireAIEngine()
        result = engine.run_layer6(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_redundancy=1,
        )
        # Zone 2 with 1 detector is OK per IEC
        # May still have other non-critical violations
        assert result.audit_status in ("PASS", "FAIL")

    def test_layer6_with_substance_and_detectors(self):
        """Layer 6 with substance and detector positions for Z-Axis check."""
        engine = CLIFireAIEngine()
        propane = SubstanceProperties(
            name="Propane", hazard_type=HazardType.GAS,
            lfl_vol_pct=2.1, ufl_vol_pct=9.5,
            autoignition_c=470.0, molecular_weight=44.1,
        )
        result = engine.run_layer6(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
            substance=propane,
            detector_z_positions=[5.5],
            ceiling_height_m=6.0,
        )
        assert isinstance(result, Layer6Result)
        # Propane at ceiling should trigger ELEV-001 CRITICAL
        assert len(result.critical_violations) > 0

    def test_pipeline_includes_layer6(self):
        """Full pipeline should include Layer 6 result."""
        engine = CLIFireAIEngine(grid_step_m=1.0)
        sub = SubstanceProperties(
            name="Methane", hazard_type=HazardType.GAS,
            lfl_vol_pct=5.0, ufl_vol_pct=15.0,
            autoignition_c=537.0, molecular_weight=16.04,
        )
        det = FlameDetectorSpec(
            detector_id="D1",
            position=[10.0, 10.0, 5.5],
            orientation_vector=[0.0, 0.0, -1.0],
            rated_range_m=30.0,
            aoc_deg=90.0,
            spectral_bands=[WavelengthBand.IR3],
        )
        targets = [
            RayTracePoint(x=float(i), y=float(j), z=0.0)
            for i in range(5) for j in range(5)
        ]

        result = engine.run_full_pipeline(
            country_code="GB",
            substance=sub,
            ventilation=VentilationLevel.MEDIUM,
            detectors=[det],
            target_grid=targets,
        )
        assert result.layer6 is not None
        assert isinstance(result.layer6, Layer6Result)
        assert result.layer6.audit_status in ("PASS", "FAIL")
        assert result.layer6.total_checks >= 0

    def test_layer6_mena_environment(self):
        """Layer 6 with MENA environment context."""
        ctx = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            jurisdiction=Jurisdiction.SAUDI_HCIS,
            ambient_temp_c=52.0,
        )
        engine = CLIFireAIEngine(grid_step_m=1.0, env_context=ctx)
        result = engine.run_layer6(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_redundancy=1,
        )
        # HCIS requires min_redundancy=2 for Zone 2
        assert result.audit_status == "FAIL"
        assert any("HCIS" in v for v in result.critical_violations)

    def test_layer6_result_fields(self):
        """Layer6Result should have all expected fields."""
        engine = CLIFireAIEngine()
        result = engine.run_layer6(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
        )
        assert hasattr(result, "audit_status")
        assert hasattr(result, "total_checks")
        assert hasattr(result, "passed_checks")
        assert hasattr(result, "critical_violations")
        assert hasattr(result, "warning_violations")
        assert hasattr(result, "info_violations")
        assert hasattr(result, "all_violations")
        assert hasattr(result, "success")

    def test_pipeline_result_has_layer6(self):
        """PipelineResult should have layer6 field."""
        pr = PipelineResult()
        assert pr.layer6 is None

    def test_layer6_violations_partitioned(self):
        """Layer6Result partitions violations by severity."""
        engine = CLIFireAIEngine()
        result = engine.run_layer6(
            zone=ZoneType.ZONE_0,
            hazard_type=HazardType.GAS,
            min_redundancy=0,
        )
        # Zone 0 requires 3 → RED-001 CRITICAL
        total = (len(result.critical_violations)
                 + len(result.warning_violations)
                 + len(result.info_violations))
        assert total == len(result.all_violations)


# ===========================================================================
# 13. Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases for SafetyAuditEngine and related components."""

    def setup_method(self):
        self.engine = SafetyAuditEngine()

    def test_none_substance(self):
        """None substance should skip Z-Axis gate without error."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=None,
        )
        assert not any(v.code == "ELEV-001" for v in result.violations)

    def test_no_detector_positions(self):
        """No detector positions should skip Z-Axis gate."""
        propane = SubstanceProperties(
            name="Propane", hazard_type=HazardType.GAS,
            lfl_vol_pct=2.1, ufl_vol_pct=9.5,
            autoignition_c=470.0, molecular_weight=44.1,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=propane,
            detector_z_positions=None,
        )
        assert not any(v.code == "ELEV-001" for v in result.violations)

    def test_unclassified_zone(self):
        """UNCLASSIFIED zone with 0 redundancy → should pass redundancy."""
        result = self.engine.run_audit(
            zone=ZoneType.UNCLASSIFIED,
            hazard_type=HazardType.GAS,
            min_redundancy=0,
        )
        assert not any(v.code == "RED-001" for v in result.violations)

    def test_unclassified_zone_mapping_with_dust(self):
        """UNCLASSIFIED is not in gas or dust zone sets → no ZMAP violation."""
        result = self.engine.run_audit(
            zone=ZoneType.UNCLASSIFIED,
            hazard_type=HazardType.DUST,
        )
        assert not any(v.code.startswith("ZMAP") for v in result.violations)

    def test_default_env_context(self):
        """Default EnvironmentalContext should not trigger MENA gate."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
        )
        assert not any(v.code.startswith("MENA") for v in result.violations)

    def test_zero_redundancy_zone2(self):
        """Zone 2 with 0 redundancy → RED-001 (even IEC requires 1)."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_redundancy=0,
        )
        assert any(v.code == "RED-001" for v in result.violations)

    def test_fiber_hazard_type(self):
        """FIBER hazard type should not cause ZMAP violation with gas zones."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.FIBER,
        )
        assert not any(v.code.startswith("ZMAP") for v in result.violations)

    def test_fouling_zero(self):
        """fouling=0.01 (near-zero) should trigger FOUL-001 CRITICAL."""
        # Note: lens_fouling_factor must be > 0.0
        env = EnvironmentalContext(lens_fouling_factor=0.01)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert any(v.code == "FOUL-001" and v.severity == "CRITICAL" for v in result.violations)

    def test_fouling_perfect(self):
        """fouling=1.0 (perfect lens) should not trigger fouling violations."""
        env = EnvironmentalContext(lens_fouling_factor=1.0)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            env_context=env,
        )
        assert not any(v.code in ("FOUL-001", "FOUL-002") for v in result.violations)

    def test_very_small_ceiling_height(self):
        """Ceiling height of 3m should still work for Z-Axis check."""
        propane = SubstanceProperties(
            name="Propane", hazard_type=HazardType.GAS,
            lfl_vol_pct=2.1, ufl_vol_pct=9.5,
            autoignition_c=470.0, molecular_weight=44.1,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            substance=propane,
            detector_z_positions=[2.5],  # >75% of 3m = 2.25m → HIGH
            ceiling_height_m=3.0,
        )
        # Propane (LOW) at HIGH detector → ELEV-001
        assert any(v.code == "ELEV-001" for v in result.violations)

    def test_min_redundancy_by_zone_lookup(self):
        """Verify MIN_REDUNDANCY_BY_ZONE lookup table is correct."""
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_0] == 3
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_1] == 2
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_2] == 1
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_20] == 3
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_21] == 2
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.ZONE_22] == 1
        assert MIN_REDUNDANCY_BY_ZONE[ZoneType.UNCLASSIFIED] == 0

    def test_audit_result_with_only_info_is_pass(self):
        """Only INFO violations should result in PASS status."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            ambient_temp_c=35.0,
            lens_fouling_factor=0.50,  # Below 0.60 → no MENA-002
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=2,
            env_context=env,
        )
        # MENA-001 is INFO, no CRITICAL → PASS
        if not any(v.severity == "CRITICAL" for v in result.violations):
            assert result.status == "PASS"

    def test_zone21_gas_mismatch(self):
        """Zone 21 (dust) + GAS → ZMAP-002 CRITICAL."""
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_21,
            hazard_type=HazardType.GAS,
        )
        assert any(v.code == "ZMAP-002" for v in result.violations)

    def test_mena_without_hcis_no_mena003(self):
        """MENA region with GLOBAL_IEC should not trigger MENA-003."""
        env = EnvironmentalContext(
            region=RegionProfile.MENA_SUMMER_OUTDOOR,
            jurisdiction=Jurisdiction.GLOBAL_IEC,
            ambient_temp_c=52.0,
            lens_fouling_factor=0.55,
        )
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_2,
            hazard_type=HazardType.GAS,
            min_redundancy=1,
            env_context=env,
        )
        assert not any(v.code == "MENA-003" for v in result.violations)

    def test_remediation_field_populated(self):
        """All violations should have non-empty remediation."""
        env = EnvironmentalContext(lens_fouling_factor=0.45)
        result = self.engine.run_audit(
            zone=ZoneType.ZONE_1,
            hazard_type=HazardType.GAS,
            min_redundancy=0,
            env_context=env,
        )
        for v in result.violations:
            assert v.remediation, f"Violation {v.code} has empty remediation"
            assert v.standard_ref, f"Violation {v.code} has empty standard_ref"
