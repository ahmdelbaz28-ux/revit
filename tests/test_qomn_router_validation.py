"""
tests/test_qomn_router_validation.py — QOMN Router Input Validation Tests
==========================================================================
Validates the Pydantic request models in backend/routers/qomn.py for the
QOMN-FIRE engineering kernel HTTP API.

V118 FIX (Finding #3): Previously, the router's `awg_gauge` regex accepted
6 AWG values (3, 250, 300, 350, 400, 500) that DO NOT EXIST in the kernel's
NEC_TABLE8_RESISTANCE_OHM_PER_KM table — a false-advertising bug per
agent.md Anti-Deception Directive. This file enforces that:

  1. Router-accepted AWG set == Kernel table keys (single source of truth)
  2. AWG normalization matches the kernel logic exactly
     (.strip().upper().replace("AWG","").strip())
  3. User-friendly variants ("AWG14", "14 ", "awg 1/0") all normalize
     correctly BEFORE reaching the kernel
  4. Any AWG that passes the router is GUARANTEED to be accepted by the
     kernel (no split-brain validation)

Safety-Critical: AWG validation determines wire resistance used in voltage
drop calculations. An incorrect AWG → incorrect voltage drop → potentially
under-powered notification appliance → silent alarm in a real fire.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path for module resolution
_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
from pydantic import ValidationError

from backend.routers.qomn import (
    VoltageDropRequest,
    _NEC_TABLE8_VALID_AWG,
    _normalize_awg_gauge,
)
from fireai.core.qomn_kernel import NEC_TABLE8_RESISTANCE_OHM_PER_KM


# ═══════════════════════════════════════════════════════════════════════════════
# V118 — AWG Normalization Tests (validator behavior)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAWGNormalization:
    """The validator must normalize identically to the kernel."""

    def test_plain_numeric(self):
        r = VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge="14")
        assert r.awg_gauge == "14"

    def test_awg_prefix_stripped(self):
        """V118: 'AWG14' must be accepted (matches kernel behavior)."""
        r = VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge="AWG14")
        assert r.awg_gauge == "14"

    def test_trailing_whitespace_stripped(self):
        """V118: '14 ' must be accepted (matches kernel behavior)."""
        r = VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge="14 ")
        assert r.awg_gauge == "14"

    def test_leading_whitespace_stripped(self):
        r = VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge=" 14")
        assert r.awg_gauge == "14"

    def test_case_insensitive(self):
        """V118: 'awg 14' (lowercase, space) must normalize to '14'."""
        r = VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge="awg 14")
        assert r.awg_gauge == "14"

    def test_aught_sizes(self):
        """1/0, 2/0, 3/0, 4/0 (aught sizes) must work."""
        for aught in ("1/0", "2/0", "3/0", "4/0"):
            r = VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge=aught)
            assert r.awg_gauge == aught

    def test_aught_with_awg_prefix(self):
        """V118: 'AWG 1/0' must normalize to '1/0'."""
        r = VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge="AWG 1/0")
        assert r.awg_gauge == "1/0"

    def test_default_applied(self):
        """When omitted, default '14' is used."""
        r = VoltageDropRequest(current_a=1.0, length_m=100.0)
        assert r.awg_gauge == "14"


# ═══════════════════════════════════════════════════════════════════════════════
# V118 — False-Accept Regression Tests
# Historic regex accepted these but kernel rejected them (split-brain).
# ═══════════════════════════════════════════════════════════════════════════════


class TestHistoricFalseAcceptsRejected:
    """V118: These values were silently accepted by the V65 router regex
    but rejected by the kernel — a deceptive HTTP API contract."""

    @pytest.mark.parametrize("bad_awg", ["3", "250", "300", "350", "400", "500"])
    def test_kernel_unsupported_awg_now_rejected_at_router(self, bad_awg):
        """V118 FIX: These 6 sizes exist in NEC for power circuits but
        are not in our fire-alarm-relevant NEC_TABLE8_RESISTANCE_OHM_PER_KM.
        Router previously accepted them, then kernel raised ValueError →
        user got an opaque error. Now the router rejects them upfront with
        a clear list of valid options."""
        # Sanity: confirm the kernel really does NOT have these
        assert bad_awg not in NEC_TABLE8_RESISTANCE_OHM_PER_KM, (
            f"Test premise wrong: kernel actually supports {bad_awg}; "
            "this test should be removed."
        )
        with pytest.raises(ValidationError) as exc_info:
            VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge=bad_awg)
        # Error message must point user to the valid set
        assert "not in NEC Table 8" in str(exc_info.value)


class TestTrulyInvalidRejected:
    """Inputs that have never been valid must still be rejected."""

    def test_unknown_gauge_rejected(self):
        with pytest.raises(ValidationError):
            VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge="99")

    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError):
            VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge="")

    def test_whitespace_only_rejected(self):
        with pytest.raises(ValidationError):
            VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge="   ")

    def test_integer_rejected(self):
        """awg_gauge must be a string per the API contract."""
        with pytest.raises(ValidationError):
            VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge=14)

    def test_garbage_rejected(self):
        with pytest.raises(ValidationError):
            VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge="!!INVALID!!")


# ═══════════════════════════════════════════════════════════════════════════════
# V118 — Kernel/Router Contract Tests (single source of truth)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRouterKernelContract:
    """The router's accepted AWG set MUST equal the kernel's table keys."""

    def test_router_set_equals_kernel_table_keys(self):
        """V118 FIX: This was the root cause — the regex and the table
        diverged. They must now be a single source of truth."""
        kernel_keys = set(NEC_TABLE8_RESISTANCE_OHM_PER_KM.keys())
        router_keys = set(_NEC_TABLE8_VALID_AWG)
        assert router_keys == kernel_keys, (
            f"Router/kernel AWG sets diverged again! "
            f"router-only={router_keys - kernel_keys}, "
            f"kernel-only={kernel_keys - router_keys}"
        )

    def test_every_router_accepted_value_works_in_kernel(self):
        """Belt-and-braces: independently verify each accepted value
        actually returns a valid voltage drop computation."""
        from fireai.core.qomn_kernel import compute_voltage_drop
        for awg in sorted(_NEC_TABLE8_VALID_AWG):
            r = VoltageDropRequest(current_a=1.0, length_m=100.0, awg_gauge=awg)
            result = compute_voltage_drop(1.0, 100.0, r.awg_gauge)
            assert result["voltage_drop_v"] > 0, (
                f"AWG {awg!r} passed router but kernel produced invalid result"
            )

    def test_normalization_function_idempotent(self):
        """Applying _normalize_awg_gauge twice must equal applying once."""
        for raw in ("AWG14", "14 ", "awg 1/0", "  AWG  4/0  "):
            once = _normalize_awg_gauge(raw)
            twice = _normalize_awg_gauge(once)
            assert once == twice, f"Not idempotent on {raw!r}: {once!r} → {twice!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# Other VoltageDropRequest field validations (defense-in-depth checks)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOtherFieldValidation:
    """Verify non-AWG validations still work after the V118 refactor."""

    def test_negative_current_rejected(self):
        with pytest.raises(ValidationError):
            VoltageDropRequest(current_a=-1.0, length_m=100.0)

    def test_zero_current_rejected(self):
        with pytest.raises(ValidationError):
            VoltageDropRequest(current_a=0.0, length_m=100.0)

    def test_negative_length_rejected(self):
        with pytest.raises(ValidationError):
            VoltageDropRequest(current_a=1.0, length_m=-100.0)

    def test_max_drop_pct_upper_bound(self):
        """max_drop_pct ≤ 50."""
        VoltageDropRequest(current_a=1.0, length_m=100.0, max_drop_pct=50.0)
        with pytest.raises(ValidationError):
            VoltageDropRequest(current_a=1.0, length_m=100.0, max_drop_pct=51.0)
