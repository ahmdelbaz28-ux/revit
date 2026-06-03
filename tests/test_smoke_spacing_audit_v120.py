"""
tests/test_smoke_spacing_audit_v120.py — Phase A Safety Net Tests (Finding #1)
================================================================================
V120 Phase A: WARNING log safety net for spot-type smoke detection above 20 ft.

This phase deliberately does NOT change any computed spacing values. The
existing 1%/ft reduction formula is preserved verbatim pending FPE review
(see /SMOKE_SPACING_AUDIT_FINDING_1.md).

These tests verify:
  1. Backward compatibility — all pre-V120 spacing values are UNCHANGED
  2. The new audit_notice key appears ONLY above 6.096 m (20 ft)
  3. The runtime WARNING log fires at the correct threshold
  4. The audit notice text correctly cites NFPA sections and alternatives

If/when Phase C lands (post-FPE review), these tests will be replaced
with the new contract.
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

from fireai.core.qomn_kernel import compute_smoke_detector_spacing


# ═══════════════════════════════════════════════════════════════════════════════
# V120 Phase A — Backward Compatibility (values UNCHANGED)
# ═══════════════════════════════════════════════════════════════════════════════


class TestV120BackwardCompatibility:
    """V120 Phase A is non-functional for numeric output — every pre-V120
    spacing value must be reproduced exactly. If any of these fails,
    Phase A has accidentally regressed Phase C scope."""

    def test_h_10ft_unchanged(self):
        """h=10ft (3.048m): table value 9.144m, no reduction → 9.144m."""
        r = compute_smoke_detector_spacing(3.048)
        assert r["listed_spacing_m"] == pytest.approx(9.144, abs=1e-3)

    def test_h_12ft_unchanged(self):
        """h=12ft (3.658m): 8.534 × 0.98 = 8.363m (pre-V120 behavior)."""
        r = compute_smoke_detector_spacing(3.658)
        # 8.534 × (1 - 0.01 × 2) = 8.534 × 0.98 = 8.36332
        assert r["listed_spacing_m"] == pytest.approx(8.534 * 0.98, abs=1e-3)

    def test_h_15ft_unchanged(self):
        """h=15ft (4.572m): 7.620 × 0.95 = 7.239m (pre-V120 behavior)."""
        r = compute_smoke_detector_spacing(4.572)
        assert r["listed_spacing_m"] == pytest.approx(7.620 * 0.95, abs=1e-3)

    def test_h_20ft_unchanged(self):
        """h=20ft (6.096m): 5.791 × 0.90 = 5.212m (pre-V120 behavior)."""
        r = compute_smoke_detector_spacing(6.096)
        assert r["listed_spacing_m"] == pytest.approx(5.791 * 0.90, abs=1e-3)

    def test_h_30ft_unchanged(self):
        """h=30ft (9.144m): 3.962 × 0.80 = 3.170m (pre-V120 behavior)."""
        r = compute_smoke_detector_spacing(9.144)
        assert r["listed_spacing_m"] == pytest.approx(3.962 * 0.80, abs=1e-3)

    def test_h_60ft_unchanged(self):
        """h=60ft (18.288m): 1.829 × 0.50 (floor) = 0.914m."""
        r = compute_smoke_detector_spacing(18.288)
        # max 50% reduction → factor = 0.50
        assert r["listed_spacing_m"] == pytest.approx(1.829 * 0.50, abs=1e-3)

    def test_coverage_radius_unchanged(self):
        """Coverage radius = 0.7 × spacing — invariant by V120."""
        for h in (3.0, 4.0, 5.0, 6.0, 9.0, 15.0):
            r = compute_smoke_detector_spacing(h)
            assert r["coverage_radius_m"] == pytest.approx(
                0.7 * r["listed_spacing_m"], rel=1e-4
            )

    def test_nfpa_section_unchanged(self):
        """The nfpa_section key must remain stable for downstream consumers."""
        r = compute_smoke_detector_spacing(3.0)
        assert "NFPA 72" in r["nfpa_section"]

    def test_computation_hash_present(self):
        """Audit hash still computed."""
        r = compute_smoke_detector_spacing(3.0)
        assert len(r["computation_hash"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# V120 Phase A — New audit_notice key (additive)
# ═══════════════════════════════════════════════════════════════════════════════


class TestV120AuditNoticeAdditive:
    """V120 Phase A adds an audit_notice key to the result dict above
    6.096 m. Low ceilings retain the EXACT pre-V120 dict shape."""

    def test_low_ceiling_no_audit_notice_key(self):
        """h ≤ 6.096 m: dict must NOT have audit_notice key
        (backward-compatible shape)."""
        for h in (1.0, 3.0, 4.0, 5.0, 6.0, 6.096):
            r = compute_smoke_detector_spacing(h)
            assert "audit_notice" not in r, (
                f"V120 Phase A regression: h={h}m unexpectedly carries "
                f"audit_notice. This breaks dict-shape backward compat."
            )

    def test_high_ceiling_includes_audit_notice(self):
        """h > 6.096 m: dict MUST include audit_notice key."""
        for h in (6.1, 7.0, 9.0, 12.0, 15.0, 18.0):
            r = compute_smoke_detector_spacing(h)
            assert "audit_notice" in r, (
                f"V120 Phase A failed: h={h}m missing audit_notice"
            )
            assert isinstance(r["audit_notice"], str)
            assert len(r["audit_notice"]) > 0

    def test_audit_notice_cites_stratification(self):
        """The notice must cite NFPA 72 §17.7.1.11 (stratification)."""
        r = compute_smoke_detector_spacing(10.0)
        assert "17.7.1.11" in r["audit_notice"]

    def test_audit_notice_offers_alternatives(self):
        """The notice must direct the operator toward beam, aspirating,
        OR performance-based design — never leaving them without guidance."""
        r = compute_smoke_detector_spacing(10.0)
        notice = r["audit_notice"].lower()
        assert "beam" in notice
        assert "aspirating" in notice or "air-sampling" in notice
        assert "performance-based" in notice or "annex b" in notice

    def test_audit_notice_references_audit_report(self):
        """The notice must point operators to the full audit report."""
        r = compute_smoke_detector_spacing(10.0)
        assert "SMOKE_SPACING_AUDIT_FINDING_1.md" in r["audit_notice"]

    def test_audit_notice_threshold_exact(self):
        """The threshold is EXACTLY 6.096 m (20 ft). 6.096 = no notice,
        6.097 = notice."""
        r_at = compute_smoke_detector_spacing(6.096)
        r_above = compute_smoke_detector_spacing(6.097)
        assert "audit_notice" not in r_at
        assert "audit_notice" in r_above


# ═══════════════════════════════════════════════════════════════════════════════
# V120 Phase A — Runtime WARNING log
# ═══════════════════════════════════════════════════════════════════════════════


class TestV120WarningLog:
    """V120 Phase A logs a WARNING at the kernel's logger when high-
    ceiling spot smoke detection is requested. This is non-blocking."""

    def test_warning_emitted_above_threshold(self, caplog):
        with caplog.at_level(logging.WARNING, logger="fireai.core.qomn_kernel"):
            compute_smoke_detector_spacing(10.0)
        warning_messages = [
            r.message for r in caplog.records
            if r.levelno == logging.WARNING
        ]
        assert any("V120 AUDIT WARNING" in m for m in warning_messages), (
            f"Expected V120 AUDIT WARNING log at h=10m; got: {warning_messages}"
        )

    def test_no_warning_below_threshold(self, caplog):
        with caplog.at_level(logging.WARNING, logger="fireai.core.qomn_kernel"):
            compute_smoke_detector_spacing(3.0)
        warning_messages = [
            r.message for r in caplog.records
            if r.levelno == logging.WARNING and "V120" in r.message
        ]
        assert not warning_messages, (
            f"V120 WARNING fired below threshold (h=3m): {warning_messages}"
        )

    def test_logging_failure_does_not_break_computation(self, monkeypatch):
        """If logging fails for any reason, the engineering computation
        MUST still return correctly. Per agent.md: 'logging failures must
        never break the engineering computation.'"""
        # Force logging.getLogger to raise — simulating a misconfigured environment
        import logging as _real_logging
        original_get_logger = _real_logging.getLogger

        def broken_get_logger(name):
            raise RuntimeError("Simulated logging failure")
        monkeypatch.setattr(_real_logging, "getLogger", broken_get_logger)

        # The call must still succeed and return the correct spacing
        try:
            r = compute_smoke_detector_spacing(10.0)
            assert r["listed_spacing_m"] > 0
            # Notice key still added (notice text is built independently of logging)
            assert "audit_notice" in r
        finally:
            monkeypatch.setattr(_real_logging, "getLogger", original_get_logger)


# ═══════════════════════════════════════════════════════════════════════════════
# V120 Phase A — Existing kernel exceptions preserved
# ═══════════════════════════════════════════════════════════════════════════════


class TestV120ExistingGuardsPreserved:
    """V120 must not weaken any pre-existing physics guards."""

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
