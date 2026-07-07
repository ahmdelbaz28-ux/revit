# NOSONAR
"""
tests/test_smoke_spacing_audit_v120.py — V130 Flat Smoke Spacing Audit Tests
=============================================================================
V130 CRITICAL FIX (2026-06-13): Smoke detector spacing is FLAT 9.1m per
NFPA 72-2022 §17.7.3.2.3 with NO height-based reduction.

V120 introduced the audit_notice key. V127 added height-adjusted spacing
from Table 17.6.3.1.1 (which incorrectly applied heat detector reduction
to smoke detectors). V130 corrects this to flat 9.1m per §17.7.3.2.3.

These tests verify:
  1. V130 flat spacing S=9.1m at ALL valid ceiling heights
  2. The audit_notice key appears ONLY above 6.096 m (20 ft) — stratification advisory
  3. The runtime WARNING log fires at the correct threshold (V130 advisory)
  4. The audit notice text correctly cites NFPA sections and alternatives
  5. Pre-existing physics guards are preserved
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest

from fireai.core.qomn_kernel import compute_smoke_detector_spacing

# ═══════════════════════════════════════════════════════════════════════════════
# V130 — Flat Spacing at ALL heights per §17.7.3.2.3
# ═══════════════════════════════════════════════════════════════════════════════


class TestV130FlatSpacing:
    """
    V130: Smoke detector spacing is FLAT 9.1m at ALL ceiling heights.
    Per NFPA 72-2022 §17.7.3.2.3: 30 ft (9.1 m) — NO height reduction.
    """

    @pytest.mark.parametrize("height", [
        3.0,     # 10 ft
        3.048,   # exactly 10 ft
        3.658,   # 12 ft
        4.572,   # 15 ft
        6.096,   # 20 ft
        9.144,   # 30 ft
        18.288,  # 60 ft (hard limit)
    ])
    def test_flat_spacing_at_various_heights(self, height):
        """Spacing must be 9.1m at ALL heights — flat per §17.7.3.2.3."""
        r = compute_smoke_detector_spacing(height)
        assert r["listed_spacing_m"] == pytest.approx(9.10, abs=1e-3), (
            f"At h={height}m, expected S=9.1m (flat per §17.7.3.2.3), "
            f"got S={r['listed_spacing_m']}m"
        )

    def test_coverage_radius(self):
        """Coverage radius = 0.7 × spacing per NFPA 72 §17.7.4.2.3.1."""
        for h in (3.0, 4.0, 5.0, 6.0, 9.0, 15.0):
            r = compute_smoke_detector_spacing(h)
            assert r["coverage_radius_m"] == pytest.approx(
                0.7 * r["listed_spacing_m"], rel=1e-4
            )

    def test_nfpa_section_in_result(self):
        """The nfpa_section key must cite §17.7.3.2.3."""
        r = compute_smoke_detector_spacing(3.0)
        assert "NFPA 72" in r["nfpa_section"]
        assert "17.7.3.2.3" in r["nfpa_section"]

    def test_computation_hash_present(self):
        """Audit hash still computed."""
        r = compute_smoke_detector_spacing(3.0)
        assert len(r["computation_hash"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# V130 — Audit Notice (stratification advisory for h > 6.096m)
# ═══════════════════════════════════════════════════════════════════════════════


class TestV130AuditNotice:
    """
    V130 adds an audit_notice key for h > 6.096m (stratification advisory).
    Low ceilings have no audit_notice key (backward-compatible shape).
    """

    def test_low_ceiling_no_audit_notice_key(self):
        """
        H ≤ 6.096 m: dict must NOT have audit_notice key
        (backward-compatible shape).
        """
        for h in (1.0, 3.0, 4.0, 5.0, 6.0, 6.096):
            r = compute_smoke_detector_spacing(h)
            assert "audit_notice" not in r, (
                f"V120 Phase A regression: h={h}m unexpectedly carries "
                f"audit_notice. This breaks dict-shape backward compat."
            )

    def test_high_ceiling_includes_audit_notice(self):
        """H > 6.096 m: dict MUST include audit_notice key."""
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
        assert "17.7.1.11" in r["audit_notice"]  # NOSONAR - python:S1313

    def test_audit_notice_offers_alternatives(self):
        """
        The notice must direct the operator toward beam, aspirating,
        OR performance-based design — never leaving them without guidance.
        """
        r = compute_smoke_detector_spacing(10.0)
        notice = r["audit_notice"].lower()
        assert "beam" in notice
        assert "aspirating" in notice or "air-sampling" in notice
        assert "performance-based" in notice or "annex b" in notice

    def test_audit_notice_references_v130_correction(self):
        """V130: The notice must reference the V130 correction (flat spacing)."""
        r = compute_smoke_detector_spacing(10.0)
        assert "V130" in r["audit_notice"]

    def test_audit_notice_confirms_flat_spacing(self):
        """V130: The notice must confirm 9.1m flat spacing per §17.7.3.2.3."""
        r = compute_smoke_detector_spacing(10.0)
        notice = r["audit_notice"]
        assert "9.1m" in notice
        assert "17.7.3.2.3" in notice

    def test_audit_notice_threshold_exact(self):
        """
        The threshold is EXACTLY 6.096 m (20 ft). 6.096 = no notice,
        6.097 = notice.
        """
        r_at = compute_smoke_detector_spacing(6.096)
        r_above = compute_smoke_detector_spacing(6.097)
        assert "audit_notice" not in r_at
        assert "audit_notice" in r_above


# ═══════════════════════════════════════════════════════════════════════════════
# V130 — Runtime WARNING log
# ═══════════════════════════════════════════════════════════════════════════════


class TestV130WarningLog:
    """
    V130 logs a WARNING at the kernel's logger when high-
    ceiling spot smoke detection is requested. This is non-blocking.
    """

    def test_warning_emitted_above_threshold(self, caplog):
        with caplog.at_level(logging.WARNING, logger="fireai.core.qomn_kernel"):
            compute_smoke_detector_spacing(10.0)
        warning_messages = [
            r.message for r in caplog.records
            if r.levelno == logging.WARNING
        ]
        assert any("V130" in m or "stratification" in m.lower() for m in warning_messages), (
            f"Expected V130 ADVISORY log at h=10m; got: {warning_messages}"
        )

    def test_no_warning_below_threshold(self, caplog):
        with caplog.at_level(logging.WARNING, logger="fireai.core.qomn_kernel"):
            compute_smoke_detector_spacing(3.0)
        warning_messages = [
            r.message for r in caplog.records
            if r.levelno == logging.WARNING and ("V130" in r.message or "V120" in r.message)
        ]
        assert not warning_messages, (
            f"V130 ADVISORY fired below threshold (h=3m): {warning_messages}"
        )

    def test_logging_failure_does_not_break_computation(self, monkeypatch):
        """
        If logging fails for any reason, the engineering computation
        MUST still return correctly. Per agent.md: 'logging failures must
        never break the engineering computation.'
        """
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
# V120 Phase A — Existing kernel exceptions preserved
# ═══════════════════════════════════════════════════════════════════════════════


class TestV120ExistingGuardsPreserved:
    """V120 must not weaken any pre-existing physics guards."""

    def test_nan_still_rejected(self):
        from fireai.core.qomn_kernel import PhysicsGuardError
        with pytest.raises(PhysicsGuardError):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
            compute_smoke_detector_spacing(float("nan"))

    def test_inf_still_rejected(self):
        from fireai.core.qomn_kernel import PhysicsGuardError
        with pytest.raises(PhysicsGuardError):  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # noqa: S5778
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
            compute_smoke_detector_spacing(18.5)
