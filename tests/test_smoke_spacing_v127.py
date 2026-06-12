"""
tests/test_smoke_spacing_v127.py — V127 Phase C Corrected Smoke Spacing Tests
=============================================================================
V127 Phase C: The 1%/ft reduction misapplication has been corrected.
Per NFPA 72-2022 §17.7.3.2.3.1, smoke detectors use a FLAT nominal
spacing of 30 ft (9.1 m) with NO per-foot height reduction.

The height-adjusted spacing values from NFPA 72 Table 17.6.3.1.1 are
now used directly from the canonical source (fireai/constants/__init__.py),
with NO additional scalar reduction applied.

These tests verify:
  1. Correct spacing values per NFPA 72 Table 17.6.3.1.1 (no 1%/ft reduction)
  2. The audit_notice key appears above 6.096 m (20 ft)
  3. The runtime WARNING log fires at the correct threshold
  4. The audit notice text correctly cites NFPA sections and alternatives
  5. Pre-existing physics guards are preserved
  6. Consistency with fireai/constants/__init__.py (single source of truth)
"""

from __future__ import annotations

import logging
import math
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest

from fireai.core.qomn_kernel import compute_smoke_detector_spacing, NFPA72_SMOKE_MAX_SPACING_M
from fireai.constants import SMOKE_MAX_SPACING_M, NFPA72_HEIGHT_SPACING_TABLE


# ═══════════════════════════════════════════════════════════════════════════════
# V127 Phase C — Corrected Spacing Values (no 1%/ft reduction)
# ═══════════════════════════════════════════════════════════════════════════════


class TestV127CorrectedSpacing:
    """V127 Phase C: The 1%/ft reduction has been removed.
    Spacing values now match NFPA 72 Table 17.6.3.1.1 directly."""

    def test_h_3m_correct_spacing(self):
        """h=3.0m: Table 17.6.3.1.1 → S=9.10m (no reduction applied)."""
        r = compute_smoke_detector_spacing(3.0)
        assert r["listed_spacing_m"] == pytest.approx(9.10, abs=1e-3)

    def test_h_3_7m_correct_spacing(self):
        """h=3.7m: Table 17.6.3.1.1 → S=8.70m (no reduction applied)."""
        r = compute_smoke_detector_spacing(3.7)
        assert r["listed_spacing_m"] == pytest.approx(8.70, abs=1e-3)

    def test_h_4_6m_correct_spacing(self):
        """h=4.6m: Table 17.6.3.1.1 → S=8.20m (no reduction applied).
        Previously: 7.620 × 0.95 = 7.239m (WRONG — 1%/ft reduction)."""
        r = compute_smoke_detector_spacing(4.6)
        assert r["listed_spacing_m"] == pytest.approx(8.20, abs=1e-3)

    def test_h_6_1m_correct_spacing(self):
        """h=6.1m: Table 17.6.3.1.1 → S=7.30m (no reduction applied).
        Previously: 5.791 × 0.90 = 5.212m (WRONG — 1%/ft reduction)."""
        r = compute_smoke_detector_spacing(6.1)
        assert r["listed_spacing_m"] == pytest.approx(7.30, abs=1e-3)

    def test_h_9_1m_correct_spacing(self):
        """h=9.1m: Table 17.6.3.1.1 → S=6.40m (no reduction applied)."""
        r = compute_smoke_detector_spacing(9.1)
        assert r["listed_spacing_m"] == pytest.approx(6.40, abs=1e-3)

    def test_h_12_2m_correct_spacing(self):
        """h=12.2m: Table 17.6.3.1.1 max → S=5.60m (no reduction applied)."""
        r = compute_smoke_detector_spacing(12.2)
        assert r["listed_spacing_m"] == pytest.approx(5.60, abs=1e-3)

    def test_h_above_table_uses_fallback(self):
        """h=15.0m > 12.2m: Beyond NFPA table → conservative fallback 5.20m."""
        r = compute_smoke_detector_spacing(15.0)
        assert r["listed_spacing_m"] == pytest.approx(5.20, abs=1e-3)

    def test_h_max_boundary_18_288m(self):
        """h=18.288m (60 ft): Maximum allowed by guard, uses fallback."""
        r = compute_smoke_detector_spacing(18.288)
        assert r["listed_spacing_m"] == pytest.approx(5.20, abs=1e-3)

    def test_spacing_never_exceeds_max(self):
        """All spacings must be ≤ NFPA72_SMOKE_MAX_SPACING_M (9.10 m)."""
        for h in (1.0, 2.0, 3.0, 4.0, 6.0, 9.0, 12.0, 15.0, 18.0):
            r = compute_smoke_detector_spacing(h)
            assert r["listed_spacing_m"] <= NFPA72_SMOKE_MAX_SPACING_M + 1e-6

    def test_higher_ceiling_not_greater_spacing(self):
        """Higher ceiling should not produce greater spacing than low ceiling.
        (Within table range, spacing decreases; above table, fallback is used.)"""
        r_low = compute_smoke_detector_spacing(3.0)
        for h in (4.0, 6.0, 9.0, 12.0, 15.0):
            r_high = compute_smoke_detector_spacing(h)
            assert r_high["listed_spacing_m"] <= r_low["listed_spacing_m"] + 1e-6


class TestV127CoverageRadius:
    """Coverage radius = 0.7 × spacing per NFPA 72 §17.7.4.2.3.1."""

    def test_coverage_radius_at_all_heights(self):
        """R = 0.7 × S at all ceiling heights."""
        for h in (2.0, 3.0, 4.6, 6.1, 9.1, 12.2, 15.0, 18.0):
            r = compute_smoke_detector_spacing(h)
            assert r["coverage_radius_m"] == pytest.approx(
                0.7 * r["listed_spacing_m"], rel=1e-4
            )

    def test_coverage_radius_h3m(self):
        """h=3.0m: R = 0.7 × 9.10 = 6.37m."""
        r = compute_smoke_detector_spacing(3.0)
        assert r["coverage_radius_m"] == pytest.approx(0.7 * 9.10, rel=1e-3)


class TestV127ConsistencyWithConstants:
    """V127: qomn_kernel spacing must be consistent with constants/__init__.py."""

    def test_max_spacing_matches_constants(self):
        """NFPA72_SMOKE_MAX_SPACING_M in kernel must match constants module."""
        assert NFPA72_SMOKE_MAX_SPACING_M == SMOKE_MAX_SPACING_M

    def test_table_values_match_constants(self):
        """Spacing table in kernel must match NFPA72_HEIGHT_SPACING_TABLE in constants."""
        from fireai.core.qomn_kernel import NFPA72_SMOKE_SPACING_TABLE
        for (h_kernel, s_kernel), (h_const, s_const, _heat) in zip(
            NFPA72_SMOKE_SPACING_TABLE, NFPA72_HEIGHT_SPACING_TABLE
        ):
            assert h_kernel == pytest.approx(h_const, abs=0.01)
            assert s_kernel == pytest.approx(s_const, abs=0.01)


# ═══════════════════════════════════════════════════════════════════════════════
# V127 — Audit Notice (retained from V120, updated for V127)
# ═══════════════════════════════════════════════════════════════════════════════


class TestV127AuditNotice:
    """V127: audit_notice appears above 6.096 m, updated for Phase C correction."""

    def test_low_ceiling_no_audit_notice(self):
        """h ≤ 6.096 m: dict must NOT have audit_notice key."""
        for h in (1.0, 3.0, 4.0, 5.0, 6.0, 6.096):
            r = compute_smoke_detector_spacing(h)
            assert "audit_notice" not in r, (
                f"h={h}m unexpectedly carries audit_notice."
            )

    def test_high_ceiling_includes_audit_notice(self):
        """h > 6.096 m: dict MUST include audit_notice key."""
        for h in (6.1, 7.0, 9.0, 12.0, 15.0, 18.0):
            r = compute_smoke_detector_spacing(h)
            assert "audit_notice" in r, f"h={h}m missing audit_notice"

    def test_audit_notice_cites_stratification(self):
        """The notice must cite §17.7.1.11 (stratification)."""
        r = compute_smoke_detector_spacing(10.0)
        assert "17.7.1.11" in r["audit_notice"]

    def test_audit_notice_offers_alternatives(self):
        """The notice must direct toward beam, aspirating, or performance-based."""
        r = compute_smoke_detector_spacing(10.0)
        notice = r["audit_notice"].lower()
        assert "beam" in notice
        assert "aspirating" in notice or "air-sampling" in notice
        assert "performance-based" in notice or "annex b" in notice

    def test_audit_notice_references_v127_correction(self):
        """V127: The notice must reference the Phase C correction."""
        r = compute_smoke_detector_spacing(10.0)
        assert "V127" in r["audit_notice"]

    def test_audit_notice_threshold_exact(self):
        """The threshold is EXACTLY 6.096 m. 6.096 = no notice, 6.097 = notice."""
        r_at = compute_smoke_detector_spacing(6.096)
        r_above = compute_smoke_detector_spacing(6.097)
        assert "audit_notice" not in r_at
        assert "audit_notice" in r_above


# ═══════════════════════════════════════════════════════════════════════════════
# V127 — Runtime WARNING log (retained from V120)
# ═══════════════════════════════════════════════════════════════════════════════


class TestV127WarningLog:
    """V127: WARNING log at high-ceiling spot smoke detection."""

    def test_warning_emitted_above_threshold(self, caplog):
        with caplog.at_level(logging.WARNING, logger="fireai.core.qomn_kernel"):
            compute_smoke_detector_spacing(10.0)
        warning_messages = [
            r.message for r in caplog.records
            if r.levelno == logging.WARNING
        ]
        assert any("V127" in m or "stratification" in m.lower() for m in warning_messages)

    def test_no_warning_below_threshold(self, caplog):
        with caplog.at_level(logging.WARNING, logger="fireai.core.qomn_kernel"):
            compute_smoke_detector_spacing(3.0)
        warning_messages = [
            r.message for r in caplog.records
            if r.levelno == logging.WARNING and ("V127" in r.message or "V120" in r.message)
        ]
        assert not warning_messages

    def test_logging_failure_does_not_break_computation(self, monkeypatch):
        """If logging fails, computation MUST still return correctly."""
        import logging as _real_logging
        original_get_logger = _real_logging.getLogger

        def broken_get_logger(name):
            raise RuntimeError("Simulated logging failure")
        monkeypatch.setattr(_real_logging, "getLogger", broken_get_logger)

        try:
            r = compute_smoke_detector_spacing(10.0)
            assert r["listed_spacing_m"] > 0
            assert "audit_notice" in r
        finally:
            monkeypatch.setattr(_real_logging, "getLogger", original_get_logger)


# ═══════════════════════════════════════════════════════════════════════════════
# V127 — Existing kernel exceptions preserved
# ═══════════════════════════════════════════════════════════════════════════════


class TestV127ExistingGuardsPreserved:
    """V127 must not weaken any pre-existing physics guards."""

    def test_nan_still_rejected(self):
        from fireai.core.qomn_kernel import PhysicsGuardError
        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(float("nan"))

    def test_inf_still_rejected(self):
        from fireai.core.qomn_kernel import PhysicsGuardError
        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(float("inf"))

    def test_negative_still_rejected(self):
        from fireai.core.qomn_kernel import PhysicsGuardError
        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(-1.0)

    def test_zero_still_rejected(self):
        from fireai.core.qomn_kernel import PhysicsGuardError
        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(0.0)

    def test_above_18288m_still_rejected(self):
        """NFPA global scope ceiling unchanged at 18.288 m."""
        from fireai.core.qomn_kernel import PhysicsGuardError
        with pytest.raises(PhysicsGuardError):
            compute_smoke_detector_spacing(20.0)
