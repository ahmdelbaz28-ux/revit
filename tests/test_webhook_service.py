"""test_webhook_service.py — Tests for Webhook Delivery Service.

MISSION TASK 3.3 — Validates the WebhookDeliveryService that delivers
events to external HTTP endpoints with retry, DLQ, and HMAC signatures.

Per agent.md Rule 10: tests run after every modification.
Per agent.md Rule 1: no fabrication.
"""

from __future__ import annotations

import json

import pytest

from fireai.infrastructure.webhook_service import (
    compute_webhook_signature,
    DeliveryStatus,
    DeadLetterEntry,
    WEBHOOK_EVENT_TYPES,
    WebhookDeliveryAttempt,
    WebhookDeliveryService,
    WebhookStatus,
    WebhookSubscription,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    """WebhookDeliveryService with HTTP allowed (for testing)."""
    return WebhookDeliveryService(allow_http=True, max_retries=2)


@pytest.fixture
def valid_subscription():
    return WebhookSubscription(
        id="sub-test-001",
        url="https://example.com/webhook",
        secret="very-secure-secret-key-1234567890-abcdef",
        event_types=["DESIGN_COMPLETED"],
    )


# ---------------------------------------------------------------------------
# Signature Tests
# ---------------------------------------------------------------------------


class TestSignature:
    def test_signature_is_64_char_hex(self):
        sig = compute_webhook_signature(b"payload", "very-secure-secret-key-1234567890-abcdef")
        assert len(sig) == 64
        # All hex characters
        int(sig, 16)  # raises if not hex

    def test_same_payload_secret_same_signature(self):
        sig1 = compute_webhook_signature(b"payload", "secret")
        sig2 = compute_webhook_signature(b"payload", "secret")
        assert sig1 == sig2

    def test_different_payload_different_signature(self):
        sig1 = compute_webhook_signature(b"payload1", "secret")
        sig2 = compute_webhook_signature(b"payload2", "secret")
        assert sig1 != sig2

    def test_different_secret_different_signature(self):
        sig1 = compute_webhook_signature(b"payload", "secret1")
        sig2 = compute_webhook_signature(b"payload", "secret2")
        assert sig1 != sig2


# ---------------------------------------------------------------------------
# Subscription Validation Tests
# ---------------------------------------------------------------------------


class TestSubscriptionValidation:
    def test_valid_https_subscription_accepted(self, service, valid_subscription):
        service.subscribe(valid_subscription)
        assert service.get_subscription(valid_subscription.id) is not None

    def test_http_rejected_in_production_mode(self):
        prod_service = WebhookDeliveryService(allow_http=False)
        with pytest.raises(ValueError, match="HTTP webhooks are not allowed"):
            prod_service.subscribe(WebhookSubscription(
                id="sub-1", url="http://insecure.com/hook",
                secret="very-secure-secret-key-1234567890-abcdef",
            ))

    def test_http_allowed_in_development_mode(self):
        dev_service = WebhookDeliveryService(allow_http=True)
        # Should not raise
        dev_service.subscribe(WebhookSubscription(
            id="sub-1", url="http://localhost:8000/hook",
            secret="very-secure-secret-key-1234567890-abcdef",
        ))

    def test_short_secret_rejected(self, service):
        """V135 F-33: Secret must be ≥ 32 chars (NIST SP 800-107)."""
        with pytest.raises(ValueError, match="at least 32 characters"):
            service.subscribe(WebhookSubscription(
                id="sub-1", url="https://example.com/hook",
                secret="short-secret-only-20-chars",  # 28 chars < 32
            ))

    def test_empty_id_rejected(self, service):
        with pytest.raises(ValueError, match="non-empty string"):
            service.subscribe(WebhookSubscription(
                id="", url="https://example.com/hook",
                secret="very-secure-secret-key-1234567890-abcdef",
            ))

    def test_empty_url_rejected(self, service):
        with pytest.raises(ValueError, match="non-empty string"):
            service.subscribe(WebhookSubscription(
                id="sub-1", url="",
                secret="very-secure-secret-key-1234567890-abcdef",
            ))

    def test_non_http_scheme_rejected(self, service):
        with pytest.raises(ValueError, match="http or https scheme"):
            service.subscribe(WebhookSubscription(
                id="sub-1", url="ftp://example.com/hook",
                secret="very-secure-secret-key-1234567890-abcdef",
            ))

    def test_host_allowlist_enforced(self):
        service = WebhookDeliveryService(
            allow_http=True,
            allowed_hosts={"allowed.com"},
        )
        # Allowed host
        service.subscribe(WebhookSubscription(
            id="sub-1", url="https://allowed.com/hook",
            secret="very-secure-secret-key-1234567890-abcdef",
        ))
        # Disallowed host
        with pytest.raises(ValueError, match="not in allowlist"):
            service.subscribe(WebhookSubscription(
                id="sub-2", url="https://forbidden.com/hook",
                secret="very-secure-secret-key-1234567890-abcdef",
            ))


# ---------------------------------------------------------------------------
# Subscription Management Tests
# ---------------------------------------------------------------------------


class TestSubscriptionManagement:
    def test_subscribe_and_get(self, service, valid_subscription):
        service.subscribe(valid_subscription)
        retrieved = service.get_subscription(valid_subscription.id)
        assert retrieved is not None
        assert retrieved.url == valid_subscription.url

    def test_unsubscribe_existing(self, service, valid_subscription):
        service.subscribe(valid_subscription)
        assert service.unsubscribe(valid_subscription.id) is True
        assert service.get_subscription(valid_subscription.id) is None

    def test_unsubscribe_nonexistent_returns_false(self, service):
        assert service.unsubscribe("nonexistent") is False

    def test_list_subscriptions(self, service):
        sub1 = WebhookSubscription(
            id="sub-1", url="https://example.com/1",
            secret="very-secure-secret-key-1234567890-abcdef",
        )
        sub2 = WebhookSubscription(
            id="sub-2", url="https://example.com/2",
            secret="very-secure-secret-key-1234567890-abcdef",
        )
        service.subscribe(sub1)
        service.subscribe(sub2)
        subs = service.list_subscriptions()
        assert len(subs) == 2


# ---------------------------------------------------------------------------
# Event Matching Tests
# ---------------------------------------------------------------------------


class TestEventMatching:
    def test_subscription_matches_specified_event(self, valid_subscription):
        assert valid_subscription.matches_event("DESIGN_COMPLETED") is True

    def test_subscription_doesnt_match_other_event(self, valid_subscription):
        assert valid_subscription.matches_event("ROOM_ANALYSIS_COMPLETED") is False

    def test_empty_event_types_matches_all(self):
        sub = WebhookSubscription(
            id="sub-1", url="https://example.com/hook",
            secret="very-secure-secret-key-1234567890-abcdef",
            event_types=[],  # empty = receive all
        )
        assert sub.matches_event("ANY_EVENT") is True

    def test_paused_subscription_doesnt_match(self):
        sub = WebhookSubscription(
            id="sub-1", url="https://example.com/hook",
            secret="very-secure-secret-key-1234567890-abcdef",
            status=WebhookStatus.PAUSED,
        )
        assert sub.matches_event("DESIGN_COMPLETED") is False

    def test_disabled_subscription_doesnt_match(self):
        sub = WebhookSubscription(
            id="sub-1", url="https://example.com/hook",
            secret="very-secure-secret-key-1234567890-abcdef",
            status=WebhookStatus.DISABLED,
        )
        assert sub.matches_event("DESIGN_COMPLETED") is False


# ---------------------------------------------------------------------------
# Event Publishing Tests
# ---------------------------------------------------------------------------


class TestEventPublishing:
    def test_publish_with_no_subscribers_returns_event_id(self, service):
        event_id = service.publish_event(
            event_type="DESIGN_COMPLETED",
            source="test",
            data={"room_id": "R-001"},
        )
        assert event_id is not None
        assert len(event_id) > 0

    def test_publish_to_matching_subscriber(self, service, valid_subscription):
        service.subscribe(valid_subscription)
        # Publishing will try to deliver but fail (example.com doesn't accept)
        # — that's OK, we're testing the routing, not the delivery
        event_id = service.publish_event(
            event_type="DESIGN_COMPLETED",
            source="test",
            data={"room_id": "R-001"},
        )
        assert event_id is not None
        # Check delivery history was recorded
        history = service.get_delivery_history()
        assert len(history) > 0

    def test_publish_skips_non_matching_subscribers(self, service):
        sub = WebhookSubscription(
            id="sub-1", url="https://example.com/hook",
            secret="very-secure-secret-key-1234567890-abcdef",
            event_types=["ROOM_ANALYSIS_COMPLETED"],  # different event
        )
        service.subscribe(sub)
        service.publish_event(
            event_type="DESIGN_COMPLETED",
            source="test",
            data={},
        )
        # No delivery attempts should be recorded
        history = service.get_delivery_history()
        assert len(history) == 0


# ---------------------------------------------------------------------------
# Delivery & Retry Tests
# ---------------------------------------------------------------------------


class TestDeliveryRetry:
    def test_failed_delivery_goes_to_dlq(self, service):
        """After max retries, failed deliveries go to dead-letter queue."""
        sub = WebhookSubscription(
            id="sub-1",
            url="https://nonexistent-domain-12345.invalid/hook",
            secret="very-secure-secret-key-1234567890-abcdef",
        )
        service.subscribe(sub)

        service.publish_event(
            event_type="DESIGN_COMPLETED",
            source="test",
            data={"room_id": "R-001"},
        )

        dlq = service.get_dead_letter_queue()
        assert len(dlq) > 0
        assert dlq[0].subscription_id == "sub-1"
        assert "error" in dlq[0].final_error.lower() or "urlerror" in dlq[0].final_error.lower()

    def test_delivery_history_recorded(self, service):
        sub = WebhookSubscription(
            id="sub-1",
            url="https://nonexistent-domain-12345.invalid/hook",
            secret="very-secure-secret-key-1234567890-abcdef",
        )
        service.subscribe(sub)
        service.publish_event(
            event_type="DESIGN_COMPLETED",
            source="test",
            data={},
        )
        history = service.get_delivery_history()
        assert len(history) > 0
        # Each attempt should be recorded
        for attempt in history:
            assert isinstance(attempt, WebhookDeliveryAttempt)
            assert attempt.status in (
                DeliveryStatus.SUCCESS, DeliveryStatus.FAILED,
                DeliveryStatus.RETRYING, DeliveryStatus.DEAD_LETTERED,
            )

    def test_clear_dlq(self, service):
        sub = WebhookSubscription(
            id="sub-1",
            url="https://nonexistent-domain-12345.invalid/hook",
            secret="very-secure-secret-key-1234567890-abcdef",
        )
        service.subscribe(sub)
        service.publish_event(
            event_type="DESIGN_COMPLETED",
            source="test",
            data={},
        )
        assert len(service.get_dead_letter_queue()) > 0
        cleared = service.clear_dead_letter_queue()
        assert cleared > 0
        assert len(service.get_dead_letter_queue()) == 0


# ---------------------------------------------------------------------------
# Event Types Tests
# ---------------------------------------------------------------------------


class TestEventTypes:
    def test_design_completed_in_standard_types(self):
        assert "DESIGN_COMPLETED" in WEBHOOK_EVENT_TYPES

    def test_generative_attempt_in_standard_types(self):
        assert "GENERATIVE_ATTEMPT" in WEBHOOK_EVENT_TYPES

    def test_compliance_violation_in_standard_types(self):
        assert "COMPLIANCE_VIOLATION_DETECTED" in WEBHOOK_EVENT_TYPES


# ---------------------------------------------------------------------------
# Security Tests
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_signature_verification_works(self):
        """Verify that HMAC signature can be recomputed and matches."""
        payload = b'{"event": "test"}'
        secret = "very-secure-secret-key-1234567890-abcdef"
        sig = compute_webhook_signature(payload, secret)

        # Receiver recomputes and compares
        recomputed = compute_webhook_signature(payload, secret)
        assert sig == recomputed

    def test_is_https_detection(self):
        https_sub = WebhookSubscription(
            id="sub-1", url="https://example.com",
            secret="very-secure-secret-key-1234567890-abcdef",
        )
        http_sub = WebhookSubscription(
            id="sub-2", url="http://example.com",
            secret="very-secure-secret-key-1234567890-abcdef",
        )
        assert https_sub.is_https() is True
        assert http_sub.is_https() is False


# ---------------------------------------------------------------------------
# Singleton Tests
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_webhook_service_returns_instance(self):
        from fireai.infrastructure.webhook_service import get_webhook_service
        service = get_webhook_service()
        assert service is not None
        assert isinstance(service, WebhookDeliveryService)

    def test_get_webhook_service_returns_same_instance(self):
        from fireai.infrastructure.webhook_service import get_webhook_service
        s1 = get_webhook_service()
        s2 = get_webhook_service()
        assert s1 is s2
