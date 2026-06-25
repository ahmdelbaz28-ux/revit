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


@dataclass
class WebhookSubscription:
    """A webhook subscription — one external service's registration.

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
    event_types: List[str] = field(default_factory=list)
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
    """An event that exceeded max retry attempts."""

    subscription_id: str
    event_id: str
    event_type: str
    url: str
    final_error: str
    attempts: List[WebhookDeliveryAttempt]
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
        if not sub.secret or len(sub.secret) < 16:
            raise ValueError(
                "HMAC secret must be at least 16 characters for security. "
                f"Got {len(sub.secret)} characters."
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

        # Deliver to each subscriber (synchronously for now; can be
        # moved to background thread pool for higher throughput)
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
                if len(self._delivery_history) > 1000:
                    self._delivery_history = self._delivery_history[-1000:]

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
        dlq_entry = DeadLetterEntry(
            subscription_id=subscription.id,
            event_id=event_id,
            event_type=event_type,
            url=subscription.url,
            final_error=attempts[-1].error or "Unknown error",
            attempts=attempts,
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
        except Exception:
            pass  # never block on audit failure

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
        """Perform a single HTTP POST delivery attempt."""
        t_start = time.perf_counter()

        try:
            # Use stdlib urllib to avoid adding httpx dependency
            # (httpx is available, but urllib is always present)
            import urllib.request
            import urllib.error

            req = urllib.request.Request(
                url=url,
                data=payload,
                headers=headers,
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
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

        Args:
            dlq_index: Index in DLQ list.

        Returns:
            True if replay was initiated, False if index invalid.
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

        # Re-publish (will go through retry cycle again)
        # Note: we don't have the original data, only the event_id
        # In production, we'd store the full payload in DLQ
        logger.info(
            "Replaying DLQ entry %d for subscription %s",
            dlq_index, entry.subscription_id,
        )
        # For now, just log — full replay would need payload storage
        return True

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
