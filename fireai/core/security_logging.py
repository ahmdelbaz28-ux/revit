"""
fireai.core.security_logging — Security Event Audit Logging & Log Rotation
==========================================================================

Centralized security event logging for the FireAI system. Provides:

1. **Security Event Audit Log** — Dedicated log for security-sensitive events
   (authentication, authorization, configuration changes, HMAC operations).
   Events are written to a separate file and include tamper-evident chaining.

2. **Sensitive Data Masking** — Automatic redaction of API keys, tokens,
   and other secrets from log output. Prevents accidental credential leakage.

3. **Log Rotation** — Size-based and time-based rotation to prevent disk
   exhaustion. Configurable retention and compression.

SECURITY DESIGN:
  - Security audit log is SEPARATE from application log (different file,
    different handler). This prevents security events from being lost in
    verbose application logs.
  - Log entries include a chain hash for tamper detection.
  - All secrets are automatically masked before writing to any log.

USAGE:
  from fireai.core.security_logging import security_audit, mask_sensitive

  security_audit.log_event("AUTH_FAILURE", ip="1.2.3.4", path="/api/projects")
  logger.info(f"Key: {mask_sensitive(api_key)}")

NFPA 72 Reference:
  - §10.6.7 — Record retention requirements
  - §14.2.4 — Documentation integrity requirements
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

# ═══════════════════════════════════════════════════════════════════════════════
# SENSITIVE DATA MASKING
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns that match common sensitive values
_SENSITIVE_PATTERNS = [
    # API keys and tokens (common variable names in logs)
    re.compile(
        r'(api[_-]?key|token|secret|password|auth[_-]?key|bearer|credential)'
        r'["\s:=]+["\']?([A-Za-z0-9_\-\.]{8,})',
        re.IGNORECASE,
    ),
    # Bearer tokens in Authorization headers
    re.compile(r'(Bearer\s+)([A-Za-z0-9_\-\.]+)', re.IGNORECASE),
    # Long hex strings that look like keys/hashes
    re.compile(r'(?<=["\s:=])([a-f0-9]{32,})(?=["\s,])', re.IGNORECASE),
]

# Known sensitive environment variable names
_SENSITIVE_ENV_VARS = frozenset({
    "FIREAI_API_KEY",
    "FIREAI_EVIDENCE_HMAC_KEY",
    "AUDIT_HMAC_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "FIREAI_OPENAI_API_KEY",
    "DATABASE_URL",
})


def mask_sensitive(text: str, mask: str = "***REDACTED***") -> str:
    """Mask sensitive values in a string before logging.

    Replaces API keys, tokens, passwords, and other secrets with
    a redaction marker. This prevents accidental credential leakage
    in log files, error reports, and debugging output.

    Args:
        text: The string to mask.
        mask: The replacement string for sensitive values.

    Returns:
        The string with sensitive values replaced by the mask.
    """
    if not text or not isinstance(text, str):
        return str(text) if text is not None else ""

    result = text

    # Mask values from sensitive environment variables
    for var_name in _SENSITIVE_ENV_VARS:
        value = os.getenv(var_name, "")
        if value and len(value) >= 4 and value in result:
            result = result.replace(value, mask)

    # Apply regex patterns
    for pattern in _SENSITIVE_PATTERNS:
        result = pattern.sub(
            lambda m: m.group(0).replace(
                m.group(m.lastindex or 0), mask
            ) if m.lastindex else m.group(0),
            result,
        )

    return result


class SensitiveDataFilter(logging.Filter):
    """Logging filter that automatically masks sensitive data in log records.

    Attach to any logger to prevent credential leakage:
        logger.addFilter(SensitiveDataFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_sensitive(record.msg)
        if record.args and isinstance(record.args, dict):
            record.args = {
                k: mask_sensitive(str(v)) if isinstance(v, str) else v
                for k, v in record.args.items()
            }
        elif record.args and isinstance(record.args, tuple):
            record.args = tuple(
                mask_sensitive(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True


# ═══════════════════════════════════════════════════════════════════════════════
# LOG ROTATION CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Default rotation settings (configurable via environment variables)
_DEFAULT_MAX_BYTES = int(os.getenv("FIREAI_LOG_MAX_BYTES", str(50 * 1024 * 1024)))  # 50 MB
_DEFAULT_BACKUP_COUNT = int(os.getenv("FIREAI_LOG_BACKUP_COUNT", "10"))  # 10 rotating files
_DEFAULT_RETENTION_DAYS = int(os.getenv("FIREAI_LOG_RETENTION_DAYS", "30"))  # 30 days

# Log directory (configurable)
_LOG_DIR = Path(os.getenv("FIREAI_LOG_DIR", "logs"))


def configure_log_rotation(
    logger_instance: logging.Logger,
    log_file: str = "fireai.log",
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> None:
    """Configure size-based log rotation for a logger.

    Args:
        logger_instance: The logger to configure.
        log_file: Filename for the log file (within _LOG_DIR).
        max_bytes: Maximum size per log file before rotation.
        backup_count: Number of rotated backup files to keep.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / log_file

    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    handler.addFilter(SensitiveDataFilter())
    logger_instance.addHandler(handler)


def configure_timed_rotation(
    logger_instance: logging.Logger,
    log_file: str = "fireai.log",
    when: str = "midnight",
    backup_count: int = _DEFAULT_RETENTION_DAYS,
) -> None:
    """Configure time-based log rotation for a logger.

    Args:
        logger_instance: The logger to configure.
        log_file: Filename for the log file (within _LOG_DIR).
        when: Rotation interval ('midnight', 'D' for daily, 'H' for hourly).
        backup_count: Number of days of logs to retain.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / log_file

    handler = TimedRotatingFileHandler(
        log_path,
        when=when,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    handler.addFilter(SensitiveDataFilter())
    logger_instance.addHandler(handler)


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════════

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


class SecurityAuditLogger:
    """Dedicated logger for security-sensitive events.

    Writes security events to a separate log file with:
    - Tamper-evident chain hashing (each entry links to the previous)
    - Structured JSON format for easy parsing
    - Automatic sensitive data masking
    - Size-based log rotation

    SECURITY DESIGN:
    The chain hash ensures that if any entry is modified or deleted,
    the chain is broken and tampering is detectable. This is similar
    to how the audit_log.py works but for a different purpose:
    audit_log.py tracks engineering decisions; this tracks security events.
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
        self._chain_hash = "GENESIS"  # First entry has no predecessor
        # V102 FIX: Thread-safe lock for chain hash integrity (same pattern
        # as audit_log.py V69-11 FIX). Without this, concurrent log_event()
        # calls break the tamper-evident chain.
        self._lock = __import__("threading").Lock()

        # Set up dedicated logger (separate from root logger)
        self._logger = logging.getLogger("fireai.security_audit")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False  # Don't duplicate to root logger

        # Add rotating file handler with sensitive data filter
        handler = RotatingFileHandler(
            self._log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON
        handler.addFilter(SensitiveDataFilter())
        self._logger.addHandler(handler)

    def log_event(
        self,
        event_type: str,
        **details: Any,
    ) -> str:
        """Log a security event with tamper-evident chain hashing.

        Thread-safe: acquires self._lock to prevent concurrent chain hash
        corruption (V102 FIX — same pattern as audit_log.py V69-11 FIX).

        Args:
            event_type: Type of security event (use SecurityEventType constants).
            **details: Additional key-value pairs describing the event.

        Returns:
            The event ID (hash-based) for traceability.
        """
        with self._lock:
            timestamp = datetime.now(timezone.utc).isoformat()

            # Generate event ID
            event_id = hashlib.sha256(
                f"{timestamp}:{event_type}:{self._chain_hash}".encode("utf-8")
            ).hexdigest()[:16]

            # Build the event record
            event = {
                "event_id": event_id,
                "timestamp": timestamp,
                "event_type": event_type,
                "chain_hash": self._chain_hash,
                "details": {k: mask_sensitive(str(v)) for k, v in details.items()},
            }

            # Compute new chain hash for the next event
            event_json = json.dumps(event, sort_keys=True, separators=(",", ":"))
            self._chain_hash = hashlib.sha256(
                event_json.encode("utf-8")
            ).hexdigest()[:32]

            # Write to security audit log
            self._logger.info(event_json)

            return event_id

    def verify_chain(self) -> Dict[str, Any]:
        """Verify the integrity of the security audit log chain.

        Returns:
            Dict with verification results:
            - valid: True if chain is intact
            - entries_checked: Number of entries verified
            - first_break: Event ID where chain was broken (if any)
        """
        if not self._log_path.exists():
            return {"valid": True, "entries_checked": 0, "first_break": None}

        entries_checked = 0
        expected_chain = "GENESIS"
        first_break = None

        with open(self._log_path, "r", encoding="utf-8") as f:
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
                        # Recompute expected chain hash
                        event_json = json.dumps(event, sort_keys=True, separators=(",", ":"))
                        expected_chain = hashlib.sha256(
                            event_json.encode("utf-8")
                        ).hexdigest()[:32]
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
