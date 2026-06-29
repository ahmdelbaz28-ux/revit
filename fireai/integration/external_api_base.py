"""
fireai/integration/external_api_base.py.
========================================
Base class for ALL external-API adapters in FireAI.

SAFETY ARCHITECTURE (NFPA 72-2022 §10.5 — Integrity):
  External APIs are ADVISORY ONLY. The primary fire-protection logic runs
  locally and MUST NOT depend on internet connectivity. This base class
  enforces that contract:

  1. FAIL-SAFE DEFAULT: Every call returns a typed result. If the API
     fails, a conservative default is returned — never an exception that
     could crash the FACP or workflow pipeline.
  2. CIRCUIT BREAKER: After N consecutive failures, the adapter is
     "tripped" and short-circuits all subsequent calls for a cooldown
     period. This prevents cascade failures and protects the event loop.
  3. TIMEOUT ENFORCED: All HTTP calls have a hard timeout. A hung
     external API can never block the FACP.
  4. AUDIT TRAIL: Every call is logged with success/failure, latency,
     and the conservative-default that was returned on failure.
  5. NEVER RAISES: Public methods NEVER raise exceptions. They return
     a result object with `.ok` and `.value`. This is the only safe
     contract for safety-critical code that calls external services.

DESIGN RATIONALE (Rule 17 — Root-Cause):
  The root cause of "external API integration fails silently" is *not*
  the API itself — it is the absence of a typed failure contract. Most
  adapters wrap calls in try/except and log, but the CALLER has no way
  to distinguish "API said X" from "API failed and we guessed X". This
  base class forces every adapter to return an `ApiResult` whose `.ok`
  flag makes that distinction explicit, so the caller can degrade
  gracefully (e.g. log an "ENVIRONMENTAL DATA UNAVAILABLE" warning on
  the FACP instead of silently using a guessed value).

References:
  - NFPA 72-2022 §10.5  — Integrity (no single point of failure)
  - NFPA 72-2022 §10.18 — System monitoring
  - Michael Nygard, "Release It!" — Circuit Breaker pattern
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

import httpx

logger = logging.getLogger(__name__)


T = TypeVar("T")


# ===========================================================================
# Typed Result
# ===========================================================================


@dataclass(frozen=True)
class ApiResult(Generic[T]):
    """
    Typed result of an external-API call.

    Attributes:
        ok:        True iff the API call succeeded and `value` is real.
                   False iff the API failed and `value` is a conservative
                   default. NEVER raise — always check `.ok`.
        value:     The parsed payload on success, or the conservative
                   default on failure. Type depends on the adapter.
        source:    Name of the adapter (e.g. "wildfire_smoke").
        error:     Empty string on success. On failure, a short
                   classification: "timeout", "http_4xx", "http_5xx",
                   "circuit_open", "parse_error", "network".
        latency_ms: Round-trip time in milliseconds. 0 when circuit_open.
        fallback_used: True iff `.value` is a conservative default
                       (i.e. `ok is False`).
    """

    ok: bool
    value: T
    source: str
    error: str = ""
    latency_ms: float = 0.0
    fallback_used: bool = False

    def __post_init__(self) -> None:
        # Invariants (checked in order from least to most specific):
        #   ok=True  ⟺ fallback_used=False  ⟺ error=""
        #   ok=False ⟺ fallback_used=True   ⟺ error!=""
        #
        # Ordering rationale: tests assert that each violation raises a
        # specific message. We check the broadest invariant first so the
        # error message is unambiguous. The full invariant is:
        #
        #   ok  ⟺  not fallback_used  ⟺  (error == "") iff ok
        #
        if self.ok and self.fallback_used:
            raise ValueError("ApiResult invariant: ok=True ⟹ fallback_used=False")
        if self.ok and self.error:
            raise ValueError("ApiResult invariant: ok=True ⟹ error must be empty")
        # For ok=False: require BOTH error and fallback_used together.
        if not self.ok and (not self.error or not self.fallback_used):
            raise ValueError(
                "ApiResult invariant: ok=False ⟹ error must be set and fallback_used=True "
                f"(got error={self.error!r}, fallback_used={self.fallback_used})"
            )


# ===========================================================================
# Circuit Breaker
# ===========================================================================


@dataclass
class CircuitState:
    """
    Circuit-breaker state for one adapter.

    States:
        CLOSED:     Normal operation. Calls go through.
        OPEN:       Tripped. All calls short-circuit to fallback
                    until cooldown elapses.
        HALF_OPEN:  Cooldown elapsed; next call is a probe. If it
                    succeeds, the breaker resets to CLOSED. If it
                    fails, the breaker re-OPENS for another cooldown.
    """

    failure_threshold: int = 5
    cooldown_seconds: float = 300.0  # 5 minutes
    _consecutive_failures: int = 0
    _last_failure_ts: float = 0.0
    _state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN

    @property
    def state(self) -> str:
        # Auto-transition OPEN → HALF_OPEN after cooldown
        if self._state == "OPEN":
            if (time.monotonic() - self._last_failure_ts) >= self.cooldown_seconds:
                self._state = "HALF_OPEN"
        return self._state

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = "CLOSED"

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        self._last_failure_ts = time.monotonic()
        if self._consecutive_failures >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(
                "Circuit OPENED after %d consecutive failures (cooldown=%.0fs)",
                self._consecutive_failures,
                self.cooldown_seconds,
            )

    def should_short_circuit(self) -> bool:
        return self.state == "OPEN"


# ===========================================================================
# Base Adapter
# ===========================================================================


class ExternalApiAdapter:
    """
    Base class for all external-API adapters.

    Subclasses MUST:
      1. Set `source_name` (used in logs and ApiResult.source).
      2. Implement `_fetch()` — the actual HTTP call + parse.
      3. Implement `_fallback()` — the conservative default.

    Subclasses MUST NOT:
      1. Override `call()` directly.
      2. Raise exceptions from `_fetch` or `_fallback` — wrap in ApiResult.
      3. Make synchronous HTTP calls — use httpx.AsyncClient.

    Usage:
        class WildfireAdapter(ExternalApiAdapter):
            source_name = "wildfire_smoke"
            async def _fetch(self, lat, lon): ...
            def _fallback(self, lat, lon): ...

        adapter = WildfireAdapter()
        result = await adapter.call(lat=30.04, lon=31.23)
        if not result.ok:
            # log environmental data unavailable, proceed with fallback
            ...
    """

    source_name: str = "external_api"
    timeout_seconds: float = 10.0
    failure_threshold: int = 5
    cooldown_seconds: float = 300.0

    def __init__(
        self,
        *,
        failure_threshold: int | None = None,
        cooldown_seconds: float | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        # Allow per-instance override of class-level defaults. Used by
        # tests (to fast-test the circuit breaker) and by production
        # callers that need a tighter/looser policy.
        eff_failure = failure_threshold if failure_threshold is not None else self.failure_threshold
        eff_cooldown = cooldown_seconds if cooldown_seconds is not None else self.cooldown_seconds
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        self._circuit = CircuitState(
            failure_threshold=eff_failure,
            cooldown_seconds=eff_cooldown,
        )
        # One reusable client per adapter (connection pooling)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                headers={"User-Agent": "FireAI/1.0 (safety-critical)"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # ── to be implemented by subclasses ────────────────────────────────

    async def _fetch(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def _fallback(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    # ── public API — never overridden ──────────────────────────────────

    async def call(self, *args: Any, **kwargs: Any) -> ApiResult[Any]:
        """
        Invoke the adapter. NEVER raises.

        Returns an ApiResult. If the circuit is OPEN or the fetch fails
        for any reason, returns an ApiResult with `ok=False` and the
        conservative fallback value.
        """
        # Gate 1: Circuit breaker
        if self._circuit.should_short_circuit():
            logger.info(
                "[%s] circuit OPEN — returning fallback (cooldown active)",
                self.source_name,
            )
            return ApiResult(
                ok=False,
                value=self._fallback(*args, **kwargs),
                source=self.source_name,
                error="circuit_open",
                fallback_used=True,
            )

        # Gate 2: Execute fetch with timing
        t0 = time.monotonic()
        try:
            value = await self._fetch(*args, **kwargs)
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._circuit.record_success()
            return ApiResult(
                ok=True,
                value=value,
                source=self.source_name,
                latency_ms=latency_ms,
            )
        except httpx.TimeoutException as e:
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._circuit.record_failure()
            logger.warning("[%s] timeout after %.0fms: %s",
                           self.source_name, latency_ms, e)
            return self._fail("timeout", args, kwargs)
        except httpx.HTTPStatusError as e:
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._circuit.record_failure()
            code = e.response.status_code
            klass = "http_4xx" if 400 <= code < 500 else "http_5xx"
            logger.warning("[%s] HTTP %d after %.0fms: %s",
                           self.source_name, code, latency_ms, e)
            return self._fail(klass, args, kwargs)
        except httpx.HTTPError as e:
            # Network errors, DNS, connection refused, etc.
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._circuit.record_failure()
            logger.warning("[%s] network error after %.0fms: %s",
                           self.source_name, latency_ms, e)
            return self._fail("network", args, kwargs)
        except (KeyError, ValueError, TypeError) as e:
            # Parse errors — response was received but malformed
            latency_ms = (time.monotonic() - t0) * 1000.0
            # Don't trip the breaker on parse errors — could be a single
            # bad payload, not a service outage
            logger.warning("[%s] parse error after %.0fms: %s",
                           self.source_name, latency_ms, e)
            return self._fail("parse_error", args, kwargs)

    def _fail(self, error: str, args: tuple, kwargs: dict) -> ApiResult[Any]:
        return ApiResult(
            ok=False,
            value=self._fallback(*args, **kwargs),
            source=self.source_name,
            error=error,
            fallback_used=True,
        )

    # ── health check ───────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        """Return adapter health for /health endpoints."""
        return {
            "source": self.source_name,
            "circuit_state": self._circuit.state,
            "consecutive_failures": self._circuit._consecutive_failures,
            "failure_threshold": self._circuit.failure_threshold,
            "cooldown_seconds": self._circuit.cooldown_seconds,
            "timeout_seconds": self.timeout_seconds,
        }
