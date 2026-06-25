from __future__ import annotations

"""
QOMN-FIRE Self-Healing Runtime Engine V2.0
Author: Safety-Critical Systems Architect
Standards Reference:
- IEEE-754 (2019) Standard for Floating-Point Arithmetic (Section 6.1)
- NFPA 72 (2022) National Fire Alarm and Signaling Code (Section 10.3)
- ISO/IEC 15408 Common Criteria for Information Technology Security Evaluation

V53 BUG FIXES PRESERVED:
- BUG 1 (CRITICAL): LruCache was FIFO, now true LRU using OrderedDict + move_to_end
- BUG 2 (HIGH): CircuitBreaker.is_open() was mutating state; split into pure query + try_cooldown()
- BUG 3 (HIGH): SafetyResult.status now validates against allowed literal values
- BUG 4 (MEDIUM): HMAC secret key now loaded from environment variable with fallback
- BUG 5 (CRITICAL): None healed values now caught and rejected before returning to caller
- BUG 6 (HIGH): LruCache.get() now returns deep copies to prevent cache corruption
- BUG 7 (HIGH): AuditLogger.log_event() now catches OSError to prevent crash on I/O failure
- BUG 8 (MEDIUM): TypeError handler now safely falls back to conservative_estimate on cast failure
- BUG 9 (MEDIUM): CircuitBreaker now exposes health() method for proactive monitoring
- BUG 10 (LOW): LruCache now tracks hit/miss/eviction statistics for operational visibility

V58 BUG FIXES PRESERVED:
- BUG #4: inspect.getsource(func) wrapped in try-except for non-standard deployments
- BUG #6: check_and_cooldown() acquires lock ONCE (race condition fix)
- BUG #10: ZeroDivisionError heals to safe_minimum instead of float('inf')
- BUG #11: LruCache.update() deep-copies value on insert
- BUG #12: NaN/Inf detection uses math module, not fragile string comparison

V FIXES PRESERVED:
- NaN/Inf guard for default_value in ZeroDivisionError path
- validate_sprinkler_pressure rejects float('inf')
- Tier 3 fallback uses safe_minimum (7.0 psi) not 0.0 (0 psi = "no protection")
- IndexError with physics_validator delegates to Tier 2 for safer recovery

V2.0 MERGED FEATURES (from consultant — good ideas only):
- WeightedCircuitBreaker: severity-based weighted scoring, O(1) deque, HALF_OPEN state
- AsyncAuditLogger: file rotation, batch statistics, HMAC signing preserved
- Half-Open recovery pattern: probe requests after cooldown, gradual recovery
- LLM Rate Limiter: prevents Ollama service overload
- Config class: centralized environment-variable-backed configuration
- ErrorSeverity enum: classification for weighted circuit breaker scoring
- SafetyCriticalFailure exception: dedicated safety-critical failure type
- audit_ref field: HMAC traceability reference in SafetyResult

V76 BUG FIXES:
- FIX 1 (CRITICAL): Nominal path physics validation — functions returning
  physically invalid values (NaN, negative pressure, etc.) were reported as
  NOMINAL. Now validated before caching/returning. Three improvements over
  the original proposal: (a) validate BEFORE LRU cache update, (b) register
  with circuit breaker for threshold accumulation, (c) prefer default_value
  over safe_minimum as replacement.
- FIX 2 (CRITICAL): Config._safe_float() NaN/Inf bypass — NaN from env
  vars passed min_val check (NaN < 1.0 is False in IEEE-754), making
  circuit breaker threshold=NaN so it NEVER trips. Added math.isfinite().
- FIX 3 (HIGH): Audit hash chain — each entry includes previous entry's
  SHA-256 hash, creating a tamper-evident chain that detects deletion of
  audit entries. Chain survives file rotation. Added verify_chain() for
  forensic analysis.
"""

import copy
import functools
import hashlib
import hmac
import inspect
import json
import logging
import math
import os
import threading
import time
import traceback
import urllib.error
import urllib.request
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

# Setup secure audit logger console format
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")


# =====================================================================
# SECTION 1: DATA TYPES & ENCAPSULATED OUTPUT MODEL
# =====================================================================


class SecurityError(Exception):
    """Raised when a security policy violation prevents continuation.

    Used by audit subsystem to reject operations that would compromise
    audit log integrity (e.g., missing HMAC key in production).
    """

    pass


class ErrorSeverity(Enum):
    """Classification of error severity for weighted circuit breaker scoring.

    Weighted scoring ensures critical errors trip the circuit breaker faster
    than transient ones -- a ZeroDivisionError in a pressure calculation is
    far more dangerous than a transient cache miss.

    V2.0 FEATURE (from consultant): Enables severity-aware circuit breaking.
    """

    TRANSIENT = 1
    DEGRADED = 3
    CRITICAL = 5
    CATASTROPHIC = 10


# V53 FIX (BUG 3) + V2.0 EXTENSION: Allowed status values as type constraint
StatusType = Literal["NOMINAL", "HEALED", "CRITICAL_CIRCUIT_OPEN", "HALF_OPEN", "DEGRADED"]


class SystemStatus:
    """Allowed status values for SafetyResult and system state reporting.

    Uses string constants (NOT Enum) for backward compatibility:
    SystemStatus.HEALED == "HEALED" returns True, so existing code
    comparing status to string literals continues to work.

    V53 FIX (BUG 3): Status values are constrained to prevent invalid strings.
    V2.0 EXTENSION: Added HALF_OPEN and DEGRADED for weighted CB + half-open.
    """

    NOMINAL: StatusType = "NOMINAL"
    HEALED: StatusType = "HEALED"
    CRITICAL_CIRCUIT_OPEN: StatusType = "CRITICAL_CIRCUIT_OPEN"
    HALF_OPEN: StatusType = "HALF_OPEN"
    DEGRADED: StatusType = "DEGRADED"


# V53 FIX (BUG 3) + V2.0 EXTENSION: Allowed status values as type constraint
VALID_STATUSES = (
    SystemStatus.NOMINAL,
    SystemStatus.HEALED,
    SystemStatus.CRITICAL_CIRCUIT_OPEN,
    SystemStatus.HALF_OPEN,
    SystemStatus.DEGRADED,
)


@dataclass(frozen=True)
class SafetyResult:
    """An immutable, type-safe representation of safety-critical output values.
    Every healed result is explicitly marked with its healing classification.

    V53 FIX (BUG 3): status validated at construction time to prevent
    invalid status strings like "FAKE_NOMINAL" from being created.
    V2.0 EXTENSION: Added audit_ref for HMAC traceability.
    """

    value: Any
    status: StatusType
    metadata: Dict[str, Any] = field(default_factory=dict)
    audit_ref: Optional[str] = None  # HMAC audit reference for traceability

    def __post_init__(self):
        """V53 FIX: Validate status at construction time to prevent invalid values."""
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid SafetyResult.status: '{self.status}'. "
                f"Must be one of {VALID_STATUSES}. "
                f"This is a safety-critical constraint violation."
            )

    def is_nominal(self) -> bool:
        return self.status == SystemStatus.NOMINAL

    def is_healed(self) -> bool:
        return self.status == SystemStatus.HEALED

    def is_circuit_open(self) -> bool:
        return self.status == SystemStatus.CRITICAL_CIRCUIT_OPEN

    def is_half_open(self) -> bool:
        return self.status == SystemStatus.HALF_OPEN

    def is_degraded(self) -> bool:
        return self.status == SystemStatus.DEGRADED


class PhysicsGuardViolation(Exception):
    """Raised when a healed value violates hard physical/engineering bounds."""

    pass


class SafetyCriticalFailure(Exception):
    """Raised when a safety-critical operation cannot produce a valid result.

    This is distinct from PhysicsGuardViolation -- it indicates a systemic
    failure (e.g., all healing tiers exhausted) rather than a value-level
    constraint violation.

    V2.0 FEATURE (from consultant).
    """

    pass


class LLMUnavailableError(Exception):
    """Raised when the local LLM (Ollama) service is unreachable.

    Used by the LLM Rate Limiter to signal that the LLM tier is
    temporarily unavailable, not that it has permanently failed.

    V2.0 FEATURE (from consultant).
    """

    pass


# =====================================================================
# SECTION 2: CONFIGURATION
# =====================================================================

class Config:
    """Environment-variable-backed configuration for the self-healing engine.

    All parameters can be overridden via environment variables, enabling
    deployment-specific tuning without code changes.

    V2.0 FEATURE (from consultant): Centralized configuration with env-var overrides.
    """

    @staticmethod
    def _safe_float(env_var: str, default: float, min_val: float = 0.0) -> float:
        """V71 FIX: Parse float from env var with validation. Falls back to
        default on invalid values instead of crashing the module import.

        V76 FIX (CRITICAL): Reject NaN/Inf from environment variables.
        Without this guard, QOMN_CB_THRESHOLD=nan passes because NaN < 1.0
        is False in IEEE-754, so the min_val check is bypassed. With
        threshold=NaN, the circuit breaker NEVER trips (current_weight > NaN
        is always False) — the safety system has no protection. Similarly,
        QOMN_CB_THRESHOLD=inf makes the threshold unreachable. In a fire
        protection system, a circuit breaker that never trips means the
        system continues operating with accumulating faults — potentially
        returning wrong sprinkler pressures or coverage calculations while
        appearing functional. Per QOMN kernel safety principle: NaN/Inf
        NEVER propagate. math.isfinite() rejects both NaN and Inf.

        In a safety-critical system, a typo in an environment variable
        (e.g., QOMN_CB_THRESHOLD=abc) must NOT crash the entire system.
        The safe default is always preferable to a crash.
        """
        raw = os.environ.get(env_var, "")
        if not raw:
            return default
        try:
            val = float(raw)
            # V76 FIX: Reject NaN and Inf BEFORE min_val check.
            # NaN < min_val evaluates to False (IEEE-754), bypassing the
            # guard. Inf passes the min_val check but makes the threshold
            # unreachable. Both must be rejected explicitly.
            if not math.isfinite(val):
                logging.warning(
                    f"[CONFIG] {env_var}={raw} is not finite (NaN/Inf rejected). "
                    f"Using default: {default}."
                )
                return default
            if val < min_val:
                logging.warning(
                    f"[CONFIG] {env_var}={val} is below minimum {min_val}. "
                    f"Using default: {default}."
                )
                return default
            return val
        except (ValueError, TypeError):
            logging.warning(
                f"[CONFIG] {env_var}='{raw}' is not a valid number. "
                f"Using default: {default}."
            )
            return default

    @staticmethod
    def _safe_int(env_var: str, default: int, min_val: int = 1) -> int:
        """V71 FIX: Parse int from env var with validation."""
        raw = os.environ.get(env_var, "")
        if not raw:
            return default
        try:
            val = int(raw)
            if val < min_val:
                logging.warning(
                    f"[CONFIG] {env_var}={val} is below minimum {min_val}. "
                    f"Using default: {default}."
                )
                return default
            return val
        except (ValueError, TypeError):
            logging.warning(
                f"[CONFIG] {env_var}='{raw}' is not a valid integer. "
                f"Using default: {default}."
            )
            return default

    def __init__(self):
        # Circuit Breaker Configuration
        self.CB_THRESHOLD: float = self._safe_float("QOMN_CB_THRESHOLD", 10.0, min_val=1.0)
        self.CB_WINDOW: float = self._safe_float("QOMN_CB_WINDOW", 60.0, min_val=1.0)
        self.CB_COOLDOWN: float = self._safe_float("QOMN_CB_COOLDOWN", 10.0, min_val=1.0)
        self.CB_HALF_OPEN_MAX: int = self._safe_int("QOMN_CB_HALF_OPEN_MAX", 3, min_val=1)

        # LLM / Ollama Configuration
        self.OLLAMA_TIMEOUT: float = self._safe_float("QOMN_OLLAMA_TIMEOUT", 2.0, min_val=0.1)
        self.OLLAMA_MAX_RPS: float = self._safe_float("QOMN_OLLAMA_MAX_RPS", 5.0, min_val=1.0)

        # Audit Logger Configuration
        self.AUDIT_MAX_BYTES: int = self._safe_int(
            "QOMN_AUDIT_MAX_BYTES", 10 * 1024 * 1024, min_val=1024
        )  # 10MB default
        self.AUDIT_BACKUP_COUNT: int = self._safe_int("QOMN_AUDIT_BACKUP_COUNT", 5, min_val=1)
        self.AUDIT_FLUSH_INTERVAL: float = self._safe_float("QOMN_AUDIT_FLUSH_INTERVAL", 1.0, min_val=0.1)

        # HMAC Secret Key
        self.SECRET_KEY: Optional[bytes] = None
        env_key = os.environ.get("QOMN_AUDIT_SECRET_KEY", "")
        if env_key:
            self.SECRET_KEY = env_key.encode("utf-8")


# Error type to severity mapping for weighted circuit breaker
ERROR_WEIGHTS: Dict[str, ErrorSeverity] = {
    "ZeroDivisionError": ErrorSeverity.CRITICAL,
    "PhysicsGuardViolation": ErrorSeverity.CATASTROPHIC,
    "SafetyCriticalFailure": ErrorSeverity.CATASTROPHIC,
    "ValueError": ErrorSeverity.DEGRADED,
    "KeyError": ErrorSeverity.DEGRADED,
    "TypeError": ErrorSeverity.DEGRADED,
    "IndexError": ErrorSeverity.TRANSIENT,
    "AssertionError": ErrorSeverity.DEGRADED,
    "MemoryError": ErrorSeverity.CRITICAL,
    "TimeoutError": ErrorSeverity.TRANSIENT,
    "OSError": ErrorSeverity.CRITICAL,
    "LLMUnavailableError": ErrorSeverity.DEGRADED,
    # V76 FIX: New error types for nominal path physics validation
    "NominalPhysicsViolation": ErrorSeverity.CRITICAL,
    "PhysicsValidatorCrash": ErrorSeverity.CRITICAL,
    "NominalNaNInf": ErrorSeverity.CATASTROPHIC,
    "default": ErrorSeverity.DEGRADED,
}


# =====================================================================
# SECTION 3: CRYPTOGRAPHICALLY-SIGNED AUDIT LOGGER (WITH ROTATION)
# =====================================================================

class AsyncAuditLogger:
    """Thread-safe, append-only JSON Lines logger with HMAC-SHA256 signatures,
    file rotation, and batch statistics.

    SAFETY DESIGN DECISION: Despite the name "Async", log_event() writes
    IMMEDIATELY to disk. In a life-safety system, audit events MUST be
    persisted before the function returns -- if the process crashes during
    a fire event, the audit trail must show what happened. Batching delays
    create an unacceptable window where events could be lost.

    The consultant's original AsyncAuditLogger used async def log_event(),
    but the self_healing decorator is synchronous. Calling an async function
    without await returns a coroutine that is never awaited -- meaning log
    events would NEVER be written. This is a CRITICAL BUG in the consultant's
    design. Our implementation keeps immediate synchronous writes (safe)
    while adding rotation and monitoring features from the consultant's design.

    V53 FIX (BUG 4): Secret key loaded from environment variable with fallback.
    V53 FIX (BUG 7): File I/O errors caught and logged, not propagated.
    V2.0 FEATURE (from consultant): File rotation + batch statistics.
    V76 FIX (HIGH): Hash chain for tamper detection (deletion detection).
    """

    def __init__(
        self,
        filepath: str = "qomn_fire_healing_audit.jsonl",
        secret_key: Optional[bytes] = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
    ):
        self.filepath = filepath
        self.max_bytes = max_bytes
        self.backup_count = backup_count

        # V76 FIX (HIGH): Hash chain — each entry includes the hash of the
        # previous entry, creating a tamper-evident chain. If any entry is
        # deleted, the chain breaks at the next entry (previous_hash mismatch).
        # This detects the "missing audit entries" attack where an attacker
        # removes evidence of a healing action from the middle of the log.
        # Genesis hash: 64 zeros (standard blockchain convention).
        self._last_chain_hash: str = "0" * 64

        # V53 FIX (BUG 4): Load secret from environment with secure fallback
        # H-2 FIX: Removed hardcoded default secret key b"QOMN_SECRET_KEY".
        # A known-default key means any attacker can forge HMAC signatures
        # on audit logs, creating fake "healed" results that appear legitimate.
        # In a fire protection system, forged audit records could hide the
        # fact that a healing action was never actually performed — a
        # life-safety hazard. Now, if no key is provided, a random key is
        # generated at startup and logged as a warning. This key is valid
        # only for the current process lifetime; restart generates a new one.
        # For production, ALWAYS set QOMN_AUDIT_SECRET_KEY environment variable.
        if secret_key is not None:
            self.secret_key = secret_key
        elif os.environ.get("QOMN_AUDIT_SECRET_KEY", ""):
            self.secret_key = os.environ.get("QOMN_AUDIT_SECRET_KEY").encode("utf-8")
        else:
            # V127 SAFETY-CRITICAL FIX (agent.md Rule #17 — NO HALF-SOLUTIONS):
            # The previous "pytest in sys.modules" check used a hardcoded
            # b"QOMN_SECRET_KEY" as fallback. This is a CATASTROPHIC vulnerability
            # because pytest is importable in many production environments that
            # install test dependencies (CI runners, Docker images bundling test
            # deps, developer laptops running uvicorn locally with test deps
            # installed). A known-default HMAC key allows attackers to forge
            # audit log entries, hiding the fact that a self-healing action was
            # never actually performed.
            #
            # FIX:
            #   - Production (FIREAI_ENV=production): RAISE SecurityError.
            #     Audit logging cannot proceed without a stable HMAC key.
            #   - Non-production: generate a random per-process key with WARNING.
            #     Tests that need a deterministic key must pass secret_key=...
            #     explicitly via the constructor.
            import secrets as _secrets
            env = os.environ.get("FIREAI_ENV", "development").lower()
            is_production = env in ("production", "prod")
            if is_production:
                raise SecurityError(
                    "QOMN_AUDIT_SECRET_KEY is not set in production. "
                    "Audit log HMAC cannot be verified without a stable key. "
                    "Generate one with: "
                    "python -c 'import secrets; print(secrets.token_hex(32))'"
                )
            self.secret_key = _secrets.token_bytes(32)
            logging.warning(
                "[AUDIT SECURITY] QOMN_AUDIT_SECRET_KEY not set in environment. "
                "Generated a random key for this session. This key will change on "
                "restart, making previous audit logs unverifiable. For production, "
                "set QOMN_AUDIT_SECRET_KEY to a stable, cryptographically random value "
                "(>= 32 bytes). A known-default key like b'QOMN_SECRET_KEY' allows "
                "attackers to forge audit log signatures."
            )
        self.lock = threading.Lock()

        # Batch statistics for monitoring
        self._total_events: int = 0
        self._failed_writes: int = 0
        self._bytes_written: int = 0

    def _rotate_if_needed(self):
        """Rotate audit log file if it exceeds max_bytes.

        Rotation strategy:
        - qomn_fire_healing_audit.jsonl -> .jsonl.1
        - .jsonl.1 -> .jsonl.2
        - etc., up to backup_count

        Thread safety: Must be called with self.lock held.
        """
        try:
            if not os.path.exists(self.filepath):
                return
            if os.path.getsize(self.filepath) < self.max_bytes:
                return

            # Rotate existing backups
            for i in range(self.backup_count - 1, 0, -1):
                src = f"{self.filepath}.{i}"
                dst = f"{self.filepath}.{i + 1}"
                if os.path.exists(src):
                    if os.path.exists(dst):
                        os.remove(dst)
                    os.rename(src, dst)

            # Rotate current file
            dst = f"{self.filepath}.1"
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(self.filepath, dst)

            logging.info(f"[AUDIT ROTATION] Rotated audit log to {dst}")
        except OSError as e:
            logging.warning(f"[AUDIT ROTATION FAILED] {e}. Continuing without rotation.")

    def log_event(self, event_data: Dict[str, Any]) -> bool:
        """Serializes, signs, and appends the healing event to the audit ledger.
        Returns True if logging succeeded, False if it failed (I/O error).

        V53 FIX (BUG 7): Catches OSError to prevent crash on I/O failure.
        V2.0 FEATURE: Rotation + batch statistics.
        V76 FIX (HIGH): Hash chain — each entry links to the previous entry
        via previous_hash, creating a tamper-evident chain. This detects
        deletion of audit entries (e.g., removing evidence of a healing
        action). The chain is persisted within each file; on rotation,
        the last hash from the old file is carried forward as the genesis
        for the new file, maintaining cross-file chain integrity.
        """
        with self.lock:
            try:
                # Rotate if needed before writing
                # V76 FIX: Save chain hash BEFORE rotation so it carries
                # forward to the new file. Without this, rotation breaks
                # the chain — the new file starts with genesis hash "0"*64,
                # making it impossible to detect deletion of the rotated file.
                self._rotate_if_needed()

                # Copy event_data to avoid mutating the caller's dictionary
                event_data = dict(event_data)
                # Enforce clean UTC timestamp (V59 AUDIT-012 timezone fix)
                event_data["timestamp_utc"] = datetime.now(timezone.utc).isoformat()

                # V76 FIX: Include previous hash for chain integrity
                event_data["previous_hash"] = self._last_chain_hash

                # Serialize deterministically for consistent hashing
                serialized_payload = json.dumps(event_data, sort_keys=True, default=str)

                # Generate cryptographic HMAC-SHA256 signature
                signature = hmac.new(
                    self.secret_key,
                    serialized_payload.encode("utf-8"),
                    hashlib.sha256
                ).hexdigest()

                entry = {
                    "payload": event_data,
                    "signature": signature
                }

                # Append to ledger
                entry_str = json.dumps(entry) + "\n"
                with open(self.filepath, "a", encoding="utf-8") as f:
                    f.write(entry_str)

                # V76 FIX: Update chain hash — hash of the entry content
                # (the JSON line WITHOUT trailing newline) becomes the next
                # entry's previous_hash. This makes the chain tamper-evident:
                # changing any entry changes its hash, which breaks the
                # chain at the NEXT entry. Note: we hash the content without
                # the newline because file-reading tools typically strip
                # trailing newlines, and the hash must match across read/write.
                self._last_chain_hash = hashlib.sha256(
                    entry_str.rstrip("\n").encode("utf-8")
                ).hexdigest()

                # Update statistics
                self._total_events += 1
                self._bytes_written += len(entry_str)

                return True

            except Exception as e:
                # V53 FIX (BUG 7): Never let I/O errors crash the safety system
                # V70 FIX (MEDIUM): Broadened from OSError to Exception.
                # The old code only caught OSError, but json.dumps() can raise
                # TypeError (non-serializable objects whose __str__ also fails),
                # and hmac.new() can raise TypeError if secret_key is corrupted.
                # Any of these would crash the safety system. In a life-safety
                # system, the audit logger must NEVER be the cause of a crash.
                # Better to lose an audit event than to lose the entire system.
                self._failed_writes += 1
                logging.critical(
                    f"[AUDIT LOGGER FAILURE] Cannot write to {self.filepath}: {type(e).__name__}: {e}. "
                    f"Event data NOT persisted to disk. "
                    f"Event: {str(event_data)[:200]}"
                )
                return False

    def stats(self) -> Dict[str, Any]:
        """Return audit logger statistics for operational monitoring."""
        with self.lock:
            return {
                "total_events": self._total_events,
                "failed_writes": self._failed_writes,
                "bytes_written": self._bytes_written,
                "filepath": self.filepath,
                "chain_hash": self._last_chain_hash,  # V76: Current chain tip
            }

    def verify_chain(self, filepath: Optional[str] = None) -> Dict[str, Any]:
        """V76 FIX: Verify the hash chain integrity of an audit log file.

        Reads the entire file and checks that each entry's previous_hash
        matches the SHA-256 hash of the previous entry. Returns a report
        with chain_valid (bool), break_points (list of line numbers where
        chain breaks), and total_entries checked.

        This enables post-incident forensic analysis: if anyone deleted
        audit entries to hide a healing action, the chain will be broken.
        """
        target = filepath or self.filepath
        break_points: List[int] = []
        total_entries = 0
        expected_hash = "0" * 64  # Genesis

        try:
            with open(target, encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        payload = entry.get("payload", {})
                        actual_prev = payload.get("previous_hash", "")

                        if actual_prev != expected_hash:
                            break_points.append(line_num)

                        # Compute hash of this entry for next comparison
                        expected_hash = hashlib.sha256(
                            line.encode("utf-8")
                        ).hexdigest()
                        total_entries += 1
                    except json.JSONDecodeError:
                        break_points.append(line_num)
        except FileNotFoundError:
            return {
                "chain_valid": False,
                "error": f"File not found: {target}",
                "total_entries": 0,
                "break_points": [],
            }
        except OSError as e:
            return {
                "chain_valid": False,
                "error": str(e),
                "total_entries": total_entries,
                "break_points": break_points,
            }

        return {
            "chain_valid": len(break_points) == 0,
            "total_entries": total_entries,
            "break_points": break_points,
            "chain_tip": expected_hash,
        }

    def flush(self) -> bool:
        """Explicit flush -- with immediate write mode, this is a no-op.

        Provided for API compatibility with buffered logger implementations.
        Always returns True because events are already persisted.
        """
        return True


# Backward compatibility alias -- preserves existing imports
AuditLogger = AsyncAuditLogger


# =====================================================================
# SECTION 4: SYSTEM MEMORY CACHE (TRUE LRU CONFORMANCE)
# =====================================================================

class LruCache:
    """Thread-safe storage of Last Known Good (LKG) values for critical systems.
    Reference: ISO/IEC 15408 fallback recovery patterns.

    V53 FIX (BUG 1): Now uses OrderedDict with move_to_end() for TRUE LRU eviction.
    V53 FIX (BUG 6): get() returns deep copies to prevent cache corruption.
    V53 FIX (BUG 10): Now tracks hit/miss/eviction statistics.
    V58 FIX (BUG #11): update() deep-copies value on insert to prevent caller
    from corrupting cached data.
    """

    def __init__(self, maxsize: int = 128):
        self.maxsize = maxsize
        # V53 FIX (BUG 1): OrderedDict preserves insertion order and supports move_to_end
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.lock = threading.Lock()
        # V53 FIX (BUG 10): Statistics for operational monitoring
        self._hits: int = 0
        self._misses: int = 0
        self._evictions: int = 0

    def update(self, key: str, value: Any):
        """Insert or update a key, marking it as most-recently-used.

        V58 FIX (BUG #11): Deep-copies value on insert to prevent caller from
        corrupting cached data. Without this, mutating the original object
        after update() silently corrupts the LKG (Last Known Good) value.
        """
        with self.lock:
            if key in self.cache:
                # Key exists: remove and re-insert to move to end (most recently used)
                del self.cache[key]
            elif len(self.cache) >= self.maxsize:
                # V53 FIX (BUG 1): Evict LEAST recently used (first item in OrderedDict)
                self.cache.popitem(last=False)
                self._evictions += 1
            self.cache[key] = copy.deepcopy(value)  # V58 FIX: deep copy on insert

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a cached value, marking it as most-recently-used.
        V53 FIX (BUG 6): Returns a deep copy to prevent caller from corrupting cache.
        V53 FIX (BUG 1): Moves accessed key to end (most recently used position).
        """
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)  # V53 FIX: True LRU access ordering
                self._hits += 1
                # V53 FIX (BUG 6): Deep copy prevents caller from mutating cached value
                return copy.deepcopy(self.cache[key])
            self._misses += 1
            return None

    def stats(self) -> Dict[str, int]:
        """V53 FIX (BUG 10): Return cache statistics for operational monitoring."""
        with self.lock:
            return {  # type: ignore[dict-item]
                "size": len(self.cache),
                "maxsize": self.maxsize,
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_ratio": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0.0  # type: ignore[dict-item]
            }


# =====================================================================
# SECTION 5: WEIGHTED CIRCUIT BREAKER WITH HALF-OPEN RECOVERY
# =====================================================================

class WeightedCircuitBreaker:
    """Thread-safe weighted circuit breaker with O(1) deque and half-open recovery.

    V2.0 FEATURES (from consultant):
    - Weighted scoring: errors contribute severity-based weight to the threshold,
      so critical errors trip the breaker faster than transient ones.
    - O(1) deque: Uses collections.deque for efficient window pruning instead
      of O(n) list comprehension.
    - HALF_OPEN state: After cooldown, breaker transitions to HALF_OPEN and
      allows limited "probe" requests to test recovery before full closure.

    PRESERVED FIXES:
    - V53 FIX (BUG 2): is_open() is pure query; mutation handled separately.
    - V53 FIX (BUG 9): health() method for proactive monitoring.
    - V58 FIX (BUG #6): check_and_cooldown() acquires lock ONCE.
    """

    # State constants (string values for backward compatibility)
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        threshold: float = 10.0,
        window_seconds: float = 60.0,
        cooldown_seconds: float = 10.0,
        half_open_max: int = 3,
    ):
        self.threshold = threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max = half_open_max

        # O(1) deque: stores (timestamp, weight) tuples
        self._events: deque = deque()

        self.state = self.CLOSED
        self.open_time: float = 0.0
        self.half_open_count: int = 0
        self.lock = threading.Lock()

    def _prune_expired(self, now: float) -> float:
        """Remove events outside the sliding window. O(1) amortized per event.

        Returns the current weighted sum within the window.
        Thread safety: Must be called with self.lock held.
        """
        while self._events and (now - self._events[0][0]) > self.window_seconds:
            self._events.popleft()
        return sum(weight for _, weight in self._events)

    def register_healing_event(self, error_type: str = "default") -> bool:
        """Registers a healing incident with severity-weighted scoring.
        Returns True if the circuit breaker remains CLOSED, False if it TRIPS (OPENS).

        Error severity is looked up from ERROR_WEIGHTS. Critical errors
        contribute more weight toward the threshold, causing the breaker
        to trip faster for dangerous failures.

        Backward compatible: default error_type="default" preserves
        the old register_healing_event() call signature.
        """
        severity = ERROR_WEIGHTS.get(error_type, ERROR_WEIGHTS["default"])
        weight = severity.value

        with self.lock:
            now = time.time()
            self._events.append((now, weight))
            current_weight = self._prune_expired(now)

            if current_weight > self.threshold:
                self.state = self.OPEN
                self.open_time = now
                self.half_open_count = 0
                logging.critical(
                    f"[CIRCUIT BREAKER CRITICAL] Weighted fault rate exceeded threshold "
                    f"(weight: {current_weight:.1f}/{self.threshold:.1f} in {self.window_seconds}s). "
                    f"State transitioned to OPEN. System is in fallback recovery."
                )
                return False
            return True

    def record_success(self) -> None:
        """Record a successful operation. In HALF_OPEN state, consecutive successes
        transition the breaker back to CLOSED after half_open_max successes.

        This is called ONLY when the wrapped function completes WITHOUT
        raising an exception -- a healed result does NOT count as a success,
        because the underlying system is still failing.
        """
        with self.lock:
            if self.state == self.HALF_OPEN:
                self.half_open_count += 1
                if self.half_open_count >= self.half_open_max:
                    self.state = self.CLOSED
                    self._events.clear()
                    self.half_open_count = 0
                    logging.info(
                        "[CIRCUIT BREAKER] Half-open recovery successful. "
                        f"{self.half_open_max} consecutive successes recorded. "
                        "Restoring to CLOSED."
                    )

    def record_probe_failure(self) -> None:
        """Record a probe failure in HALF_OPEN state, transitioning back to OPEN.

        In a safety-critical system, a "healed" call does NOT count as a
        success for half-open recovery. The circuit breaker is testing whether
        the UNDERLYING system has recovered, not whether the healing system
        can cover for it. If the function raises an exception during a probe,
        the probe has FAILED -- even if Tier 1/2 healing produces a valid result.
        """
        with self.lock:
            if self.state == self.HALF_OPEN:
                self.state = self.OPEN
                self.open_time = time.time()
                self.half_open_count = 0
                logging.warning(
                    "[CIRCUIT BREAKER] Half-open probe FAILED. "
                    "Returning to OPEN state. System in fallback recovery."
                )

    def is_open(self) -> bool:
        """Pure query: checks if circuit breaker is currently OPEN.
        V53 FIX (BUG 2): This method does not mutate state. Use try_cooldown() for that.
        """
        with self.lock:
            return self.state == self.OPEN

    def try_cooldown(self) -> bool:
        """Attempts auto-cooldown if the cooldown period has elapsed.
        Returns True if the breaker transitioned from OPEN to HALF_OPEN.
        V53 FIX (BUG 2): Separated from is_open() for Command-Query Separation.
        V2.0 EXTENSION: Cooldown transitions to HALF_OPEN (not CLOSED directly).
        """
        with self.lock:
            if self.state == self.OPEN:
                if time.time() - self.open_time > self.cooldown_seconds:
                    self.state = self.HALF_OPEN
                    self.half_open_count = 0
                    logging.info(
                        "[CIRCUIT BREAKER] Cooldown complete. Transitioning to HALF_OPEN. "
                        f"Allowing up to {self.half_open_max} probe requests."
                    )
                    return True
            return False

    def check_and_cooldown(self) -> Tuple[bool, str]:
        """Combined check: returns (is_fully_open, state_at_check) tuple.

        V58 FIX (BUG #6): Acquires lock ONCE instead of twice. The original
        code called try_cooldown() then is_open(), which released and
        re-acquired the lock, creating a race condition between the two operations.

        V2.0 EXTENSION: Cooldown now transitions to HALF_OPEN instead of CLOSED,
        allowing probe requests before full recovery.

        V66 FIX (CRITICAL): Now returns the state at time of check as a second
        element, eliminating the race condition where the caller reads cb.state
        without holding the lock. Previously, between check_and_cooldown()
        releasing the lock and the caller reading cb.state, another thread
        could transition the state -- causing was_half_open to be incorrect.
        This could lead to: (a) record_probe_failure() called when it shouldn't
        be, prematurely returning the breaker to OPEN, or (b) DEGRADED status
        returned when HEALED was correct, or vice versa. In a safety-critical
        fire protection system, an incorrect status means operators don't know
        the true system state during a fire event.

        Returns:
            (True, state)  -- breaker is fully OPEN, caller should use Tier 3 fallback
            (False, state) -- breaker is CLOSED or HALF_OPEN, caller may proceed
            state is the state at the moment of the atomic check

        """
        with self.lock:
            if self.state == self.OPEN:
                if time.time() - self.open_time > self.cooldown_seconds:
                    self.state = self.HALF_OPEN
                    self.half_open_count = 0
                    logging.info(
                        "[CIRCUIT BREAKER] Cooldown complete. Transitioning to HALF_OPEN."
                    )
                    return (False, self.HALF_OPEN)  # just cooled down to HALF_OPEN
                return (True, self.OPEN)  # still OPEN
            if self.state == self.HALF_OPEN:
                return (False, self.HALF_OPEN)  # HALF_OPEN, allow probe
            return (False, self.CLOSED)  # CLOSED

    def is_half_open_and_available(self) -> bool:
        """Check if the breaker is in HALF_OPEN state and has probe capacity.
        Returns True if a probe request can be allowed through.
        """
        with self.lock:
            return (
                self.state == self.HALF_OPEN
                and self.half_open_count < self.half_open_max
            )

    def health(self) -> Dict[str, Any]:
        """V53 FIX (BUG 9): Returns health metrics for proactive monitoring.
        Allows operators to detect approaching threshold before breaker trips.
        V2.0 EXTENSION: Includes weighted metrics and half-open status.
        """
        with self.lock:
            now = time.time()
            current_weight = self._prune_expired(now)
            event_count = len(self._events)
            return {
                "state": self.state,
                "weighted_sum": round(current_weight, 2),
                "event_count": event_count,
                "threshold": self.threshold,
                "window_seconds": self.window_seconds,
                "utilization_pct": round(
                    (current_weight / self.threshold) * 100, 1
                ) if self.threshold > 0 else 0.0,
                "cooldown_seconds": self.cooldown_seconds,
                "half_open_max": self.half_open_max,
                "half_open_count": self.half_open_count,
                "seconds_since_open": (
                    (now - self.open_time)
                    if self.state in (self.OPEN, self.HALF_OPEN) else None
                ),
            }

    def reset(self):
        """Reset the circuit breaker to CLOSED state."""
        with self.lock:
            self.state = self.CLOSED
            self._events.clear()
            self.half_open_count = 0


# Backward compatibility alias -- preserves existing imports
CircuitBreaker = WeightedCircuitBreaker


# =====================================================================
# SECTION 6: LLM RATE LIMITER
# =====================================================================

class LLMCircuitBreaker:
    """Rate limiter for local Ollama LLM calls.

    Prevents overwhelming the LLM service with too many requests.
    Uses a sliding window counter to enforce max requests per second.

    V2.0 FEATURE (from consultant): Essential for preventing Ollama overload.
    Without rate limiting, every error triggers an LLM call with no throttle.
    """

    def __init__(self, max_rps: float = 5.0, timeout: float = 2.0):
        self.max_rps = max_rps
        self.timeout = timeout
        self._call_timestamps: deque = deque()
        self.lock = threading.Lock()

    def allow_request(self) -> bool:
        """Check if an LLM request is allowed within the rate limit.
        Returns True if the request is allowed, False if rate limited.

        V74 FIX: Only consumes a rate limit slot when the request is actually
        allowed. Previously, allow_request() would append a timestamp even
        if the caller was just "checking" availability. This violated
        Command-Query Separation and could cause false rate limiting when
        the caller checks availability but doesn't make the request.
        Now, the timestamp is only recorded on success (True return).
        """
        with self.lock:
            now = time.time()
            # Prune timestamps outside 1-second window
            while self._call_timestamps and (now - self._call_timestamps[0]) > 1.0:
                self._call_timestamps.popleft()

            if len(self._call_timestamps) < self.max_rps:
                self._call_timestamps.append(now)
                return True
            return False

    def peek(self) -> bool:
        """V74 FIX: Pure query -- check if a request WOULD be allowed without
        consuming a rate limit slot. This allows callers to check
        availability without side effects.
        """
        with self.lock:
            now = time.time()
            while self._call_timestamps and (now - self._call_timestamps[0]) > 1.0:
                self._call_timestamps.popleft()
            return len(self._call_timestamps) < self.max_rps

    def record_failure(self):
        """Record an LLM call failure for monitoring."""
        pass  # Placeholder for future circuit-breaking on LLM failures

    def stats(self) -> Dict[str, Any]:
        """Return rate limiter statistics."""
        with self.lock:
            now = time.time()
            while self._call_timestamps and (now - self._call_timestamps[0]) > 1.0:
                self._call_timestamps.popleft()
            return {
                "calls_in_window": len(self._call_timestamps),
                "max_rps": self.max_rps,
                "timeout": self.timeout,
            }


# =====================================================================
# SECTION 7: SELF-HEALING DECORATOR IMPLEMENTATION
# =====================================================================

# Global Instances -- initialized from Config
_config = Config()
global_audit_logger = AsyncAuditLogger(
    filepath="qomn_fire_healing_audit.jsonl",
    secret_key=_config.SECRET_KEY,
    max_bytes=_config.AUDIT_MAX_BYTES,
    backup_count=_config.AUDIT_BACKUP_COUNT,
)
global_lru_cache = LruCache()
global_circuit_breaker = WeightedCircuitBreaker(
    threshold=_config.CB_THRESHOLD,
    window_seconds=_config.CB_WINDOW,
    cooldown_seconds=_config.CB_COOLDOWN,
    half_open_max=_config.CB_HALF_OPEN_MAX,
)
global_llm_breaker = LLMCircuitBreaker(
    max_rps=_config.OLLAMA_MAX_RPS,
    timeout=_config.OLLAMA_TIMEOUT,
)


def compute_hash(data: Any) -> str:
    """Computes deterministic SHA-256 hash representation of values.

    V73 FIX: Handles non-serializable objects (functions, memory addresses)
    by replacing them with deterministic representations before hashing.
    The old code used default=str which produces non-deterministic output
    for function objects (e.g., "<function foo at 0x7f...>") because the
    memory address changes between runs. This broke audit trail integrity
    verification -- the same inputs would produce different hashes.
    Now, function objects and other non-serializable types are replaced
    with their qualified name or type name, which is deterministic.
    """
    def _make_serializable(obj: Any) -> Any:
        """Recursively replace non-serializable objects with deterministic strings."""
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        if isinstance(obj, (list, tuple)):
            return [_make_serializable(item) for item in obj]
        if isinstance(obj, dict):
            return {str(k): _make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, set):
            return sorted([_make_serializable(item) for item in obj])
        # For functions, use __qualname__ (deterministic across runs)
        if hasattr(obj, '__qualname__'):
            return f"<function:{obj.__qualname__}>"
        # For other objects, use type name (deterministic)
        return f"<{type(obj).__name__}>"

    try:
        clean_data = _make_serializable(data)
        serialized = json.dumps(clean_data, sort_keys=True)
    except Exception:
        serialized = str(data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def self_healing(
    safe_minimum: float = 0.0,
    default_value: Any = None,
    conservative_estimate: Any = 1.0,
    partial_result: Any = None,
    physics_validator: Optional[Callable[[Any], bool]] = None,
    force_mock_ollama: bool = False
):
    """Self-healing decorator enforcing three tiers of system healing.

    V2.0 EXTENSIONS:
    - Weighted circuit breaker: errors contribute severity-based weight
    - Half-open recovery: after cooldown, allows probe requests
    - LLM rate limiter: prevents Ollama overload
    - DEGRADED status: when healing in half-open probe mode
    - audit_ref: HMAC traceability reference in SafetyResult

    ALL V53 + V58 BUG FIXES PRESERVED.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., SafetyResult]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> SafetyResult:
            func_name = func.__name__
            input_args_dict = {"args": args, "kwargs": kwargs}
            before_hash = compute_hash(input_args_dict)

            # ---------------------------------------------------------
            # CHECK TIER 3: CIRCUIT BREAKER STATUS
            # V53 FIX (BUG 2): Use check_and_cooldown() for combined
            # query + cooldown in a single atomic operation
            # V2.0 EXTENSION: Half-open recovery pattern
            # ---------------------------------------------------------
            cb = global_circuit_breaker

            is_fully_open, state_at_check = cb.check_and_cooldown()

            if is_fully_open:
                # Breaker is fully OPEN -- instant fallback to static safe defaults
                safe_fallback = default_value if default_value is not None else safe_minimum

                # V67 FIX (CRITICAL): NaN/Inf guard in Tier 3 fallback path.
                # Without this guard, default_value=float('inf') or float('nan')
                # would pass through the physics_validator check when no
                # validator is provided (physics_validator=None). Infinity as a
                # sprinkler pressure is physically meaningless and would propagate
                # into downstream voltage drop and battery calculations, causing
                # PhysicsGuardError crashes or silently wrong results.
                # Per QOMN kernel safety principle: "NaN/Inf NEVER propagate."
                if isinstance(safe_fallback, float) and (
                    math.isnan(safe_fallback) or math.isinf(safe_fallback)
                ):
                    safe_fallback = safe_minimum

                # V68 FIX (HIGH): Wrap physics_validator in try/except in Tier 3.
                # In Tier 1 (line 1010-1012), the validator call is wrapped in
                # try/except, but in Tier 3 it was NOT. If the validator raises
                # an exception (e.g., safe_fallback is a string and the validator
                # expects a float), the exception would propagate up and crash
                # the safety system. In a life-safety system, crashing is worse
                # than returning a conservative fallback.
                if physics_validator:
                    try:
                        if not physics_validator(safe_fallback):
                            safe_fallback = safe_minimum
                    except Exception:
                        safe_fallback = safe_minimum  # V FIX: was 0.0 (absolute floor).
                    # 0.0 is dangerous for pressure calculations -- 0 psi is
                    # "no pressure" which is physically wrong and could be
                    # misinterpreted as "no sprinkler protection needed."
                    # safe_minimum (7.0 psi per NFPA 13) is the correct
                    # conservative fallback.

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
                    "user_notification_status": "ALERTED"
                }
                global_audit_logger.log_event(event_data)

                return SafetyResult(
                    value=safe_fallback,
                    status=SystemStatus.CRITICAL_CIRCUIT_OPEN,
                    metadata={"error": "Circuit Breaker Tripped"},
                    audit_ref=f"SH-{before_hash[:8]}-{after_hash[:8]}",
                )

            # V66 FIX (CRITICAL): Use state_at_check from atomic check_and_cooldown()
            # instead of reading cb.state without a lock. The old code:
            #   was_half_open = cb.state == cb.HALF_OPEN
            # had a race condition -- between check_and_cooldown() releasing
            # its lock and this line executing, another thread could change
            # cb.state. Now we use the state captured atomically inside the lock.
            was_half_open = state_at_check == cb.HALF_OPEN

            # ---------------------------------------------------------
            # EXECUTE NOMINAL PATH
            # ---------------------------------------------------------
            try:
                nominal_value = func(*args, **kwargs)

                # V76 FIX (CRITICAL): Validate nominal value against physics
                # constraints BEFORE declaring NOMINAL status. Without this
                # guard, a function that returns float('nan') or a physically
                # impossible value (e.g., negative pressure) is reported as
                # NOMINAL — the operator believes the system is working when
                # it has produced a dangerous result.
                #
                # Three specific problems fixed vs the original proposal:
                # 1. LRU cache was updated BEFORE validation — wrong values
                #    stored as "Last Known Good" and recovered on MemoryError.
                #    Fix: validate BEFORE caching.
                # 2. Circuit breaker was not notified — repeated bad nominal
                #    values don't accumulate toward breaker threshold.
                #    Fix: register NominalPhysicsViolation with CB.
                # 3. safe_minimum was the only fallback — inappropriate for
                #    non-pressure functions (e.g., safe_minimum=0.0 for audio
                #    means "no alarm sound"). Fix: try default_value first.
                if physics_validator:
                    try:
                        if not physics_validator(nominal_value):
                            # Nominal value is physically invalid!
                            # Determine best replacement: prefer default_value
                            # (function-specific) over safe_minimum (generic).
                            replacement = safe_minimum
                            if default_value is not None:
                                try:
                                    if physics_validator(default_value):
                                        replacement = default_value
                                except Exception:
                                    pass  # validator crash on default_value

                            # Register with circuit breaker so repeated
                            # physics violations accumulate toward threshold
                            cb.register_healing_event(
                                error_type="NominalPhysicsViolation"
                            )

                            after_hash = compute_hash(replacement)
                            global_audit_logger.log_event({
                                "function_name": func_name,
                                "error_type": "NominalPhysicsViolation",
                                "error_message": (
                                    f"Nominal value {nominal_value} failed "
                                    f"physics validation"
                                ),
                                "tier_used": 1,
                                "fix_applied": replacement,
                                "verification_result": "PASSED_PHYSICS_GUARD",
                                "before_hash": before_hash,
                                "after_hash": after_hash,
                                "user_notification_status": "ALERTED"
                            })

                            return SafetyResult(
                                value=replacement,
                                status=SystemStatus.DEGRADED,
                                metadata={
                                    "warning": "Nominal value invalid",
                                    "original": nominal_value,
                                    "replacement_reason": "physics_validator_rejected",
                                },
                                audit_ref=f"SH-{before_hash[:8]}-{after_hash[:8]}",
                            )
                    except Exception as validator_err:
                        # The validator ITSELF crashed — treat as DEGRADED
                        # with safe_minimum, because we cannot trust any
                        # value that a crashing validator might have passed.
                        cb.register_healing_event(
                            error_type="PhysicsValidatorCrash"
                        )

                        after_hash = compute_hash(safe_minimum)
                        global_audit_logger.log_event({
                            "function_name": func_name,
                            "error_type": "PhysicsValidatorCrash",
                            "error_message": str(validator_err),
                            "tier_used": 1,
                            "fix_applied": safe_minimum,
                            "verification_result": "VALIDATOR_CRASH_FALLBACK",
                            "before_hash": before_hash,
                            "after_hash": after_hash,
                            "user_notification_status": "ALERTED"
                        })

                        return SafetyResult(
                            value=safe_minimum,
                            status=SystemStatus.DEGRADED,
                            metadata={
                                "warning": "Physics validator crashed",
                                "validator_error": str(validator_err),
                            },
                            audit_ref=f"SH-{before_hash[:8]}-{after_hash[:8]}",
                        )

                # Also catch NaN/Inf that slipped through without a validator
                if isinstance(nominal_value, float) and (
                    math.isnan(nominal_value) or math.isinf(nominal_value)
                ):
                    cb.register_healing_event(
                        error_type="NominalNaNInf"
                    )
                    replacement = default_value if default_value is not None else safe_minimum
                    # V67 FIX: NaN/Inf guard on replacement too
                    if isinstance(replacement, float) and (
                        math.isnan(replacement) or math.isinf(replacement)
                    ):
                        replacement = safe_minimum

                    after_hash = compute_hash(replacement)
                    global_audit_logger.log_event({
                        "function_name": func_name,
                        "error_type": "NominalNaNInf",
                        "error_message": (
                            f"Nominal value is {nominal_value} — "
                            f"NaN/Inf never propagate (QOMN kernel principle)"
                        ),
                        "tier_used": 1,
                        "fix_applied": replacement,
                        "verification_result": "PASSED_NAN_INF_GUARD",
                        "before_hash": before_hash,
                        "after_hash": after_hash,
                        "user_notification_status": "ALERTED"
                    })

                    return SafetyResult(
                        value=replacement,
                        status=SystemStatus.DEGRADED,
                        metadata={
                            "warning": "Nominal value was NaN/Inf",
                            "original": str(nominal_value),
                        },
                        audit_ref=f"SH-{before_hash[:8]}-{after_hash[:8]}",
                    )

                # All validations passed: update LRU cache with verified LKG
                global_lru_cache.update(func_name, nominal_value)

                # V2.0: Record success for half-open recovery
                cb.record_success()

                return SafetyResult(value=nominal_value, status=SystemStatus.NOMINAL)

            except Exception as e:
                # V72 FIX (MEDIUM): SafetyCriticalFailure must NEVER be healed.
                # This exception type means "the system has fundamentally failed
                # in a way that healing is inappropriate" -- for example, all
                # calculation tiers have been exhausted, or a physical constraint
                # has been violated in a way that no safe fallback exists.
                # Healing such a failure would mask a systemic problem and create
                # a false sense of safety. In a fire protection system, masking
                # a SafetyCriticalFailure could mean operators believe the system
                # is working when it has actually suffered a catastrophic failure.
                # The correct response is to re-raise immediately so callers can
                # trigger emergency procedures, alert authorities, or shut down.
                if isinstance(e, SafetyCriticalFailure):
                    logging.critical(
                        f"[SAFETY CRITICAL FAILURE] {func_name} raised "
                        f"SafetyCriticalFailure: {e!s}. "
                        f"This exception type is NON-HEALABLE by design. "
                        f"Re-raising immediately. System requires immediate attention."
                    )
                    # Still register with circuit breaker for monitoring
                    cb.register_healing_event(error_type="SafetyCriticalFailure")
                    # Still log the event for audit trail
                    global_audit_logger.log_event({
                        "function_name": func_name,
                        "error_type": "SafetyCriticalFailure",
                        "error_message": str(e),
                        "tier_used": 0,  # No tier applied -- non-healable
                        "fix_applied": None,
                        "verification_result": "NON_HEALABLE",
                        "before_hash": before_hash,
                        "after_hash": "NONE",
                        "user_notification_status": "CRITICAL_ALERT"
                    })
                    raise

                # Execution failed: capture original stack context
                err_type = type(e).__name__
                err_msg = str(e)
                traceback.format_exc()

                # V2.0: If in HALF_OPEN state, probe has FAILED
                # A "healed" result does NOT count as a success for recovery --
                # the circuit breaker tests whether the UNDERLYING system works,
                # not whether the healing system can cover for it.
                if was_half_open:
                    cb.record_probe_failure()

                # Register weighted healing event; trip circuit breaker if threshold exceeded
                circuit_closed = cb.register_healing_event(error_type=err_type)

                # Determine result status based on breaker state when error occurred
                if was_half_open:
                    result_status = SystemStatus.DEGRADED
                else:
                    result_status = SystemStatus.HEALED

                # -----------------------------------------------------
                # TIER 1: DETERMINISTIC RULE-BASED HEALING
                # -----------------------------------------------------
                healed_val = None
                tier_1_applied = False

                if err_type == "ZeroDivisionError":
                    # V58 FIX (BUG #8) + V59 CORRECTION + V FIX: For ZeroDivisionError,
                    # prefer safe_minimum over default_value when default_value is
                    # NaN/Inf. Per QOMN kernel safety principle, NaN/Inf NEVER
                    # propagate -- always caught and rejected.
                    if default_value is not None and physics_validator is not None:
                        try:
                            # V FIX: NaN/Inf guard -- reject infinite defaults even
                            # if a permissive validator would accept them.
                            if isinstance(default_value, float) and (math.isnan(default_value) or math.isinf(default_value)):
                                healed_val = safe_minimum
                            elif physics_validator(default_value):
                                healed_val = default_value
                            else:
                                healed_val = safe_minimum
                        except Exception:
                            healed_val = safe_minimum
                    elif default_value is not None:
                        # V FIX: Same NaN/Inf guard for paths without validator
                        if isinstance(default_value, float) and (math.isnan(default_value) or math.isinf(default_value)):
                            healed_val = safe_minimum
                        else:
                            healed_val = default_value
                    else:
                        healed_val = safe_minimum
                    tier_1_applied = True

                elif err_type == "IndexError":
                    # V FIX: When a physics_validator is provided, the function
                    # is safety-critical and Tier 1's last-element fallback may return an
                    # incorrect value. Delegate to Tier 2 which uses the configured
                    # default_value after validation.
                    if physics_validator is None:
                        # Non-safety-critical: return last valid item of first list parameter
                        if args and isinstance(args[0], (list, tuple)) and len(args[0]) > 0:
                            healed_val = args[0][-1]
                        else:
                            healed_val = default_value
                        tier_1_applied = True
                    # else: tier_1_applied remains False, falls through to Tier 2

                elif err_type == "ValueError":
                    # NFPA 72 Section 10.3 safety minimum limits
                    healed_val = safe_minimum
                    tier_1_applied = True

                elif err_type == "KeyError":
                    # V75 FIX: NaN/Inf guard for KeyError path, same as ZeroDivisionError.
                    # Without this, default_value=float('inf') would pass through
                    # and be returned as a healed value.
                    if default_value is not None:
                        if isinstance(default_value, float) and (
                            math.isnan(default_value) or math.isinf(default_value)
                        ):
                            healed_val = safe_minimum
                        else:
                            healed_val = default_value
                    else:
                        healed_val = safe_minimum
                    tier_1_applied = True

                elif err_type == "TypeError":
                    # V53 FIX (BUG 8): Duck typing fallback casting with safe fallback
                    try:
                        if default_value is not None:
                            healed_val = type(default_value)(conservative_estimate)
                        else:
                            healed_val = float(conservative_estimate)
                    except (TypeError, ValueError):
                        # V53 FIX: If casting fails, use conservative_estimate directly
                        # rather than default_value which could be None (BUG 5)
                        healed_val = conservative_estimate
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

                # V53 FIX (BUG 5): Reject None healed values before returning to caller
                # In a safety-critical system, returning None as a "healed" value is
                # unacceptable because downstream code may crash on None, causing a
                # cascade failure. Force Tier 2 if Tier 1 produced None.
                if tier_1_applied and healed_val is None:
                    logging.warning(
                        f"[TIER 1 SAFETY GUARD] Tier 1 produced None for {err_type} "
                        f"in {func_name}. Escalating to Tier 2 for safe recovery."
                    )
                    tier_1_applied = False

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
                            "user_notification_status": "SILENT" if circuit_closed else "ALERTED"
                        }
                        global_audit_logger.log_event(event_data)

                        return SafetyResult(
                            value=healed_val,
                            status=result_status,
                            metadata={"tier": 1, "rule": err_type},
                            audit_ref=f"SH-{before_hash[:8]}-{after_hash[:8]}",
                        )

                # -----------------------------------------------------
                # TIER 2: LOCAL LLM RECOVERY LOOP (OLLAMA / LLAMA)
                # -----------------------------------------------------
                logging.warning(
                    f"[TIER 2 HEALING INITIALIZED] Standard Tier 1 rules could "
                    f"not safely resolve {err_type} in {func_name}. Querying Local LLM Agent..."
                )

                llm_response_val = None
                tier_2_verified = False

                # V58 FIX (BUG #4): Wrap inspect.getsource() in try-except.
                # This function raises OSError when source is unavailable
                # (PyInstaller bundles, .pyc-only, Cython, REPL, frozen exe).
                try:
                    source_code = inspect.getsource(func)
                except (OSError, TypeError):
                    source_code = "<source unavailable>"

                # V2.0: Rate limiter check before calling LLM
                if not global_llm_breaker.allow_request():
                    logging.warning(
                        "[LLM RATE LIMITER] Ollama request rate limit reached. "
                        "Falling back to safe default."
                    )
                    llm_response_val = default_value if default_value is not None else safe_minimum
                elif force_mock_ollama:
                    # Deterministic mock fallback for environment consistency
                    llm_response_val = default_value if default_value is not None else safe_minimum
                else:
                    # Make a structured HTTP call to localhost Ollama service
                    llm_response_val = query_local_ollama_engine(
                        func_name=func_name,
                        err_type=err_type,
                        err_msg=err_msg,
                        inputs=input_args_dict,
                        source_code=source_code,
                        default_fallback=default_value if default_value is not None else safe_minimum,
                        timeout=global_llm_breaker.timeout,
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
                        "user_notification_status": "ALERTED"
                    }
                    global_audit_logger.log_event(event_data)

                    # Log message notifying user/operator of recovery action
                    logging.info(
                        f"[TIER 2 HEALED SUCCESS] Recovered from {err_type} in {func_name} "
                        f"using verified LLM patch value: {llm_response_val}."
                    )

                    return SafetyResult(
                        value=llm_response_val,
                        status=result_status,
                        metadata={"tier": 2, "suggested_by": "ollama_agent"},
                        audit_ref=f"SH-{before_hash[:8]}-{after_hash[:8]}",
                    )

                # If all healing fails, raise original error
                raise e

        return wrapper
    return decorator


# =====================================================================
# SECTION 8: LOCAL OLLAMA MCP DRIVER
# =====================================================================

def query_local_ollama_engine(
    func_name: str,
    err_type: str,
    err_msg: str,
    inputs: Dict[str, Any],
    source_code: str,
    default_fallback: Any,
    timeout: float = 2.0,
) -> Any:
    """Connects to the local Ollama instance (llama3) to generate a patch.
    This process is contained locally and does not leak telemetry data externally.

    V58 FIX (BUG #12): NaN/Inf detection uses math module, not fragile string comparison.
    V2.0 EXTENSION: Configurable timeout via parameter.
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

    payload = {
        "model": "llama3",
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    req_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        # Enforce strict timeout to prevent stalling the safety thread
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            llm_text = res_json.get("response", "{}")

            # Parse inner JSON
            parsed_text = json.loads(llm_text)
            suggested_val = parsed_text.get("suggested_return_value")

            # V58 FIX (BUG #12): Robust NaN/Inf detection using math module
            # instead of fragile string comparison. Also catches float('inf').
            if isinstance(suggested_val, float) and (math.isnan(suggested_val) or math.isinf(suggested_val)):
                return default_fallback

            # String representation fallback for edge cases
            if str(suggested_val).lower() in ("nan", "inf", "-inf", "+inf"):
                return default_fallback

            return suggested_val

    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        # Local Ollama offline, timeouts, or invalid JSON response falls back to mock validation
        logging.warning(
            f"[LOCAL OLLAMA UNREACHABLE/TIMEOUT] Reason: {e!s}. "
            f"Failing-over to local safe boundary validation logic."
        )
        return default_fallback


# =====================================================================
# SECTION 9: SYSTEM INTEGRATION & USAGE EXAMPLES
# =====================================================================

def validate_sprinkler_pressure(val: Any) -> bool:
    """Sprinkler operating pressure must be positive, non-zero, and finite.

    V FIX: Removed `or val == float('inf')` clause. Per the QOMN kernel
    safety principle, float('inf') must NEVER be accepted as a valid
    healed value because it propagates into downstream kernel computations
    (voltage drop, battery calculations) causing PhysicsGuardError crashes.
    A sprinkler pressure of infinity is physically meaningless -- the correct
    response to zero k-factor is the safe_minimum (7.0 psi per NFPA 13),
    not infinity.

    V69 FIX (HIGH): Reject val == 0.0. A sprinkler pressure of 0.0 psi
    means NO water is flowing through the sprinkler head. NFPA 13 Section
    23.4.4 requires a minimum operating pressure of 7.0 psi. A value of
    0.0 psi would pass the old validator (val >= 0.0 is True for 0.0),
    causing the system to report NOMINAL status for a sprinkler that
    provides ZERO fire protection. In a real fire, sprinklers at 0 psi
    deliver no water -- people die.
    """
    if isinstance(val, (int, float)):
        return val > 0.0 and math.isfinite(val)
    return False


@self_healing(safe_minimum=7.0, default_value=7.0, physics_validator=validate_sprinkler_pressure)
def calculate_sprinkler_pressure(flow_gpm: float, k_factor: float) -> float:
    """Computes required operating pressure: P = (Q / K)^2
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
    force_mock_ollama=True  # Demonstrates Tier 2 fallback processing
)
def fetch_emergency_audio_sequence(sequence_list: List[str], index: int) -> str:
    """Fetches scheduled audio tone file.
    Citing: NFPA 72 Section 18.4
    """
    if index >= len(sequence_list):
        raise IndexError("Sequence index overflow.")
    return sequence_list[index]


def demonstrate_and_verify_all_tiers():
    """Demonstrates active runtime healing across all tiers, logging actions in the ledger.
    """
    print("\n" + "=" * 70)
    print("RUNNING QOMN-FIRE SELF-HEALING SYSTEM V2.0 (MERGED)")
    print("=" * 70)

    # Reset state
    global_circuit_breaker.reset()

    # 1. NOMINAL RUN
    print("\n--- Running Nominal Calculations ---")
    nom_result = calculate_sprinkler_pressure(100.0, 5.6)
    print(f"Nominal Result: {nom_result.value:.4f} psi (Status: {nom_result.status})")

    # 2. TIER 1 HEALING RUN (ZeroDivisionError)
    print("\n--- Triggering Tier 1 ZeroDivisionError Healing ---")
    healed_result_t1 = calculate_sprinkler_pressure(100.0, 0.0)
    print(
        f"Healed Result T1 Value: {healed_result_t1.value} "
        f"(Status: {healed_result_t1.status}, Metadata: {healed_result_t1.metadata})"
    )

    # 3. TIER 2 HEALING RUN (IndexError LLM Fallback)
    print("\n--- Triggering Tier 2 IndexError Healing (Verified Local LLM) ---")
    sequence_blocks = ["ALERT_CHIME", "EVAC_VOICE_ENG"]
    healed_result_t2 = fetch_emergency_audio_sequence(sequence_blocks, 99)
    print(
        f"Healed Result T2 Value: '{healed_result_t2.value}' "
        f"(Status: {healed_result_t2.status}, Metadata: {healed_result_t2.metadata})"
    )

    # 4. TIER 3 HEALING RUN (Circuit Breaker Tripping)
    print("\n--- Stress Testing Circuit Breaker (Tier 3 Cascade Prevention) ---")
    global_circuit_breaker.reset()

    print("Simulating high-frequency fault occurrences...")
    for cycle in range(12):
        res = calculate_sprinkler_pressure(100.0, 0.0)
        if res.status == SystemStatus.CRITICAL_CIRCUIT_OPEN:
            print(f"Cycle {cycle:02d}: Circuit Breaker OPENED! Fallback value: {res.value}")
            break
        if res.status == SystemStatus.DEGRADED:
            print(f"Cycle {cycle:02d}: DEGRADED (half-open probe). Value: {res.value}")
        else:
            print(
                f"Cycle {cycle:02d}: Healed value ({res.value}). "
                f"State: {global_circuit_breaker.state}"
            )

    # 5. Circuit Breaker Health Monitor
    print("\n--- Circuit Breaker Health Monitor ---")
    health = global_circuit_breaker.health()
    for k, v in health.items():
        print(f"  {k}: {v}")

    # 6. LRU Cache Statistics
    print("\n--- LRU Cache Statistics ---")
    stats = global_lru_cache.stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # 7. Audit Logger Statistics
    print("\n--- Audit Logger Statistics ---")
    audit_stats = global_audit_logger.stats()
    for k, v in audit_stats.items():
        print(f"  {k}: {v}")

    # 8. LLM Rate Limiter Statistics
    print("\n--- LLM Rate Limiter Statistics ---")
    llm_stats = global_llm_breaker.stats()
    for k, v in llm_stats.items():
        print(f"  {k}: {v}")

    # Restoring System State
    global_circuit_breaker.reset()
    print("\n" + "=" * 70)
    print("SELF-HEALING DEMONSTRATION RUN COMPLETE (V2.0 MERGED)")
    print("=" * 70)
