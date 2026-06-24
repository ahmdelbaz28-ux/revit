"""
fireai/core/guardrails.py — Tripwire-style validation for safety-critical calculations
=====================================================================================

Adapted (NOT copied) from the guardrail pattern in OpenAI's agents-python SDK
(src/agents/guardrail.py, MIT License, Copyright (c) 2025 OpenAI).

The original is designed for LLM agent input/output validation. This file
reimplements the core IDEA — decoupling validation detection from action
via a {tripwire_triggered, output_info} return type — for FireAI's
deterministic NFPA 72 calculation pipeline.

Design rationale:
  - Traditional validation raises ValueError inline, which loses context
    about WHAT was validated and WHAT the result was.
  - Tripwire-style validation returns a structured result, allowing the
    caller to decide: log + continue, log + halt, or escalate.
  - For safety-critical fire protection calculations, this distinction
    is crucial: a failed spacing check should produce an audit-trail
    entry with the full calculation context, not just a stack trace.

V133 (2026-06-22): Initial implementation.
"""

from __future__ import annotations

import functools
import logging
import time
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ============================================================================
# Tripwire Result Types
# ============================================================================

@dataclass(frozen=True)
class TripwireResult:
    """Result of a guardrail check.

    Attributes:
        tripwire_triggered: True if the guardrail detected a violation.
            When True, the caller should halt the calculation pipeline
            and log the output_info for audit trail.
        output_info: Arbitrary dict with details about the check result.
            Includes: check_name, message, severity, context, timestamp.
    """
    tripwire_triggered: bool
    output_info: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.output_info, dict):
            raise TypeError(
                f"output_info must be a dict, got {type(self.output_info).__name__}"
            )


# ============================================================================
# Calculation Error Snapshot (adapted from RunErrorDetails pattern)
# ============================================================================

@dataclass
class CalculationErrorSnapshot(Exception):
    """Exception carrying a full calculation snapshot for post-mortem.

    Adapted from openai-agents-python's RunErrorDetails pattern
    (src/agents/exceptions.py, MIT License).

    When a safety-critical calculation fails, this exception carries:
      - The input parameters that produced the failure
      - The intermediate calculation steps
      - The guardrail results that were checked
      - The timestamp and calculation ID for audit trail correlation

    This is critical for NFPA 72 compliance: when a fire alarm design
    calculation fails, the audit trail must show EXACTLY what was
    calculated, what was checked, and what failed — not just a
    stack trace.
    """

    calculation_id: str
    calculation_type: str
    input_params: dict[str, Any]
    intermediate_steps: list[dict[str, Any]]
    guardrail_results: list[TripwireResult]
    error_message: str
    timestamp: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
    ))

    def __post_init__(self) -> None:
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format a human-readable error message with audit context."""
        triggered = [
            r for r in self.guardrail_results if r.tripwire_triggered
        ]
        return (
            f"[{self.timestamp}] Calculation {self.calculation_id} "
            f"({self.calculation_type}) FAILED: {self.error_message}. "
            f"{len(triggered)} guardrail(s) triggered. "
            f"Input: {self.input_params}. "
            f"Steps: {len(self.intermediate_steps)}."
        )

    def to_audit_dict(self) -> dict[str, Any]:
        """Convert to a dict suitable for audit trail logging."""
        return {
            "calculation_id": self.calculation_id,
            "calculation_type": self.calculation_type,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "input_params": self.input_params,
            "intermediate_steps": self.intermediate_steps,
            "guardrail_results": [
                {
                    "tripwire_triggered": r.tripwire_triggered,
                    "output_info": r.output_info,
                }
                for r in self.guardrail_results
            ],
        }


# ============================================================================
# Guardrail Decorators
# ============================================================================

def input_guardrail(
    func: Callable[..., TripwireResult] | None = None,
    *,
    name: str | None = None,
) -> Callable:
    """Decorator that marks a function as an input guardrail.

    The decorated function should accept the calculation input and
    return a TripwireResult. The decorator:
      - Logs the guardrail execution (for audit trail)
      - Preserves the original function's sync/async nature
      - Attaches metadata (is_guardrail=True, guardrail_name=...)

    Usage:
        @input_guardrail(name="ceiling_height_positive")
        def check_ceiling_height(params: dict) -> TripwireResult:
            h = params.get("ceiling_height_m", 0)
            if h <= 0:
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={"check": "ceiling_height_positive",
                                 "message": f"Height {h} must be positive",
                                 "severity": "critical"}
                )
            return TripwireResult(tripwire_triggered=False)

    Adapted from openai-agents-python's @input_guardrail decorator
    (src/agents/guardrail.py, MIT License, Copyright (c) 2025 OpenAI).
    """
    def decorator(fn: Callable[..., TripwireResult]) -> Callable[..., TripwireResult]:
        guardrail_name = name or fn.__name__

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> TripwireResult:
            start = time.monotonic()
            try:
                result = fn(*args, **kwargs)
                elapsed_ms = (time.monotonic() - start) * 1000
                logger.debug(
                    "Guardrail %s executed in %.1fms: triggered=%s",
                    guardrail_name, elapsed_ms, result.tripwire_triggered,
                )
                return result
            except Exception as e:
                logger.error(
                    "Guardrail %s raised exception: %s", guardrail_name, e
                )
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={
                        "check": guardrail_name,
                        "message": f"Guardrail crashed: {e}",
                        "severity": "critical",
                        "exception": type(e).__name__,
                    },
                )

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> TripwireResult:
            start = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
                elapsed_ms = (time.monotonic() - start) * 1000
                logger.debug(
                    "Guardrail %s executed in %.1fms: triggered=%s",
                    guardrail_name, elapsed_ms, result.tripwire_triggered,
                )
                return result
            except Exception as e:
                logger.error(
                    "Guardrail %s raised exception: %s", guardrail_name, e
                )
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={
                        "check": guardrail_name,
                        "message": f"Guardrail crashed: {e}",
                        "severity": "critical",
                        "exception": type(e).__name__,
                    },
                )

        wrapper = async_wrapper if _is_async(fn) else sync_wrapper
        wrapper.is_guardrail = True  # type: ignore[attr-defined]
        wrapper.guardrail_name = guardrail_name  # type: ignore[attr-defined]
        return wrapper

    if func is not None and callable(func):
        return decorator(func)
    return decorator


def output_guardrail(
    func: Callable[..., TripwireResult] | None = None,
    *,
    name: str | None = None,
) -> Callable:
    """Decorator that marks a function as an output guardrail.

    Same semantics as @input_guardrail but for validating calculation
    OUTPUTS. Use this to verify that calculated values are within
    physically reasonable ranges before they're committed to the
    audit trail.

    Usage:
        @output_guardrail(name="detector_count_reasonable")
        def check_detector_count(result: dict) -> TripwireResult:
            count = result.get("total_detectors", 0)
            if count > 1000:
                return TripwireResult(
                    tripwire_triggered=True,
                    output_info={"check": "detector_count_reasonable",
                                 "message": f"Count {count} exceeds 1000",
                                 "severity": "high"}
                )
            return TripwireResult(tripwire_triggered=False)

    Adapted from openai-agents-python's @output_guardrail decorator.
    """
    # output_guardrail has identical semantics to input_guardrail in this
    # implementation — the distinction is semantic (what you're checking),
    # not mechanical. Both return TripwireResult.
    return input_guardrail(func, name=name)


# ============================================================================
# Guardrail Runner
# ============================================================================

def run_guardrails(
    guardrails: list[Callable[..., TripwireResult]],
    params: dict[str, Any],
    *,
    stop_on_first_trigger: bool = True,
) -> list[TripwireResult]:
    """Run a list of guardrails against the given parameters.

    Args:
        guardrails: List of decorated guardrail functions.
        params: The input/output parameters to validate.
        stop_on_first_trigger: If True, stop at the first triggered
            guardrail. If False, run all guardrails and collect all
            results (useful for comprehensive audit reports).

    Returns:
        List of all TripwireResults (or just the triggered ones if
        stop_on_first_trigger is True and one was triggered).
    """
    results: list[TripwireResult] = []
    for guardrail in guardrails:
        result = guardrail(params)
        results.append(result)
        if result.tripwire_triggered and stop_on_first_trigger:
            logger.warning(
                "Guardrail %s triggered — stopping (stop_on_first_trigger=True)",
                getattr(guardrail, "guardrail_name", guardrail.__name__),
            )
            break
    return results


# ============================================================================
# Helpers
# ============================================================================

def _is_async(func: Callable) -> bool:
    """Check if a function is async (coroutine function)."""
    import asyncio
    return asyncio.iscoroutinefunction(func)


__all__ = [
    "TripwireResult",
    "CalculationErrorSnapshot",
    "input_guardrail",
    "output_guardrail",
    "run_guardrails",
]
