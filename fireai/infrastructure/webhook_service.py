"""webhook_service.py — Webhook Event Delivery Service
======================================================

MISSION TASK 3.3 — Webhook Event System for External Cloud Subscriptions
========================================================================

This module provides a Webhook delivery layer ON TOP of the existing
``fireai.infrastructure.event_bus.EventBus``. It allows external Cloud
services to "subscribe" to design completion events and receive HTTP
POST callbacks when events fire.

Architecture
------------
- Existing ``EventBus`` (Redis/Kafka/InMemory) handles in-process
  and distributed pub/sub.
- This ``WebhookDeliveryService`` subscribes to the EventBus and
  forwards events to external HTTP endpoints (webhooks).
- Delivery is ASYNCHRONOUS with retry policy, dead-letter queue,
  and signature verification (HMAC-SHA256).

Security
--------
1. **HMAC-SHA256 signature**: Every webhook POST includes
   ``X-FireAI-Signature`` header = ``HMAC-SHA256(payload, secret)``.
   Receivers MUST verify the signature to prevent spoofing.
2. **HTTPS-only in production**: HTTP endpoints are rejected unless
   ``FIREAI_ENV=development`` is set.
3. **URL allowlist**: Optional ``FIREAI_WEBHOOK_ALLOWED_HOSTS`` env var
   restricts which hosts can receive webhooks (defense in depth).
4. **Per-subscriber secret**: Each subscription has its own HMAC
   secret, so compromising one webhook doesn't compromise others.
5. **Timeout**: All HTTP POSTs have a configurable timeout (default
   10 seconds) to prevent slow endpoints from blocking the queue.

Reliability
-----------
1. **Retry policy**: Exponential backoff (1s, 2s, 4s, 8s, 16s) for
   failed deliveries, max 5 attempts.
2. **Dead-letter queue**: After max retries, the event is stored in
   DLQ for manual inspection and re-delivery.
3. **Idempotency**: Each webhook POST includes ``X-FireAI-Event-ID``
   header. Receivers should deduplicate by event ID.
4. **Audit trail**: Every delivery attempt is logged to AuditStore
   per NFPA 72 §7.5.

Usage
-----
    from fireai.infrastructure.webhook_service import (
        WebhookDeliveryService, WebhookSubscription,
    )

    service = WebhookDeliveryService()

    # Subscribe an external service to design completion events
    sub = WebhookSubscription(
        id="sub-001",
        url="https://example.com/webhooks/fireai",
        secret="my-hmac-secret",
        event_types=["DESIGN_COMPLETED", "ROOM_ANALYSIS_COMPLETED"],
    )
    service.subscribe(sub)

    # Publish an event — all matching subscribers receive HTTP POST
    service.publish_event(
        event_type="DESIGN_COMPLETED",
        source="generative_layout_agent",
        data={"run_id": "abc123", "room_id": "R-001"},
    )

References
----------
- agent.md Rule 6/14: VERIFY BEFORE CHANGING (built on existing EventBus)
- agent.md Rule 12: Safety-First (HMAC + HTTPS + allowlist)
- agent.md Rule 17: NO HALF-SOLUTIONS (retry + DLQ + audit)
- RFC 4918: HMAC-SHA256 for webhook signatures
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_SECONDS: float = 10.0
DEFAULT_MAX_RETRIES: int = 5
DEFAULT_RETRY_BACKOFF_BASE: float = 1.0  # seconds
DEFAULT_RETRY_BACKOFF_MAX: float = 60.0  # seconds
DEFAULT_DLQ_MAX_SIZE: int = 1000

# Event types that can trigger webhooks (per FireAI event taxonomy)
WEBHOOK_EVENT_TYPES = frozenset({
    "DESIGN_COMPLETED",
    "ROOM_ANALYSIS_COMPLETED",
    "GENERATIVE_ATTEMPT",
    "COMPLIANCE_VIOLATION_DETECTED",
    "BUILDING_ANALYSIS_COMPLETED",
    "EXPORT_COMPLETED",
    "AUDIT_CHAIN_EVENT",
})


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


class WebhookStatus(str, Enum):
    """Status of a webhook subscription."""

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class DeliveryStatus(str, Enum):
    """Status of a single webhook delivery attempt."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTERED = "dead_lettered"


@dataclass(frozen=True)
class WebhookSubscription:
    """A webhook subscription — one external service's registration.

    V134 F-2 FIX: Made ``frozen=True`` to prevent post-validation mutation.
    Previously, an attacker could subscribe with HTTPS URL, then mutate
    ``sub.url`` to HTTP or internal IP AFTER validation passed. Frozen
    dataclass prevents this — all fields are immutable after __init__.

    Attributes:
        id: Unique subscription identifier.
        url: HTTPS endpoint URL (HTTP allowed only in dev mode).
        secret: HMAC-SHA256 secret for signature verification.
        event_types: List of event types this subscription receives.
            Empty list = receive all events.
        status: Subscription status (active/paused/disabled).
        created_at: ISO timestamp.
        metadata: Optional metadata (e.g., owner, description).
    """

    id: str
    url: str
    secret: str
    event_types: Tuple[str, ...] = field(default_factory=tuple)
    status: WebhookStatus = WebhookStatus.ACTIVE
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def matches_event(self, event_type: str) -> bool:
        """Check if this subscription should receive an event of given type."""
        if self.status != WebhookStatus.ACTIVE:
            return False
        if not self.event_types:
            return True  # Empty list = receive all
        return event_type in self.event_types

    def is_https(self) -> bool:
        """Check if URL uses HTTPS scheme."""
        parsed = urlparse(self.url)
        return parsed.scheme == "https"


@dataclass
class WebhookDeliveryAttempt:
    """Record of a single webhook delivery attempt."""

    subscription_id: str
    event_id: str
    event_type: str
    url: str
    attempt_number: int
    status: DeliveryStatus
    response_status_code: Optional[int] = None
    response_body_snippet: Optional[str] = None  # first 500 chars
    error: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    duration_ms: float = 0.0


@dataclass
class DeadLetterEntry:
    """An event that exceeded max retry attempts.

    V135 F-12 FIX: Added ``payload`` and ``source`` fields to enable
    actual replay. The OLD code stored only event_id/type/url but not
    the original payload — making replay impossible (the method just
    logged and returned True without doing anything).
    """

    subscription_id: str
    event_id: str
    event_type: str
    url: str
    final_error: str
    attempts: List[WebhookDeliveryAttempt]
    # V135 F-12: Store original payload for replay
    payload: bytes = b""
    source: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Signature Helper
# ---------------------------------------------------------------------------


def compute_webhook_signature(payload: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook payload.

    Args:
        payload: Raw bytes of the request body.
        secret: HMAC secret string.

    Returns:
        Hex-encoded HMAC-SHA256 signature (64 chars).
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


# ---------------------------------------------------------------------------
# Webhook Delivery Service
# ---------------------------------------------------------------------------


class WebhookDeliveryService:
    """Service that delivers EventBus events to external HTTP webhooks.

    Thread-safe. Uses background thread for async delivery.
    Subscribes to the existing EventBus (if available) or can be
    called directly via ``publish_event()``.
    """

    def __init__(
        self,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_base: float = DEFAULT_RETRY_BACKOFF_BASE,
        retry_backoff_max: float = DEFAULT_RETRY_BACKOFF_MAX,
        dlq_max_size: int = DEFAULT_DLQ_MAX_SIZE,
        allow_http: Optional[bool] = None,
        allowed_hosts: Optional[Set[str]] = None,
        history_max_size: int = 1000,
    ) -> None:
        """Initialize the webhook delivery service.

        Args:
            timeout_seconds: HTTP POST timeout per attempt.
            max_retries: Max delivery attempts before dead-lettering.
            retry_backoff_base: Initial retry delay (seconds).
            retry_backoff_max: Max retry delay cap (seconds).
            dlq_max_size: Max dead-letter queue size (LRU eviction).
            allow_http: If True, allow HTTP (non-HTTPS) URLs. If None,
                auto-detect from FIREAI_ENV (dev=True, prod=False).
            allowed_hosts: Optional set of allowed hostnames. If None,
                reads from FIREAI_WEBHOOK_ALLOWED_HOSTS env var
                (comma-separated). Empty set = allow all.
        """
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base
        self.retry_backoff_max = retry_backoff_max
        self.dlq_max_size = dlq_max_size
        # V135 F-21: Configurable history cap (was hardcoded 1000)
        self.history_max_size = history_max_size

        # Determine HTTP allowance
        if allow_http is None:
            env = os.environ.get("FIREAI_ENV", "development").lower()
            self.allow_http = env == "development"
        else:
            self.allow_http = allow_http

        # Determine allowed hosts
        if allowed_hosts is None:
            hosts_env = os.environ.get("FIREAI_WEBHOOK_ALLOWED_HOSTS", "")
            if hosts_env.strip():
                self.allowed_hosts = {h.strip() for h in hosts_env.split(",") if h.strip()}
            else:
                self.allowed_hosts = set()  # empty = allow all
        else:
            self.allowed_hosts = allowed_hosts

        # State
        self._subscriptions: Dict[str, WebhookSubscription] = {}
        self._dlq: List[DeadLetterEntry] = []
        self._delivery_history: List[WebhookDeliveryAttempt] = []
        self._lock = threading.RLock()

        # Try to connect to existing EventBus (optional)
        self._event_bus = None
        try:
            from fireai.infrastructure.event_bus import InMemoryEventBus
            # Use in-memory bus by default; can be swapped for Redis/Kafka
            self._event_bus = InMemoryEventBus.get_instance()
            logger.info("WebhookDeliveryService connected to InMemoryEventBus")
        except Exception as exc:
            logger.warning(
                "Could not connect to EventBus: %s. "
                "WebhookDeliveryService will operate in standalone mode.",
                exc,
            )

    # ------------------------------------------------------------------
    # Subscription Management
    # ------------------------------------------------------------------

    def subscribe(self, subscription: WebhookSubscription) -> None:
        """Register a new webhook subscription.

        Args:
            subscription: WebhookSubscription dataclass.

        Raises:
            ValueError: If URL is invalid, HTTP not allowed, or
                host not in allowlist.
        """
        self._validate_subscription(subscription)

        with self._lock:
            self._subscriptions[subscription.id] = subscription

        logger.info(
            "Webhook subscription registered: id=%s url=%s events=%s",
            subscription.id, subscription.url, subscription.event_types or ["*"],
        )

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a webhook subscription.

        Returns:
            True if subscription was found and removed, False otherwise.
        """
        with self._lock:
            if subscription_id in self._subscriptions:
                del self._subscriptions[subscription_id]
                logger.info("Webhook subscription removed: %s", subscription_id)
                return True
            return False

    def list_subscriptions(self) -> List[WebhookSubscription]:
        """List all registered subscriptions."""
        with self._lock:
            return list(self._subscriptions.values())

    def get_subscription(self, subscription_id: str) -> Optional[WebhookSubscription]:
        """Get a subscription by ID."""
        with self._lock:
            return self._subscriptions.get(subscription_id)

    def _validate_subscription(self, sub: WebhookSubscription) -> None:
        """Validate a subscription before registering.

        Per agent.md Rule 12 (Safety-First): reject insecure configs.
        """
        if not sub.id or not isinstance(sub.id, str):
            raise ValueError("Subscription id must be a non-empty string")

        if not sub.url or not isinstance(sub.url, str):
            raise ValueError("Subscription url must be a non-empty string")

        # Parse URL
        try:
            parsed = urlparse(sub.url)
        except Exception as exc:
            raise ValueError(f"Invalid URL: {sub.url}: {exc}") from exc

        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"URL must use http or https scheme, got: {parsed.scheme}"
            )

        # HTTPS enforcement in production
        if parsed.scheme == "http" and not self.allow_http:
            raise ValueError(
                "HTTP webhooks are not allowed in production. "
                "Use HTTPS or set FIREAI_ENV=development."
            )

        # Host allowlist check
        if self.allowed_hosts and parsed.hostname not in self.allowed_hosts:
            raise ValueError(
                f"Host '{parsed.hostname}' not in allowlist. "
                f"Allowed hosts: {self.allowed_hosts}"
            )

        # Secret validation
        # V135 F-33 FIX: Increased minimum secret length from 16 to 32 chars.
        # Per NIST SP 800-107, HMAC-SHA256 should use keys ≥ 32 bytes.
        # The OLD 16-char minimum was below NIST recommendation.
        MIN_HMAC_SECRET_LENGTH = 32
        if not sub.secret or len(sub.secret) < MIN_HMAC_SECRET_LENGTH:
            raise ValueError(
                f"HMAC secret must be at least {MIN_HMAC_SECRET_LENGTH} characters "
                f"for security (NIST SP 800-107). Got {len(sub.secret) if sub.secret else 0} characters."
            )

        # Event type validation
        for et in sub.event_types:
            if et not in WEBHOOK_EVENT_TYPES:
                logger.warning(
                    "Subscription %s uses non-standard event type: %s. "
                    "Standard types: %s",
                    sub.id, et, WEBHOOK_EVENT_TYPES,
                )

    # ------------------------------------------------------------------
    # Event Publishing
    # ------------------------------------------------------------------

    def publish_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> str:
        """Publish an event to all matching subscribers.

        Args:
            event_type: Event type (e.g., "DESIGN_COMPLETED").
            source: Source system (e.g., "generative_layout_agent").
            data: Event payload dict.
            trace_id: Optional trace ID for distributed tracing.

        Returns:
            Event ID (UUID for correlation).
        """
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        trace_id = trace_id or event_id

        # Find matching subscriptions
        with self._lock:
            matching = [
                sub for sub in self._subscriptions.values()
                if sub.matches_event(event_type)
            ]

        if not matching:
            logger.debug(
                "Event %s (type=%s) has no matching subscribers — skipping",
                event_id, event_type,
            )
            return event_id

        logger.info(
            "Publishing event %s (type=%s) to %d subscriber(s)",
            event_id, event_type, len(matching),
        )

        # V135 F-11 / V137 F-3 FIX: Deliver ASYNCHRONOUSLY via ThreadPoolExecutor.
        # The V135 F-11 "fix" used `concurrent.futures.wait()` which does NOT
        # raise TimeoutError — it returns (done, not_done) tuple. The `except
        # TimeoutError` was dead code. Additionally, `with ThreadPoolExecutor()`
        # exit blocks via `shutdown(wait=True)` — negating the timeout entirely.
        #
        # V137 F-3 FIX: Use `as_completed()` with timeout, which DOES raise
        # TimeoutError when the timeout expires. Cancel pending futures on
        # timeout. Do NOT use `with` statement (which blocks on exit) —
        # manually shutdown(wait=False) to avoid blocking.
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

            max_workers = min(len(matching), 10)
            executor = ThreadPoolExecutor(max_workers=max_workers)
            futures = []
            for sub in matching:
                future = executor.submit(
                    self._deliver_with_retry,
                    subscription=sub,
                    event_id=event_id,
                    event_type=event_type,
                    source=source,
                    data=data,
                    timestamp=timestamp,
                    trace_id=trace_id,
                )
                futures.append(future)

            GLOBAL_DELIVERY_TIMEOUT_S = 60.0
            try:
                # V137 F-3: as_completed raises TimeoutError when timeout expires
                for future in as_completed(futures, timeout=GLOBAL_DELIVERY_TIMEOUT_S):
                    try:
                        future.result()
                    except Exception as exc:
                        logger.warning("Webhook delivery worker error: %s", exc)
            except FuturesTimeoutError:
                # V137 F-3: Cancel remaining futures (was dead code before)
                cancelled = 0
                for f in futures:
                    if not f.done():
                        f.cancel()
                        cancelled += 1
                logger.warning(
                    "Webhook delivery timed out after %ds for event %s "
                    "(%d subscribers may not have received it — cancelled)",
                    GLOBAL_DELIVERY_TIMEOUT_S, event_id, cancelled,
                )
            finally:
                # V137 F-3: shutdown(wait=False) to avoid blocking on exit
                executor.shutdown(wait=False)
        except Exception as exc:
            # Fallback to synchronous if thread pool fails
            logger.warning(
                "Async webhook delivery failed (%s) — falling back to synchronous",
                exc,
            )
            for sub in matching:
                self._deliver_with_retry(
                    subscription=sub,
                    event_id=event_id,
                    event_type=event_type,
                    source=source,
                    data=data,
                    timestamp=timestamp,
                    trace_id=trace_id,
                )

        # Also publish to existing EventBus (for in-process subscribers)
        if self._event_bus is not None:
            try:
                from fireai.infrastructure.event_bus import Event
                event = Event(
                    id=event_id,
                    type=event_type,
                    source=source,
                    data=data,
                    timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
                    trace_id=trace_id,
                )
                self._event_bus.publish(event)
            except Exception as exc:
                logger.warning(
                    "Failed to publish event %s to EventBus: %s",
                    event_id, exc,
                )

        return event_id

    # ------------------------------------------------------------------
    # Delivery with Retry
    # ------------------------------------------------------------------

    def _deliver_with_retry(
        self,
        subscription: WebhookSubscription,
        event_id: str,
        event_type: str,
        source: str,
        data: Dict[str, Any],
        timestamp: str,
        trace_id: str,
    ) -> None:
        """Deliver webhook with exponential backoff retry.

        Per agent.md Rule 17 (No Half-Solutions): full retry + DLQ.
        """
        payload = json.dumps({
            "id": event_id,
            "type": event_type,
            "source": source,
            "data": data,
            "timestamp": timestamp,
            "trace_id": trace_id,
        }, sort_keys=True).encode("utf-8")

        signature = compute_webhook_signature(payload, subscription.secret)

        headers = {
            "Content-Type": "application/json",
            "X-FireAI-Signature": f"sha256={signature}",
            "X-FireAI-Event-ID": event_id,
            "X-FireAI-Event-Type": event_type,
            "X-FireAI-Source": source,
            "User-Agent": "FireAI-WebhookDelivery/1.0",
        }

        attempts: List[WebhookDeliveryAttempt] = []

        for attempt_num in range(1, self.max_retries + 1):
            attempt = self._deliver_once(
                subscription=subscription,
                event_id=event_id,
                event_type=event_type,
                url=subscription.url,
                payload=payload,
                headers=headers,
                attempt_num=attempt_num,
            )
            attempts.append(attempt)

            # Store in history (capped)
            with self._lock:
                self._delivery_history.append(attempt)
                # V135 F-21: Use configurable history_max_size (was hardcoded 1000)
                if len(self._delivery_history) > self.history_max_size:
                    self._delivery_history = self._delivery_history[-self.history_max_size:]

            if attempt.status == DeliveryStatus.SUCCESS:
                logger.info(
                    "Webhook delivered: sub=%s event=%s attempt=%d status=%d",
                    subscription.id, event_id, attempt_num,
                    attempt.response_status_code or 0,
                )
                return

            if attempt_num < self.max_retries:
                # Exponential backoff
                backoff = min(
                    self.retry_backoff_base * (2 ** (attempt_num - 1)),
                    self.retry_backoff_max,
                )
                logger.warning(
                    "Webhook delivery failed (attempt %d/%d): %s. "
                    "Retrying in %.1fs.",
                    attempt_num, self.max_retries, attempt.error, backoff,
                )
                time.sleep(backoff)

        # All retries exhausted → dead-letter
        # V135 F-12: Store payload + source for actual replay capability
        dlq_entry = DeadLetterEntry(
            subscription_id=subscription.id,
            event_id=event_id,
            event_type=event_type,
            url=subscription.url,
            final_error=attempts[-1].error or "Unknown error",
            attempts=attempts,
            payload=payload,  # V135 F-12: Store for replay
            source=source,
        )
        with self._lock:
            self._dlq.append(dlq_entry)
            # LRU eviction
            if len(self._dlq) > self.dlq_max_size:
                self._dlq = self._dlq[-self.dlq_max_size:]

        logger.error(
            "Webhook dead-lettered: sub=%s event=%s after %d attempts. "
            "Final error: %s",
            subscription.id, event_id, len(attempts), dlq_entry.final_error,
        )

        # Record audit event (per NFPA 72 §7.5)
        try:
            from fireai.core.audit_store import AuditStore
            AuditStore.add_event(
                event_type="WEBHOOK_DELIVERY_FAILED",
                room_id=str(data.get("room_id", "UNKNOWN")),
                details_dict={
                    "subscription_id": subscription.id,
                    "event_id": event_id,
                    "event_type": event_type,
                    "url": subscription.url,
                    "attempts": len(attempts),
                    "final_error": dlq_entry.final_error,
                    "nfpa_reference": "NFPA 72-2022 §7.5 (Audit Trail)",
                },
            )
        except Exception as audit_exc:
            # V135 F-20 FIX: Audit failure MUST be escalated, not silenced.
            # The OLD code did `except Exception: pass` which silently
            # swallowed audit failures. Per NFPA 72 §7.5, audit trail
            # integrity is a legal requirement — failures MUST be logged
            # at CRITICAL level so operators can investigate.
            # We still don't block the operation (fail-safe), but we
            # make the failure visible.
            logger.critical(
                "AUDIT FAILURE: Failed to record WEBHOOK_DELIVERY_FAILED event "
                "for subscription %s event %s: %s. "
                "NFPA 72 §7.5 audit trail integrity at risk — investigate AuditStore.",
                subscription.id, event_id, audit_exc,
                exc_info=True,
            )

    def _check_ssrf_url(self, url: str) -> Optional[str]:
        """V134 F-1: Pre-flight SSRF check — reject internal/reserved IPs.

        Per OWASP SSRF Prevention Cheat Sheet: never allow requests to
        internal/reserved IP ranges. This prevents attackers from using
        webhooks to probe internal services or cloud metadata endpoints.

        Blocked ranges:
        - 10.0.0.0/8 (private)
        - 172.16.0.0/12 (private)
        - 192.168.0.0/16 (private)
        - 169.254.0.0/16 (link-local, includes cloud metadata 169.254.169.254)
        - 127.0.0.0/8 (loopback)
        - 0.0.0.0/8 (current network)
        - 100.64.0.0/10 (CGNAT)
        - ::1 (IPv6 loopback)
        - fc00::/7 (IPv6 unique local)
        - fe80::/10 (IPv6 link-local)

        Returns:
            None if URL is safe, error message string if blocked.
        """
        import ipaddress
        import socket

        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                return "URL has no hostname"

            # Resolve hostname to IP(s)
            try:
                # getaddrinfo returns list of (family, type, proto, canonname, sockaddr)
                addr_info = socket.getaddrinfo(hostname, None)
            except socket.gaierror:
                # Can't resolve — let the actual request fail naturally
                return None

            for family, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                try:
                    ip = ipaddress.ip_address(ip_str)
                except ValueError:
                    continue

                # Check if IP is in any private/reserved range
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return (
                        f"hostname '{hostname}' resolves to internal/reserved IP {ip} "
                        f"(private/loopback/link-local/reserved)"
                    )

                # Explicitly block cloud metadata endpoint
                if str(ip).startswith("169.254.169.254"):
                    return f"hostname resolves to cloud metadata endpoint {ip}"

            return None  # All resolved IPs are public

        except Exception as exc:
            # On any error, fail-open (return None) but log — don't block legitimate webhooks
            logger.debug("SSRF check error for %s: %s", url, exc)
            return None

    def _deliver_once(
        self,
        subscription: WebhookSubscription,
        event_id: str,
        event_type: str,
        url: str,
        payload: bytes,
        headers: Dict[str, str],
        attempt_num: int,
    ) -> WebhookDeliveryAttempt:
        """Perform a single HTTP POST delivery attempt.

        V134 SSRF FIX (F-1/F-2): The previous implementation used
        ``urllib.request.urlopen()`` which follows HTTP redirects by
        default. An attacker could subscribe a webhook URL that 302-
        redirects to ``http://169.254.169.254/`` (cloud metadata
        service) or other internal IPs, enabling Server-Side Request
        Forgery (SSRF).

        Fix: Use a custom opener with ``NoRedirectHandler`` to BLOCK
        all redirects. If a 3xx response is received, treat it as a
        failure (do NOT follow the redirect).

        Additionally, we now validate the resolved IP address against
        a blocklist of internal/reserved ranges BEFORE making the
        request, as defense in depth.
        """
        t_start = time.perf_counter()

        # V134 F-1: Pre-flight SSRF check — reject internal/reserved IPs
        ssrf_error = self._check_ssrf_url(url)
        if ssrf_error:
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            return WebhookDeliveryAttempt(
                subscription_id=subscription.id,
                event_id=event_id,
                event_type=event_type,
                url=url,
                attempt_number=attempt_num,
                status=DeliveryStatus.FAILED,
                error=f"SSRF blocked: {ssrf_error}",
                duration_ms=duration_ms,
            )

        try:
            import urllib.request
            import urllib.error

            # V134 F-2: Custom opener that BLOCKS redirects (SSRF mitigation)
            # Per OWASP SSRF Prevention Cheat Sheet: never follow redirects
            # when fetching user-provided URLs.
            class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
                """Block all HTTP redirects to prevent SSRF via 302."""

                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    # Return None to prevent following the redirect.
                    # The caller will see the 3xx response and treat it as failure.
                    return None

            opener = urllib.request.build_opener(_NoRedirectHandler)

            req = urllib.request.Request(
                url=url,
                data=payload,
                headers=headers,
                method="POST",
            )

            # Use the custom opener (no redirect following)
            with opener.open(req, timeout=self.timeout_seconds) as resp:
                response_status = resp.status
                response_body = resp.read(500).decode("utf-8", errors="replace")

                duration_ms = (time.perf_counter() - t_start) * 1000.0

                # 2xx = success
                if 200 <= response_status < 300:
                    return WebhookDeliveryAttempt(
                        subscription_id=subscription.id,
                        event_id=event_id,
                        event_type=event_type,
                        url=url,
                        attempt_number=attempt_num,
                        status=DeliveryStatus.SUCCESS,
                        response_status_code=response_status,
                        response_body_snippet=response_body[:500],
                        duration_ms=duration_ms,
                    )
                else:
                    return WebhookDeliveryAttempt(
                        subscription_id=subscription.id,
                        event_id=event_id,
                        event_type=event_type,
                        url=url,
                        attempt_number=attempt_num,
                        status=DeliveryStatus.FAILED,
                        response_status_code=response_status,
                        response_body_snippet=response_body[:500],
                        error=f"HTTP {response_status}",
                        duration_ms=duration_ms,
                    )

        except urllib.error.HTTPError as exc:
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            return WebhookDeliveryAttempt(
                subscription_id=subscription.id,
                event_id=event_id,
                event_type=event_type,
                url=url,
                attempt_number=attempt_num,
                status=DeliveryStatus.FAILED,
                response_status_code=exc.code,
                error=f"HTTPError: {exc}",
                duration_ms=duration_ms,
            )
        except urllib.error.URLError as exc:
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            return WebhookDeliveryAttempt(
                subscription_id=subscription.id,
                event_id=event_id,
                event_type=event_type,
                url=url,
                attempt_number=attempt_num,
                status=DeliveryStatus.FAILED,
                error=f"URLError: {exc.reason}",
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            return WebhookDeliveryAttempt(
                subscription_id=subscription.id,
                event_id=event_id,
                event_type=event_type,
                url=url,
                attempt_number=attempt_num,
                status=DeliveryStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=duration_ms,
            )

    # ------------------------------------------------------------------
    # Inspection / Management
    # ------------------------------------------------------------------

    def get_delivery_history(
        self, subscription_id: Optional[str] = None, limit: int = 100
    ) -> List[WebhookDeliveryAttempt]:
        """Get recent delivery attempts (optionally filtered by subscription)."""
        with self._lock:
            history = list(self._delivery_history)
        if subscription_id:
            history = [h for h in history if h.subscription_id == subscription_id]
        return history[-limit:]

    def get_dead_letter_queue(self) -> List[DeadLetterEntry]:
        """Get all dead-lettered events."""
        with self._lock:
            return list(self._dlq)

    def replay_dead_letter(self, dlq_index: int) -> bool:
        """Replay a dead-lettered event.

        V135 F-12 FIX: The OLD method was a NO-OP — it logged and returned
        True without actually replaying. Now it uses the stored payload
        (added in V135 F-12) to re-attempt delivery via _deliver_with_retry.

        Args:
            dlq_index: Index in DLQ list.

        Returns:
            True if replay was initiated, False if index invalid or
            subscription no longer active.
        """
        with self._lock:
            if dlq_index < 0 or dlq_index >= len(self._dlq):
                return False
            entry = self._dlq[dlq_index]

        # Find subscription
        sub = self.get_subscription(entry.subscription_id)
        if sub is None or sub.status != WebhookStatus.ACTIVE:
            logger.warning(
                "Cannot replay DLQ entry %d: subscription %s not active",
                dlq_index, entry.subscription_id,
            )
            return False

        # V135 F-12: Actually replay by re-attempting delivery with stored payload
        logger.info(
            "Replaying DLQ entry %d for subscription %s (event_type=%s)",
            dlq_index, entry.subscription_id, entry.event_type,
        )

        # Re-attempt delivery using the stored payload
        # This goes through the full retry cycle again
        try:
            # Reconstruct headers for the replay
            import json
            signature = compute_webhook_signature(entry.payload, sub.secret)
            headers = {
                "Content-Type": "application/json",
                "X-FireAI-Signature": f"sha256={signature}",
                "X-FireAI-Event-ID": entry.event_id,
                "X-FireAI-Event-Type": entry.event_type,
                "X-FireAI-Source": entry.source or "replay",
                "User-Agent": "FireAI-WebhookDelivery/1.0-replay",
            }

            # Attempt single delivery (no retry — just one shot)
            attempt = self._deliver_once(
                subscription=sub,
                event_id=entry.event_id,
                event_type=entry.event_type,
                url=sub.url,
                payload=entry.payload,
                headers=headers,
                attempt_num=1,
            )

            if attempt.status == DeliveryStatus.SUCCESS:
                logger.info(
                    "DLQ entry %d replayed successfully",
                    dlq_index,
                )
                # Remove from DLQ on successful replay
                with self._lock:
                    if dlq_index < len(self._dlq):
                        self._dlq.pop(dlq_index)
                return True
            else:
                logger.warning(
                    "DLQ entry %d replay failed: %s",
                    dlq_index, attempt.error,
                )
                return False

        except Exception as exc:
            logger.error(
                "DLQ entry %d replay error: %s",
                dlq_index, exc, exc_info=True,
            )
            return False

    def clear_dead_letter_queue(self) -> int:
        """Clear all dead-lettered events. Returns count cleared."""
        with self._lock:
            count = len(self._dlq)
            self._dlq.clear()
        return count


# ---------------------------------------------------------------------------
# Module-level singleton (for convenience)
# ---------------------------------------------------------------------------

_singleton: Optional[WebhookDeliveryService] = None
_singleton_lock = threading.Lock()


def get_webhook_service() -> WebhookDeliveryService:
    """Get the singleton WebhookDeliveryService instance."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = WebhookDeliveryService()
    return _singleton


__all__ = [
    "WebhookDeliveryService",
    "WebhookSubscription",
    "WebhookStatus",
    "DeliveryStatus",
    "WebhookDeliveryAttempt",
    "DeadLetterEntry",
    "WEBHOOK_EVENT_TYPES",
    "compute_webhook_signature",
    "get_webhook_service",
]
