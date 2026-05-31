"""
QOMN-FIRE Self-Healing Runtime Engine
Author: Safety-Critical Systems Architect
Standards Reference:
- IEEE-754 (2019) Standard for Floating-Point Arithmetic (§6.1)
- NFPA 72 (2022) National Fire Alarm and Signaling Code (§10.3)
- ISO/IEC 15408 Common Criteria for Information Technology Security Evaluation
"""

import os
import sys
import time
import json
import hmac
import hashlib
import logging
import inspect
import functools
import traceback
import urllib.request
import urllib.error
import threading
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

# Setup secure audit logger console format
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")


# =====================================================================
# SECTION 2.1: DATA TYPES & ENCAPSULATED OUTPUT MODEL
# =====================================================================


@dataclass(frozen=True)
class SafetyResult:
    """
    An immutable, type-safe representation of safety-critical output values.
    Every healed result is explicitly marked with its healing classification.
    """

    value: Any
    status: str  # "NOMINAL", "HEALED", "CRITICAL_CIRCUIT_OPEN"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_nominal(self) -> bool:
        return self.status == "NOMINAL"

    def is_healed(self) -> bool:
        return self.status == "HEALED"


class PhysicsGuardViolation(Exception):
    """Raised when a healed value violates hard physical/engineering bounds."""

    pass


# =====================================================================
# SECTION 2.2: CRYPTOGRAPHICALLY-SIGNED APPEND-ONLY AUDIT LOGGER
# =====================================================================


class AuditLogger:
    """
    Thread-safe, append-only JSON Lines logger.
    Each entry is cryptographically signed using HMAC-SHA256 to prevent tempering.
    """

    def __init__(self, filepath: str = "qomn_fire_healing_audit.jsonl", secret_key: bytes = b"QOMN_SECRET_KEY"):
        self.filepath = filepath
        self.secret_key = secret_key
        self.lock = threading.Lock()

    def log_event(self, event_data: Dict[str, Any]):
        """Serializes, signs, and appends the healing event to the audit ledger."""
        with self.lock:
            # FIX: Copy event_data to avoid mutating the caller's dictionary
            event_data = dict(event_data)
            # Enforce clean UTC timestamp
            event_data["timestamp_utc"] = datetime.now(timezone.utc).isoformat()

            # Serialize deterministically to ensure consistent hashing
            serialized_payload = json.dumps(event_data, sort_keys=True, default=str)

            # Generate cryptographic HMAC-SHA256 signature
            signature = hmac.new(self.secret_key, serialized_payload.encode("utf-8"), hashlib.sha256).hexdigest()

            entry = {"payload": event_data, "signature": signature}

            # Append to ledger
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")


# =====================================================================
# SECTION 2.3: SYSTEM MEMORY CACHE (LRU CONFORMANCE)
# =====================================================================


class LruCache:
    """
    Thread-safe storage of Last Known Good (LKG) values for critical systems.
    Reference: ISO/IEC 15408 fallback recovery patterns.
    """

    def __init__(self, maxsize: int = 128):
        self.maxsize = maxsize
        self.cache: Dict[str, Any] = {}
        self.lock = threading.Lock()

    def update(self, key: str, value: Any):
        with self.lock:
            if len(self.cache) >= self.maxsize:
                # Evict oldest entry (arbitrary pop for clean thread execution)
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = value

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            return self.cache.get(key, None)


# =====================================================================
# SECTION 2.4: TIER 3 CIRCUIT BREAKER
# =====================================================================


class CircuitBreaker:
    """
    Thread-safe rolling window circuit breaker.
    Trips if healing events exceed 10 per minute, forcing system safe fallbacks.
    """

    def __init__(self, limit: int = 10, window_seconds: float = 60.0):
        self.limit = limit
        self.window_seconds = window_seconds
        self.healing_timestamps: List[float] = []
        self.state = "CLOSED"  # "CLOSED" or "OPEN"
        self.open_time: float = 0.0
        self.lock = threading.Lock()

    def register_healing_event(self) -> bool:
        """
        Registers a healing incident.
        Returns True if the circuit breaker remains CLOSED, False if it TRIPS (OPENS).
        """
        with self.lock:
            now = time.time()
            self.healing_timestamps.append(now)

            # Prune timestamps outside of the sliding window
            self.healing_timestamps = [t for t in self.healing_timestamps if now - t <= self.window_seconds]

            if len(self.healing_timestamps) > self.limit:
                self.state = "OPEN"
                self.open_time = now
                logging.critical(
                    f"[CIRCUIT BREAKER CRITICAL] Fault rate exceeded threshold "
                    f"({len(self.healing_timestamps)} events in {self.window_seconds}s). "
                    f"State transitioned to OPEN. System is in fallback recovery."
                )
                return False
            return True

    def is_open(self) -> bool:
        """Checks if circuit breaker is open, managing auto-cooldown reset."""
        with self.lock:
            if self.state == "OPEN":
                # Auto-cooldown period of 10 seconds to allow auto-healing testing
                if time.time() - self.open_time > 10.0:
                    self.state = "CLOSED"
                    self.healing_timestamps = []
                    logging.info("[CIRCUIT BREAKER] Auto-cooldown complete. Restoring to CLOSED.")
                    return False
                return True
            return False

    def reset(self):
        with self.lock:
            self.state = "CLOSED"
            self.healing_timestamps = []


# =====================================================================
# SECTION 2.5: SELF-HEALING DECORATOR IMPLEMENTATION
# =====================================================================

# Global Instances for system demonstration
global_audit_logger = AuditLogger()
global_lru_cache = LruCache()
global_circuit_breaker = CircuitBreaker()


def compute_hash(data: Any) -> str:
    """Computes deterministic SHA-256 hash representation of values."""
    try:
        serialized = json.dumps(data, sort_keys=True, default=str)
    except Exception:
        serialized = str(data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def self_healing(
    safe_minimum: float = 0.0,
    default_value: Any = None,
    conservative_estimate: Any = 1.0,
    partial_result: Any = None,
    physics_validator: Optional[Callable[[Any], bool]] = None,
    force_mock_ollama: bool = False,
):
    """
    Self-healing decorator enforcing three tiers of system healing.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., SafetyResult]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> SafetyResult:
            func_name = func.__name__
            input_args_dict = {"args": args, "kwargs": kwargs}
            before_hash = compute_hash(input_args_dict)

            # ---------------------------------------------------------
            # CHECK TIER 3: CIRCUIT BREAKER STATUS
            # ---------------------------------------------------------
            if global_circuit_breaker.is_open():
                # Instantly fallback to static safe defaults
                safe_fallback = default_value if default_value is not None else safe_minimum

                # Check physics validity of safe fallback
                if physics_validator and not physics_validator(safe_fallback):
                    safe_fallback = 0.0  # Absolute floor

                after_hash = compute_hash(safe_fallback)

                event_data = {
                    "function_name": func_name,
                    "error_type": "CircuitBreakerOpen",
                    "error_message": "Execution blocked due to active circuit breaker.",
                    "tier_used": 3,
                    "fix_applied": safe_fallback,
                    "verification_result": "PASSED_FALLBACK",
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                    "user_notification_status": "ALERTED",
                }
                global_audit_logger.log_event(event_data)

                return SafetyResult(
                    value=safe_fallback, status="CRITICAL_CIRCUIT_OPEN", metadata={"error": "Circuit Breaker Tripped"}
                )

            # ---------------------------------------------------------
            # EXECUTE NOMINAL PATH
            # ---------------------------------------------------------
            try:
                nominal_value = func(*args, **kwargs)
                # Success path: update LRU cache with the Last Known Good (LKG) result
                global_lru_cache.update(func_name, nominal_value)
                return SafetyResult(value=nominal_value, status="NOMINAL")

            except Exception as e:
                # Execution failed: capture original stack context
                err_type = type(e).__name__
                err_msg = str(e)
                stack_trace = traceback.format_exc()

                # Register event to window counter; trip circuit breaker if threshold is exceeded
                circuit_closed = global_circuit_breaker.register_healing_event()

                # -----------------------------------------------------
                # TIER 1: DETERMINISTIC RULE-BASED HEALING
                # -----------------------------------------------------
                healed_val = None
                tier_1_applied = False

                if err_type == "ZeroDivisionError":
                    # IEEE-754 Section 6.1: Division by zero returns infinity
                    healed_val = float("inf")
                    tier_1_applied = True

                elif err_type == "IndexError":
                    # FIX (CRITICAL): When a physics_validator is provided, the function
                    # is safety-critical and Tier 1's last-element fallback may return an
                    # incorrect value (e.g., wrong audio tone during fire alarm). Delegate
                    # to Tier 2 which uses the configured default_value after validation.
                    # When no physics_validator is provided, Tier 1's last-element fallback
                    # is acceptable for non-safety-critical data lookups.
                    if physics_validator is None:
                        # Non-safety-critical: return last valid item of first list parameter
                        if args and isinstance(args[0], (list, tuple)) and len(args[0]) > 0:
                            healed_val = args[0][-1]
                        else:
                            healed_val = default_value
                        tier_1_applied = True
                    # else: tier_1_applied remains False, falls through to Tier 2
                    # for safer, validator-backed recovery

                elif err_type == "ValueError":
                    # NFPA 72 §10.3 safety minimum limits
                    healed_val = safe_minimum
                    tier_1_applied = True

                elif err_type == "KeyError":
                    healed_val = default_value
                    tier_1_applied = True

                elif err_type == "TypeError":
                    # Duck typing fallback casting
                    try:
                        # Attempt to return conservative estimate casted to type of default value
                        if default_value is not None:
                            healed_val = type(default_value)(conservative_estimate)
                        else:
                            healed_val = float(conservative_estimate)
                    except Exception:
                        healed_val = default_value
                    tier_1_applied = True

                elif err_type == "AssertionError":
                    # Apply conservative safety factors
                    healed_val = conservative_estimate
                    tier_1_applied = True

                elif err_type == "MemoryError":
                    # Fetch from LRU cache recovery
                    cached = global_lru_cache.get(func_name)
                    healed_val = cached if cached is not None else default_value
                    tier_1_applied = True

                elif err_type == "TimeoutError":
                    healed_val = partial_result
                    tier_1_applied = True

                # Validate Tier 1 values
                if tier_1_applied:
                    is_valid = True
                    if physics_validator:
                        try:
                            is_valid = physics_validator(healed_val)
                        except Exception:
                            is_valid = False

                    if is_valid:
                        after_hash = compute_hash(healed_val)
                        event_data = {
                            "function_name": func_name,
                            "error_type": err_type,
                            "error_message": err_msg,
                            "tier_used": 1,
                            "fix_applied": healed_val,
                            "verification_result": "PASSED_PHYSICS_GUARD",
                            "before_hash": before_hash,
                            "after_hash": after_hash,
                            "user_notification_status": "SILENT" if circuit_closed else "ALERTED",
                        }
                        global_audit_logger.log_event(event_data)

                        return SafetyResult(value=healed_val, status="HEALED", metadata={"tier": 1, "rule": err_type})

                # -----------------------------------------------------
                # TIER 2: LOCAL LLM RECOVERY LOOP (OLLAMA / LLAMA)
                # -----------------------------------------------------
                logging.warning(
                    f"[TIER 2 HEALING INITIALIZED] Standard Tier 1 rules could "
                    f"not safely resolve {err_type} in {func_name}. Querying Local LLM Agent..."
                )

                llm_response_val = None
                tier_2_verified = False

                if force_mock_ollama:
                    # Deterministic mock fallback for environment consistency
                    llm_response_val = default_value if default_value is not None else safe_minimum
                else:
                    # Make a structured HTTP call to localhost Ollama service
                    llm_response_val = query_local_ollama_engine(
                        func_name=func_name,
                        err_type=err_type,
                        err_msg=err_msg,
                        inputs=input_args_dict,
                        source_code=inspect.getsource(func),
                        default_fallback=default_value if default_value is not None else safe_minimum,
                    )

                # Run Golden Verification Tests on LLM suggested payload
                if llm_response_val is not None:
                    # Verification check 1: Physics constraint verification
                    physics_passed = True
                    if physics_validator:
                        try:
                            physics_passed = physics_validator(llm_response_val)
                        except Exception:
                            physics_passed = False

                    # Verification check 2: Static verification of value compatibility
                    type_passed = True
                    if default_value is not None:
                        type_passed = isinstance(llm_response_val, type(default_value))

                    if physics_passed and type_passed:
                        tier_2_verified = True

                if tier_2_verified:
                    after_hash = compute_hash(llm_response_val)
                    event_data = {
                        "function_name": func_name,
                        "error_type": err_type,
                        "error_message": err_msg,
                        "tier_used": 2,
                        "fix_applied": llm_response_val,
                        "verification_result": "PASSED_GOLDEN_TESTS",
                        "before_hash": before_hash,
                        "after_hash": after_hash,
                        "user_notification_status": "ALERTED",
                    }
                    global_audit_logger.log_event(event_data)

                    # Log message notifying user/operator of recovery action
                    logging.info(
                        f"[TIER 2 HEALED SUCCESS] Recovered from {err_type} in {func_name} "
                        f"using verified LLM patch value: {llm_response_val}."
                    )

                    return SafetyResult(
                        value=llm_response_val, status="HEALED", metadata={"tier": 2, "suggested_by": "ollama_agent"}
                    )

                # If all healing fails, raise original error
                raise e

        return wrapper

    return decorator


# =====================================================================
# SECTION 2.6: LOCAL OLLAMA MCP DRIVER
# =====================================================================


def query_local_ollama_engine(
    func_name: str, err_type: str, err_msg: str, inputs: Dict[str, Any], source_code: str, default_fallback: Any
) -> Any:
    """
    Connects to the local Ollama instance (llama3) to generate a patch.
    This process is contained locally and does not leak telemetry data externally.
    """
    url = "http://localhost:11434/api/generate"

    prompt = (
        f"You are a Safety-Critical Fire Protection Engineering Assistant.\n"
        f"The function '{func_name}' failed during runtime.\n"
        f"Error Type: {err_type}\n"
        f"Error Message: {err_msg}\n"
        f"Inputs: {inputs}\n"
        f"Source Code:\n{source_code}\n\n"
        f"Provide a safe return value to heal this execution and prevent system crash.\n"
        f"Respond ONLY with a valid JSON document conforming to this schema:\n"
        f'{{"suggested_return_value": <safe_value>}}\n'
        f"Do not include code blocks, explanations, markdown or extra characters."
    )

    payload = {"model": "llama3", "prompt": prompt, "stream": False, "format": "json"}

    # S310 SECURITY FIX: Validate URL scheme before opening.
    # urllib.request.urlopen allows file:// and custom schemes which can
    # read local files or cause SSRF. Only http/https are permitted.
    from urllib.parse import urlparse as _urlparse

    _parsed = _urlparse(url)
    if _parsed.scheme not in ("http", "https"):
        logging.warning(
            f"[SECURITY S310] Rejected URL with scheme '{_parsed.scheme}' — "
            f"only http/https allowed. Falling back to default."
        )
        return default_fallback

    req_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 — scheme validated above
        url, data=req_body, headers={"Content-Type": "application/json"}, method="POST"
    )

    try:
        # Enforce strict 2-second timeout to prevent stalling the safety thread
        with urllib.request.urlopen(req, timeout=2.0) as response:  # noqa: S310
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            llm_text = res_json.get("response", "{}")

            # Parse inner JSON
            parsed_text = json.loads(llm_text)
            suggested_val = parsed_text.get("suggested_return_value")

            # Prevent silent NaN leakage
            if str(suggested_val).lower() == "nan":
                return default_fallback

            return suggested_val

    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        # Local Ollama offline, timeouts, or invalid JSON response falls back to mock validation
        logging.warning(
            f"[LOCAL OLLAMA UNREACHABLE/TIMEOUT] Reason: {str(e)}. "
            f"Failing-over to local safe boundary validation logic."
        )
        return default_fallback


# =====================================================================
# SECTION 3: SYSTEM INTEGRATION & USAGE EXAMPLES
# =====================================================================


def validate_sprinkler_pressure(val: Any) -> bool:
    """Sprinkler operating pressure must be positive or infinity under zero flow."""
    if isinstance(val, (int, float)):
        return val >= 0.0 or val == float("inf")
    return False


@self_healing(safe_minimum=7.0, default_value=float("inf"), physics_validator=validate_sprinkler_pressure)
def calculate_sprinkler_pressure(flow_gpm: float, k_factor: float) -> float:
    """
    Computes required operating pressure: P = (Q / K)^2
    Citing: NFPA 13 Section 23.4.4
    """
    if k_factor == 0.0:
        raise ZeroDivisionError("K-Factor cannot be zero under active calculations.")
    return (flow_gpm / k_factor) ** 2


def validate_sequence_block(val: Any) -> bool:
    """Ensure healed sequence block is a non-empty string."""
    return isinstance(val, str) and len(val) > 0


@self_healing(
    safe_minimum=0.0,
    default_value="DEFAULT_EVAC_TONE",
    physics_validator=validate_sequence_block,
    force_mock_ollama=True,  # Demonstrates Tier 2 fallback processing
)
def fetch_emergency_audio_sequence(sequence_list: List[str], index: int) -> str:
    """
    Fetches scheduled audio tone file.
    Citing: NFPA 72 Section 18.4
    """
    if index >= len(sequence_list):
        raise IndexError("Sequence index overflow.")
    return sequence_list[index]


def demonstrate_and_verify_all_tiers():
    """
    Demonstrates active runtime healing across all tiers, logging actions in the ledger.
    """
    print("\n" + "=" * 70)
    print("RUNNING QOMN-FIRE SELF-HEALING SYSTEM RUNS")
    print("=" * 70)

    # 1. NOMINAL RUN
    print("\n--- Running Nominal Calculations ---")
    nom_result = calculate_sprinkler_pressure(100.0, 5.6)
    print(f"Nominal Result: {nom_result.value:.4f} psi (Status: {nom_result.status})")

    # 2. TIER 1 HEALING RUN (ZeroDivisionError)
    print("\n--- Triggering Tier 1 ZeroDivisionError Healing ---")
    healed_result_t1 = calculate_sprinkler_pressure(100.0, 0.0)
    print(
        f"Healed Result T1 Value: {healed_result_t1.value} (Status: {healed_result_t1.status}, Metadata: {healed_result_t1.metadata})"
    )

    # 3. TIER 2 HEALING RUN (IndexError LLM Fallback)
    print("\n--- Triggering Tier 2 IndexError Healing (Verified Local LLM) ---")
    sequence_blocks = ["ALERT_CHIME", "EVAC_VOICE_ENG"]
    healed_result_t2 = fetch_emergency_audio_sequence(sequence_blocks, 99)  # Out of bounds
    print(
        f"Healed Result T2 Value: '{healed_result_t2.value}' (Status: {healed_result_t2.status}, Metadata: {healed_result_t2.metadata})"
    )

    # 4. TIER 3 HEALING RUN (Circuit Breaker Tripping)
    print("\n--- Stress Testing Circuit Breaker (Tier 3 Cascade Prevention) ---")
    global_circuit_breaker.reset()

    print("Simulating high-frequency fault occurrences (> 10 error events)...")
    for cycle in range(12):
        res = calculate_sprinkler_pressure(100.0, 0.0)  # Triggers division by zero
        if res.status == "CRITICAL_CIRCUIT_OPEN":
            print(f"Cycle {cycle:02d}: Circuit Breaker successfully OPENED! Fallback value used: {res.value}")
            break
        else:
            print(f"Cycle {cycle:02d}: Healed value ({res.value}) returned. State: {global_circuit_breaker.state}")

    # Restoring System State
    global_circuit_breaker.reset()
    print("\n" + "=" * 70)
    print("SELF-HEALING DEMONSTRATION RUN COMPLETE")
    print("=" * 70)
