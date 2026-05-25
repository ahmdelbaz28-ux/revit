"""
test_v21_edge_cases.py – V21 Pydantic Edge Cases
===================================================
Every dangerous boundary condition explicitly tested.
Required by consultant Section 8.4.

Covers:
  - SubstanceProperties boundary values (LFL=0, flash>=autoignition, HYBRID needs both)
  - Temperature class Fix #15 (strictly below autoignition)
  - EPL Fix #14 (hierarchy: Ga>Gb>Gc)
  - Country selector Fix #1, #3, #5, Q3 (UnknownCountryError)
  - HAC Classification (critical_flags, hemisphere, hybrid)
  - Ray Trace (sensitivity cap, no double-counting, spectral transparency)
"""

import pytest
from pydantic import ValidationError

from fireai.core.models_v21 import (
    SubstanceProperties, HazardType, VentilationLevel,
    ZoneExtent, ATEXEquipmentSpec, ZoneType, TemperatureClass,
    FlameDetectorSpec, WavelengthBand, _select_temp_class,
    Obstruction, RayTracePoint,
)
from fireai.core.international_reg_selector import (
    resolve, UnknownCountryError, convert_division_to_zone,
)
from fireai.core.hac_classification_engine import HACClassificationEngine
from fireai.core.flame_detector_aoc_raytrace import FlameDetectorAOCRayTrace


# ── SubstanceProperties boundary values ──────────────────────────────────────

def test_substance_lfl_zero_rejected():
    """LFL=0 is physically impossible — must be rejected."""
    with pytest.raises(ValidationError, match="greater than"):
        SubstanceProperties(
            name="test", hazard_type=HazardType.GAS, lfl_vol_pct=0.0
        )

def test_substance_autoignition_85c_minimum():
    """autoignition=85C: minimum viable (T6 covers it)."""
    s = SubstanceProperties(
        name="test", hazard_type=HazardType.GAS,
        lfl_vol_pct=1.0, autoignition_c=85.0,
    )
    assert s.autoignition_c == 85.0

def test_substance_flash_above_autoignition_rejected():
    """flash_point >= autoignition violates physics — must fail."""
    with pytest.raises(ValidationError, match="flash_point_c.*strictly"):
        SubstanceProperties(
            name="test", hazard_type=HazardType.GAS,
            lfl_vol_pct=1.0, flash_point_c=200.0, autoignition_c=180.0,
        )

def test_substance_flash_equal_autoignition_rejected():
    """flash_point == autoignition: also rejected."""
    with pytest.raises(ValidationError):
        SubstanceProperties(
            name="test", hazard_type=HazardType.GAS,
            lfl_vol_pct=1.0, flash_point_c=180.0, autoignition_c=180.0,
        )

def test_substance_hybrid_needs_both():
    """HYBRID without MEC must fail."""
    with pytest.raises(ValidationError, match="mec_g_m3"):
        SubstanceProperties(
            name="test", hazard_type=HazardType.HYBRID, lfl_vol_pct=1.0
        )

def test_substance_dust_needs_mec():
    """DUST without MEC must fail."""
    with pytest.raises(ValidationError, match="mec_g_m3"):
        SubstanceProperties(name="test", hazard_type=HazardType.DUST)

def test_substance_dict_rejected_strict():
    """Passing a dict instead of SubstanceProperties must fail."""
    engine = HACClassificationEngine()
    with pytest.raises((ValidationError, AttributeError, TypeError)):
        engine.classify_v21(
            substance={"name": "test", "hazard_type": "GAS"},  # type: ignore
            ventilation=VentilationLevel.MEDIUM,
            is_indoor=True,
        )


# ── Temperature class Fix #15 ────────────────────────────────────────────────

def test_temp_class_autoignition_180():
    """autoignition=180C -> returned T-class max surface must be < 180C."""
    t = _select_temp_class(180.0)
    from fireai.core.models_v21 import _T_CLASS_MAX
    max_surface = _T_CLASS_MAX[t.value]
    assert max_surface < 180.0, (
        f"Got {t.value} (max {max_surface}C) — "
        f"max surface must be STRICTLY below autoignition 180C!"
    )

def test_temp_class_autoignition_200():
    """autoignition=200C -> returned T-class max surface must be < 200C."""
    t = _select_temp_class(200.0)
    from fireai.core.models_v21 import _T_CLASS_MAX
    max_surface = _T_CLASS_MAX[t.value]
    assert max_surface < 200.0, (
        f"Got {t.value} (max {max_surface}C) — "
        f"max surface must be STRICTLY below autoignition 200C!"
    )

def test_temp_class_autoignition_300():
    """autoignition=300C -> returned T-class max surface must be < 300C."""
    t = _select_temp_class(300.0)
    from fireai.core.models_v21 import _T_CLASS_MAX
    max_surface = _T_CLASS_MAX[t.value]
    assert max_surface < 300.0, (
        f"Got {t.value} (max {max_surface}C) — "
        f"max surface must be STRICTLY below autoignition 300C!"
    )

def test_temp_class_autoignition_too_low():
    """autoignition <= 85C cannot be handled — must raise."""
    with pytest.raises(ValueError, match="No safe temperature class"):
        _select_temp_class(80.0)

def test_temp_class_autoignition_85_boundary():
    """autoignition=85C: at T6 boundary. T6 max=85C, need STRICTLY less."""
    with pytest.raises(ValueError):
        _select_temp_class(85.0)   # 85 is NOT < 85


# ── EPL Fix #14 ──────────────────────────────────────────────────────────────

def test_epl_gc_rejected_for_zone_0():
    """Gc (lowest gas protection) must be rejected for Zone 0 (needs Ga)."""
    with pytest.raises(ValidationError, match="INSUFFICIENT"):
        ATEXEquipmentSpec(
            zone=ZoneType.ZONE_0,
            epl_required="Gc",
            atex_category="1G",
            temp_class=TemperatureClass.T4,
            protection_modes=["ia"],
        )

def test_epl_gb_rejected_for_zone_0():
    """Gb rejected for Zone 0."""
    with pytest.raises(ValidationError, match="INSUFFICIENT"):
        ATEXEquipmentSpec(
            zone=ZoneType.ZONE_0,
            epl_required="Gb",
            atex_category="1G",
            temp_class=TemperatureClass.T4,
            protection_modes=["ia"],
        )

def test_epl_ga_accepted_for_zone_0():
    """Ga accepted for Zone 0."""
    spec = ATEXEquipmentSpec(
        zone=ZoneType.ZONE_0,
        epl_required="Ga",
        atex_category="1G",
        temp_class=TemperatureClass.T4,
        protection_modes=["ia"],
    )
    assert spec.epl_required == "Ga"

def test_epl_ga_accepted_for_zone_1():
    """Ga (more protective than Gb) must be accepted for Zone 1."""
    spec = ATEXEquipmentSpec(
        zone=ZoneType.ZONE_1,
        epl_required="Ga",
        atex_category="2G",
        temp_class=TemperatureClass.T4,
        protection_modes=["ia"],
    )
    assert spec.epl_required == "Ga"


# ── Protection mode Fix #17 ──────────────────────────────────────────────────

def test_protection_mode_ia_zone_2_accepted():
    """ia is permitted (though over-spec) for Zone 2."""
    spec = ATEXEquipmentSpec(
        zone=ZoneType.ZONE_2,
        epl_required="Gc",
        atex_category="3G",
        temp_class=TemperatureClass.T4,
        protection_modes=["ia"],
    )
    assert "ia" in spec.protection_modes

def test_protection_invalid_zone_0():
    """'n' protection mode rejected for Zone 0."""
    with pytest.raises(ValidationError):
        ATEXEquipmentSpec(
            zone=ZoneType.ZONE_0,
            epl_required="Ga",
            atex_category="1G",
            temp_class=TemperatureClass.T4,
            protection_modes=["n"],   # 'n' not allowed in Zone 0
        )


# ── Country selector Fix #1, #3, #5, Q3 ─────────────────────────────────────

def test_unknown_country_raises():
    """Unregistered country must RAISE, never silently fall back."""
    with pytest.raises(UnknownCountryError) as exc_info:
        resolve("XX")
    assert "XX" in str(exc_info.value)
    assert "criminal liability" in str(exc_info.value).lower()

def test_canada_is_zone_cec():
    """Canada must be CEC Zone system, not NEC Division."""
    result = resolve("CA")
    assert result.zone_system == "ZONE"
    assert "CEC" in result.framework.value

def test_norway_is_efta():
    """Norway is EFTA, not EU member."""
    result = resolve("NO")
    assert result.framework.value == "EFTA"
    assert any("EFTA" in w or "DSB" in w for w in result.warnings)

def test_class_iii_no_zone_equivalent():
    """CLASS_III (fibers) has NO IEC Zone equivalent."""
    with pytest.raises(ValueError, match="CLASS_III.*NO IEC"):
        convert_division_to_zone("DIVISION_1", "CLASS_III")

def test_gas_div1_to_zone1():
    """CLASS_I DIVISION_1 -> ZONE_1."""
    assert convert_division_to_zone("DIVISION_1", "CLASS_I") == "ZONE_1"

def test_dust_div1_to_zone21():
    """CLASS_II DIVISION_1 -> ZONE_21 (not ZONE_1)."""
    assert convert_division_to_zone("DIVISION_1", "CLASS_II") == "ZONE_21"

def test_egypt_registered():
    """Egypt must be registered (Fix #5)."""
    result = resolve("EG")
    assert result is not None

def test_all_fix5_countries():
    """All 15 countries from Fix #5 must be registered."""
    fix5_countries = ["IR", "EG", "SG", "MY", "ID", "NG", "TR", "CH",
                      "TH", "PH", "VN", "PK", "CO", "AR", "CL"]
    for code in fix5_countries:
        result = resolve(code)
        assert result.framework is not None, f"{code} not found"


# ── HAC Classification ───────────────────────────────────────────────────────

def test_poor_ventilation_zone0_critical_flag():
    """Zone 0 + POOR ventilation must have critical flag in result."""
    engine = HACClassificationEngine()
    sub = SubstanceProperties(
        name="methane", hazard_type=HazardType.GAS, lfl_vol_pct=5.0
    )
    # The engine should ADD the critical flag before HACResult construction
    # so HACResult validator passes. The flag must be present in the result.
    result = engine.classify_v21(sub, VentilationLevel.POOR, is_indoor=True)
    assert result.zone == ZoneType.ZONE_0
    assert len(result.critical_flags) > 0
    assert any("CRITICAL" in f for f in result.critical_flags)

def test_hybrid_takes_more_severe_zone():
    """Hybrid classification must take the most severe zone."""
    engine = HACClassificationEngine()
    sub = SubstanceProperties(
        name="hybrid", hazard_type=HazardType.HYBRID,
        lfl_vol_pct=1.0, mec_g_m3=30.0,
    )
    result = engine.classify_v21(sub, VentilationLevel.LOW, is_indoor=True)
    assert result.zone in (
        ZoneType.ZONE_0, ZoneType.ZONE_20,
        ZoneType.ZONE_1, ZoneType.ZONE_21,
    )
    assert "HYBRID" in " ".join(result.warnings)

def test_indoor_extent_is_hemisphere():
    """Indoor zone extent must use hemisphere (2/3*pi*r^3), not sphere."""
    engine = HACClassificationEngine()
    sub = SubstanceProperties(
        name="propane", hazard_type=HazardType.GAS, lfl_vol_pct=2.1
    )
    result = engine.classify_v21(sub, VentilationLevel.MEDIUM, is_indoor=True)
    r = result.extent.horizontal_m
    expected_hemisphere = (2.0/3.0) * 3.14159 * r**3
    assert abs(result.extent.volume_m3 - expected_hemisphere) < expected_hemisphere * 0.06

def test_outdoor_extent_is_full_sphere():
    """Outdoor zone extent must use full sphere (4/3*pi*r^3)."""
    engine = HACClassificationEngine()
    sub = SubstanceProperties(
        name="propane", hazard_type=HazardType.GAS, lfl_vol_pct=2.1
    )
    result = engine.classify_v21(sub, VentilationLevel.MEDIUM, is_indoor=False)
    r = result.extent.horizontal_m
    expected_sphere = (4.0/3.0) * 3.14159 * r**3
    assert abs(result.extent.volume_m3 - expected_sphere) < expected_sphere * 0.06


# ── Ray Trace ────────────────────────────────────────────────────────────────

def test_sensitivity_capped_at_1_for_near_distance():
    """Fix #19: Sensitivity must not exceed 1.0 for near distances."""
    engine = FlameDetectorAOCRayTrace()
    s = engine._sensitivity_v21(distance_m=1.0, rated_range=10.0)
    assert s == 1.0, f"Sensitivity={s} exceeds 1.0 for distance < rated_range"

def test_sensitivity_inverse_square_beyond_range():
    """Beyond rated range, sensitivity follows inverse square law."""
    engine = FlameDetectorAOCRayTrace()
    s = engine._sensitivity_v21(distance_m=20.0, rated_range=10.0)
    expected = (10.0/20.0)**2
    assert abs(s - expected) < 0.001

def test_no_double_counting_multi_detector():
    """Fix #20: Coverage from two overlapping detectors not double-counted."""
    det1 = FlameDetectorSpec(
        detector_id="D1", position=[0, 0, 3], orientation_vector=[0, 0, -1],
        rated_range_m=10.0, aoc_deg=90.0, spectral_bands=[WavelengthBand.IR3],
    )
    det2 = FlameDetectorSpec(
        detector_id="D2", position=[1, 0, 3], orientation_vector=[0, 0, -1],
        rated_range_m=10.0, aoc_deg=90.0, spectral_bands=[WavelengthBand.IR3],
    )
    targets = [RayTracePoint(x=0.5, y=0.0, z=0.0)]
    engine = FlameDetectorAOCRayTrace()
    result = engine.analyse_multi_v21([det1, det2], targets, obstructions=[])
    # Should be 1 covered, NOT 2
    assert result.covered_points == 1
    assert result.total_points == 1

def test_upward_facing_detector_warning():
    """Detector aimed upward must trigger warning."""
    det = FlameDetectorSpec(
        detector_id="D_UP", position=[5, 5, 0.5], orientation_vector=[0, 0, 1],
        rated_range_m=10.0, aoc_deg=90.0, spectral_bands=[WavelengthBand.IR3],
    )
    assert det.is_facing_upward()
    targets = [RayTracePoint(x=5, y=5, z=0.0)]
    engine = FlameDetectorAOCRayTrace()
    result = engine.analyse_single_v21(det, targets, obstructions=[])
    assert any("upward" in w.lower() for w in result.warnings)

def test_spectral_glass_blocks_uv_passes_ir():
    """Glass obstruction: UV blocked, IR transparent."""
    glass = Obstruction(
        obstruction_id="GLASS",
        vertices=[[2, -1, 0], [2, 1, 0], [2, 1, 5], [2, -1, 5]],
        spectral_transparency={
            WavelengthBand.UV:  0.0,
            WavelengthBand.VIS: 0.9,
            WavelengthBand.IR1: 0.8,
            WavelengthBand.IR3: 0.7,
        }
    )
    assert not glass.is_transparent_for(WavelengthBand.UV)
    assert glass.is_transparent_for(WavelengthBand.IR1)
    assert glass.is_transparent_for(WavelengthBand.IR3)

def test_coverage_fraction_never_exceeds_1():
    """Coverage fraction must always be in [0.0, 1.0]."""
    det = FlameDetectorSpec(
        detector_id="D1", position=[5, 5, 3], orientation_vector=[0, 0, -1],
        rated_range_m=20.0, aoc_deg=180.0, spectral_bands=[WavelengthBand.IR3],
    )
    targets = [RayTracePoint(x=i*0.5, y=i*0.5, z=0) for i in range(20)]
    engine = FlameDetectorAOCRayTrace()
    result = engine.analyse_multi_v21([det], targets, obstructions=[])
    assert 0.0 <= result.coverage_fraction <= 1.0
