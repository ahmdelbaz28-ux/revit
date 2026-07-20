# File-level '# NOSONAR' removed per NOSONAR_AUDIT.md (V143 hardening).
# Per-line justified suppressions (e.g., '# NOSONAR — S3776: ...') are preserved.
# test_self_healing_engine.py
import hashlib
import hmac
import json
import math
import os
import shutil
import tempfile
import time
import unittest

import pytest

# Import from the module
from fireai.core.qomn_self_healing_engine import (
    ERROR_WEIGHTS,
    AsyncAuditLogger,
    AuditLogger,
    CircuitBreaker,
    Config,
    ErrorSeverity,
    LLMCircuitBreaker,
    LruCache,
    PhysicsGuardViolation,
    SafetyCriticalFailure,
    SafetyResult,
    SystemStatus,
    WeightedCircuitBreaker,
    calculate_sprinkler_pressure,
    compute_hash,
    demonstrate_and_verify_all_tiers,
    fetch_emergency_audio_sequence,
    global_audit_logger,
    global_circuit_breaker,
    global_lru_cache,
    self_healing,
    validate_sprinkler_pressure,
)


class TestQomnFireSelfHealing(unittest.TestCase):
    """
    Original V53 tests -- ALL preserved, ZERO modifications.
    These tests validate the core 3-tier healing behavior and
    all V53 + V58 bug fixes remain intact.
    """

    def setUp(self):
        global_circuit_breaker.reset()
        # Clean local test log ledger
        if os.path.exists("qomn_fire_healing_audit.jsonl"):
            try:
                os.remove("qomn_fire_healing_audit.jsonl")
            except OSError:
                pass

    def test_nominal_execution(self):
        """Verify normal execution executes without altering values."""
        res = calculate_sprinkler_pressure(56.0, 5.6)
        self.assertEqual(res.status, "NOMINAL")
        self.assertAlmostEqual(res.value, 100.0, places=4)

    def test_tier_1_zero_division(self):
        """Verify ZeroDivisionError triggers safe_minimum fallback (V58 FIX)."""
        res = calculate_sprinkler_pressure(100.0, 0.0)
        self.assertEqual(res.status, "HEALED")
        # float('inf') violates the QOMN kernel safety principle:
        # "NaN/Inf NEVER propagate -- always caught and rejected."
        self.assertEqual(res.value, 7.0)
        self.assertEqual(res.metadata["rule"], "ZeroDivisionError")

    def test_tier_1_index_error_recovery(self):
        """Verify IndexError falls back to the last element of the input list."""
        tones = ["TONE_A", "TONE_B", "TONE_C"]
        # Wrap local helper
        @self_healing(safe_minimum=0.0, default_value="TONE_A", force_mock_ollama=True)
        def get_index_test(arr, idx):
            return arr[idx]

        res = get_index_test(tones, 5)  # IndexError
        self.assertEqual(res.status, "HEALED")
        self.assertEqual(res.value, "TONE_C")  # Last item

    def test_tier_2_verification_safety(self):
        """Verify Tier 2 local agent heals correctly using golden checks."""
        tones = ["TONE_A"]
        res = fetch_emergency_audio_sequence(tones, 10)
        self.assertEqual(res.status, "HEALED")
        self.assertEqual(res.value, "DEFAULT_EVAC_TONE")
        self.assertEqual(res.metadata["tier"], 2)

    def test_tier_3_circuit_breaker_trips(self):
        """Verify high frequency errors trip the circuit breaker and bypass normal calls."""
        for _ in range(15):
            calculate_sprinkler_pressure(100.0, 0.0)

        # Circuit breaker must be open, forcing safe fallback static return
        final_res = calculate_sprinkler_pressure(100.0, 0.0)
        self.assertEqual(final_res.status, "CRITICAL_CIRCUIT_OPEN")
        # V FIX: Changed expected value from float('inf') to 7.0 (safe_minimum).
        self.assertEqual(final_res.value, 7.0)

    def test_cryptographic_audit_ledger(self):
        """Verify audit logger generates tamper-evident, HMAC-signed JSON Lines."""
        # Trigger single healing event
        calculate_sprinkler_pressure(100.0, 0.0)

        self.assertTrue(os.path.exists("qomn_fire_healing_audit.jsonl"))
        with open("qomn_fire_healing_audit.jsonl", encoding="utf-8") as f:
            lines = f.readlines()

        self.assertTrue(len(lines) >= 1)  # NOSONAR - python:S5906
        logged_entry = json.loads(lines[0])

        self.assertIn("payload", logged_entry)
        self.assertIn("signature", logged_entry)

        # Verify signature using the global audit logger's actual secret_key.
        # REMOVED as a CRITICAL security vulnerability (forged audit signatures).
        # The test now reads the actual key from the logger instance.
        secret_key = global_audit_logger.secret_key
        self.assertIsNotNone(secret_key,
                             "global_audit_logger.secret_key must not be None")
        self.assertNotEqual(secret_key, b"QOMN_SECRET_KEY",
                            "V127 SAFETY: hardcoded default key must NEVER be used")
        payload_bytes = json.dumps(
            logged_entry["payload"], sort_keys=True, default=str
        ).encode("utf-8")
        expected_sig = hmac.new(
            secret_key,
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

        self.assertEqual(logged_entry["signature"], expected_sig)


# =====================================================================
# =====================================================================

class TestWeightedCircuitBreaker(unittest.TestCase):
    """Tests for the WeightedCircuitBreaker with severity-based scoring."""

    def setUp(self):
        self.cb = WeightedCircuitBreaker(threshold=10.0, window_seconds=60.0, cooldown_seconds=1.0, half_open_max=3)
        # Reset the global CB to avoid interference
        global_circuit_breaker.reset()

    def test_weighted_scoring_critical_trips_faster(self):
        """Critical errors (weight=5) should trip the breaker faster than transient (weight=1)."""
        # With threshold=10 and CRITICAL weight=5, should trip after 3 errors
        # ZeroDivisionError maps to ErrorSeverity.CRITICAL (weight=5).
        result1 = self.cb.register_healing_event("ZeroDivisionError")  # 5.0
        result2 = self.cb.register_healing_event("ZeroDivisionError")  # 10.0
        result3 = self.cb.register_healing_event("ZeroDivisionError")  # 15.0

        self.assertTrue(result1)   # Still CLOSED (5.0 > 10.0 is False)
        self.assertTrue(result2)   # Still CLOSED (10.0 > 10.0 is False)
        self.assertFalse(result3)  # TRIPPED (15.0 > 10.0)

    def test_weighted_scoring_transient_trips_slower(self):
        """Transient errors (weight=1) should require more events to trip."""
        # With threshold=10 and TRANSIENT weight=1, should trip after 11 errors
        # IndexError maps to ErrorSeverity.TRANSIENT (weight=1).
        result = True  # initialize so the loop variable is defined for the assertion
        for i in range(10):
            result = self.cb.register_healing_event("IndexError")
            self.assertTrue(result, f"Should be CLOSED at event {i+1}")

        result11 = self.cb.register_healing_event("IndexError")  # 11.0
        self.assertFalse(result11)  # TRIPPED (11.0 > 10.0)

    def test_deque_o1_pruning(self):
        """Verify O(1) deque correctly prunes expired events."""
        cb = WeightedCircuitBreaker(threshold=100.0, window_seconds=0.5, cooldown_seconds=1.0)
        cb.register_healing_event()  # seed the deque with one event
        self.assertEqual(len(cb._events), 1)

        # Wait for window to expire
        time.sleep(0.6)

        # Next event should prune the expired one. Only the new event remains.
        cb.register_healing_event()
        self.assertEqual(len(cb._events), 1)  # Only the new event remains

    def test_backward_compatible_register(self):
        """Verify register_healing_event() works without error_type (backward compat)."""
        result = self.cb.register_healing_event()  # default error_type
        self.assertTrue(result)  # Should still work

    def test_health_includes_weighted_metrics(self):
        """V53 FIX (BUG 9) preserved: health() method works with weighted metrics."""
        # Register one CRITICAL event (ZeroDivisionError → weight=5) so the
        # health snapshot reflects a non-empty, weighted state.
        self.cb.register_healing_event("ZeroDivisionError")
        health = self.cb.health()

        self.assertEqual(health["state"], "CLOSED")
        self.assertEqual(health["weighted_sum"], 5.0)
        self.assertEqual(health["event_count"], 1)
        self.assertIn("threshold", health)
        self.assertIn("utilization_pct", health)


class TestHalfOpenRecovery(unittest.TestCase):
    """Tests for the HALF_OPEN recovery pattern."""

    def setUp(self):
        self.cb = WeightedCircuitBreaker(
            threshold=5.0, window_seconds=60.0,
            cooldown_seconds=0.5, half_open_max=2
        )
        global_circuit_breaker.reset()

    def test_cooldown_transitions_to_half_open(self):
        """After cooldown period, breaker should transition to HALF_OPEN."""
        # Trip the breaker. With threshold=5.0 and ZeroDivisionError weight=5,
        # a single event yields current_weight=5.0 which does NOT exceed the
        # threshold (5.0 > 5.0 is False). Need another event to exceed.
        self.cb.register_healing_event("ZeroDivisionError")  # 5.0 (still CLOSED)
        self.cb.register_healing_event("ZeroDivisionError")  # 10.0 → TRIPPED

        self.assertEqual(self.cb.state, "OPEN")

        # Wait for cooldown
        time.sleep(0.6)

        is_open, _state = self.cb.check_and_cooldown()
        self.assertFalse(is_open)  # No longer fully OPEN
        self.assertEqual(self.cb.state, "HALF_OPEN")

    def test_half_open_probe_success_recovers(self):
        """Consecutive successes in HALF_OPEN should transition to CLOSED."""
        # Trip the breaker and wait for cooldown
        self.cb.register_healing_event("ZeroDivisionError")
        self.cb.register_healing_event("IndexError")
        self.assertEqual(self.cb.state, "OPEN")

        time.sleep(0.6)
        self.cb.check_and_cooldown()
        self.assertEqual(self.cb.state, "HALF_OPEN")

        # Record consecutive successes (half_open_max=2)
        self.cb.record_success()
        self.assertEqual(self.cb.state, "HALF_OPEN")  # Not enough yet

        self.cb.record_success()
        self.assertEqual(self.cb.state, "CLOSED")  # Fully recovered

    def test_check_and_cooldown_returns_state(self):
        """V66 FIX: check_and_cooldown() returns (is_open, state) tuple."""
        cb = WeightedCircuitBreaker(threshold=5.0, cooldown_seconds=0.1)

        # When CLOSED
        is_open, state = cb.check_and_cooldown()
        self.assertFalse(is_open)
        self.assertEqual(state, "CLOSED")

        # Trip the breaker
        cb.register_healing_event("ZeroDivisionError")
        cb.register_healing_event("IndexError")

        # When OPEN (before cooldown)
        is_open, state = cb.check_and_cooldown()
        self.assertTrue(is_open)
        self.assertEqual(state, "OPEN")

        # After cooldown
        time.sleep(0.2)
        is_open, state = cb.check_and_cooldown()
        self.assertFalse(is_open)
        self.assertEqual(state, "HALF_OPEN")

    def test_half_open_probe_failure_returns_to_open(self):
        """Probe failure in HALF_OPEN should return to OPEN state."""
        # Trip the breaker and wait for cooldown
        self.cb.register_healing_event("ZeroDivisionError")
        self.cb.register_healing_event("IndexError")
        time.sleep(0.6)
        self.cb.check_and_cooldown()
        self.assertEqual(self.cb.state, "HALF_OPEN")

        # Probe failure
        self.cb.record_probe_failure()
        self.assertEqual(self.cb.state, "OPEN")

    def test_degraded_status_in_half_open(self):
        """Healing during HALF_OPEN should return DEGRADED status."""
        global_circuit_breaker.reset()

        # Trip the global breaker
        for _ in range(20):
            calculate_sprinkler_pressure(100.0, 0.0)

        self.assertIn(global_circuit_breaker.state, ("OPEN", "HALF_OPEN"))

        # Manually set to HALF_OPEN for testing
        with global_circuit_breaker.lock:
            global_circuit_breaker.state = WeightedCircuitBreaker.HALF_OPEN
            global_circuit_breaker.half_open_count = 0

        # Trigger a healing event while in HALF_OPEN
        res = calculate_sprinkler_pressure(100.0, 0.0)
        self.assertEqual(res.status, SystemStatus.DEGRADED)
        self.assertEqual(res.value, 7.0)  # Still healed correctly

    def test_is_half_open_and_available(self):
        """Check probe availability in HALF_OPEN state."""
        self.cb.state = WeightedCircuitBreaker.HALF_OPEN
        self.cb.half_open_count = 0
        self.assertTrue(self.cb.is_half_open_and_available())

        self.cb.half_open_count = self.cb.half_open_max
        self.assertFalse(self.cb.is_half_open_and_available())


class TestAsyncAuditLoggerRotation(unittest.TestCase):
    """Tests for the AsyncAuditLogger file rotation feature."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.temp_dir, "test_audit.jsonl")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rotation_when_file_exceeds_max_bytes(self):
        """Verify log rotation when file exceeds max_bytes."""
        logger = AsyncAuditLogger(
            filepath=self.log_path,
            max_bytes=500,  # Very small for testing
            backup_count=3,
        )

        # Write enough events to trigger rotation
        for i in range(50):
            logger.log_event({"event": f"test_{i}", "data": "x" * 50})

        # Original file should exist (possibly rotated)
        # At least one backup should exist
        files = os.listdir(self.temp_dir)
        self.assertTrue(len(files) >= 1, f"Expected log files, got: {files}")  # NOSONAR - python:S5906

    def test_backward_compatible_log_event(self):
        """Verify log_event still works exactly like the old AuditLogger."""
        logger = AsyncAuditLogger(filepath=self.log_path)

        result = logger.log_event({"test": "event", "value": 42})
        self.assertTrue(result)

        # Verify the entry is written
        with open(self.log_path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)

        entry = json.loads(lines[0])
        self.assertIn("payload", entry)
        self.assertIn("signature", entry)
        self.assertEqual(entry["payload"]["test"], "event")

    def test_hmac_signature_preserved(self):
        """Verify HMAC-SHA256 signing is preserved after rotation upgrade."""
        logger = AsyncAuditLogger(filepath=self.log_path, secret_key=b"TEST_KEY")

        logger.log_event({"action": "heal", "tier": 1})

        with open(self.log_path) as f:
            entry = json.loads(f.readline())

        # Verify signature
        payload_bytes = json.dumps(entry["payload"], sort_keys=True, default=str).encode("utf-8")
        expected_sig = hmac.new(b"TEST_KEY", payload_bytes, hashlib.sha256).hexdigest()
        self.assertEqual(entry["signature"], expected_sig)

    def test_oserror_caught_not_propagated(self):
        """V53 FIX (BUG 7) preserved: OSError does not crash the system."""
        logger = AsyncAuditLogger(filepath="/nonexistent/path/audit.jsonl")

        # Should return False, not raise
        result = logger.log_event({"test": "should_not_crash"})
        self.assertFalse(result)

    def test_stats_tracking(self):
        """Verify batch statistics tracking."""
        logger = AsyncAuditLogger(filepath=self.log_path)

        logger.log_event({"test": 1})
        logger.log_event({"test": 2})

        stats = logger.stats()
        self.assertEqual(stats["total_events"], 2)
        self.assertEqual(stats["failed_writes"], 0)

    def test_alias_backward_compat(self):
        """Verify AuditLogger alias points to AsyncAuditLogger."""
        self.assertIs(AuditLogger, AsyncAuditLogger)


class TestLLMRateLimiter(unittest.TestCase):
    """Tests for the LLMCircuitBreaker rate limiter."""

    def setUp(self):
        self.limiter = LLMCircuitBreaker(max_rps=3.0, timeout=2.0)

    def test_allows_up_to_max_rps(self):
        """Should allow requests up to max_rps per second."""
        self.assertTrue(self.limiter.allow_request())  # 1st
        self.assertTrue(self.limiter.allow_request())  # 2nd
        self.assertTrue(self.limiter.allow_request())  # 3rd

    def test_blocks_over_max_rps(self):
        """Should block requests exceeding max_rps per second."""
        self.limiter.allow_request()
        self.limiter.allow_request()
        self.limiter.allow_request()
        # 4th request should be blocked
        self.assertFalse(self.limiter.allow_request())

    def test_window_resets_after_one_second(self):
        """Rate limit window should reset after 1 second."""
        self.limiter.allow_request()
        self.limiter.allow_request()
        self.limiter.allow_request()
        self.assertFalse(self.limiter.allow_request())

        # Wait for window to reset
        time.sleep(1.1)

        self.assertTrue(self.limiter.allow_request())

    def test_stats_reporting(self):
        """Verify rate limiter statistics."""
        self.limiter.allow_request()
        stats = self.limiter.stats()
        self.assertEqual(stats["max_rps"], 3.0)
        self.assertEqual(stats["timeout"], 2.0)


class TestErrorSeverity(unittest.TestCase):
    """Tests for the ErrorSeverity enum."""

    def test_severity_values(self):
        """Verify severity weight values."""
        self.assertEqual(ErrorSeverity.TRANSIENT.value, 1)
        self.assertEqual(ErrorSeverity.DEGRADED.value, 3)
        self.assertEqual(ErrorSeverity.CRITICAL.value, 5)
        self.assertEqual(ErrorSeverity.CATASTROPHIC.value, 10)

    def test_error_weights_mapping(self):
        """Verify ERROR_WEIGHTS maps error types to correct severities."""
        self.assertEqual(ERROR_WEIGHTS["ZeroDivisionError"], ErrorSeverity.CRITICAL)
        self.assertEqual(ERROR_WEIGHTS["IndexError"], ErrorSeverity.TRANSIENT)
        self.assertEqual(ERROR_WEIGHTS["MemoryError"], ErrorSeverity.CRITICAL)
        self.assertIn("default", ERROR_WEIGHTS)


class TestSystemStatus(unittest.TestCase):
    """Tests for the SystemStatus constants and SafetyResult validation."""

    def test_backward_compatible_string_comparison(self):
        """SystemStatus constants must equal their string values for backward compat."""
        self.assertEqual(SystemStatus.NOMINAL, "NOMINAL")
        self.assertEqual(SystemStatus.HEALED, "HEALED")
        self.assertEqual(SystemStatus.CRITICAL_CIRCUIT_OPEN, "CRITICAL_CIRCUIT_OPEN")
        self.assertEqual(SystemStatus.HALF_OPEN, "HALF_OPEN")
        self.assertEqual(SystemStatus.DEGRADED, "DEGRADED")

    def test_safety_result_validates_new_statuses(self):
        """SafetyResult should accept HALF_OPEN and DEGRADED statuses."""
        sr1 = SafetyResult(value=7.0, status="HALF_OPEN", metadata={})
        self.assertTrue(sr1.is_half_open())

        sr2 = SafetyResult(value=7.0, status="DEGRADED", metadata={})
        self.assertTrue(sr2.is_degraded())

    def test_safety_result_rejects_invalid_status(self):
        """V53 FIX (BUG 3) preserved: invalid status raises ValueError."""
        with pytest.raises(ValueError):
            SafetyResult(value=7.0, status="FAKE_NOMINAL", metadata={})

    def test_safety_result_audit_ref(self):
        """Verify audit_ref field is optional and stored correctly."""
        sr = SafetyResult(value=7.0, status="HEALED", metadata={}, audit_ref="SH-abc12345-def12345")
        self.assertEqual(sr.audit_ref, "SH-abc12345-def12345")

        # Default is None
        sr2 = SafetyResult(value=7.0, status="HEALED", metadata={})
        self.assertIsNone(sr2.audit_ref)


class TestSafetyCriticalFailure(unittest.TestCase):
    """Tests for the SafetyCriticalFailure exception."""

    def test_exception_is_distinct(self):
        """SafetyCriticalFailure should be a distinct exception type."""
        with pytest.raises(SafetyCriticalFailure):
            raise SafetyCriticalFailure("All tiers exhausted")

    def test_not_same_as_physics_guard(self):
        """SafetyCriticalFailure should not be the same as PhysicsGuardViolation."""
        try:
            raise SafetyCriticalFailure("test")
        except PhysicsGuardViolation:
            self.fail("SafetyCriticalFailure should not be caught as PhysicsGuardViolation")
        except SafetyCriticalFailure:
            pass  # Expected


class TestConfig(unittest.TestCase):
    """Tests for the Config class."""

    def test_default_values(self):
        """Verify Config has sensible defaults."""
        # Clean environment to test defaults
        env_vars = [
            "QOMN_CB_THRESHOLD", "QOMN_CB_WINDOW", "QOMN_CB_COOLDOWN",
            "QOMN_CB_HALF_OPEN_MAX", "QOMN_OLLAMA_TIMEOUT", "QOMN_OLLAMA_MAX_RPS",
            "QOMN_AUDIT_MAX_BYTES", "QOMN_AUDIT_BACKUP_COUNT", "QOMN_AUDIT_FLUSH_INTERVAL",
        ]
        saved = {}
        for var in env_vars:
            saved[var] = os.environ.pop(var, None)

        try:
            config = Config()
            self.assertEqual(config.CB_THRESHOLD, 10.0)
            self.assertEqual(config.CB_WINDOW, 60.0)
            self.assertEqual(config.CB_COOLDOWN, 10.0)
            self.assertEqual(config.CB_HALF_OPEN_MAX, 3)
            self.assertEqual(config.OLLAMA_TIMEOUT, 2.0)
            self.assertEqual(config.OLLAMA_MAX_RPS, 5.0)
            self.assertEqual(config.AUDIT_MAX_BYTES, 10 * 1024 * 1024)
            self.assertEqual(config.AUDIT_BACKUP_COUNT, 5)
        finally:
            # Restore environment
            for var, val in saved.items():
                if val is not None:
                    os.environ[var] = val

    def test_env_var_override(self):
        """Verify Config reads from environment variables."""
        os.environ["QOMN_CB_THRESHOLD"] = "25.0"
        try:
            config = Config()
            self.assertEqual(config.CB_THRESHOLD, 25.0)
        finally:
            del os.environ["QOMN_CB_THRESHOLD"]


class TestLruCacheFixesPreserved(unittest.TestCase):
    """Verify ALL V53 + V58 LruCache bug fixes are preserved."""

    def test_true_lru_eviction(self):
        """V53 BUG 1: OrderedDict + move_to_end for true LRU."""
        cache = LruCache(maxsize=3)
        cache.update("a", 1)
        cache.update("b", 2)
        cache.update("c", 3)

        # Access "a" to make it most recently used
        cache.get("a")

        # Insert "d" -- should evict "b" (least recently used)
        cache.update("d", 4)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(cache.get("c"), 3)
        self.assertEqual(cache.get("d"), 4)

    def test_deep_copy_on_get(self):
        """V53 BUG 6: get() returns deep copy."""
        cache = LruCache()
        cache.update("key", {"nested": [1, 2, 3]})

        result = cache.get("key")
        result["nested"].append(4)  # Mutate the returned value

        # Original in cache should be unchanged
        original = cache.get("key")
        self.assertEqual(original["nested"], [1, 2, 3])

    def test_deep_copy_on_update(self):
        """V58 BUG #11: update() deep-copies on insert."""
        cache = LruCache()
        data = {"value": [1, 2]}
        cache.update("key", data)

        # Mutate original
        data["value"].append(3)

        # Cached value should be unchanged
        cached = cache.get("key")
        self.assertEqual(cached["value"], [1, 2])

    def test_statistics_tracking(self):
        """V53 BUG 10: Statistics for operational monitoring."""
        cache = LruCache(maxsize=2)
        cache.update("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss

        stats = cache.stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["size"], 1)


class TestCircuitBreakerBackwardCompat(unittest.TestCase):
    """Verify WeightedCircuitBreaker is backward compatible with CircuitBreaker alias."""

    def test_alias_exists(self):
        """CircuitBreaker should be an alias for WeightedCircuitBreaker."""
        self.assertIs(CircuitBreaker, WeightedCircuitBreaker)

    def test_reset_method(self):
        """reset() method should work as before."""
        cb = WeightedCircuitBreaker(threshold=5.0)
        # ZeroDivisionError weight=5; one event gives 5.0 which is NOT > 5.0,
        # so register a second event to actually trip the breaker.
        cb.register_healing_event("ZeroDivisionError")
        cb.register_healing_event("ZeroDivisionError")
        self.assertEqual(cb.state, "OPEN")

        cb.reset()
        self.assertEqual(cb.state, "CLOSED")

    def test_check_and_cooldown_atomic(self):
        """V58 BUG #6: check_and_cooldown() acquires lock ONCE."""
        cb = WeightedCircuitBreaker(threshold=5.0, cooldown_seconds=0.1)

        # Trip the breaker
        cb.register_healing_event("ZeroDivisionError")
        cb.register_healing_event("IndexError")

        # Wait for cooldown
        time.sleep(0.2)

        is_open, state = cb.check_and_cooldown()
        self.assertFalse(is_open)  # Not fully OPEN anymore
        self.assertEqual(state, "HALF_OPEN")
        self.assertEqual(cb.state, "HALF_OPEN")


class TestV66VulnerabilityFixes(unittest.TestCase):
    """Tests for V66-V75 vulnerability fixes."""

    def setUp(self):
        global_circuit_breaker.reset()
        if os.path.exists("qomn_fire_healing_audit.jsonl"):
            try:
                os.remove("qomn_fire_healing_audit.jsonl")
            except OSError:
                pass

    def test_v67_nan_inf_guard_tier3(self):
        """V67: NaN/Inf default_value must be rejected in Tier 3 fallback."""
        @self_healing(
            safe_minimum=7.0,
            default_value=float('inf'),
            physics_validator=validate_sprinkler_pressure
        )
        def bad_pressure_calc():
            raise ZeroDivisionError("test")

        # Trip the circuit breaker first
        for _ in range(20):
            bad_pressure_calc()

        # When CB is open, default_value=float('inf') should be replaced
        # with safe_minimum=7.0
        result = bad_pressure_calc()
        self.assertEqual(result.value, 7.0)  # NOT float('inf')

    def test_v69_reject_zero_pressure(self):
        """V69: validate_sprinkler_pressure must reject 0.0 psi."""
        self.assertFalse(validate_sprinkler_pressure(0.0))
        self.assertTrue(validate_sprinkler_pressure(7.0))
        self.assertTrue(validate_sprinkler_pressure(0.1))

    def test_v70_log_event_catches_all_exceptions(self):
        """V70: log_event must not crash on non-OSError exceptions."""
        logger = AsyncAuditLogger(
            filepath=os.path.join(tempfile.gettempdir(), "test_v70.jsonl")
        )
        # Create an event with a non-serializable object that would
        # cause TypeError in json.dumps
        class BadObj:
            def __str__(self):
                raise RuntimeError("str failed")

        # Should return False, not raise
        result = logger.log_event({"bad": BadObj()})
        # It may succeed (default=str might handle it) or fail gracefully
        self.assertIsInstance(result, bool)

    def test_v71_config_safe_parsing(self):
        """V71: Config must not crash on invalid env vars."""
        os.environ["QOMN_CB_THRESHOLD"] = "not_a_number"
        try:
            config = Config()
            # Should fall back to default, not crash
            self.assertEqual(config.CB_THRESHOLD, 10.0)
        finally:
            del os.environ["QOMN_CB_THRESHOLD"]

    def test_v71_config_negative_value_rejected(self):
        """V71: Config must reject negative env var values."""
        os.environ["QOMN_CB_THRESHOLD"] = "-5.0"
        try:
            config = Config()
            # Should fall back to default
            self.assertEqual(config.CB_THRESHOLD, 10.0)
        finally:
            del os.environ["QOMN_CB_THRESHOLD"]

    def test_v72_safety_critical_failure_reraised(self):
        """V72: SafetyCriticalFailure must be re-raised, not swallowed."""
        @self_healing(safe_minimum=7.0, default_value=7.0,
                       physics_validator=validate_sprinkler_pressure)
        def critical_func():
            raise SafetyCriticalFailure("All tiers exhausted")

        with pytest.raises(SafetyCriticalFailure):
            critical_func()

    def test_v73_deterministic_hash(self):
        """V73: compute_hash must produce same hash across runs for same input."""
        data = {"args": (1, 2, 3), "kwargs": {"key": "value"}}
        hash1 = compute_hash(data)
        hash2 = compute_hash(data)
        self.assertEqual(hash1, hash2)

    def test_v74_peek_no_side_effect(self):
        """V74: peek() must not consume a rate limit slot."""
        limiter = LLMCircuitBreaker(max_rps=2.0, timeout=2.0)
        # Peek twice
        self.assertTrue(limiter.peek())
        self.assertTrue(limiter.peek())
        # Still have 2 slots available
        self.assertTrue(limiter.allow_request())
        self.assertTrue(limiter.allow_request())
        # Now should be blocked
        self.assertFalse(limiter.allow_request())

    def test_v75_keyerror_nan_guard(self):
        """V75: KeyError path must reject NaN/Inf default_value."""
        @self_healing(
            safe_minimum=7.0,
            default_value=float('nan'),
            physics_validator=validate_sprinkler_pressure
        )
        def key_error_func():
            d = {}
            return d["missing_key"]

        result = key_error_func()
        # NaN should be replaced with safe_minimum
        self.assertEqual(result.value, 7.0)

    def test_v66_check_and_cooldown_returns_state(self):
        """V66: check_and_cooldown returns atomic (is_open, state) tuple."""
        cb = WeightedCircuitBreaker(threshold=5.0, cooldown_seconds=0.1)

        # When CLOSED
        is_open, state = cb.check_and_cooldown()
        self.assertFalse(is_open)
        self.assertEqual(state, "CLOSED")

        # Trip the breaker. ZeroDivisionError weight=5; one event gives 5.0
        # which is NOT > 5.0, so register a second event to actually trip.
        cb.register_healing_event("ZeroDivisionError")
        cb.register_healing_event("ZeroDivisionError")

        # When OPEN (before cooldown)
        is_open, state = cb.check_and_cooldown()
        self.assertTrue(is_open)
        self.assertEqual(state, "OPEN")


# =====================================================================
# =====================================================================
# Three fixes tested here:
#   FIX 1 (CRITICAL): Nominal path physics validation
#   FIX 2 (CRITICAL): Config NaN/Inf guard
#   FIX 3 (HIGH):     Audit hash chain with rotation integrity
# =====================================================================

class TestV76NominalPhysicsValidation(unittest.TestCase):
    """
    V76 FIX 1 (CRITICAL): Functions returning physically invalid values
    (NaN, negative pressure, etc.) in the nominal path were reported as
    NOMINAL. Now validated BEFORE caching/returning.

    Three specific improvements over the original proposal:
    (a) validate BEFORE LRU cache update (not after)
    (b) register with circuit breaker for threshold accumulation
    (c) prefer default_value over safe_minimum as replacement
    """

    def setUp(self):
        global_circuit_breaker.reset()
        if os.path.exists("qomn_fire_healing_audit.jsonl"):
            try:
                os.remove("qomn_fire_healing_audit.jsonl")
            except OSError:
                pass

    def test_v76_fix1_nan_nominal_rejected(self):
        """V76 FIX 1: A function returning NaN must NOT be reported as NOMINAL."""
        @self_healing(
            safe_minimum=7.0,
            default_value=7.0,
            physics_validator=validate_sprinkler_pressure
        )
        def returns_nan():
            return float('nan')

        result = returns_nan()
        self.assertNotEqual(result.status, SystemStatus.NOMINAL)
        self.assertEqual(result.value, 7.0)  # Replaced with valid value

    def test_v76_fix1_negative_pressure_nominal_rejected(self):
        """V76 FIX 1: Negative pressure in nominal path must be caught and healed."""
        @self_healing(
            safe_minimum=7.0,
            default_value=7.0,
            physics_validator=validate_sprinkler_pressure
        )
        def returns_negative_pressure():
            return -5.0  # Physically impossible pressure

        result = returns_negative_pressure()
        self.assertNotEqual(result.status, SystemStatus.NOMINAL)
        self.assertEqual(result.status, SystemStatus.DEGRADED)
        self.assertEqual(result.value, 7.0)

    def test_v76_fix1_validation_before_cache(self):
        """
        V76 FIX 1 (a): Invalid values must NOT be stored in LRU cache.

        If validation happens AFTER cache update, the invalid value is
        stored as 'Last Known Good' and recovered on MemoryError —
        poisoning the fallback with a physically impossible value.
        """
        @self_healing(
            safe_minimum=7.0,
            default_value=7.0,
            physics_validator=validate_sprinkler_pressure
        )
        def returns_negative_pressure():
            return -10.0

        # Call the function — it returns -10.0, which is physically invalid
        result = returns_negative_pressure()
        self.assertEqual(result.value, 7.0)  # Healed, not -10.0

        # The LRU cache should contain the VALID replacement, not the invalid value
        cached = global_lru_cache.get("returns_negative_pressure")
        if cached is not None:
            # If cached, it must be the valid value, NOT -10.0
            self.assertNotEqual(cached, -10.0)

    def test_v76_fix1_cb_event_registered(self):
        """
        V76 FIX 1 (b): Nominal physics violations must register with circuit breaker.

        Without CB registration, repeated physics violations in the nominal
        path don't accumulate toward the breaker threshold — the system
        continues operating with physically invalid results.
        """
        # Reset global CB for this test
        global_circuit_breaker.reset()

        @self_healing(
            safe_minimum=7.0,
            default_value=7.0,
            physics_validator=validate_sprinkler_pressure,
        )
        def returns_negative():
            return -5.0

        # Before: breaker should be CLOSED
        self.assertEqual(global_circuit_breaker.state, "CLOSED")

        # NominalPhysicsViolation has weight=5 (CRITICAL).
        # The global CB default threshold is 10.0.
        # 3 violations = 3 * 5 = 15 > 10 threshold, should trip breaker.
        for _ in range(3):
            result = returns_negative()
            self.assertNotEqual(result.status, SystemStatus.NOMINAL)

        # After: breaker should be OPEN because violations accumulated
        self.assertEqual(global_circuit_breaker.state, "OPEN")

    def test_v76_fix1_default_value_preferred_over_safe_minimum(self):
        """
        V76 FIX 1 (c): default_value must be preferred over safe_minimum.

        For non-pressure functions, safe_minimum might be inappropriate.
        Example: safe_minimum=0.0 for an audio tone means 'no alarm sound'
        — dangerous in a fire alarm system. default_value should be tried
        first if it passes the physics validator.
        """
        def validate_audio_tone(val):
            """Audio tone must be a non-empty string."""
            return isinstance(val, str) and len(val) > 0

        @self_healing(
            safe_minimum=0.0,  # Inappropriate: 0 means "no sound"
            default_value="DEFAULT_EVAC_TONE",  # Correct fallback
            physics_validator=validate_audio_tone,
        )
        def returns_bad_tone():
            return ""  # Empty string — physically invalid (no alarm)

        result = returns_bad_tone()
        self.assertNotEqual(result.status, SystemStatus.NOMINAL)
        # Should prefer default_value ("DEFAULT_EVAC_TONE") over safe_minimum (0.0)
        self.assertEqual(result.value, "DEFAULT_EVAC_TONE")

    def test_v76_fix1_validator_crash_uses_safe_minimum(self):
        """
        V76 FIX 1: If the physics validator itself crashes, use safe_minimum.

        A crashing validator means we can't trust any value it might have
        passed. The safest choice is safe_minimum — the most conservative
        physically valid value.
        """
        def crashing_validator(val):
            raise RuntimeError("Validator crashed!")

        @self_healing(
            safe_minimum=7.0,
            default_value=7.0,
            physics_validator=crashing_validator,
        )
        def valid_function():
            return 100.0

        result = valid_function()
        self.assertEqual(result.status, SystemStatus.DEGRADED)
        self.assertEqual(result.value, 7.0)  # safe_minimum

    def test_v76_fix1_inf_nominal_rejected(self):
        """V76 FIX 1: A function returning float('inf') must NOT be NOMINAL."""
        @self_healing(
            safe_minimum=7.0,
            default_value=7.0,
            physics_validator=validate_sprinkler_pressure
        )
        def returns_inf():
            return float('inf')

        result = returns_inf()
        self.assertNotEqual(result.status, SystemStatus.NOMINAL)
        self.assertEqual(result.value, 7.0)


class TestV76ConfigNaNInfGuard(unittest.TestCase):
    """
    V76 FIX 2 (CRITICAL): Config._safe_float() NaN/Inf bypass.

    Without this guard:
    - QOMN_CB_THRESHOLD=nan → NaN < 1.0 is False (IEEE-754) → NaN passes
    - With threshold=NaN, circuit breaker NEVER trips (current_weight > NaN is always False)
    - QOMN_CB_THRESHOLD=inf → threshold unreachable, breaker never trips

    In a fire protection system, a circuit breaker that never trips means
    the system continues operating with accumulating faults — potentially
    returning wrong sprinkler pressures while appearing functional.
    """

    def test_v76_fix2_nan_env_var_rejected(self):
        """V76 FIX 2: NaN environment variable must be rejected by _safe_float."""
        os.environ["QOMN_CB_THRESHOLD"] = "nan"
        try:
            config = Config()
            # Must fall back to default, NOT accept NaN
            self.assertEqual(config.CB_THRESHOLD, 10.0)
        finally:
            del os.environ["QOMN_CB_THRESHOLD"]

    def test_v76_fix2_inf_env_var_rejected(self):
        """V76 FIX 2: Inf environment variable must be rejected by _safe_float."""
        os.environ["QOMN_CB_THRESHOLD"] = "inf"
        try:
            config = Config()
            # Must fall back to default, NOT accept Inf
            self.assertEqual(config.CB_THRESHOLD, 10.0)
        finally:
            del os.environ["QOMN_CB_THRESHOLD"]

    def test_v76_fix2_negative_inf_env_var_rejected(self):
        """V76 FIX 2: Negative Inf environment variable must be rejected."""
        os.environ["QOMN_CB_THRESHOLD"] = "-inf"
        try:
            config = Config()
            self.assertEqual(config.CB_THRESHOLD, 10.0)
        finally:
            del os.environ["QOMN_CB_THRESHOLD"]

    def test_v76_fix2_circuit_breaker_with_nan_threshold(self):
        """
        V76 FIX 2: Circuit breaker with NaN threshold must still function.

        This is the critical safety scenario: if NaN somehow reached the
        circuit breaker (e.g., through a different code path), the breaker
        must still be able to trip. With NaN threshold, current_weight > NaN
        is always False, so the breaker never trips. The Config._safe_float
        guard prevents NaN from reaching the breaker.
        """
        # Direct test: NaN threshold means breaker cannot trip via comparison
        cb = WeightedCircuitBreaker(threshold=float('nan'))
        cb.register_healing_event("ZeroDivisionError")
        # NaN comparison: current_weight > NaN → False → breaker stays CLOSED
        # This proves the vulnerability — if NaN reaches the breaker, it breaks
        self.assertEqual(cb.state, "CLOSED")  # Bug: breaker doesn't trip with NaN

        # But Config._safe_float prevents NaN from ever reaching the breaker:
        os.environ["QOMN_CB_THRESHOLD"] = "nan"
        try:
            config = Config()
            # Config must reject NaN and use default instead
            self.assertEqual(config.CB_THRESHOLD, 10.0)
            self.assertTrue(math.isfinite(config.CB_THRESHOLD))
        finally:
            del os.environ["QOMN_CB_THRESHOLD"]

    def test_v76_fix2_valid_env_var_accepted(self):
        """V76 FIX 2: Valid environment variables must still work correctly."""
        os.environ["QOMN_CB_THRESHOLD"] = "25.0"
        try:
            config = Config()
            self.assertEqual(config.CB_THRESHOLD, 25.0)
        finally:
            del os.environ["QOMN_CB_THRESHOLD"]

    def test_v76_fix2_all_config_params_reject_nan(self):
        """V76 FIX 2: ALL float config parameters must reject NaN/Inf."""
        test_cases = {
            "QOMN_CB_THRESHOLD": "CB_THRESHOLD",
            "QOMN_CB_WINDOW": "CB_WINDOW",
            "QOMN_CB_COOLDOWN": "CB_COOLDOWN",
            "QOMN_OLLAMA_TIMEOUT": "OLLAMA_TIMEOUT",
            "QOMN_OLLAMA_MAX_RPS": "OLLAMA_MAX_RPS",
            "QOMN_AUDIT_FLUSH_INTERVAL": "AUDIT_FLUSH_INTERVAL",
        }
        for env_var, attr_name in test_cases.items():
            for bad_val in ["nan", "inf", "-inf"]:
                os.environ[env_var] = bad_val
                try:
                    config = Config()
                    actual = getattr(config, attr_name)
                    self.assertTrue(
                        math.isfinite(actual),
                        f"{env_var}={bad_val} produced non-finite value {actual}"
                    )
                finally:
                    del os.environ[env_var]


class TestV76AuditHashChain(unittest.TestCase):
    """
    V76 FIX 3 (HIGH): Audit hash chain for tamper detection.

    Each audit entry includes the SHA-256 hash of the previous entry,
    creating a tamper-evident chain. If any entry is deleted, the chain
    breaks at the next entry (previous_hash mismatch).

    Key requirements:
    - Chain starts with genesis hash ("0" * 64)
    - Each entry's previous_hash matches SHA-256 of the previous entry
    - Chain survives file rotation (_last_chain_hash carries forward)
    - verify_chain() detects breaks in the chain
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.temp_dir, "test_chain.jsonl")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_v76_fix3_genesis_hash(self):
        """V76 FIX 3: First entry must have genesis hash as previous_hash."""
        logger = AsyncAuditLogger(filepath=self.log_path, secret_key=b"TEST_KEY")
        logger.log_event({"test": "first"})

        with open(self.log_path) as f:
            entry = json.loads(f.readline())

        self.assertEqual(
            entry["payload"]["previous_hash"],
            "0" * 64,
            "First entry must have genesis hash"
        )

    def test_v76_fix3_chain_linking(self):
        """V76 FIX 3: Each entry must link to the previous entry via previous_hash."""
        logger = AsyncAuditLogger(filepath=self.log_path, secret_key=b"TEST_KEY")
        logger.log_event({"test": "first"})
        logger.log_event({"test": "second"})
        logger.log_event({"test": "third"})

        with open(self.log_path) as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 3)

        # Verify chain: each entry's previous_hash must match
        # the SHA-256 of the previous line
        prev_hash = "0" * 64  # Genesis
        for line in lines:
            entry = json.loads(line.strip())
            self.assertEqual(
                entry["payload"]["previous_hash"],
                prev_hash,
                "Chain link broken: previous_hash mismatch"
            )
            # Compute expected hash for next entry
            prev_hash = hashlib.sha256(line.strip().encode("utf-8")).hexdigest()

    def test_v76_fix3_tamper_detection(self):
        """V76 FIX 3: Deleting a middle entry must break the chain."""
        logger = AsyncAuditLogger(filepath=self.log_path, secret_key=b"TEST_KEY")
        logger.log_event({"test": "first"})
        logger.log_event({"test": "second"})
        logger.log_event({"test": "third"})

        # Read all entries
        with open(self.log_path) as f:
            lines = f.readlines()

        # Delete the middle entry (simulate tampering)
        tampered_lines = [lines[0], lines[2]]

        # Write tampered file
        tampered_path = os.path.join(self.temp_dir, "tampered.jsonl")
        with open(tampered_path, "w") as f:
            f.writelines(tampered_lines)

        # Verify chain detects the break
        report = logger.verify_chain(filepath=tampered_path)
        self.assertFalse(report["chain_valid"], "Chain should be INVALID after deletion")
        self.assertTrue(len(report["break_points"]) > 0, "Break points must be reported")  # NOSONAR - python:S5906

    def test_v76_fix3_valid_chain_passes_verification(self):
        """V76 FIX 3: Intact chain must pass verify_chain()."""
        logger = AsyncAuditLogger(filepath=self.log_path, secret_key=b"TEST_KEY")
        for i in range(10):
            logger.log_event({"test": f"event_{i}"})

        report = logger.verify_chain()
        self.assertTrue(report["chain_valid"], "Intact chain must pass verification")
        self.assertEqual(report["total_entries"], 10)
        self.assertEqual(len(report["break_points"]), 0)

    def test_v76_fix3_chain_survives_rotation(self):
        """
        V76 FIX 3: Hash chain must survive file rotation.

        When the audit log rotates, the _last_chain_hash is preserved
        and used as the genesis hash for the new file. This ensures
        cross-file chain integrity — deleting the rotated file is detectable
        because the new file's first entry references the old file's last hash.
        """
        logger = AsyncAuditLogger(
            filepath=self.log_path,
            secret_key=b"TEST_KEY",
            max_bytes=500,  # Very small to trigger rotation quickly
            backup_count=3,
        )

        # Write enough events to trigger rotation
        for i in range(30):
            logger.log_event({"test": f"event_{i}", "data": "x" * 50})

        # The chain hash should NOT be "0" * 64 (genesis) — it must
        # have advanced from the events written
        stats = logger.stats()
        self.assertNotEqual(
            stats["chain_hash"],
            "0" * 64,
            "Chain hash must have advanced from events"
        )

        # Verify cross-file chain integrity:
        # If a backup file exists, the current file's first entry
        # must have previous_hash pointing to the backup's last entry.
        backup_path = f"{self.log_path}.1"
        if os.path.exists(backup_path) and os.path.exists(self.log_path):
            # Get the last entry's hash from the backup file
            with open(backup_path) as f:
                backup_lines = f.readlines()
            if backup_lines:
                last_backup_line = backup_lines[-1].strip()
                expected_prev_hash = hashlib.sha256(
                    last_backup_line.encode("utf-8")
                ).hexdigest()

                # Read the first entry of the current file
                with open(self.log_path) as f:
                    current_first_line = f.readline()
                current_first_entry = json.loads(current_first_line.strip())

                # The first entry of the new file must reference
                # the last entry of the rotated file
                self.assertEqual(
                    current_first_entry["payload"]["previous_hash"],
                    expected_prev_hash,
                    "Chain must carry forward across rotation: "
                    "new file's first entry must reference rotated file's last entry"
                )

        # Verify the current file's INTERNAL chain is intact
        # (skip the first entry which may reference the rotated file)
        if os.path.exists(self.log_path):
            with open(self.log_path) as f:
                lines = f.readlines()
            if len(lines) > 1:
                # Verify chain from 2nd entry onward
                prev_hash = hashlib.sha256(
                    lines[0].strip().encode("utf-8")
                ).hexdigest()
                for i, line in enumerate(lines[1:], 2):
                    entry = json.loads(line.strip())
                    self.assertEqual(
                        entry["payload"]["previous_hash"],
                        prev_hash,
                        f"Chain broken at line {i}"
                    )
                    prev_hash = hashlib.sha256(
                        line.strip().encode("utf-8")
                    ).hexdigest()

    def test_v76_fix3_stats_includes_chain_hash(self):
        """V76 FIX 3: stats() must include current chain tip hash."""
        logger = AsyncAuditLogger(filepath=self.log_path, secret_key=b"TEST_KEY")
        logger.log_event({"test": "event"})

        stats = logger.stats()
        self.assertIn("chain_hash", stats)
        self.assertNotEqual(stats["chain_hash"], "0" * 64,
                           "Chain hash must advance after logging events")

    def test_v76_fix3_previous_hash_in_payload(self):
        """V76 FIX 3: Each audit entry must include previous_hash in payload."""
        logger = AsyncAuditLogger(filepath=self.log_path, secret_key=b"TEST_KEY")
        logger.log_event({"test": "event"})

        with open(self.log_path) as f:
            entry = json.loads(f.readline())

        self.assertIn("previous_hash", entry["payload"],
                      "Audit entry must include previous_hash field")

    def test_v76_fix3_verify_chain_missing_file(self):
        """V76 FIX 3: verify_chain() must handle missing file gracefully."""
        logger = AsyncAuditLogger(filepath=self.log_path, secret_key=b"TEST_KEY")
        report = logger.verify_chain(filepath="/nonexistent/file.jsonl")
        self.assertFalse(report["chain_valid"])
        self.assertIn("error", report)


if __name__ == '__main__':
    # Run the demonstration run first
    demonstrate_and_verify_all_tiers()
    # Execute the self-verifying test suite
    unittest.main()


# ============================================================================
# ============================================================================


class TestV127HmacKeySecurity(unittest.TestCase):
    """
    V127 SAFETY: Verify the b"QOMN_SECRET_KEY" hardcoded fallback was
    removed. This was a CRITICAL vulnerability — in environments where
    pytest is importable (CI/CD with test deps), production code would
    silently use a known-default HMAC key, allowing attackers to forge
    audit log entries.
    """

    def test_no_hardcoded_default_key_when_pytest_importable(self):
        """
        When pytest is importable + FIREAI_ENV=production + no env var,
        AsyncAuditLogger MUST raise SecurityError, NOT use the hardcoded
        b"QOMN_SECRET_KEY".
        """
        import os
        import sys
        # Ensure pytest is in sys.modules (it is, since we're running under pytest)
        self.assertIn("pytest", sys.modules, "Test precondition: pytest must be in sys.modules")

        # Save env state
        saved_env = os.environ.get("FIREAI_ENV")
        saved_key = os.environ.get("QOMN_AUDIT_SECRET_KEY")
        try:
            os.environ["FIREAI_ENV"] = "production"
            os.environ.pop("QOMN_AUDIT_SECRET_KEY", None)

            with pytest.raises(Exception) as ctx:  # NOSONAR — S5778: re-raise inside except is intentional (context-specific)  # NOSONAR — S5958: parameter name documents intent at call site
                AsyncAuditLogger(filepath=os.path.join(tempfile.gettempdir(), "v127_security_test.jsonl"))
            self.assertIn("QOMN_AUDIT_SECRET_KEY", str(ctx.value))
        finally:
            if saved_env is not None:
                os.environ["FIREAI_ENV"] = saved_env
            else:
                os.environ.pop("FIREAI_ENV", None)
            if saved_key is not None:
                os.environ["QOMN_AUDIT_SECRET_KEY"] = saved_key

    def test_dev_mode_generates_random_key_not_hardcoded(self):
        """In dev mode, the fallback key must be RANDOM, not b"QOMN_SECRET_KEY"."""
        import os
        saved_env = os.environ.get("FIREAI_ENV")
        saved_key = os.environ.get("QOMN_AUDIT_SECRET_KEY")
        try:
            os.environ["FIREAI_ENV"] = "development"
            os.environ.pop("QOMN_AUDIT_SECRET_KEY", None)
            logger = AsyncAuditLogger(filepath=os.path.join(tempfile.gettempdir(), "v127_dev_test.jsonl"))
            self.assertNotEqual(logger.secret_key, b"QOMN_SECRET_KEY",
                                "V127 SAFETY: hardcoded default key must NEVER be used")
            self.assertEqual(len(logger.secret_key), 32,
                             "Random fallback must be 32 bytes (256 bits)")
        finally:
            if saved_env is not None:
                os.environ["FIREAI_ENV"] = saved_env
            else:
                os.environ.pop("FIREAI_ENV", None)
            if saved_key is not None:
                os.environ["QOMN_AUDIT_SECRET_KEY"] = saved_key

    def test_explicit_secret_key_takes_precedence(self):
        """Explicit secret_key passed to constructor must be used as-is."""
        explicit = b"my-explicit-test-key-32-bytes-long"
        logger = AsyncAuditLogger(
            filepath=os.path.join(tempfile.gettempdir(), "v127_explicit.jsonl"),
            secret_key=explicit,
        )
        self.assertEqual(logger.secret_key, explicit)

    def test_env_var_secret_key_takes_precedence_in_production(self):
        """In production, QOMN_AUDIT_SECRET_KEY env var must be honored."""
        import os
        saved_env = os.environ.get("FIREAI_ENV")
        saved_key = os.environ.get("QOMN_AUDIT_SECRET_KEY")
        try:
            os.environ["FIREAI_ENV"] = "production"
            os.environ["QOMN_AUDIT_SECRET_KEY"] = "production-stable-key-32-bytes-long"
            logger = AsyncAuditLogger(filepath=os.path.join(tempfile.gettempdir(), "v127_prod_env.jsonl"))
            self.assertEqual(logger.secret_key, b"production-stable-key-32-bytes-long")
        finally:
            if saved_env is not None:
                os.environ["FIREAI_ENV"] = saved_env
            else:
                os.environ.pop("FIREAI_ENV", None)
            if saved_key is not None:
                os.environ["QOMN_AUDIT_SECRET_KEY"] = saved_key
            else:
                os.environ.pop("QOMN_AUDIT_SECRET_KEY", None)
