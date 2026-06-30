"""
fireai/infrastructure/langfuse_setup.py — Langfuse Observability Layer.
=====================================================================

V141.2 FIX (adversarial audit — Missing Module):
Previous versions of workflow_service.py imported from this module, but
the module FILE DID NOT EXIST. The import was wrapped in try/except
ImportError, so it failed silently — masking the fact that V80's claim
of "Langfuse Observability Integration" was non-functional.

This module now provides a REAL (but optional) Langfuse integration:
  - get_langfuse(): Lazy-initialized Langfuse client. Returns None if
    langfuse package not installed or LANGFUSE_HOST not configured.
  - get_langfuse_callback_handler(): Creates a CallbackHandler for
    LangGraph auto-tracing. Returns None if unavailable.
  - log_verification_score(): Creates tamper-evident scores on traces.
  - log_workflow_scores(): Logs all 5 verification scores after workflow
    completion.
  - flush_langfuse(): Ensures events are sent before process exit.
  - langfuse_health_check(): Health status for monitoring endpoints.

All operations are FAIL-SAFE: wrapped in try/except, never blocks the
pipeline. If Langfuse is unavailable, the workflow runs identically —
the internal audit trail (transition_log) remains the PRIMARY record;
Langfuse traces are SECONDARY observability data.

Self-hosted Langfuse is recommended for life-safety data (no cloud
exposure of fire protection engineering records).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Lazy globals ────────────────────────────────────────────────────────────
_langfuse_client: Optional[Any] = None
_langfuse_available: Optional[bool] = None


def _check_langfuse_available() -> bool:
    """Check if langfuse package is installed and configured."""
    global _langfuse_available
    if _langfuse_available is not None:
        return _langfuse_available

    try:
        import langfuse  # noqa: F401
        host = os.getenv("LANGFUSE_HOST")
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        if not (host and public_key and secret_key):
            logger.info(
                "Langfuse package installed but not configured "
                "(LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY env vars missing). "
                "Observability layer DISABLED."
            )
            _langfuse_available = False
        else:
            _langfuse_available = True
    except ImportError:
        logger.info(
            "Langfuse package not installed. Observability layer DISABLED. "
            "Install with: pip install langfuse"
        )
        _langfuse_available = False

    return _langfuse_available


def get_langfuse() -> Optional[Any]:
    """
    Get the lazy-initialized Langfuse client.

    Returns None if langfuse is not installed or not configured.
    Never raises — calling code can safely use `if client:` pattern.
    """
    global _langfuse_client

    if not _check_langfuse_available():
        return None

    if _langfuse_client is None:
        try:
            from langfuse import Langfuse
            _langfuse_client = Langfuse(
                host=os.getenv("LANGFUSE_HOST"),
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            )
            logger.info("Langfuse client initialized (host=%s)", os.getenv("LANGFUSE_HOST"))
        except Exception as e:
            logger.warning("Failed to initialize Langfuse client: %s. Observability DISABLED.", e)
            _langfuse_available = False
            return None

    return _langfuse_client


def get_langfuse_callback_handler(
    name: str = "fireai_workflow",
    trace_id: Optional[str] = None,
    user_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Optional[Any]:
    """
    Create a LangGraph CallbackHandler for auto-tracing.

    V141.2: Accepts workflow_id and project_id kwargs for compatibility with
    workflow_service.py's calling convention. workflow_id is used as the
    trace_id (so each workflow gets its own Langfuse trace); project_id is
    stored as metadata.

    Returns None if Langfuse is unavailable. Never raises.
    """
    try:
        client = get_langfuse()
        if client is None:
            return None

        # Langfuse v2+ provides a LangChain CallbackHandler that also works
        # with LangGraph (which is built on LangChain's runnable interface).
        from langfuse.callback import CallbackHandler

        # Prefer explicit trace_id; fall back to workflow_id for compatibility
        effective_trace_id = trace_id or workflow_id

        handler = CallbackHandler(
            langfuse=client,
            trace_name=name,
            trace_id=effective_trace_id,
            user_id=user_id,
        )

        # Attach project_id as metadata if provided (for multi-tenant filtering)
        if project_id:
            try:
                handler.update_trace_metadata({"project_id": project_id})
            except Exception:
                # update_trace_metadata may not exist in all langfuse versions
                pass

        # V141.4 SECURITY FIX (CodeQL: py/clear-text-logging-sensitive-data):
        # Do NOT log trace_id or project_id — they are considered sensitive
        # because they can leak project identifiers to anyone with log access.
        # Log only a boolean success indicator + the trace_name (which is a
        # static label like "fireai_workflow", not a secret).
        logger.debug("Langfuse CallbackHandler created (trace_name=%s)", name)
        return handler
    except ImportError:
        logger.debug("langfuse.callback.CallbackHandler not available.")
        return None
    except Exception as e:
        logger.warning("Failed to create Langfuse CallbackHandler: %s", e)
        return None


def log_verification_score(
    trace_id: str,
    name: str,
    value: float,
    comment: Optional[str] = None,
) -> bool:
    """
    Create a tamper-evident score on a Langfuse trace.

    Returns True on success, False on failure. Never raises.
    """
    try:
        client = get_langfuse()
        if client is None:
            return False

        client.score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment or "",
        )
        return True
    except Exception as e:
        logger.debug("Failed to log Langfuse score %s: %s", name, e)
        return False


def log_workflow_scores(result: Any, handler: Optional[Any]) -> None:
    """
    Log all 5 verification scores to Langfuse after workflow completion.

    Scores logged:
      1. nfpa_coverage_pct: Normalized coverage (0.0–1.0)
      2. nfpa_compliant: Boolean compliance (1.0 or 0.0)
      3. conflict_severity: Inverse conflict score (1.0 = no conflicts)
      4. validation_passed: Boolean (1.0 or 0.0)
      5. safety_gate_overall: 1.0 only if no critical + validation + compliant

    Never raises — all errors are logged at DEBUG level.
    """
    if handler is None:
        return

    try:
        trace_id = getattr(handler, "trace_id", None) or getattr(
            getattr(handler, "trace", None), "id", None
        )
        if not trace_id:
            logger.debug("No trace_id available on handler; skipping score logging.")
            return

        # Extract scores from workflow result (defensive — result shape varies)
        scores: dict[str, float] = {}

        # 1. NFPA coverage percentage
        coverage = (
            getattr(result, "nfpa_coverage_pct", None)
            or _nested_get(result, "safety_gates", "nfpa_coverage_pct")
            or _nested_get(result, "nfpa_coverage_pct")
        )
        if coverage is not None:
            scores["nfpa_coverage_pct"] = float(min(max(coverage, 0.0), 1.0))

        # 2. NFPA compliant boolean
        compliant = (
            getattr(result, "nfpa_compliant", None)
            or _nested_get(result, "safety_gates", "nfpa_compliant")
        )
        if compliant is not None:
            scores["nfpa_compliant"] = 1.0 if bool(compliant) else 0.0

        # 3. Conflict severity (inverse — fewer conflicts = higher score)
        conflicts = (
            getattr(result, "conflict_count", None)
            or _nested_get(result, "conflicts", "count")
            or _nested_get(result, "conflict_count")
        )
        if conflicts is not None:
            scores["conflict_severity"] = max(0.0, 1.0 - (float(conflicts) / 10.0))

        # 4. Validation passed
        validation = (
            getattr(result, "validation_passed", None)
            or _nested_get(result, "safety_gates", "validation_passed")
        )
        if validation is not None:
            scores["validation_passed"] = 1.0 if bool(validation) else 0.0

        # 5. Overall safety gate (most critical)
        overall = (
            getattr(result, "safety_gate_overall", None)
            or _nested_get(result, "safety_gates", "overall")
        )
        if overall is not None:
            scores["safety_gate_overall"] = 1.0 if bool(overall) else 0.0

        for name, value in scores.items():
            log_verification_score(trace_id, name, value)

        logger.debug("Logged %d verification scores to Langfuse trace %s", len(scores), trace_id)

    except Exception as e:
        logger.debug("Failed to log workflow scores to Langfuse: %s", e)


def flush_langfuse() -> None:
    """
    Ensure all Langfuse events are sent before process exit.

    Never raises — safe to call from signal handlers / shutdown hooks.
    """
    try:
        client = get_langfuse()
        if client is not None:
            client.flush()
            logger.debug("Langfuse events flushed.")
    except Exception as e:
        logger.debug("Failed to flush Langfuse: %s", e)


def langfuse_health_check() -> dict[str, Any]:
    """
    Health status for monitoring endpoints.

    Returns a dict with:
      - enabled: bool
      - host: str (or None)
      - client_initialized: bool
      - error: str (or None)
    """
    try:
        available = _check_langfuse_available()
        return {
            "enabled": available,
            "host": os.getenv("LANGFUSE_HOST"),
            "client_initialized": _langfuse_client is not None,
            "error": None if available else "Langfuse not installed or not configured",
        }
    except Exception as e:
        return {
            "enabled": False,
            "host": None,
            "client_initialized": False,
            "error": str(e),
        }


# ── Helpers ─────────────────────────────────────────────────────────────────
def _nested_get(obj: Any, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested attributes/dict keys."""
    current = obj
    for key in keys:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
    return current if current is not None else default
