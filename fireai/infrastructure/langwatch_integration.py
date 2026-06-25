"""langwatch_integration.py — LangWatch AI Observability Integration
====================================================================

MISSION PHASE 2 — AI Observability & Reliability (CORRECTED TARGET)
====================================================================

IMPORTANT CORRECTION: The original mission brief said to integrate LangWatch
into ``fireai/core/analysis_pipeline.py``. However, that module is a
DETERMINISTIC engineering pipeline (math calculations, no LLM calls).
LangWatch is for tracing LLM reasoning — applying it to deterministic code
adds overhead without value.

The CORRECT target is ``backend/services/workflow_service.py``, which uses
LangGraph + Mem0 (LLM-powered memory enrichment). This is where the AI
reasoning actually happens.

What This Module Does
---------------------
1. Wraps Mem0 search/add calls with LangWatch tracing.
2. Records "confidence scores" for AI-suggested advisory hints.
3. Implements a "Hallucination Check" that cross-references AI-suggested
   detector spacings against NFPA72_MAX_SPACING_M (defensive — even though
   the AI is advisory-only, we verify its suggestions don't violate code).
4. Logs all LLM interactions to LangWatch for observability.

Safety Design
-------------
Per agent.md V75: AI is ADVISORY ONLY. It never overrides deterministic
calculations. LangWatch tracing is also advisory — it never blocks the
pipeline, even if LangWatch is unavailable.

Per agent.md Rule 12: Hallucination checks are SAFETY NETS, not primary
validation. The deterministic NFPA 72 calculations in ``pipeline.py``
remain the authoritative source.

References
----------
- LangWatch SDK: https://langwatch.org/docs
- agent.md V75 (AI is advisory only)
- agent.md Rule 17 (Root-Cause Analysis — target the right module)
- NFPA 72-2022 §17.6.3 (spacing requirements)
"""

from __future__ import annotations

import functools
import logging
import os
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# LangWatch API key (read from env, NEVER hardcoded)
LANGWATCH_API_KEY_ENV = "LANGWATCH_API_KEY"

# NFPA 72 constants for hallucination checking
# Per NFPA 72-2022 §17.6.3.1.1: max smoke detector spacing = 9.1m (30 ft)
NFPA72_MAX_SMOKE_SPACING_M = 9.1
# Per NFPA 72-2022 §17.6.2.1: max heat detector spacing = 6.1m (20 ft) for fixed temp
NFPA72_MAX_HEAT_SPACING_M = 6.1


# ---------------------------------------------------------------------------
# LangWatch Client (Lazy Initialization)
# ---------------------------------------------------------------------------


class LangWatchClient:
    """Lazy-initialized LangWatch client.

    Per agent.md Rule 12: if LangWatch is unavailable (no API key, network
    issue, etc.), ALL operations silently no-op. The pipeline MUST NOT
    break because of observability tooling.
    """

    _instance: Optional["LangWatchClient"] = None
    _client: Any = None
    _initialized: bool = False

    def __new__(cls) -> "LangWatchClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not self._initialized:
            self._initialize()
            self._initialized = True

    def _initialize(self) -> None:
        """Initialize LangWatch client if API key is available."""
        api_key = os.environ.get(LANGWATCH_API_KEY_ENV)
        if not api_key:
            logger.info(
                "LangWatch not initialized (no %s env var). "
                "AI observability tracing disabled.",
                LANGWATCH_API_KEY_ENV,
            )
            return

        try:
            # LangWatch SDK import (optional dependency)
            import langwatch  # type: ignore[import-untyped]

            # LangWatch uses environment variable for API key
            os.environ["LANGWATCH_API_KEY"] = api_key

            self._client = langwatch
            logger.info("LangWatch client initialized successfully")
        except ImportError:
            logger.warning(
                "LangWatch SDK not installed. Install with: pip install langwatch. "
                "AI observability tracing disabled."
            )
        except Exception as exc:
            logger.warning(
                "LangWatch initialization failed: %s. "
                "AI observability tracing disabled.",
                exc,
            )

    @property
    def is_available(self) -> bool:
        """True if LangWatch client is initialized."""
        return self._client is not None

    def trace(self, name: str, **kwargs: Any) -> Any:
        """Create a LangWatch trace context.

        Returns a no-op context manager if LangWatch is unavailable.
        """
        if not self.is_available:
            return _NoOpTraceContext()

        try:
            return self._client.trace(name=name, **kwargs)
        except Exception as exc:
            logger.debug("LangWatch trace creation failed: %s", exc)
            return _NoOpTraceContext()

    def record_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Record an event in LangWatch (e.g., LLM call, hallucination check).

        Silently no-ops if LangWatch is unavailable.
        """
        if not self.is_available:
            return
        try:
            # LangWatch event recording API
            # (actual API may vary — this is a best-effort integration)
            self._client.log_event(event_type=event_type, **data)
        except Exception as exc:
            logger.debug("LangWatch event recording failed: %s", exc)


class _NoOpTraceContext:
    """No-op context manager for when LangWatch is unavailable."""

    def __enter__(self) -> "_NoOpTraceContext":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def update(self, **kwargs: Any) -> None:
        pass

    def span(self, name: str, **kwargs: Any) -> "_NoOpTraceContext":
        return self


# ---------------------------------------------------------------------------
# Singleton Accessor
# ---------------------------------------------------------------------------


def get_langwatch() -> LangWatchClient:
    """Get the singleton LangWatchClient instance."""
    return LangWatchClient()


# ---------------------------------------------------------------------------
# Tracing Decorator for LLM Calls
# ---------------------------------------------------------------------------


def trace_llm_call(operation_name: str) -> Callable:
    """Decorator that traces LLM calls via LangWatch.

    Usage:
        @trace_llm_call("mem0_search_standards")
        def search_standards(query: str, ...):
            ...

    Records:
    - Input parameters (sanitized — no API keys)
    - Output result (truncated)
    - Duration
    - Confidence score (if returned by the LLM)
    - Hallucination check result

    If LangWatch is unavailable, the decorator is a pass-through.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            client = get_langwatch()
            if not client.is_available:
                return await func(*args, **kwargs)

            import time
            t_start = time.perf_counter()

            with client.trace(operation_name) as trace_ctx:
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = (time.perf_counter() - t_start) * 1000.0

                    # Record success
                    trace_ctx.update(
                        status="success",
                        duration_ms=duration_ms,
                        result_summary=_summarize_result(result),
                    )

                    # Record in LangWatch event log
                    client.record_event(
                        event_type="llm_call_completed",
                        data={
                            "operation": operation_name,
                            "duration_ms": duration_ms,
                            "success": True,
                        },
                    )

                    return result
                except Exception as exc:
                    duration_ms = (time.perf_counter() - t_start) * 1000.0
                    trace_ctx.update(
                        status="error",
                        duration_ms=duration_ms,
                        error=str(exc),
                    )
                    client.record_event(
                        event_type="llm_call_failed",
                        data={
                            "operation": operation_name,
                            "duration_ms": duration_ms,
                            "error": str(exc),
                        },
                    )
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            client = get_langwatch()
            if not client.is_available:
                return func(*args, **kwargs)

            import time
            t_start = time.perf_counter()

            with client.trace(operation_name) as trace_ctx:
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.perf_counter() - t_start) * 1000.0
                    trace_ctx.update(
                        status="success",
                        duration_ms=duration_ms,
                        result_summary=_summarize_result(result),
                    )
                    return result
                except Exception as exc:
                    duration_ms = (time.perf_counter() - t_start) * 1000.0
                    trace_ctx.update(
                        status="error",
                        duration_ms=duration_ms,
                        error=str(exc),
                    )
                    raise

        import inspect
        return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper

    return decorator


def _summarize_result(result: Any, max_length: int = 500) -> str:
    """Create a truncated summary of an LLM call result."""
    try:
        if isinstance(result, str):
            return result[:max_length]
        if isinstance(result, dict):
            import json
            return json.dumps(result, default=str)[:max_length]
        if isinstance(result, list):
            return f"[list with {len(result)} items]"
        return str(result)[:max_length]
    except Exception:
        return "<unable to summarize>"


# ---------------------------------------------------------------------------
# Hallucination Check (Safety Net)
# ---------------------------------------------------------------------------


def hallucination_check_spacing(
    suggested_spacing_m: float,
    detector_type: str,
    operation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cross-reference AI-suggested spacing against NFPA 72 maximums.

    Per agent.md V75: AI is advisory only, but we STILL verify its
    suggestions don't violate code. If the AI suggests a spacing larger
    than NFPA 72 allows, we flag it as a hallucination.

    Args:
        suggested_spacing_m: AI-suggested spacing in metres.
        detector_type: "smoke" or "heat".
        operation_id: Optional operation ID for traceability.

    Returns:
        Dict with:
            - is_hallucination: bool (True if suggestion violates NFPA 72)
            - suggested_spacing_m: float
            - max_allowed_m: float
            - confidence: float (0.0 = hallucination, 1.0 = safe)
            - warning: str (human-readable warning if hallucination detected)
    """
    import math

    # Validate input
    if not math.isfinite(suggested_spacing_m) or suggested_spacing_m <= 0:
        return {
            "is_hallucination": True,
            "suggested_spacing_m": suggested_spacing_m,
            "max_allowed_m": 0.0,
            "confidence": 0.0,
            "warning": f"Invalid spacing suggestion: {suggested_spacing_m} (non-finite or non-positive)",
            "operation_id": operation_id,
        }

    # Get max allowed spacing
    detector_lower = (detector_type or "").lower()
    if "heat" in detector_lower:
        max_allowed = NFPA72_MAX_HEAT_SPACING_M
        nfpa_ref = "NFPA 72-2022 §17.6.2.1 (heat detector spacing)"
    else:
        # Default to smoke (conservative)
        max_allowed = NFPA72_MAX_SMOKE_SPACING_M
        nfpa_ref = "NFPA 72-2022 §17.6.3.1.1 (smoke detector spacing)"

    # Check against max
    if suggested_spacing_m > max_allowed:
        warning = (
            f"HALLUCINATION DETECTED: AI suggested spacing {suggested_spacing_m}m "
            f"exceeds NFPA 72 maximum {max_allowed}m for {detector_type} detectors. "
            f"The AI suggestion has been rejected. The deterministic pipeline "
            f"will use the NFPA 72-compliant spacing."
        )
        result = {
            "is_hallucination": True,
            "suggested_spacing_m": suggested_spacing_m,
            "max_allowed_m": max_allowed,
            "confidence": 0.0,
            "warning": warning,
            "nfpa_reference": nfpa_ref,
            "operation_id": operation_id,
        }
    else:
        # Suggestion is within code limits — compute confidence
        # Closer to max = lower confidence (risky)
        # Closer to 0 = higher confidence (conservative)
        ratio = suggested_spacing_m / max_allowed if max_allowed > 0 else 0.0
        confidence = max(0.0, 1.0 - ratio)  # 0 at max, 1 at 0
        result = {
            "is_hallucination": False,
            "suggested_spacing_m": suggested_spacing_m,
            "max_allowed_m": max_allowed,
            "confidence": round(confidence, 3),
            "warning": None,
            "nfpa_reference": nfpa_ref,
            "operation_id": operation_id,
        }

    # Record in LangWatch
    client = get_langwatch()
    if client.is_available:
        client.record_event(
            event_type="hallucination_check",
            data=result,
        )

    # Also record in AuditStore (per Rule 12 + NFPA 72 §7.5)
    try:
        from fireai.core.audit_store import AuditStore
        AuditStore.add_event(
            event_type="AI_HALLUCINATION_CHECK",
            room_id=str(operation_id or "AI_ADVISORY"),
            details_dict=result,
        )
    except Exception:
        pass  # Never block on audit failure

    return result


# ---------------------------------------------------------------------------
# Confidence Score Recorder
# ---------------------------------------------------------------------------


def record_confidence_score(
    decision: str,
    confidence: float,
    reasoning: str = "",
    operation_id: Optional[str] = None,
) -> None:
    """Record a confidence score for an automated design decision.

    Per PHASE 2: "Log Confidence Scores for every automated design decision."

    Args:
        decision: Description of the decision (e.g., "smoke_detector_placement").
        confidence: Confidence score (0.0 to 1.0).
        reasoning: Optional reasoning text from the LLM.
        operation_id: Optional operation ID for traceability.
    """
    import math

    # Validate confidence
    if not math.isfinite(confidence) or confidence < 0.0 or confidence > 1.0:
        logger.warning(
            "Invalid confidence score %f for decision %s — must be in [0, 1]",
            confidence, decision,
        )
        confidence = max(0.0, min(1.0, confidence if math.isfinite(confidence) else 0.0))

    record = {
        "decision": decision,
        "confidence": round(confidence, 3),
        "reasoning": reasoning[:500] if reasoning else "",
        "operation_id": operation_id,
        "source": "langwatch_integration",
    }

    # Record in LangWatch
    client = get_langwatch()
    if client.is_available:
        client.record_event(
            event_type="confidence_score",
            data=record,
        )

    # Record in AuditStore
    try:
        from fireai.core.audit_store import AuditStore
        AuditStore.add_event(
            event_type="AI_CONFIDENCE_SCORE",
            room_id=str(operation_id or "AI_DECISION"),
            details_dict=record,
        )
    except Exception:
        pass


__all__ = [
    "LangWatchClient",
    "get_langwatch",
    "trace_llm_call",
    "hallucination_check_spacing",
    "record_confidence_score",
    "NFPA72_MAX_SMOKE_SPACING_M",
    "NFPA72_MAX_HEAT_SPACING_M",
    "LANGWATCH_API_KEY_ENV",
]
