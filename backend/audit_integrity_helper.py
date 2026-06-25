"""audit_integrity_helper.py — Signed Audit Trail for DB Writes
===============================================================

MISSION PHASE 1.3 — Audit Integrity with Correlation-ID
========================================================

This module ensures that EVERY write operation to the FireAI database
triggers a signed entry in the AuditStore, including the Correlation-ID
for end-to-end request tracing.

Why This Matters
----------------
Per NFPA 72 §7.5 and agent.md Rule 12 (Safety-First):
- Every modification to fire protection engineering data MUST be auditable.
- The audit chain must be **tamper-evident** (HMAC-SHA256 signed).
- The Correlation-ID allows investigators to trace a single HTTP request
  through the entire stack: router → service → database → AuditStore.

Architecture
------------
This module provides a decorator and context manager that wraps database
write operations:

    @audit_db_write("create_project")
    def create_project(...):
        ...

Or:

    with audit_write_context("create_project", details={...}):
        db.execute(...)

The decorator/context manager:
1. Captures the Correlation-ID from the current request context.
2. Executes the wrapped operation.
3. On success: records a signed audit event.
4. On failure: records a failure audit event (never suppresses the original error).
5. Never blocks the operation if AuditStore is unavailable (graceful degradation).

References
----------
- agent.md Rule 12 (Safety-First) + Rule 17 (Root-Cause Analysis)
- NFPA 72-2022 §7.5 (Audit Trail)
- RFC 4122 (UUID for Correlation-ID)
"""

from __future__ import annotations

import functools
import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Correlation-ID Extraction
# ---------------------------------------------------------------------------


def get_correlation_id() -> Optional[str]:
    """Extract the Correlation-ID from the current request context.

    The CorrelationIdMiddleware (backend/request_context.py) stores the
    correlation ID in a contextvar. This function retrieves it for
    inclusion in audit log entries.

    Returns:
        Correlation-ID string, or None if not in a request context.
    """
    try:
        from backend.request_context import get_correlation_id as _get_cid
        return _get_cid()
    except ImportError:
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Audit Writer
# ---------------------------------------------------------------------------


def record_audit_write(
    operation: str,
    table: str,
    record_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> Optional[str]:
    """Record a signed audit entry for a database write operation.

    Per PHASE 1.3: every DB write MUST trigger a signed AuditStore entry
    including the Correlation-ID for traceability.

    Args:
        operation: Operation type (e.g., "create_project", "update_device").
        table: Database table affected (e.g., "projects", "devices").
        record_id: ID of the record affected (if applicable).
        details: Additional details dict (changes, values, etc.).
        success: Whether the operation succeeded.
        error: Error message if operation failed.

    Returns:
        Audit event hash (for chain verification), or None if recording failed.
    """
    try:
        from fireai.core.audit_store import AuditStore

        correlation_id = get_correlation_id()

        audit_details = {
            "operation": operation,
            "table": table,
            "record_id": record_id or "UNKNOWN",
            "correlation_id": correlation_id or "NOT_IN_REQUEST_CONTEXT",
            "success": success,
            "error": error,
            "nfpa_reference": "NFPA 72-2022 §7.5 (Audit Trail)",
            "source": "audit_integrity_helper",
        }
        if details:
            audit_details["details"] = details

        event_hash = AuditStore.add_event(
            event_type=f"DB_WRITE_{operation.upper()}",
            room_id=str(record_id or "DB_OPERATION"),
            details_dict=audit_details,
        )
        return event_hash

    except Exception as exc:
        # Per fail-safe principle: audit failure MUST NOT block the operation
        logger.error(
            "Failed to record audit write for %s on %s: %s",
            operation, table, exc, exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# Decorator: @audit_db_write
# ---------------------------------------------------------------------------


def audit_db_write(
    operation: str,
    table: str,
    record_id_arg: Optional[str] = None,
) -> Callable:
    """Decorator that wraps a database write function with audit logging.

    Usage:
        @audit_db_write("create_project", "projects", record_id_arg="project_id")
        def create_project(project_id: str, name: str, ...):
            ...

    Args:
        operation: Operation name (e.g., "create_project").
        table: Database table affected.
        record_id_arg: Name of the argument that contains the record ID.
            If None, the first argument is used.

    Returns:
        Decorated function.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract record ID
            record_id = _extract_record_id(func, args, kwargs, record_id_arg)

            try:
                result = await func(*args, **kwargs)
                # Success — record audit event
                record_audit_write(
                    operation=operation,
                    table=table,
                    record_id=record_id,
                    details=_extract_changes(result),
                    success=True,
                )
                return result
            except Exception as exc:
                # Failure — record audit event with error
                record_audit_write(
                    operation=operation,
                    table=table,
                    record_id=record_id,
                    details={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
                    success=False,
                    error=str(exc),
                )
                raise  # Re-raise the original exception

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            record_id = _extract_record_id(func, args, kwargs, record_id_arg)
            try:
                result = func(*args, **kwargs)
                record_audit_write(
                    operation=operation,
                    table=table,
                    record_id=record_id,
                    details=_extract_changes(result),
                    success=True,
                )
                return result
            except Exception as exc:
                record_audit_write(
                    operation=operation,
                    table=table,
                    record_id=record_id,
                    details={"args": str(args)[:500], "kwargs": str(kwargs)[:500]},
                    success=False,
                    error=str(exc),
                )
                raise

        # Return the appropriate wrapper based on whether the function is async
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _extract_record_id(
    func: Callable,
    args: tuple,
    kwargs: dict,
    record_id_arg: Optional[str],
) -> Optional[str]:
    """Extract the record ID from function arguments."""
    if record_id_arg:
        # Try kwargs first, then positional (using arg name)
        if record_id_arg in kwargs:
            return str(kwargs[record_id_arg])
        # Try to find in function signature
        import inspect
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        if record_id_arg in params:
            idx = params.index(record_id_arg)
            if idx < len(args):
                return str(args[idx])
    # Fallback: use first argument
    if args:
        return str(args[0])
    return None


def _extract_changes(result: Any) -> Dict[str, Any]:
    """Extract change details from function result."""
    if result is None:
        return {}
    if isinstance(result, dict):
        # Limit to first 10 keys to avoid huge audit entries
        return {k: result[k] for k in list(result.keys())[:10] if k != "password"}
    if hasattr(result, "to_dict"):
        try:
            d = result.to_dict()
            return {k: d[k] for k in list(d.keys())[:10]}
        except Exception:
            pass
    return {"result_type": type(result).__name__}


# ---------------------------------------------------------------------------
# Context Manager: with audit_write_context(...)
# ---------------------------------------------------------------------------


@contextmanager
def audit_write_context(
    operation: str,
    table: str,
    record_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
):
    """Context manager for auditing database writes.

    Usage:
        with audit_write_context("update_device", "devices", record_id="DEV-001"):
            db.execute("UPDATE devices SET ...")

    Records success on normal exit, failure on exception (re-raises).
    """
    try:
        yield
        # Success
        record_audit_write(
            operation=operation,
            table=table,
            record_id=record_id,
            details=details,
            success=True,
        )
    except Exception as exc:
        # Failure
        record_audit_write(
            operation=operation,
            table=table,
            record_id=record_id,
            details=details,
            success=False,
            error=str(exc),
        )
        raise


__all__ = [
    "audit_db_write",
    "audit_write_context",
    "record_audit_write",
    "get_correlation_id",
]
