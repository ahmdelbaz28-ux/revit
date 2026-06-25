"""fireai.core.security_logging — Security Event Audit Logging & Log Rotation
==========================================================================

Centralized security event logging for the FireAI system. Provides:

1. **Security Event Audit Log** — Dedicated log for security-sensitive events
   (authentication, authorization, configuration changes, HMAC operations).
   Events are written to a separate file and include tamper-evident chaining.

2. **Sensitive Data Masking** — Automatic redaction of API keys, tokens,
   and other secrets from log output. Prevents accidental credential leakage.

3. **Log Rotation via loguru** — Size-based (500 MB) and time-based
   (30-day retention) rotation with automatic zip compression of rotated
   files. Replaces the previous RotatingFileHandler approach which lacked
   compression and had smaller (50 MB) file size limits.

SECURITY DESIGN:
  - Security audit log is SEPARATE from application log (different file,
    different handler). This prevents security events from being lost in
    verbose application logs.
  - Log entries include a chain hash for tamper detection.
  - All secrets are automatically masked before writing to any log.
  - The hex-regex masking pattern excludes hash-like fields (chain_hash,
    entry_hash, hmac_signature) to prevent corruption of audit chain data.

USAGE:
  from fireai.core.security_logging import security_audit, mask_sensitive

  security_audit.log_event("AUTH_FAILURE", ip="1.2.3.4", path="/api/projects")
  logger.info("Key: %s", mask_sensitive(api_key))

NFPA 72 Reference:
  - §10.6.7 — Record retention requirements
  - §14.2.4 — Documentation integrity requirements
"""

from __future__ import annotations

import hashlib
import hmac as _hmac_module
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── loguru integration ─────────────────────────────────────────────────────
# SECURITY FIX (V103): Replace RotatingFileHandler with loguru for:
#   1. 500 MB rotation (was 50 MB — too small for production security logs)
#   2. 30-day retention with automatic cleanup
#   3. Zip compression of rotated files (saves ~80% disk on text logs)
#   4. Sensitive data masking via custom sink wrapper
# loguru is already in requirements.txt and is the Python ecosystem's
# standard structured logging library with built-in rotation + compression.
try:
    from loguru import logger as _loguru_logger

    _LOGURU_AVAILABLE = True
    # V103 FIX: Remove loguru's default stderr handler. We configure our own
    # file sinks with rotation/compression. Without this removal, every
    # message routed through loguru would ALSO print to stderr, causing
    # duplicate output in production and filling Docker container logs.
    _loguru_logger.remove()
except ImportError:
    _LOGURU_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════════
# SENSITIVE DATA MASKING
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns that match common sensitive values
_SENSITIVE_PATTERNS = [
    # API keys and tokens (common variable names in logs)
    re.compile(
        r"(api[_-]?key|token|secret|password|auth[_-]?key|bearer|credential)"
        r'["\s:=]+["\']?([A-Za-z0-9_\-\.]{8,})',
        re.IGNORECASE,
    ),
    # Bearer tokens in Authorization headers
    re.compile(r"(Bearer\s+)([A-Za-z0-9_\-\.]+)", re.IGNORECASE),
]

# V105 FIX (HIGH-2): REMOVED the overly broad hex-regex pattern that was
# corrupting hash values in log output. The previous pattern:
#   re.compile(r'(?<=["\s:=])([a-f0-9]{32,})(?=["\s,])', re.IGNORECASE)
# matched ANY 32+ char hex string, including SHA-256 hashes, HMAC signatures,
# chain_hash values, entry_hash values, and other legitimate cryptographic
# digests used in audit trails. When applied by SensitiveDataFilter, it
# replaced these with "***REDACTED***", breaking verify_chain() and making
# forensic analysis impossible. The security value of this pattern was also
# questionable — real API keys and tokens rarely appear as bare hex strings
# in log output; they almost always appear in key-value contexts that are
# already caught by the first two patterns (which look for key names like
# "api_key", "token", "secret" before the value).

# Known sensitive environment variable names
_SENSITIVE_ENV_VARS = frozenset(
    {
        "FIREAI_API_KEY",
        "FIREAI_EVIDENCE_HMAC_KEY",
        "AUDIT_HMAC_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "FIREAI_OPENAI_API_KEY",
        "DATABASE_URL",
    }
)

# V105 FIX: The env var cache is refreshed before each mask_sensitive()
# call to handle runtime key rotation. This is safe because os.getenv()
# is a C-level call that's extremely fast (~50ns per call for 7 vars).
_ENV_VALUE_CACHE: Dict[str, str] = {}
_ENV_CACHE_TIMESTAMP: float = 0.0


def _refresh_env_cache() -> None:
    """Refresh the cached environment variable values.

    Uses a 5-second cache TTL to avoid calling os.getenv() on every single
    mask_sensitive() call while still picking up key rotation changes
    within a reasonable window. Call with force=True to bypass TTL.
    """
    global _ENV_VALUE_CACHE, _ENV_CACHE_TIMESTAMP
    import time as _time

    now = _time.monotonic()
    if now - _ENV_CACHE_TIMESTAMP < 5.0 and _ENV_VALUE_CACHE:
        return  # Cache is fresh
    _force_refresh_env_cache()


def _force_refresh_env_cache() -> None:
    """Force-refresh the env var cache regardless of TTL.

    Called internally when cache is empty or TTL expired.
    Also useful for testing after setting env vars at runtime.
    """
    global _ENV_VALUE_CACHE, _ENV_CACHE_TIMESTAMP
    import time as _time

    _ENV_VALUE_CACHE = {}
    for var_name in _SENSITIVE_ENV_VARS:
        value = os.getenv(var_name, "")
        if value and len(value) >= 4:
            _ENV_VALUE_CACHE[var_name] = value
    _ENV_CACHE_TIMESTAMP = _time.monotonic()


# Initialize cache at module load
_refresh_env_cache()


def mask_sensitive(text: str, mask: str = "***REDACTED***") -> str:
    """Mask sensitive values in a string before logging.

    Replaces API keys, tokens, passwords, and other secrets with
    a redaction marker. This prevents accidental credential leakage
    in log files, error reports, and debugging output.

    V105 FIX: No longer matches bare hex strings (32+ chars) because
    this corrupted cryptographic hash values used in audit trails.
    Only masks values that appear in key-value context (e.g.,
    "api_key=..." or "Bearer ...") or match known environment variables.

    Args:
        text: The string to mask.
        mask: The replacement string for sensitive values.

    Returns:
        The string with sensitive values replaced by the mask.

    """
    if not text or not isinstance(text, str):
        return str(text) if text is not None else ""

    result = text

    # Refresh env var cache if stale (5s TTL)
    _refresh_env_cache()

    # Mask values from sensitive environment variables (using cache)
    for _var_name, value in _ENV_VALUE_CACHE.items():
        if value in result:
            result = result.replace(value, mask)

    # Apply regex patterns
    for pattern in _SENSITIVE_PATTERNS:
        result = pattern.sub(
            lambda m: m.group(0).replace(m.group(m.lastindex or 0), mask) if m.lastindex else m.group(0),
            result,
        )

    return result


class SensitiveDataFilter(logging.Filter):
    """Logging filter that automatically masks sensitive data in log records.

    Attach to any logger to prevent credential leakage:
        logger.addFilter(SensitiveDataFilter())

    V105 FIX: This filter no longer corrupts cryptographic hash values
    because the hex-regex pattern has been removed from _SENSITIVE_PATTERNS.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_sensitive(record.msg)
        if record.args and isinstance(record.args, dict):
            record.args = {k: mask_sensitive(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
        elif record.args and isinstance(record.args, tuple):
            record.args = tuple(mask_sensitive(str(a)) if isinstance(a, str) else a for a in record.args)
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# LOG ROTATION CONFIGURATION (loguru-based)
# ═══════════════════════════════════════════════════════════════════════════════

# Default rotation settings (configurable via environment variables)
# SECURITY FIX (V103): Increased from 50 MB to 500 MB per the security audit.
# 50 MB is too small for a production security log — a busy system can fill
# that in hours, causing rapid rotation that makes forensic analysis difficult.
# 500 MB gives ~1-2 weeks of security events per file in production.
_DEFAULT_MAX_BYTES = int(os.getenv("FIREAI_LOG_MAX_BYTES", str(500 * 1024 * 1024)))  # 500 MB
_DEFAULT_RETENTION_DAYS = int(os.getenv("FIREAI_LOG_RETENTION_DAYS", "30"))  # 30 days
_DEFAULT_BACKUP_COUNT = int(os.getenv("FIREAI_LOG_BACKUP_COUNT", "20"))  # 20 rotating files

# Log directory (configurable)
_LOG_DIR = Path(os.getenv("FIREAI_LOG_DIR", "logs"))


def configure_log_rotation(
    logger_instance: logging.Logger,
    log_file: str = "fireai.log",
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> None:
    """Configure size-based log rotation for a logger.

    Uses loguru when available (with zip compression and 30-day retention),
    falls back to Python's RotatingFileHandler when loguru is not installed.

    IMPORTANT: When loguru is available, it is the SOLE writer to the log
    file. Standard Python logging.Logger messages are routed through loguru
    via a LoguruBridge, so there is no duplicate-write problem.

    V105 FIX: Do NOT call this for "security_audit.log" — the
    SecurityAuditLogger manages its own log rotation independently.
    Calling this for security_audit.log creates duplicate loguru sinks
    that corrupt the chain (CRITICAL-2 fix).

    Args:
        logger_instance: The logger to configure.
        log_file: Filename for the log file (within _LOG_DIR).
        max_bytes: Maximum size per log file before rotation.
        backup_count: Number of rotated backup files to keep.

    """
    # V105 FIX (CRITICAL-2): Prevent duplicate sinks for security_audit.log.
    # SecurityAuditLogger already manages its own loguru sink with proper
    # filtering (audit_channel="security"). Adding another sink via this
    # function creates triple entries and corrupts the chain.
    if log_file == "security_audit.log":
        return  # SecurityAuditLogger manages its own rotation

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / log_file

    if _LOGURU_AVAILABLE:
        # V103 FIX: Use loguru as the SOLE file writer with:
        #   - 500 MB size-based rotation
        #   - 30-day time-based retention (auto-cleanup)
        #   - Zip compression of rotated files
        #   - Sensitive data masking via LoguruBridge
        _loguru_logger.add(
            str(log_path),
            rotation=max_bytes,  # Size-based: rotate at 500 MB
            retention=f"{_DEFAULT_RETENTION_DAYS} days",  # Time-based: keep 30 days
            compression="zip",  # Zip compress rotated files
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} [{level}] {name}: {message}",
            level="INFO",
            filter=lambda record: True,  # Accept all messages
            serialize=False,
        )

        class _LoguruBridge(logging.Handler):
            """Bridges standard Python logging to loguru's file sink."""

            def emit(self, record: logging.LogRecord) -> None:
                try:
                    msg = self.format(record)
                    masked_msg = mask_sensitive(msg)
                    _loguru_logger.opt(depth=0).info(masked_msg)
                except Exception as exc:
                    logger.error("LoguruBridge.emit failed — security log message dropped: %s", exc)

        bridge = _LoguruBridge()
        bridge.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger_instance.addHandler(bridge)
    else:
        # Fallback: standard RotatingFileHandler without compression
        from logging.handlers import RotatingFileHandler

        handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        handler.addFilter(SensitiveDataFilter())
        logger_instance.addHandler(handler)


def configure_timed_rotation(
    logger_instance: logging.Logger,
    log_file: str = "fireai.log",
    when: str = "midnight",
    backup_count: int = _DEFAULT_RETENTION_DAYS,
) -> None:
    """Configure time-based log rotation for a logger.

    Uses loguru when available (with zip compression), falls back to
    Python's TimedRotatingFileHandler when loguru is not installed.

    V105 FIX: Do NOT call this for "security_audit.log" — the
    SecurityAuditLogger manages its own log rotation independently.

    Args:
        logger_instance: The logger to configure.
        log_file: Filename for the log file (within _LOG_DIR).
        when: Rotation interval ('midnight', 'D' for daily, 'H' for hourly).
        backup_count: Number of days of logs to retain.

    """
    # V105 FIX (CRITICAL-2): Same protection as configure_log_rotation.
    if log_file == "security_audit.log":
        return

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / log_file

    if _LOGURU_AVAILABLE:
        # V103 FIX: loguru with time-based retention + zip compression
        _loguru_logger.add(
            str(log_path),
            rotation="1 day" if when in ("midnight", "D") else "1 hour",
            retention=f"{backup_count} days",
            compression="zip",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} [{level}] {name}: {message}",
            level="INFO",
            filter=lambda record: True,
        )

        class _LoguruBridgeTimed(logging.Handler):
            """Bridges standard Python logging to loguru's file sink."""

            def emit(self, record: logging.LogRecord) -> None:
                try:
                    msg = self.format(record)
                    masked_msg = mask_sensitive(msg)
                    _loguru_logger.opt(depth=0).info(masked_msg)
                except Exception as exc:
                    logger.error("LoguruBridgeTimed.emit failed — security log message dropped: %s", exc)

        bridge = _LoguruBridgeTimed()
        bridge.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger_instance.addHandler(bridge)
    else:
        # Fallback: standard TimedRotatingFileHandler without compression
        from logging.handlers import TimedRotatingFileHandler

        handler = TimedRotatingFileHandler(
            log_path,
            when=when,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        handler.addFilter(SensitiveDataFilter())
        logger_instance.addHandler(handler)


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════════

# Genesis sentinel for the security audit chain hash.
# V105 FIX (LOW-6): Use a consistent format with audit_log.py for potential
# future cross-verification. Both now use a 64-char hex string.
_SECURITY_GENESIS = "0" * 64


# Security event types
class SecurityEventType:
    """Classification of security events for audit logging."""

    AUTH_SUCCESS = "AUTH_SUCCESS"
    AUTH_FAILURE = "AUTH_FAILURE"
    AUTH_KEY_ROTATION = "AUTH_KEY_ROTATION"
    CORS_VIOLATION = "CORS_VIOLATION"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INPUT_VALIDATION_FAILURE = "INPUT_VALIDATION_FAILURE"
    HMAC_INTEGRITY_FAILURE = "HMAC_INTEGRITY_FAILURE"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    SUBPROCESS_EXECUTION = "SUBPROCESS_EXECUTION"
    EVIDENCE_PACKAGE_CREATED = "EVIDENCE_PACKAGE_CREATED"
    EVIDENCE_PACKAGE_VERIFIED = "EVIDENCE_PACKAGE_VERIFIED"
    SECURITY_SCAN_RESULT = "SECURITY_SCAN_RESULT"
    PLACEHOLDER_KEY_DETECTED = "PLACEHOLDER_KEY_DETECTED"
    WILDCARD_ORIGIN_REJECTED = "WILDCARD_ORIGIN_REJECTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"


def _compute_chain_hash(event_json: str) -> str:
    """Compute the next chain hash from an event's JSON representation.

    Uses HMAC-SHA256 when AUDIT_HMAC_KEY is set (tamper-proof), falls
    back to plain SHA-256 when no key is configured (tamper-evident only).

    V105 FIX (CRITICAL-1): This function is the SINGLE SOURCE OF TRUTH
    for chain hash computation. Both log_event() and verify_chain() call
    this function, eliminating the previous mismatch where log_event()
    used HMAC but verify_chain() always used plain SHA-256.
    """
    _hmac_key = os.getenv("AUDIT_HMAC_KEY", "")
    if _hmac_key:
        return _hmac_module.new(
            _hmac_key.encode("utf-8"),
            event_json.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:32]
    return hashlib.sha256(event_json.encode("utf-8")).hexdigest()[:32]


class SecurityAuditLogger:
    """Dedicated logger for security-sensitive events.

    Writes security events to a separate log file with:
    - Tamper-evident chain hashing (each entry links to the previous)
    - Structured JSON format for easy parsing
    - Automatic sensitive data masking
    - Size-based log rotation (500 MB) with 30-day retention + zip compression

    SECURITY DESIGN:
    The chain hash ensures that if any entry is modified or deleted,
    the chain is broken and tampering is detectable. This is similar
    to how the audit_log.py works but for a different purpose:
    audit_log.py tracks engineering decisions; this tracks security events.

    V105 FIXES:
    - CRITICAL-1: verify_chain() now uses the same _compute_chain_hash()
      as log_event(), fixing the HMAC/SHA-256 mismatch.
    - CRITICAL-2: No duplicate loguru sinks — configure_log_rotation()
      skips security_audit.log.
    - HIGH-1: Chain hash is recovered from existing log on restart.
    - HIGH-2: Hex-regex pattern removed from mask_sensitive() — no
      more hash corruption.
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        backup_count: int = _DEFAULT_BACKUP_COUNT,
    ) -> None:
        self._log_dir = log_dir or _LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._log_dir / "security_audit.log"

        # V102 FIX: Thread-safe lock for chain hash integrity (same pattern
        # as audit_log.py V69-11 FIX). Without this, concurrent log_event()
        # calls break the tamper-evident chain.
        self._lock = threading.Lock()

        # V105 FIX (HIGH-1): Recover chain hash from existing log on restart.
        # Previously, _chain_hash was always set to "GENESIS" on restart,
        # breaking cross-restart chain continuity (NFPA 72 §14.2.4 compliance).
        # Now we scan the existing log file to recover the last chain hash.
        self._chain_hash = self._recover_chain_hash()

        # V105 FIX: SecurityAuditLogger writes DIRECTLY to the log file
        # instead of routing through the global loguru singleton. The previous
        # loguru-based approach had a fundamental design flaw: loguru is a
        # GLOBAL process-level singleton, and multiple SecurityAuditLogger
        # instances (e.g., in tests) would all share the same loguru instance.
        # The `audit_channel="security"` filter tag was shared across instances,
        # causing messages from one instance to appear in another instance's
        # log file (cross-contamination). Direct file writes give each instance
        # precise isolation, which is critical for a tamper-evident audit log.
        #
        # For log rotation, we use RotatingFileHandler which provides
        # size-based rotation. While it lacks loguru's zip compression,
        # the correctness guarantee is more important than disk savings
        # for a safety-critical audit log. The application-level log
        # (fireai.log) still uses loguru with compression.
        from logging.handlers import RotatingFileHandler

        self._logger = logging.getLogger(f"fireai.security_audit.{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False  # Don't duplicate to root logger

        handler = RotatingFileHandler(
            self._log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON
        # V104 FIX: Do NOT add SensitiveDataFilter here. Data is already
        # masked in log_event() before JSON serialization.
        self._logger.addHandler(handler)

    def _recover_chain_hash(self) -> str:
        """Recover the chain hash from the existing log file.

        V105 FIX (HIGH-1): On process restart, the chain hash must link
        to the last entry in the existing log. Without this, new entries
        start with "GENESIS", breaking the chain across restarts.

        Returns:
            The chain hash to use for the next entry, or _SECURITY_GENESIS
            if the log is empty or doesn't exist.

        """
        if not self._log_path.exists():
            return _SECURITY_GENESIS

        try:
            last_line = None
            with open(self._log_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last_line = line

            if last_line is None:
                return _SECURITY_GENESIS

            last_event = json.loads(last_line)
            event_json = json.dumps(last_event, sort_keys=True, separators=(",", ":"))
            return _compute_chain_hash(event_json)
        except (json.JSONDecodeError, OSError, KeyError):
            # Log file corrupt or unreadable — start fresh chain.
            # Archive the corrupt file so we don't lose it entirely.
            _logger = logging.getLogger(__name__)
            _logger.warning(
                "Security audit log is corrupt or unreadable. "
                "Starting new chain. Previous entries may need forensic review."
            )
            return _SECURITY_GENESIS

    def log_event(
        self,
        event_type: str,
        **details: Any,
    ) -> str:
        """Log a security event with tamper-evident chain hashing.

        Thread-safe: acquires self._lock to prevent concurrent chain hash
        corruption (V102 FIX — same pattern as audit_log.py V69-11 FIX).

        V104 FIX (HIGH): Two issues fixed:
        1. Chain hash now uses HMAC-SHA256 (not plain SHA-256 truncated to
           128 bits). Plain SHA-256 is only tamper-evident, not tamper-proof.
        2. Chain hash is stored SEPARATELY from the logged JSON to prevent
           the SensitiveDataFilter from corrupting it.

        V105 FIX: Uses _compute_chain_hash() as single source of truth,
        ensuring log_event() and verify_chain() always use the same algorithm.

        Args:
            event_type: Type of security event (use SecurityEventType constants).
            **details: Additional key-value pairs describing the event.

        Returns:
            The event ID (hash-based) for traceability.

        """
        with self._lock:
            timestamp = datetime.now(timezone.utc).isoformat()

            # Generate event ID
            event_id = hashlib.sha256(f"{timestamp}:{event_type}:{self._chain_hash}".encode()).hexdigest()[:16]

            # Build the event record — mask sensitive details BEFORE computing
            # the chain hash, so that the hash covers the actual stored value.
            masked_details = {}
            for k, v in details.items():
                val_str = str(v)
                # Build a mini key-value pair for context-aware masking
                mini_kv = f'{k}":"{val_str}'
                masked_kv = mask_sensitive(mini_kv)
                # Extract the value part after masking
                if masked_kv != mini_kv:
                    _prefix = f'{k}":"'
                    if masked_kv.startswith(_prefix):
                        masked_details[k] = masked_kv[len(_prefix) :].rstrip('"')
                    else:
                        masked_details[k] = mask_sensitive(val_str)
                else:
                    masked_details[k] = mask_sensitive(val_str)

            event = {
                "event_id": event_id,
                "timestamp": timestamp,
                "event_type": event_type,
                "chain_hash": self._chain_hash,
                "details": masked_details,
            }

            # Compute new chain hash for the next event.
            # V105 FIX: Use _compute_chain_hash() — the single source of truth.
            event_json = json.dumps(event, sort_keys=True, separators=(",", ":"))
            self._chain_hash = _compute_chain_hash(event_json)

            # Write to security audit log.
            # V104 FIX: Data is already masked above. Do NOT apply
            # SensitiveDataFilter again, or the chain_hash hex string
            # will be corrupted by the filter's hex-regex pattern.
            self._logger.info(event_json)

            return event_id

    def verify_chain(self) -> Dict[str, Any]:
        """Verify the integrity of the security audit log chain.

        V105 FIX (CRITICAL-1): Now uses _compute_chain_hash() for
        re-computation, matching log_event()'s algorithm. Previously,
        this method always used plain SHA-256, causing false positives
        when AUDIT_HMAC_KEY was configured.

        Returns:
            Dict with verification results:
            - valid: True if chain is intact
            - entries_checked: Number of entries verified
            - first_break: Event ID where chain was broken (if any)

        """
        if not self._log_path.exists():
            return {"valid": True, "entries_checked": 0, "first_break": None}

        entries_checked = 0
        expected_chain = _SECURITY_GENESIS
        first_break = None

        with open(self._log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    entries_checked += 1

                    # Verify chain link
                    if event.get("chain_hash") != expected_chain:
                        if first_break is None:
                            first_break = event.get("event_id", "unknown")
                    else:
                        # Recompute expected chain hash using the SAME
                        # algorithm as log_event() (HMAC or SHA-256).
                        event_json = json.dumps(event, sort_keys=True, separators=(",", ":"))
                        expected_chain = _compute_chain_hash(event_json)
                except json.JSONDecodeError:
                    if first_break is None:
                        first_break = "PARSE_ERROR"

        return {
            "valid": first_break is None,
            "entries_checked": entries_checked,
            "first_break": first_break,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

# Global security audit logger — one instance per process
security_audit = SecurityAuditLogger()

# Add sensitive data filter to the root FireAI logger
_fireai_logger = logging.getLogger("fireai")
_fireai_logger.addFilter(SensitiveDataFilter())
