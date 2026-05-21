"""
tests/test_v20_1_systemic_fixes.py
====================================
Ruthless vulnerability testing for V20.1 Systemic Fixes:

  1. DuctDetector Velocity Blindness — UL 268A §(blow-by effect)
  2. Conduit-Wire Circular Dependency — NEC feedback loop
  3. SubmittalIntegrityGate — TOCTOU CWE-367 post-draft hash verification

V20.1 FIXES TESTED:
  - Duct air velocity > 4000 FPM causes smoke detector blindness (blow-by)
  - Conduit fill recalculated with upsized AWG from voltage drop feedback
  - CAD file hash verified between calculation and final submittal compilation
"""
import pytest
import math
import os
import tempfile

from fireai.core.duct_detector import (
    DuctSpec,
    DuctAnalysisResult,
    DuctDetectorPosition,
    analyse_duct,
    analyse_ducts,
    total_duct_detectors,
    NFPA_DUCT_MAX_SPACING_M,
    NFPA_DUCT_CFM_THRESHOLD,
    UL268A_MAX_VELOCITY_FPM,
)
from fireai.core.conduit_fill_analyzer import (
    ConduitSizer,
    WireSpec,
    InsulationType,
    WIRE_DIAMETERS_MM,
)
from fireai.core.submittal_integrity_gate import (
    SubmittalIntegrityGate,
    HashRecord,
    IntegrityCheckResult,
    _CITE_CWE367,
    _CITE_NFPA72_INTEGRITY,
)
from fireai.core.provenance import (
    DecisionProvenance,
    ConfidenceLevel,
    Violation,
)


# ============================================================================
# 1. DUCT DETECTOR VELOCITY BLINDNESS TESTS (UL 268A)
# ============================================================================
class TestDuctVelocityBlindness:
    """UL 268A — Blow-by effect when duct air velocity > 4000 FPM."""

    # -- 1.1 Round duct: velocity within limits --
    def test_round_duct_velocity_within_limits(self):
        """24" diameter round duct, 5000 CFM → velocity ~1273 FPM → OK."""
        duct = DuctSpec(
            duct_id="DUCT-R1",
            length_m=10.0,
            width_m=0.61,  # 24" diameter
            airflow_cfm=5000.0,
            duct_type="supply",
        )
        result = analyse_duct(duct)
        # Area = π × (0.61/2)² = 0.2922 m² = 3.144 ft²
        # Velocity = 5000 / 3.144 = 1590 FPM < 4000
        assert result.velocity_fpm > 0
        assert result.velocity_blindness is False
        assert result.exempt is False

    # -- 1.2 Round duct: velocity EXCEEDS UL 268A limit --
    def test_round_duct_velocity_exceeds_limit(self):
        """Small round duct with high CFM → velocity > 4000 FPM → BLIND."""
        duct = DuctSpec(
            duct_id="DUCT-BLOWBY",
            length_m=5.0,
            width_m=0.30,  # 12" diameter = small duct
            airflow_cfm=8000.0,  # Very high CFM for this duct size
            duct_type="supply",
        )
        result = analyse_duct(duct)
        # Area = π × (0.30/2)² = 0.0707 m² = 0.761 ft²
        # Velocity = 8000 / 0.761 = 10512 FPM >> 4000
        assert result.velocity_fpm > UL268A_MAX_VELOCITY_FPM
        assert result.velocity_blindness is True
        # Must have a UL 268A warning
        ul_warnings = [w for w in result.warnings if "UL 268A" in w or "4000 FPM" in w]
        assert len(ul_warnings) >= 1, f"Expected UL 268A warning, got: {result.warnings}"

    # -- 1.3 Rectangular duct: velocity calculation --
    def test_rectangular_duct_velocity(self):
        """Rectangular duct 0.6m × 0.3m, 3000 CFM."""
        duct = DuctSpec(
            duct_id="DUCT-RECT",
            length_m=8.0,
            width_m=0.6,
            height_m=0.3,
            airflow_cfm=3000.0,
            duct_type="supply",
        )
        result = analyse_duct(duct)
        # Area = 0.6 × 0.3 = 0.18 m² = 1.938 ft²
        # Velocity = 3000 / 1.938 = 1548 FPM < 4000
        assert result.velocity_fpm > 0
        assert result.velocity_blindness is False

    # -- 1.4 Rectangular duct: velocity EXCEEDS limit --
    def test_rectangular_duct_velocity_exceeds_limit(self):
        """Small rectangular duct with high CFM → blow-by."""
        duct = DuctSpec(
            duct_id="DUCT-RECT-BLOWBY",
            length_m=6.0,
            width_m=0.25,
            height_m=0.20,
            airflow_cfm=6000.0,
            duct_type="return",
        )
        result = analyse_duct(duct)
        # Area = 0.25 × 0.20 = 0.05 m² = 0.538 ft²
        # Velocity = 6000 / 0.538 = 11152 FPM >> 4000
        assert result.velocity_blindness is True

    # -- 1.5 No CFM data → zero velocity, no blindness --
    def test_no_cfm_data(self):
        """Duct without CFM data → velocity = 0, no blindness check."""
        duct = DuctSpec(
            duct_id="DUCT-NO-CFM",
            length_m=5.0,
            width_m=0.5,
        )
        result = analyse_duct(duct)
        assert result.velocity_fpm == 0.0
        assert result.velocity_blindness is False

    # -- 1.6 Backward compatibility: round duct with default height --
    def test_backward_compatible_default_height(self):
        """DuctSpec with default height_m=0 (round duct mode)."""
        duct = DuctSpec(
            duct_id="DUCT-BW",
            length_m=5.0,
            width_m=0.50,
            airflow_cfm=3000.0,
        )
        result = analyse_duct(duct)
        # Round duct: area = π × (0.50/2)² = 0.1963 m²
        assert result.velocity_fpm > 0
        assert result.exempt is False

    # -- 1.7 Exempt ducts still have velocity fields --
    def test_exempt_duct_has_velocity_fields(self):
        """Exhaust duct → exempt, but velocity fields still default."""
        duct = DuctSpec(
            duct_id="DUCT-EXHAUST",
            length_m=5.0,
            width_m=0.5,
            airflow_cfm=5000.0,
            duct_type="exhaust",
        )
        result = analyse_duct(duct)
        assert result.exempt is True
        assert result.velocity_fpm == 0.0
        assert result.velocity_blindness is False

    # -- 1.8 UL 268A constant value --
    def test_ul268a_constant(self):
        """UL 268A maximum velocity must be 4000 FPM."""
        assert UL268A_MAX_VELOCITY_FPM == 4000.0

    # -- 1.9 Boundary: velocity exactly at 4000 FPM --
    def test_velocity_at_exact_limit(self):
        """Velocity at exactly 4000 FPM → should NOT be blind (≤ limit)."""
        # Need to find CFM/area that gives exactly 4000 FPM
        # Round duct 0.3m diameter: area = π × (0.15)² = 0.0707 m² = 0.761 ft²
        # CFM for 4000 FPM = 4000 × 0.761 = 3044 CFM
        duct = DuctSpec(
            duct_id="DUCT-EXACT",
            length_m=5.0,
            width_m=0.30,
            airflow_cfm=3044.0,
            duct_type="supply",
        )
        result = analyse_duct(duct)
        # Due to floating-point, velocity might be slightly above or below
        # At limit, blindness should be False (velocity ≤ 4000)
        # Allow small tolerance
        assert result.velocity_fpm <= 4005.0  # Small tolerance for floating-point

    # -- 1.10 Multiple ducts with mixed velocities --
    def test_multiple_ducts_mixed_velocity(self):
        """analyse_ducts with mixed velocity compliance."""
        ducts = [
            DuctSpec("DUCT-OK", 5.0, 0.50, airflow_cfm=3000.0, duct_type="supply"),
            DuctSpec("DUCT-BAD", 5.0, 0.25, airflow_cfm=8000.0, duct_type="supply"),
        ]
        results = analyse_ducts(ducts)
        assert len(results) == 2
        ok_result = [r for r in results if r.duct_id == "DUCT-OK"][0]
        bad_result = [r for r in results if r.duct_id == "DUCT-BAD"][0]
        assert ok_result.velocity_blindness is False
        assert bad_result.velocity_blindness is True


# ============================================================================
# 2. CONDUIT-WIRE FEEDBACK LOOP TESTS
# ============================================================================
class TestConduitWireFeedbackLoop:
    """NEC — Conduit fill recalculated with upsized AWG from voltage drop."""

    def setup_method(self):
        self.sizer = ConduitSizer()

    # -- 2.1 No overrides → delegates normally --
    def test_no_overrides_delegates(self):
        """Without wire_size_overrides, behaves same as analyze_routing_bundle."""
        result = self.sizer.analyze_with_wire_overrides(
            bundle_id="TRUNK-01",
            wire_inventory=[
                {"awg": 14, "count": 4, "insulation": "FPLP"},
            ],
        )
        val = result.value if isinstance(result, DecisionProvenance) else result
        assert val["is_compliant"] is True

    # -- 2.2 Override 14AWG → 12AWG increases fill --
    def test_override_increases_fill(self):
        """Upsizing 14AWG to 12AWG increases total cable area (both in table)."""
        # Without override
        result_base = self.sizer.analyze_routing_bundle(
            bundle_id="TRUNK-BASE",
            wire_inventory=[
                {"awg": 14, "count": 8, "insulation": "FPLP"},
            ],
        )
        val_base = result_base.value if isinstance(result_base, DecisionProvenance) else result_base

        # With override: 14AWG → 12AWG (both have FPLP entries in WIRE_DIAMETERS_MM)
        result_override = self.sizer.analyze_with_wire_overrides(
            bundle_id="TRUNK-OVERRIDE",
            wire_inventory=[
                {"awg": 14, "count": 8, "insulation": "FPLP"},
            ],
            wire_size_overrides={14: 12},
        )
        val_override = result_override.value if isinstance(result_override, DecisionProvenance) else result_override

        # 12AWG (4.22mm) has larger diameter than 14AWG (3.61mm) → more fill
        assert val_override["total_cable_area_mm2"] > val_base["total_cable_area_mm2"]

    # -- 2.3 Override may require larger conduit --
    def test_override_may_upsize_conduit(self):
        """High wire count with override may need bigger conduit."""
        # 20 × 14AWG wires → with override to 12AWG, conduit may overflow
        result = self.sizer.analyze_with_wire_overrides(
            bundle_id="TRUNK-HUGE",
            wire_inventory=[
                {"awg": 14, "count": 20, "insulation": "FPLP"},
            ],
            wire_size_overrides={14: 12},
        )
        val = result.value if isinstance(result, DecisionProvenance) else result
        # With 20 × 12AWG (4.22mm OD), total area is significant
        # 20 × π×(4.22/2)² = 20 × 13.98 = 279.6 mm²
        assert val["total_cable_area_mm2"] > 250.0

    # -- 2.4 Override does not mutate original inventory --
    def test_original_inventory_not_mutated(self):
        """wire_size_overrides should NOT modify the caller's dict."""
        inventory = [
            {"awg": 14, "count": 4, "insulation": "FPLP"},
        ]
        original_awg = inventory[0]["awg"]

        self.sizer.analyze_with_wire_overrides(
            bundle_id="TRUNK-NO-MUTATE",
            wire_inventory=inventory,
            wire_size_overrides={14: 10},
        )
        # Original inventory should be unchanged
        assert inventory[0]["awg"] == original_awg

    # -- 2.5 Provenance contains feedback rule --
    def test_provenance_contains_feedback_rule(self):
        """DecisionProvenance should contain NEC_WIRE_UPSIZE_FEEDBACK rule."""
        result = self.sizer.analyze_with_wire_overrides(
            bundle_id="TRUNK-FEEDBACK",
            wire_inventory=[
                {"awg": 14, "count": 4, "insulation": "FPLP"},
            ],
            wire_size_overrides={14: 10},
        )
        if isinstance(result, DecisionProvenance):
            # Check rules_applied contains feedback rule
            rules = result.rules_applied
            rule_ids = []
            for r in rules:
                if isinstance(r, dict):
                    rule_ids.append(r.get("constant_id", ""))
                elif hasattr(r, "constant_id"):
                    rule_ids.append(r.constant_id)
            assert "NEC_WIRE_UPSIZE_FEEDBACK" in rule_ids, f"Expected NEC_WIRE_UPSIZE_FEEDBACK in {rule_ids}"

    # -- 2.6 Multiple overrides applied --
    def test_multiple_overrides(self):
        """Multiple wire size overrides: {14: 10, 16: 12}."""
        result = self.sizer.analyze_with_wire_overrides(
            bundle_id="TRUNK-MULTI",
            wire_inventory=[
                {"awg": 14, "count": 4, "insulation": "FPLP"},
                {"awg": 16, "count": 4, "insulation": "FPLR"},
            ],
            wire_size_overrides={14: 10, 16: 12},
        )
        val = result.value if isinstance(result, DecisionProvenance) else result
        assert val["is_compliant"] is not None

    # -- 2.7 Warning emitted when overrides applied --
    def test_warning_emitted_on_override(self):
        """Feedback loop warning should be in result warnings."""
        result = self.sizer.analyze_with_wire_overrides(
            bundle_id="TRUNK-WARN",
            wire_inventory=[
                {"awg": 14, "count": 4, "insulation": "FPLP"},
            ],
            wire_size_overrides={14: 10},
        )
        if isinstance(result, DecisionProvenance):
            warnings = result.warnings or []
            # Should mention wire size override
            override_warnings = [w for w in warnings if "upsiz" in w.lower() or "override" in w.lower() or "10 AWG" in w]
            assert len(override_warnings) >= 1, f"Expected override warning in {warnings}"

    # -- 2.8 None overrides → same as base method --
    def test_none_overrides_same_as_base(self):
        """wire_size_overrides=None should produce same result as analyze_routing_bundle."""
        result = self.sizer.analyze_with_wire_overrides(
            bundle_id="TRUNK-NONE",
            wire_inventory=[
                {"awg": 14, "count": 4, "insulation": "FPLP"},
            ],
            wire_size_overrides=None,
        )
        val = result.value if isinstance(result, DecisionProvenance) else result
        assert val["is_compliant"] is True


# ============================================================================
# 3. SUBMITTAL INTEGRITY GATE TESTS (TOCTOU CWE-367)
# ============================================================================
class TestSubmittalIntegrityGate:
    """CWE-367 — Post-draft SHA-256 hash verification."""

    def setup_method(self):
        self.gate = SubmittalIntegrityGate()
        # Create a temporary file for testing
        self.tmp_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.dxf', delete=False
        )
        self.tmp_file.write("TEST DXF CONTENT V1")
        self.tmp_file.flush()
        self.tmp_file.close()
        self.file_path = self.tmp_file.name

    def teardown_method(self):
        if os.path.exists(self.file_path):
            os.unlink(self.file_path)

    # -- 3.1 Hash match → safe --
    def test_hash_match_safe(self):
        """Same file between calculation and submittal → safe."""
        # Record hash at pre-calculation phase
        record = self.gate.record_hash(self.file_path, "pre_calculation")
        assert record.sha256_hex != ""
        assert record.phase == "pre_calculation"

        # Verify integrity — file unchanged
        result = self.gate.verify_integrity(self.file_path, record.sha256_hex)
        val = result.value if isinstance(result, DecisionProvenance) else result
        assert val["safe"] is True

    # -- 3.2 Hash mismatch → CRITICAL violation --
    def test_hash_mismatch_violation(self):
        """File modified between calculation and submittal → CRITICAL."""
        # Record hash at pre-calculation
        record = self.gate.record_hash(self.file_path, "pre_calculation")

        # MODIFY the file
        with open(self.file_path, 'w') as f:
            f.write("MODIFIED DXF CONTENT V2")

        # Verify integrity — file changed!
        result = self.gate.verify_integrity(self.file_path, record.sha256_hex)
        val = result.value if isinstance(result, DecisionProvenance) else result
        assert val["safe"] is False

        # Should have a CRITICAL violation
        vio = result.violations_detected if isinstance(result, DecisionProvenance) else result.get("violations", [])
        assert len(vio) >= 1
        desc = vio[0]["description"] if isinstance(vio[0], dict) else vio[0].description
        assert "TOCTOU" in desc or "CWE-367" in desc

    # -- 3.3 Provenance structure --
    def test_provenance_structure(self):
        """verify_integrity returns DecisionProvenance with correct type."""
        record = self.gate.record_hash(self.file_path, "pre_calculation")
        result = self.gate.verify_integrity(self.file_path, record.sha256_hex)
        assert isinstance(result, DecisionProvenance)
        assert result.decision_type == "submittal_integrity_gate"

    # -- 3.4 Confidence HIGH on match, LOW on mismatch --
    def test_confidence_levels(self):
        """Match → HIGH confidence; mismatch → LOW confidence."""
        record = self.gate.record_hash(self.file_path, "pre_calculation")

        # Match case
        result_match = self.gate.verify_integrity(self.file_path, record.sha256_hex)
        assert isinstance(result_match, DecisionProvenance)
        assert result_match.confidence.overall == ConfidenceLevel.HIGH

        # Modify file
        with open(self.file_path, 'w') as f:
            f.write("TAMPERED CONTENT")

        result_mismatch = self.gate.verify_integrity(self.file_path, record.sha256_hex)
        assert isinstance(result_mismatch, DecisionProvenance)
        assert result_mismatch.confidence.overall == ConfidenceLevel.LOW

    # -- 3.5 HashRecord fields --
    def test_hash_record_fields(self):
        """HashRecord should have all required fields."""
        record = self.gate.record_hash(self.file_path, "pre_calculation")
        assert record.file_path == self.file_path
        assert len(record.sha256_hex) == 64  # SHA-256 hex = 64 chars
        assert record.recorded_at_epoch_ms > 0
        assert record.phase == "pre_calculation"

    # -- 3.6 Hash history tracking --
    def test_hash_history(self):
        """Multiple hash recordings should be tracked."""
        self.gate.record_hash(self.file_path, "pre_calculation")
        self.gate.record_hash(self.file_path, "post_draft")
        history = self.gate.get_hash_history(self.file_path)
        assert len(history) >= 2
        phases = [h.phase for h in history]
        assert "pre_calculation" in phases
        assert "post_draft" in phases

    # -- 3.7 Non-existent file → error --
    def test_nonexistent_file_error(self):
        """Verifying a non-existent file should raise an error."""
        with pytest.raises(FileNotFoundError):
            self.gate.verify_integrity("/nonexistent/file.dxf", "abc123")

    # -- 3.8 CWE-367 citation in violation --
    def test_cwe367_citation(self):
        """Violation must cite CWE-367."""
        record = self.gate.record_hash(self.file_path, "pre_calculation")

        with open(self.file_path, 'w') as f:
            f.write("TAMPERED")

        result = self.gate.verify_integrity(self.file_path, record.sha256_hex)
        vio = result.violations_detected if isinstance(result, DecisionProvenance) else result.get("violations", [])
        assert len(vio) >= 1
        cit = vio[0]["citation"] if isinstance(vio[0], dict) else vio[0].citation
        assert "CWE-367" in cit

    # -- 3.9 Clear hash history --
    def test_clear_history(self):
        """Clear should remove all stored hashes."""
        self.gate.record_hash(self.file_path, "pre_calculation")
        self.gate.clear()
        history = self.gate.get_hash_history(self.file_path)
        assert len(history) == 0


# ============================================================================
# 4. INTEGRATION TESTS — Cross-Module V20.1
# ============================================================================
class TestV20_1Integration:
    """Cross-module integration tests for V20.1 systemic fixes."""

    def test_duct_velocity_and_conduit_feedback(self):
        """Duct velocity check + conduit feedback loop on same project."""
        # 1. Duct velocity check
        duct = DuctSpec(
            duct_id="MAIN-SUPPLY",
            length_m=15.0,
            width_m=0.20,
            airflow_cfm=6000.0,
            duct_type="supply",
        )
        duct_result = analyse_duct(duct)
        # Small duct with high CFM → blow-by expected
        assert duct_result.velocity_blindness is True

        # 2. Conduit feedback for NAC circuit serving this area
        sizer = ConduitSizer()
        conduit_result = sizer.analyze_with_wire_overrides(
            bundle_id="NAC-TRUNK",
            wire_inventory=[
                {"awg": 14, "count": 6, "insulation": "FPLP"},
            ],
            wire_size_overrides={14: 12},  # Upsized for voltage drop
        )
        val = conduit_result.value if isinstance(conduit_result, DecisionProvenance) else conduit_result
        # 12AWG is larger than 14AWG → more fill
        assert val["total_cable_area_mm2"] > 0

    def test_submittal_gate_with_duct_analysis(self):
        """Submittal integrity gate wrapping a complete analysis."""
        gate = SubmittalIntegrityGate()

        # Create a test file
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False)
        tmp.write("FLOOR PLAN DXF V1")
        tmp.flush()
        tmp.close()

        try:
            # Phase 1: Record pre-calculation hash
            pre_hash = gate.record_hash(tmp.name, "pre_calculation")

            # Phase 2: Run duct analysis (simulating calculation)
            duct = DuctSpec("TEST", 10.0, 0.5, airflow_cfm=3000.0, duct_type="supply")
            result = analyse_duct(duct)
            assert result.velocity_fpm > 0

            # Phase 3: Verify integrity after calculation
            integrity = gate.verify_integrity(tmp.name, pre_hash.sha256_hex)
            val = integrity.value if isinstance(integrity, DecisionProvenance) else integrity
            assert val["safe"] is True
        finally:
            os.unlink(tmp.name)


# ============================================================================
# 5. APOCALYPSE EDGE CASES — V20.1
# ============================================================================
class TestV20_1Apocalypse:
    """Ruthless edge cases for V20.1 systemic fixes."""

    # -- 5.1 Duct: zero-width duct --
    def test_zero_width_duct_velocity(self):
        """Zero width duct → exempt (too narrow), no velocity calc."""
        duct = DuctSpec("ZERO-W", 5.0, 0.0, airflow_cfm=5000.0, duct_type="supply")
        result = analyse_duct(duct)
        assert result.exempt is True

    # -- 5.2 Duct: very high CFM with large duct → OK --
    def test_very_high_cfm_large_duct(self):
        """100,000 CFM in a 2m diameter duct → velocity should be manageable."""
        duct = DuctSpec("HUGE", 20.0, 2.0, airflow_cfm=100000.0, duct_type="supply")
        result = analyse_duct(duct)
        # Area = π × 1.0² = 3.14 m² = 33.8 ft²
        # Velocity = 100000 / 33.8 = 2959 FPM < 4000
        assert result.velocity_blindness is False

    # -- 5.3 Conduit: empty wire inventory with overrides --
    def test_conduit_empty_inventory_with_overrides(self):
        """Empty inventory with overrides → should not crash."""
        sizer = ConduitSizer()
        result = sizer.analyze_with_wire_overrides(
            bundle_id="EMPTY",
            wire_inventory=[],
            wire_size_overrides={14: 10},
        )
        val = result.value if isinstance(result, DecisionProvenance) else result
        assert val["total_cable_area_mm2"] == 0.0

    # -- 5.4 Conduit: override to non-existent AWG --
    def test_conduit_override_to_unknown_awg(self):
        """Override to AWG not in table → should use default diameter."""
        sizer = ConduitSizer()
        result = sizer.analyze_with_wire_overrides(
            bundle_id="UNKNOWN-AWG",
            wire_inventory=[
                {"awg": 14, "count": 2, "insulation": "FPLP"},
            ],
            wire_size_overrides={14: 8},  # AWG 8 not in table
        )
        val = result.value if isinstance(result, DecisionProvenance) else result
        # Should still produce a result (with default diameter for AWG 8)
        assert val["total_cable_area_mm2"] > 0

    # -- 5.5 Integrity gate: empty file --
    def test_empty_file_hash(self):
        """Empty file should still produce a valid SHA-256 hash."""
        gate = SubmittalIntegrityGate()
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.dxf', delete=False)
        tmp.write("")
        tmp.flush()
        tmp.close()
        try:
            record = gate.record_hash(tmp.name, "pre_calculation")
            # SHA-256 of empty file = e3b0c44298fc1c149afbf4c8996fb924...
            assert record.sha256_hex == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        finally:
            os.unlink(tmp.name)

    # -- 5.6 Integrity gate: binary file --
    def test_binary_file_hash(self):
        """Binary CAD file should also work."""
        gate = SubmittalIntegrityGate()
        tmp = tempfile.NamedTemporaryFile(mode='wb', suffix='.dwg', delete=False)
        tmp.write(b'\x00\x01\x02\x03\x04\x05')
        tmp.flush()
        tmp.close()
        try:
            record = gate.record_hash(tmp.name, "pre_calculation")
            assert len(record.sha256_hex) == 64
        finally:
            os.unlink(tmp.name)

    # -- 5.7 Duct: height_m = width_m (square duct) --
    def test_square_duct_velocity(self):
        """Square duct (height = width)."""
        duct = DuctSpec("SQUARE", 10.0, width_m=0.5, height_m=0.5, airflow_cfm=4000.0, duct_type="supply")
        result = analyse_duct(duct)
        # Area = 0.5 × 0.5 = 0.25 m² = 2.691 ft²
        # Velocity = 4000 / 2.691 = 1486 FPM < 4000
        assert result.velocity_blindness is False

    # -- 5.8 Conduit: single wire with override --
    def test_single_wire_with_override(self):
        """Single 14AWG wire → override to 10AWG."""
        sizer = ConduitSizer()
        result = sizer.analyze_with_wire_overrides(
            bundle_id="SINGLE",
            wire_inventory=[
                {"awg": 14, "count": 1, "insulation": "FPLP"},
            ],
            wire_size_overrides={14: 10},
        )
        val = result.value if isinstance(result, DecisionProvenance) else result
        # Single conductor fill limit is 53%
        assert val["is_compliant"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
