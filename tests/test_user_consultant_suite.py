"""
test_user_consultant_suite.py – User's Consultant Test Suite
=============================================================
Comprehensive adversarial tests for TIER 1 implementation.
All tests designed by the consultant with poison pills.
"""

import pytest
from pydantic import ValidationError
from decimal import Decimal, ROUND_HALF_UP

# Imports target the newly implemented TIER 1 modules
from fireai.core.models_v21 import vapor_density_tier, ElevationTier, EnvironmentalContext, RegionProfile, FoulingCategory, Jurisdiction
from fireai.core.safety_audit_engine import SafetyAuditEngine, AuditInput, AuditResult

PRECISION = 6
AIR_MW = 28.96

# 1. TEST: ANTI-MUTATION & STRICT PYDANTIC (POISON PILL: MUTATION ATTEMPT)
def test_audit_input_strictness_and_immutability():
    # Poison pill: Passing loose types and extra malicious fields
    with pytest.raises(ValidationError):
        AuditInput(
            zone="ZONE_1",
            min_redundancy="TWO",  # Poison: String instead of int
            final_transmittance=0.9,
            substance_molecular_weight=16.04,
            detector_elevation_tier="HIGH",
            malicious_injected_field="Bypass" # Poison: Extra field not in schema
        )

    valid_input = AuditInput(
        zone="ZONE_1",
        min_redundancy=2,
        final_transmittance=0.9,
        substance_molecular_weight=16.04,
        detector_elevation_tier=ElevationTier.HIGH
    )
    
    # Poison pill: Attempt to mutate frozen instance silently
    with pytest.raises(ValidationError):
        valid_input.min_redundancy = 3

# 2. TEST: BUOYANCY PHYSICS WITH FAKE DATA (POISON PILLS: IMPOSSIBLE PHYSICS)
def test_vapor_density_tier_adversarial():
    # Poison pill: Negative molecular weight (Physically impossible)
    with pytest.raises(ValueError, match=r"greater than 0"):
        vapor_density_tier(-5.0)

    # Poison pill: Zero molecular weight (Physically impossible)
    with pytest.raises(ValueError, match=r"greater than 0"):
        vapor_density_tier(0.0)

    # Edge Case: Exactly Air MW
    assert vapor_density_tier(AIR_MW) == ElevationTier.BREATHING_ZONE
    
    # Edge Case: Boundary conditions 
    # Light < 0.97 (MW < 28.0912)
    assert vapor_density_tier(28.0911) == ElevationTier.HIGH
    # Neutral 0.97 - 1.03 (MW 28.0912 - 29.8288)
    assert vapor_density_tier(28.0912) == ElevationTier.BREATHING_ZONE
    assert vapor_density_tier(29.8288) == ElevationTier.BREATHING_ZONE
    # Heavy > 1.03 (MW > 29.8288)
    assert vapor_density_tier(29.8289) == ElevationTier.LOW

# 3. TEST: ADVISORY PRESETS (POISON PILL: SILENT OVERWRITE CHECK)
def test_region_profile_no_silent_mutation():
    # Engineer sets 24.0C in a MENA region (e.g. Inside an AC room)
    ctx = EnvironmentalContext(
        ambient_temp_c=24.0,
        region=RegionProfile.MENA_SUMMER_OUTDOOR
    )
    
    # Poison check: The system MUST NOT silently overwrite 24.0 to 55.0
    assert ctx.ambient_temp_c == 24.0, "FATAL: System silently mutated engineer input!"
    
    # It MUST generate a warning in the model's advisory property
    assert hasattr(ctx, 'advisories'), "FATAL: System lacks advisory tracking!"
    assert any("55.0" in warning for warning in ctx.advisories), "FATAL: System failed to generate advisory warning for MENA profile!"

# 4. TEST: SAFETY AUDIT ENGINE LOGIC (POISON PILL: CONTRADICTORY DATA)
def test_safety_audit_engine_adversarial():
    engine = SafetyAuditEngine()
    
    # Poison pill: Methane (Light, MW=16.04) maliciously placed at LOW_FLOOR_LEVEL
    lethal_design = AuditInput(
        zone="ZONE_1",
        min_redundancy=2,
        final_transmittance=0.8,
        substance_molecular_weight=16.04, 
        detector_elevation_tier=ElevationTier.LOW # FATAL ERROR
    )
    
    result = engine.run_audit(audit_input=lethal_design)
    assert result.status == "FAIL"
    assert any("ELEVATION" in v.message for v in result.violations)

    # Poison pill: H2S (Heavy, MW=34.08) maliciously placed at BREATHING_ZONE
    lethal_design_2 = AuditInput(
        zone="ZONE_2",
        min_redundancy=1,
        final_transmittance=0.8,
        substance_molecular_weight=34.08, 
        detector_elevation_tier=ElevationTier.BREATHING_ZONE # FATAL ERROR
    )
    
    result2 = engine.run_audit(audit_input=lethal_design_2)
    assert result2.status == "FAIL"
    assert any("ELEVATION" in v.message for v in result2.violations)


# ===========================================================================
# GEO / JURISDICTION TESTS
# ===========================================================================

# 🌍 1. THE COMPARATIVE ENVIRONMENTAL TEST (THERMODYNAMICS & FOULING)
@pytest.mark.parametrize("region, expected_advisories", [
    (RegionProfile.GULF_HCIS, 2),    # Expect 2 warnings: Temp too low, Fouling too optimistic
    (RegionProfile.EGYPT_CODE, 1),   # Expect 1 warning: Temp too low (Assuming 45C summer)
    (RegionProfile.EUROPE_IEC, 0),   # Expect 0 warnings: 25C and Clean is normal
    (RegionProfile.USA_NFPA, 0)      # Expect 0 warnings: 25C and Clean is normal
])
def test_geo_environmental_advisories(region, expected_advisories):
    """
    Test: An engineer specifies a standard 25°C room with CLEAN lenses.
    The system must generate regional WARNINGS without silently overwriting the data.
    """
    ctx = EnvironmentalContext(
        ambient_temp_c=25.0,  
        fouling_category=FoulingCategory.CLEAN,
        region=region
    )
    
    # Anti-Mutation Check: The system MUST NOT change the user's input silently
    assert ctx.ambient_temp_c == 25.0
    assert ctx.fouling_category == FoulingCategory.CLEAN
    
    # Advisory Count Check
    assert len(ctx.advisories) == expected_advisories, \
        f"Region {region.name} failed advisory logic. Expected {expected_advisories}, got {len(ctx.advisories)}."

# ⚖️ 2. THE COMPARATIVE JURISDICTION TEST (LEGAL REDUNDANCY)
@pytest.mark.parametrize("jurisdiction, expected_status", [
    (Jurisdiction.SAUDI_HCIS, "FAIL"),  # HCIS strictly forbids 1oo1 in Zone 2
    (Jurisdiction.EGYPTIAN_FIRE_CODE, "PASS"), # Egypt follows NFPA (allows 1oo1 in Zone 2)
    (Jurisdiction.GLOBAL_IEC, "PASS"),  # Europe IEC allows 1oo1 in Zone 2
    (Jurisdiction.USA_NFPA, "PASS")     # USA NFPA allows 1oo1 in Zone 2 (Class 1 Div 2 equivalent)
])
def test_geo_jurisdiction_audit(jurisdiction, expected_status):
    """
    Test: An engineer designs a Zone 2 area with a SINGLE detector (Min Redundancy = 1).
    The physical arrangement is the same, but the legal ruling changes by continent.
    """
    engine = SafetyAuditEngine()
    
    design_input = AuditInput(
        zone="ZONE_2",
        min_redundancy=1,  # The trap: 1 detector only
        final_transmittance=0.9,
        substance_molecular_weight=28.96, # Air-like, breathing zone
        detector_elevation_tier=ElevationTier.BREATHING_ZONE,
        jurisdiction=jurisdiction
    )
    
    result = engine.run_audit(audit_input=design_input)
    
    assert result.status == expected_status, \
        f"Jurisdiction {jurisdiction.name} failed. Expected {expected_status}, got {result.status}. Violations: {[v.message for v in result.violations]}"

# 🌐 3. THE GLOBAL PHYSICS TEST (BUOYANCY REMAINS CONSTANT)
@pytest.mark.parametrize("jurisdiction", [
    Jurisdiction.SAUDI_HCIS, Jurisdiction.EGYPTIAN_FIRE_CODE, 
    Jurisdiction.GLOBAL_IEC, Jurisdiction.USA_NFPA
])
def test_global_physics_invariants(jurisdiction):
    """
    Test: Gravity and molecular weight DO NOT change by region. 
    Methane on the floor MUST FAIL everywhere in the world.
    """
    engine = SafetyAuditEngine()
    
    methane_on_floor = AuditInput(
        zone="ZONE_1",
        min_redundancy=2,
        final_transmittance=0.9,
        substance_molecular_weight=16.04, # Methane (Light)
        detector_elevation_tier=ElevationTier.LOW, # FATAL FLAW
        jurisdiction=jurisdiction
    )
    
    result = engine.run_audit(audit_input=methane_on_floor)
    
    # Must fail universally, regardless of local law
    assert result.status == "FAIL"
    assert any("ELEVATION" in v.message for v in result.violations)
