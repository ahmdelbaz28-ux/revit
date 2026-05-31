# test_self_healing_engine.py
import unittest
import os
import json
import hmac
import hashlib

# Import from the module
from fireai.core.qomn_self_healing_engine import (
    SafetyResult, AuditLogger, LruCache, CircuitBreaker,
    global_audit_logger, global_lru_cache, global_circuit_breaker,
    self_healing, compute_hash, query_local_ollama_engine,
    calculate_sprinkler_pressure, validate_sprinkler_pressure,
    fetch_emergency_audio_sequence, validate_sequence_block,
    demonstrate_and_verify_all_tiers
)

class TestQomnFireSelfHealing(unittest.TestCase):

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
        # V58 FIX (BUG #8): Heal to safe_minimum (7.0) instead of float('inf').
        # float('inf') violates the QOMN kernel safety principle:
        # "NaN/Inf NEVER propagate — always caught and rejected."
        # If float('inf') is fed into any QOMN kernel computation
        # (voltage drop, battery), it crashes with PhysicsGuardError.
        # The safe_minimum (7.0 psi) is the correct conservative value.
        self.assertEqual(res.value, 7.0)
        self.assertEqual(res.metadata["rule"], "ZeroDivisionError")

    def test_tier_1_index_error_recovery(self):
        """Verify IndexError falls back to the last element of the input list."""
        tones = ["TONE_A", "TONE_B", "TONE_C"]
        # Wrap local helper
        @self_healing(safe_minimum=0.0, default_value="TONE_A", force_mock_ollama=True)
        def get_index_test(arr, idx):
            return arr[idx]
            
        res = get_index_test(tones, 5) # IndexError
        self.assertEqual(res.status, "HEALED")
        self.assertEqual(res.value, "TONE_C") # Last item

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
            res = calculate_sprinkler_pressure(100.0, 0.0)
            
        # Circuit breaker must be open, forcing safe fallback static return
        final_res = calculate_sprinkler_pressure(100.0, 0.0)
        self.assertEqual(final_res.status, "CRITICAL_CIRCUIT_OPEN")
        self.assertEqual(final_res.value, float('inf')) # Safe default value configured

    def test_cryptographic_audit_ledger(self):
        """Verify audit logger generates tamper-evident, HMAC-signed JSON Lines."""
        # Trigger single healing event
        calculate_sprinkler_pressure(100.0, 0.0)
        
        self.assertTrue(os.path.exists("qomn_fire_healing_audit.jsonl"))
        with open("qomn_fire_healing_audit.jsonl", "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        self.assertTrue(len(lines) >= 1)
        logged_entry = json.loads(lines[0])
        
        self.assertIn("payload", logged_entry)
        self.assertIn("signature", logged_entry)
        
        # Verify signature matching payload integrity
        payload_bytes = json.dumps(logged_entry["payload"], sort_keys=True, default=str).encode("utf-8")
        expected_sig = hmac.new(
            b"QOMN_SECRET_KEY",
            payload_bytes,
            hashlib.sha256
        ).hexdigest()
        
        self.assertEqual(logged_entry["signature"], expected_sig)

if __name__ == '__main__':
    # Run the demonstration run first
    demonstrate_and_verify_all_tiers()
    # Execute the self-verifying test suite
    unittest.main()
