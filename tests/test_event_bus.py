"""
tests/test_event_bus.py
========================
Comprehensive test suite for fireai/core/event_bus.py

SAFETY CRITICAL: The event bus is the nerve system of FireAI. All modules
communicate through it. If it crashes, the ENTIRE system fails. Therefore:
  - Thread-safety must be guaranteed
  - Exceptions in callbacks must NEVER crash the bus
  - All events must be recorded for forensic replay

Key features tested:
  - Pub/sub pattern (subscribe, publish, unsubscribe)
  - Wildcard subscription ("*")
  - EventRecorder (record, query, count, clear)
  - Singleton pattern (instance, reset)
  - Thread safety (concurrent publish/subscribe)
  - Exception safety in callbacks
  - Event data model (Event dataclass)
  - Events constants
"""

from __future__ import annotations

import threading

import pytest

from fireai.core.event_bus import Event, EventBus, EventRecorder, Events

# ─────────────────────────────────────────────────────────────────────────────
# Event Data Model Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEvent:
    """Test Event dataclass."""

    def test_creation(self):
        e = Event(event_type="test.event", data={"key": "value"})
        assert e.event_type == "test.event"
        assert e.data == {"key": "value"}

    def test_default_data_empty_dict(self):
        e = Event(event_type="test")
        assert e.data == {}

    def test_event_id_unique(self):
        e1 = Event(event_type="test")
        e2 = Event(event_type="test")
        assert e1.event_id != e2.event_id

    def test_datetime_utc_set(self):
        e = Event(event_type="test")
        assert e.datetime_utc != ""

    def test_to_dict(self):
        e = Event(event_type="test.event", data={"x": 1}, source="module")
        d = e.to_dict()
        assert d["event_type"] == "test.event"
        assert d["data"] == {"x": 1}
        assert d["source"] == "module"
        assert "event_id" in d
        assert "timestamp" in d
        assert "datetime_utc" in d

    def test_source_default_empty(self):
        e = Event(event_type="test")
        assert e.source == ""

    def test_correlation_id_default_empty(self):
        e = Event(event_type="test")
        assert e.correlation_id == ""


# ─────────────────────────────────────────────────────────────────────────────
# Events Constants Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventsConstants:
    """Verify all documented event types exist."""

    def test_room_analysis_events(self):
        assert Events.ROOM_ANALYSIS_START == "room.analysis.start"
        assert Events.ROOM_ANALYSIS_COMPLETE == "room.analysis.complete"

    def test_detector_events(self):
        assert Events.DETECTOR_PLACED == "detector.placed"
        assert Events.DETECTOR_REMOVED == "detector.removed"

    def test_verification_events(self):
        assert Events.CONSENSUS_RESULT == "consensus.result"
        assert Events.COVERAGE_VERIFIED == "coverage.verified"
        assert Events.COVERAGE_FAILED == "coverage.failed"

    def test_proof_events(self):
        assert Events.PROOF_CERTIFICATE_GENERATED == "proof.certificate.generated"

    def test_nfpa_events(self):
        assert Events.NFPA_COMPLIANT == "nfpa.compliant"
        assert Events.NFPA_VIOLATION == "nfpa.violation"

    def test_building_events(self):
        assert Events.BUILDING_ANALYSIS_START == "building.analysis.start"
        assert Events.BUILDING_ANALYSIS_COMPLETE == "building.analysis.complete"

    def test_twin_events(self):
        assert Events.MODEL_CHANGED == "model.changed"
        assert Events.TWIN_SNAPSHOT == "twin.snapshot"
        assert Events.TWIN_SYNC == "twin.sync"
        assert Events.TWIN_CONFLICT == "twin.conflict"
        assert Events.TWIN_DRIFT == "twin.drift"

    def test_lifecycle_events(self):
        assert Events.ROOM_LIFECYCLE_CHANGED == "room.lifecycle.changed"


# ─────────────────────────────────────────────────────────────────────────────
# EventRecorder Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventRecorder:
    """Test EventRecorder for forensic replay."""

    def test_record_and_count(self):
        rec = EventRecorder()
        rec.record(Event(event_type="test"))
        assert rec.count() == 1

    def test_get_events_no_filter(self):
        rec = EventRecorder()
        rec.record(Event(event_type="a"))
        rec.record(Event(event_type="b"))
        events = rec.get_events()
        assert len(events) == 2

    def test_get_events_filter_by_type(self):
        rec = EventRecorder()
        rec.record(Event(event_type="type_a"))
        rec.record(Event(event_type="type_b"))
        rec.record(Event(event_type="type_a"))
        events = rec.get_events(event_type="type_a")
        assert len(events) == 2

    def test_get_events_filter_by_source(self):
        rec = EventRecorder()
        rec.record(Event(event_type="test", source="module1"))
        rec.record(Event(event_type="test", source="module2"))
        events = rec.get_events(source="module1")
        assert len(events) == 1

    def test_get_events_filter_by_correlation_id(self):
        rec = EventRecorder()
        rec.record(Event(event_type="test", correlation_id="corr-1"))
        rec.record(Event(event_type="test", correlation_id="corr-2"))
        events = rec.get_events(correlation_id="corr-1")
        assert len(events) == 1

    def test_get_events_limit(self):
        rec = EventRecorder()
        for i in range(10):
            rec.record(Event(event_type=f"test-{i}"))
        events = rec.get_events(limit=3)
        assert len(events) == 3

    def test_clear(self):
        rec = EventRecorder()
        rec.record(Event(event_type="test"))
        rec.record(Event(event_type="test2"))
        rec.clear()
        assert rec.count() == 0

    def test_max_events_eviction(self):
        """Deque with maxlen should evict oldest events."""
        rec = EventRecorder(max_events=5)
        for i in range(10):
            rec.record(Event(event_type=f"test-{i}"))
        assert rec.count() == 5
        # Only the last 5 should remain
        events = rec.get_events()
        types = [e.event_type for e in events]
        assert "test-9" in types

    def test_default_max_events(self):
        rec = EventRecorder()
        assert rec._max_events == 10_000


# ─────────────────────────────────────────────────────────────────────────────
# EventBus — Subscribe & Publish Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusSubscribePublish:
    """Test basic pub/sub functionality."""

    @pytest.fixture
    def bus(self):
        return EventBus()

    def test_subscribe_and_publish(self, bus):
        received = []
        bus.subscribe("test.event", lambda e: received.append(e))
        bus.publish("test.event", {"key": "val"})
        assert len(received) == 1
        assert received[0].data["key"] == "val"

    def test_publish_without_subscribers(self, bus):
        """Event should still be recorded even with no subscribers."""
        event = bus.publish("no.subscribers", {"data": 1})
        assert event.event_type == "no.subscribers"
        assert bus.recorder.count() == 1

    def test_multiple_subscribers(self, bus):
        """All subscribers for an event type should be called."""
        results = {"a": 0, "b": 0}
        bus.subscribe("test", lambda e: results.update(a=1))
        bus.subscribe("test", lambda e: results.update(b=1))
        bus.publish("test")
        assert results["a"] == 1
        assert results["b"] == 1

    def test_subscriber_receives_event_object(self, bus):
        received = []
        bus.subscribe("test", lambda e: received.append(e))
        bus.publish("test", {"x": 42}, source="test_module", correlation_id="corr-1")
        assert received[0].data == {"x": 42}
        assert received[0].source == "test_module"
        assert received[0].correlation_id == "corr-1"

    def test_subscribe_non_callable_raises(self, bus):
        with pytest.raises(TypeError, match="callable"):
            bus.subscribe("test", "not_a_function")

    def test_duplicate_subscription_calls_twice(self):
        """Same callback subscribed twice should be called twice."""
        bus = EventBus()
        counter = []
        def cb(e):
            return counter.append(1)
        bus.subscribe("test", cb)
        bus.subscribe("test", cb)  # Register again
        bus.publish("test")
        assert len(counter) == 2  # Called twice per design


# ─────────────────────────────────────────────────────────────────────────────
# EventBus — Wildcard Subscription Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusWildcard:
    def test_wildcard_receives_all_events(self):
        bus = EventBus()
        received = []
        bus.subscribe("*", lambda e: received.append(e.event_type))
        bus.publish("event.a")
        bus.publish("event.b")
        bus.publish("event.c")
        assert len(received) == 3
        assert "event.a" in received

    def test_specific_and_wildcard_both_called(self):
        """Specific subscribers called first, then wildcard."""
        bus = EventBus()
        order = []
        bus.subscribe("test", lambda e: order.append("specific"))
        bus.subscribe("*", lambda e: order.append("wildcard"))
        bus.publish("test")
        assert order == ["specific", "wildcard"]


# ─────────────────────────────────────────────────────────────────────────────
# EventBus — Unsubscribe Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusUnsubscribe:
    def test_unsubscribe_removes_callback(self):
        bus = EventBus()
        counter = []
        def cb(e):
            return counter.append(1)
        bus.subscribe("test", cb)
        bus.publish("test")
        assert len(counter) == 1

        result = bus.unsubscribe("test", cb)
        assert result is True
        bus.publish("test")
        assert len(counter) == 1  # No additional call

    def test_unsubscribe_nonexistent_callback_returns_false(self):
        bus = EventBus()
        def cb(e):
            return None
        result = bus.unsubscribe("test", cb)
        assert result is False

    def test_unsubscribe_from_wrong_event_type(self):
        bus = EventBus()
        def cb(e):
            return None
        bus.subscribe("event.a", cb)
        result = bus.unsubscribe("event.b", cb)
        assert result is False


# ─────────────────────────────────────────────────────────────────────────────
# EventBus — Exception Safety Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusExceptionSafety:
    def test_exception_in_callback_does_not_crash_bus(self):
        """SAFETY: Bus must NEVER crash due to a bad callback."""
        bus = EventBus()
        counter = []

        def bad_callback(e):
            raise RuntimeError("Deliberate test error")

        def good_callback(e):
            counter.append(1)

        bus.subscribe("test", bad_callback)
        bus.subscribe("test", good_callback)
        bus.publish("test")

        # Good callback should still have been called
        assert len(counter) == 1
        assert bus.error_count == 1

    def test_error_count_increments(self):
        bus = EventBus()

        def bad_cb(e):
            raise ValueError("test")

        bus.subscribe("test", bad_cb)
        bus.publish("test")
        bus.publish("test")
        assert bus.error_count == 2

    def test_wildcard_exception_does_not_crash(self):
        bus = EventBus()
        counter = []

        bus.subscribe("*", lambda e: 1 / 0)  # ZeroDivisionError
        bus.subscribe("test", lambda e: counter.append(1))
        bus.publish("test")
        assert len(counter) == 1  # Specific callback still called


# ─────────────────────────────────────────────────────────────────────────────
# EventBus — Singleton Pattern Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusSingleton:
    def test_instance_returns_same_object(self):
        EventBus.reset()
        bus1 = EventBus.instance()
        bus2 = EventBus.instance()
        assert bus1 is bus2
        EventBus.reset()

    def test_reset_creates_new_instance(self):
        EventBus.reset()
        bus1 = EventBus.instance()
        EventBus.reset()
        bus2 = EventBus.instance()
        assert bus1 is not bus2
        EventBus.reset()


# ─────────────────────────────────────────────────────────────────────────────
# EventBus — Subscriber Count Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusSubscriberCount:
    def test_subscriber_count_specific(self):
        bus = EventBus()
        bus.subscribe("test", lambda e: None)
        bus.subscribe("test", lambda e: None)
        assert bus.subscriber_count("test") == 2

    def test_subscriber_count_total(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.subscribe("b", lambda e: None)
        assert bus.subscriber_count() == 3

    def test_subscriber_count_nonexistent(self):
        bus = EventBus()
        assert bus.subscriber_count("nonexistent") == 0


# ─────────────────────────────────────────────────────────────────────────────
# EventBus — Thread Safety Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusThreadSafety:
    def test_concurrent_publish(self):
        """Multiple threads publishing should not lose events."""
        bus = EventBus()
        errors = []

        def publish_many():
            try:
                for i in range(50):
                    bus.publish(Events.ROOM_ANALYSIS_START, {"i": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=publish_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert bus.recorder.count() == 200

    def test_concurrent_subscribe_and_publish(self):
        """Subscribing while publishing should not crash."""
        bus = EventBus()
        errors = []
        received = []

        def subscribe_and_publish():
            try:
                for i in range(25):
                    local_i = i
                    def cb(e, idx=local_i):
                        return received.append(idx)
                    bus.subscribe(f"event-{local_i}", cb)
                    bus.publish(f"event-{local_i}", {"idx": local_i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=subscribe_and_publish) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ─────────────────────────────────────────────────────────────────────────────
# EventBus — Recorder Integration Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusRecorderIntegration:
    def test_all_published_events_recorded(self):
        bus = EventBus()
        bus.publish("event.a", {"x": 1})
        bus.publish("event.b", {"y": 2})
        assert bus.recorder.count() == 2

    def test_recorder_accessible(self):
        bus = EventBus()
        assert isinstance(bus.recorder, EventRecorder)

    def test_recorder_query_by_event_type(self):
        bus = EventBus()
        bus.publish("type_a")
        bus.publish("type_b")
        bus.publish("type_a")
        events = bus.recorder.get_events(event_type="type_a")
        assert len(events) == 2


# ─────────────────────────────────────────────────────────────────────────────
# EventBus — Edge Cases
# ─────────────────────────────────────────────────────────────────────────────


class TestEventBusEdgeCases:
    def test_publish_returns_event(self):
        bus = EventBus()
        event = bus.publish("test", {"data": 1}, source="mod")
        assert isinstance(event, Event)
        assert event.event_type == "test"
        assert event.data == {"data": 1}
        assert event.source == "mod"

    def test_publish_with_none_data(self):
        bus = EventBus()
        event = bus.publish("test", None)
        assert event.data == {}

    def test_empty_event_type(self):
        """Empty string event type should work (though not recommended)."""
        bus = EventBus()
        received = []
        bus.subscribe("", lambda e: received.append(e))
        bus.publish("")
        assert len(received) == 1

    def test_custom_event_type(self):
        """Custom event types (not in Events) should work."""
        bus = EventBus()
        received = []
        bus.subscribe("custom.event.type", lambda e: received.append(e))
        bus.publish("custom.event.type")
        assert len(received) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
