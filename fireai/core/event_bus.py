"""event_bus.py - FireAI Event Bus (Digital Twin Foundation)
=========================================================

Central pub/sub event bus for the FireAI engineering system.

This is the NERVE SYSTEM of the entire platform. Every module
communicates through this bus — no direct coupling between components.

CRITICAL SAFETY NOTE:
  This module is used by AnalysisPipeline, RoomLifecycle, and
  DigitalTwinInterface. If it fails, the ENTIRE system fails.
  Therefore:
  - No external dependencies (stdlib only)
  - Thread-safe by design
  - Exceptions in callbacks are SILENTLY CAUGHT — never crash the bus
  - All events are recorded for forensic replay

Design Principles:
  - Singleton pattern: one bus per process
  - Synchronous dispatch (no async/await — simpler, more predictable)
  - Event ordering is guaranteed within a thread
  - EventRecorder captures all events for audit replay

Usage:
    from fireai.core.event_bus import EventBus, Events, Event, EventRecorder

    bus = EventBus()  # or EventBus.instance() for singleton

    bus.subscribe(Events.ROOM_ANALYSIS_START, my_callback)
    bus.publish(Events.ROOM_ANALYSIS_START, {"room_id": "R-01"})
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# ===========================================================================
# Event Data Model
# ===========================================================================


@dataclass
class Event:
    """Immutable event object published on the bus.

    Every event carries:
      - event_type: The category/name of the event (from Events constants)
      - data: Arbitrary payload dictionary
      - source: Module that published the event
      - correlation_id: Links related events together
      - timestamp: When the event was created (monotonic for ordering)
      - event_id: Unique identifier for forensic tracing
    """

    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    correlation_id: str = ""
    timestamp: float = field(default_factory=time.monotonic)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _wall_clock_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def datetime_utc(self) -> str:
        """ISO 8601 UTC timestamp captured at event creation time."""
        return self._wall_clock_at

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for audit storage."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "data": self.data,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "datetime_utc": self._wall_clock_at,
        }


# ===========================================================================
# Event Type Constants
# ===========================================================================


class Events:
    """Central registry of all event type strings in the FireAI system.

    Using string constants (not enums) for maximum flexibility —
    external systems can publish custom event types without modifying
    this class. However, all KNOWN events are documented here.

    Categories:
      - Room analysis lifecycle
      - Detector placement
      - Verification & consensus
      - Proof certification
      - NFPA compliance
      - Building-level aggregation
      - Digital twin synchronization
      - Room lifecycle management
    """

    # ── Room Analysis ───────────────────────────────────────────────
    ROOM_ANALYSIS_START = "room.analysis.start"
    ROOM_ANALYSIS_COMPLETE = "room.analysis.complete"

    # ── Detector Placement ──────────────────────────────────────────
    DETECTOR_PLACED = "detector.placed"
    DETECTOR_REMOVED = "detector.removed"

    # ── Verification & Consensus ────────────────────────────────────
    CONSENSUS_RESULT = "consensus.result"
    COVERAGE_VERIFIED = "coverage.verified"
    COVERAGE_FAILED = "coverage.failed"

    # ── Proof Certification ─────────────────────────────────────────
    PROOF_CERTIFICATE_GENERATED = "proof.certificate.generated"

    # ── NFPA Compliance ─────────────────────────────────────────────
    NFPA_COMPLIANT = "nfpa.compliant"
    NFPA_VIOLATION = "nfpa.violation"

    # ── Building Level ──────────────────────────────────────────────
    BUILDING_ANALYSIS_START = "building.analysis.start"
    BUILDING_ANALYSIS_COMPLETE = "building.analysis.complete"

    # ── Digital Twin ────────────────────────────────────────────────
    MODEL_CHANGED = "model.changed"
    TWIN_SNAPSHOT = "twin.snapshot"
    TWIN_SYNC = "twin.sync"
    TWIN_CONFLICT = "twin.conflict"
    TWIN_DRIFT = "twin.drift"

    # ── Room Lifecycle ──────────────────────────────────────────────
    ROOM_LIFECYCLE_CHANGED = "room.lifecycle.changed"


# ===========================================================================
# Callback Type
# ===========================================================================

# Callbacks receive the Event object. Return value is ignored.
EventCallback = Callable[[Event], None]


__all__ = [
    "Event",
    "EventBus",
    "EventCallback",
    "EventRecorder",
    "Events",
]


# ===========================================================================
# EventRecorder
# ===========================================================================


class EventRecorder:
    """Records all events for forensic replay and debugging.

    Thread-safe. Stores events in memory (bounded) for audit trail
    reconstruction without requiring database access.

    SAFETY: This is NOT the legal audit trail (that's AuditStore).
    This is for operational debugging. The legal audit trail must
    go through AuditStore with hash chain + HMAC.
    """

    def __init__(self, max_events: int = 10_000):
        self._lock = threading.Lock()
        self._events: deque[Event] = deque(maxlen=max_events)
        self._max_events = max_events

    def record(self, event: Event) -> None:
        """Record an event (called automatically by EventBus).

        Uses collections.deque with maxlen for O(1) append
        and automatic oldest eviction — no manual slicing needed.
        """
        with self._lock:
            self._events.append(event)

    def get_events(
        self,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """Query recorded events with optional filters."""
        with self._lock:
            events = list(self._events)

        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]
        if source is not None:
            events = [e for e in events if e.source == source]
        if correlation_id is not None:
            events = [e for e in events if e.correlation_id == correlation_id]

        # Return the most recent `limit` events
        return events[-limit:] if limit < len(events) else events

    def count(self) -> int:
        """Number of recorded events."""
        with self._lock:
            return len(self._events)

    def clear(self) -> None:
        """Clear all recorded events (for testing only)."""
        with self._lock:
            self._events.clear()


# ===========================================================================
# EventBus
# ===========================================================================


class EventBus:
    """Central pub/sub event bus for the FireAI engineering system.

    Thread-safe. No external dependencies. Exception-safe.

    Design Decisions (with self-critique):
      - SYNCHRONOUS dispatch: We chose sync over async because:
        1. Predictable execution order (critical for safety)
        2. No event loop dependency
        3. Easier to reason about in safety-critical code
        CRITIQUE: This means slow callbacks block the publisher.
        MITIGATION: Callbacks should be fast (<10ms). Heavy work
        should be dispatched to a queue, not done in the callback.

      - SILENT exception handling: Callbacks that raise exceptions
        are caught and logged, never crashing the bus.
        CRITIQUE: This hides errors.
        MITIGATION: EventRecorder captures all events; monitoring
        should alert on errors.

      - No event prioritization: All events are equal.
        CRITIQUE: A TAMPER_DETECTED event should be higher priority
        than a ROOM_ANALYSIS_START event.
        MITIGATION: Subscribers can implement their own priority
        queue based on event_type.

    Usage:
        bus = EventBus()
        bus.subscribe(Events.ROOM_ANALYSIS_START, my_callback)
        bus.publish(Events.ROOM_ANALYSIS_START, {"room_id": "R-01"})

        # For singleton pattern (recommended):
        bus = EventBus.instance()
    """

    _instance: Optional[EventBus] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: Dict[str, List[EventCallback]] = {}
        self._recorder = EventRecorder()
        self._error_count = 0

    @classmethod
    def instance(cls) -> EventBus:
        """Get or create the singleton EventBus.

        Use this in production — ensures all modules share the same bus.
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing only).

        WARNING: Never call this in production. It disconnects
        all subscribers.
        """
        with cls._instance_lock:
            cls._instance = None

    # ── Subscribe ────────────────────────────────────────────────────

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: The event type string (use Events.* constants).
                Use "*" to subscribe to ALL events.
            callback: Function to call when event is published.
                Receives a single Event argument.

        SAFETY: If the same callback is registered twice for the same
        event type, it will be called twice. This is intentional —
        it's the caller's responsibility to manage subscriptions.

        """
        if not callable(callback):
            raise TypeError(f"callback must be callable, got {type(callback).__name__}")
        with self._lock:
            self._listeners.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: EventCallback) -> bool:
        """Remove a specific callback from an event type.

        Returns:
            True if the callback was found and removed, False otherwise.

        """
        with self._lock:
            cbs = self._listeners.get(event_type, [])
            if callback in cbs:
                cbs.remove(callback)
                return True
            return False

    # ── Publish ──────────────────────────────────────────────────────

    def publish(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        source: str = "",
        correlation_id: str = "",
    ) -> Event:
        """Publish an event to all subscribers.

        Args:
            event_type: The event type string (use Events.* constants).
            data: Optional payload dictionary.
            source: Module that published the event.
            correlation_id: Links related events together.

        Returns:
            The Event object that was published.

        SAFETY:
            - If no subscribers exist, the event is still recorded.
            - Exceptions in callbacks are caught and counted —
              the bus NEVER crashes due to a bad callback.
            - Dispatch order: specific subscribers first, then "*" subscribers.

        """
        event = Event(
            event_type=event_type,
            data=data or {},
            source=source,
            correlation_id=correlation_id,
        )

        # Record event (always, even if no subscribers)
        self._recorder.record(event)

        # Collect callbacks (thread-safe copy)
        with self._lock:
            specific = list(self._listeners.get(event_type, []))
            wildcard = list(self._listeners.get("*", []))

        # Dispatch — specific first, then wildcard
        for callback in specific + wildcard:
            try:
                callback(event)
            except Exception as exc:
                self._error_count += 1
                # Log the error — the bus must never crash, but
                # operators MUST know about subscriber failures.
                # In a safety-critical system, silent failures are
                # unacceptable. We catch to survive, but we log to inform.
                import logging as _logging

                _logging.getLogger(__name__).error(
                    "EventBus subscriber error on %s: %s: %s",
                    event_type,
                    type(exc).__name__,
                    exc,
                )

        return event

    # ── Query ────────────────────────────────────────────────────────

    @property
    def recorder(self) -> EventRecorder:
        """Access the event recorder for forensic replay."""
        return self._recorder

    @property
    def error_count(self) -> int:
        """Number of callback errors since creation."""
        return self._error_count

    def subscriber_count(self, event_type: Optional[str] = None) -> int:
        """Count subscribers for an event type, or total if None."""
        with self._lock:
            if event_type is None:
                return sum(len(cbs) for cbs in self._listeners.values())
            return len(self._listeners.get(event_type, []))


# ===========================================================================
# Self-Test (runs when module is executed directly)
# ===========================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("EventBus Self-Test")
    print("=" * 60)

    # Test 1: Basic pub/sub
    bus = EventBus()
    received: list[Any] = []
    bus.subscribe(Events.ROOM_ANALYSIS_START, lambda e: received.append(e))
    bus.publish(Events.ROOM_ANALYSIS_START, {"room_id": "R-01"})
    assert len(received) == 1, f"Expected 1 event, got {len(received)}"
    assert received[0].data["room_id"] == "R-01"
    print("  [PASS] Test 1: Basic pub/sub")

    # Test 2: Wildcard subscription
    all_events: list[Any] = []
    bus.subscribe("*", lambda e: all_events.append(e))
    bus.publish(Events.DETECTOR_PLACED, {"count": 5})
    bus.publish(Events.NFPA_COMPLIANT, {"ref": "NFPA 72"})
    assert len(all_events) == 2, f"Expected 2 wildcard events, got {len(all_events)}"
    print("  [PASS] Test 2: Wildcard subscription")

    # Test 3: Exception safety
    def bad_callback(e):
        raise RuntimeError("Deliberate error for testing")

    bus.subscribe(Events.NFPA_VIOLATION, bad_callback)
    bus.publish(Events.NFPA_VIOLATION, {"reason": "test"})
    assert bus.error_count == 1, "Error should be counted"
    print("  [PASS] Test 3: Exception safety (bus doesn't crash)")

    # Test 4: EventRecorder
    assert bus.recorder.count() == 4, f"Expected 4 recorded events, got {bus.recorder.count()}"
    recent = bus.recorder.get_events(event_type=Events.NFPA_VIOLATION, limit=1)
    assert len(recent) == 1
    print("  [PASS] Test 4: EventRecorder")

    # Test 5: Singleton pattern
    bus1 = EventBus.instance()
    bus2 = EventBus.instance()
    assert bus1 is bus2, "Singleton should return same instance"
    EventBus.reset()
    print("  [PASS] Test 5: Singleton pattern")

    # Test 6: Thread safety
    bus3 = EventBus()
    errors: list[Any] = []

    def publish_many():
        try:
            for i in range(50):
                bus3.publish(Events.ROOM_ANALYSIS_START, {"i": i})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=publish_many) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [], f"Thread errors: {errors}"
    assert bus3.recorder.count() == 200, f"Expected 200 events, got {bus3.recorder.count()}"
    print("  [PASS] Test 6: Thread safety (4 threads × 50 events)")

    # Test 7: Unsubscribe
    counter: list[int] = []
    def cb(e):
        return counter.append(1)
    bus3.subscribe(Events.COVERAGE_VERIFIED, cb)
    bus3.publish(Events.COVERAGE_VERIFIED, {})
    assert len(counter) == 1
    bus3.unsubscribe(Events.COVERAGE_VERIFIED, cb)
    bus3.publish(Events.COVERAGE_VERIFIED, {})
    assert len(counter) == 1, "Should not receive after unsubscribe"
    print("  [PASS] Test 7: Unsubscribe")

    print("=" * 60)
    print("ALL 7 TESTS PASSED")
    print("=" * 60)
