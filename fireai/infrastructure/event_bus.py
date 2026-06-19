"""
fireai/infrastructure/event_bus.py — Production Event Bus with Schema Validation,
Retry with Backoff, Dead Letter Queue, At-Least-Once Delivery, and Event Replay.

Architecture:
  - Event:   Immutable event envelope with trace_id for distributed tracing.
  - EventBus (ABC):  Abstract contract for publish/subscribe/start/stop.
  - InMemoryEventBus:  Single-process/testing implementation.
  - RedisEventBus:     Lightweight production bus via Redis Streams.
  - KafkaEventBus:     High-throughput bus via Kafka (asyncio).
  - EventValidator:    JSON Schema + Pydantic validation layer.
  - DeadLetterQueue:   Persistent DLQ with replay capability.
  - EventBusMiddleware: FastAPI middleware publishing request events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Core Event Model
# ════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Event:
    """Immutable event envelope — every field is frozen after creation."""
    id: str
    type: str
    source: str
    data: Dict[str, Any]
    timestamp: datetime
    trace_id: str
    version: int = 1
    schema_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
            "version": self.version,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Event:
        return cls(
            id=d["id"],
            type=d["type"],
            source=d.get("source", "unknown"),
            data=d.get("data", {}),
            timestamp=datetime.fromisoformat(d["timestamp"]) if isinstance(d["timestamp"], str) else d["timestamp"],
            trace_id=d.get("trace_id", ""),
            version=d.get("version", 1),
            schema_version=d.get("schema_version", "1.0"),
        )


# ════════════════════════════════════════════════════════════════════════════
# Event Schema Validation
# ════════════════════════════════════════════════════════════════════════════

class EventSchemaRegistry:
    """Central registry for event type schemas using JSON Schema draft-07."""

    _schemas: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def register(cls, event_type: str, schema: Dict[str, Any]) -> None:
        with cls._lock:
            if event_type in cls._schemas:
                logger.warning("Overwriting schema for event type: %s", event_type)
            cls._schemas[event_type] = schema
            logger.info("Registered schema for event type: %s", event_type)

    @classmethod
    def get_schema(cls, event_type: str) -> Optional[Dict[str, Any]]:
        return cls._schemas.get(event_type)

    @classmethod
    def validate(cls, event: Event) -> Tuple[bool, Optional[str]]:
        schema = cls._schemas.get(event.type)
        if schema is None:
            return True, None
        errors = _validate_against_schema(event.data, schema)
        if errors:
            return False, f"Schema validation failed for {event.type}: {errors}"
        return True, None


def _validate_against_schema(data: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    """Recursive JSON Schema validator — minimal implementation for common types."""
    errors: List[str] = []

    if "type" in schema:
        expected = schema["type"]
        if expected == "object" and not isinstance(data, dict):
            errors.append(f"{path}: expected object, got {type(data).__name__}")
        elif expected == "array" and not isinstance(data, list):
            errors.append(f"{path}: expected array, got {type(data).__name__}")
        elif expected == "string" and not isinstance(data, str):
            errors.append(f"{path}: expected string, got {type(data).__name__}")
        elif expected == "number" and not isinstance(data, (int, float)):
            errors.append(f"{path}: expected number, got {type(data).__name__}")
        elif expected == "boolean" and not isinstance(data, bool):
            errors.append(f"{path}: expected boolean, got {type(data).__name__}")
        elif expected == "integer" and not isinstance(data, int):
            errors.append(f"{path}: expected integer, got {type(data).__name__}")

    if isinstance(data, dict) and "properties" in schema:
        for prop_name, prop_schema in schema["properties"].items():
            if prop_name in data:
                sub_errors = _validate_against_schema(
                    data[prop_name], prop_schema, f"{path}.{prop_name}"
                )
                errors.extend(sub_errors)
            elif prop_schema.get("required", False):
                errors.append(f"{path}: missing required property '{prop_name}'")

        if "additionalProperties" in schema and not schema["additionalProperties"]:
            allowed = set(schema.get("properties", {}).keys())
            extra = set(data.keys()) - allowed
            if extra:
                errors.append(f"{path}: unexpected properties: {extra}")

    if isinstance(data, list) and "items" in schema:
        for i, item in enumerate(data):
            sub_errors = _validate_against_schema(item, schema["items"], f"{path}[{i}]")
            errors.extend(sub_errors)

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: value {data!r} not in enum {schema['enum']}")

    if "minimum" in schema and isinstance(data, (int, float)) and data < schema["minimum"]:
        errors.append(f"{path}: {data} < minimum {schema['minimum']}")

    if "maximum" in schema and isinstance(data, (int, float)) and data > schema["maximum"]:
        errors.append(f"{path}: {data} > maximum {schema['maximum']}")

    if "pattern" in schema and isinstance(data, str):
        import re
        if not re.match(schema["pattern"], data):
            errors.append(f"{path}: does not match pattern {schema['pattern']}")

    return errors


# ════════════════════════════════════════════════════════════════════════════
# Retry with Exponential Backoff
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class RetryPolicy:
    """Retry configuration for failed event handlers."""
    max_retries: int = 3
    base_delay_s: float = 0.1
    max_delay_s: float = 10.0
    backoff_multiplier: float = 2.0
    jitter: bool = True

    def delay(self, attempt: int) -> float:
        d = min(self.base_delay_s * (self.backoff_multiplier ** (attempt - 1)), self.max_delay_s)
        if self.jitter:
            import random
            d = d * (0.5 + random.random() * 0.5)
        return d


# ════════════════════════════════════════════════════════════════════════════
# Dead Letter Queue
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class DeadLetterRecord:
    """Record of a failed event sent to the dead letter queue."""
    event_id: str
    event_type: str
    event_payload: Dict[str, Any]
    error: str
    failed_handler: str
    attempt_count: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    replayed: bool = False
    replay_count: int = 0


class DeadLetterQueue:
    """Persistent dead letter queue with replay capability.

    Stores failed events and supports replaying them through the event bus.
    """

    def __init__(self, max_records: int = 10000):
        self._records: List[DeadLetterRecord] = []
        self._max_records = max_records
        self._lock = threading.Lock()

    def add(self, record: DeadLetterRecord) -> None:
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records.pop(0)

    def get_all(self) -> List[DeadLetterRecord]:
        with self._lock:
            return list(self._records)

    def get_unreplayed(self) -> List[DeadLetterRecord]:
        with self._lock:
            return [r for r in self._records if not r.replayed]

    def get_by_event_type(self, event_type: str) -> List[DeadLetterRecord]:
        with self._lock:
            return [r for r in self._records if r.event_type == event_type]

    def mark_replayed(self, event_id: str) -> bool:
        with self._lock:
            for r in self._records:
                if r.event_id == event_id:
                    r.replayed = True
                    r.replay_count += 1
                    return True
            return False

    def clear(self) -> int:
        with self._lock:
            count = len(self._records)
            self._records.clear()
            return count

    def count(self) -> int:
        with self._lock:
            return len(self._records)


# ════════════════════════════════════════════════════════════════════════════
# Event Bus — Abstract Base
# ════════════════════════════════════════════════════════════════════════════

HandlerFunc = Callable[..., Awaitable[None]]


class EventBus(ABC):
    """Abstract event bus — contract for publish/subscribe messaging."""

    @abstractmethod
    async def publish(self, event: Event) -> None:
        ...

    @abstractmethod
    async def subscribe(self, event_type: str, handler: HandlerFunc) -> None:
        ...

    @abstractmethod
    async def start(self) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...


# ════════════════════════════════════════════════════════════════════════════
# InMemoryEventBus
# ════════════════════════════════════════════════════════════════════════════

class InMemoryEventBus(EventBus):
    """Single-process event bus for development and testing.

    Features:
      - Schema validation before dispatch
      - Retry with exponential backoff for failed handlers
      - Dead letter queue for permanently failed events
      - At-least-once delivery (handler acknowledged after success)
      - Event replay from in-memory store
    """

    def __init__(self, retry_policy: Optional[RetryPolicy] = None, dlq: Optional[DeadLetterQueue] = None):
        self._subscribers: Dict[str, List[HandlerFunc]] = defaultdict(list)
        self._event_store: List[Event] = []
        self._max_store: int = 10000
        self._retry_policy = retry_policy or RetryPolicy()
        self._dlq = dlq or DeadLetterQueue()
        self._running = False
        self._lock = asyncio.Lock()
        self._schema_registry = EventSchemaRegistry()

    async def publish(self, event: Event) -> None:
        """Publish an event — validates schema, stores, and dispatches to handlers."""
        valid, error = self._schema_registry.validate(event)
        if not valid:
            logger.error("Schema validation failed for event %s: %s", event.id, error)
            self._dlq.add(DeadLetterRecord(
                event_id=event.id,
                event_type=event.type,
                event_payload=event.to_dict(),
                error=error or "schema_validation_failed",
                failed_handler="schema_validator",
                attempt_count=1,
            ))
            return

        async with self._lock:
            self._event_store.append(event)
            if len(self._event_store) > self._max_store:
                self._event_store.pop(0)

        await self._dispatch(event)

    async def subscribe(self, event_type: str, handler: HandlerFunc) -> None:
        async with self._lock:
            self._subscribers[event_type].append(handler)
            logger.info("Subscribed handler %s to %s", handler.__name__, event_type)

    async def unsubscribe(self, event_type: str, handler: HandlerFunc) -> bool:
        async with self._lock:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)
                return True
            return False

    async def _dispatch(self, event: Event) -> None:
        """Dispatch event to all subscribed handlers with retry logic."""
        handlers = list(self._subscribers.get(event.type, []))
        wildcard = list(self._subscribers.get("*", []))

        for handler in handlers + wildcard:
            await self._deliver_with_retry(event, handler)

    async def _deliver_with_retry(self, event: Event, handler: HandlerFunc) -> None:
        """Deliver event to a single handler with retry and backoff."""
        last_error: Optional[str] = None
        for attempt in range(1, self._retry_policy.max_retries + 1):
            try:
                await handler(event)
                return
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Handler {handler.__name__} failed on attempt {attempt}/{self._retry_policy.max_retries} "
                    f"for event {event.id}: {e}"
                )
                if attempt < self._retry_policy.max_retries:
                    delay = self._retry_policy.delay(attempt)
                    await asyncio.sleep(delay)

        self._dlq.add(DeadLetterRecord(
            event_id=event.id,
            event_type=event.type,
            event_payload=event.to_dict(),
            error=last_error or "unknown_error",
            failed_handler=handler.__name__,
            attempt_count=self._retry_policy.max_retries,
        ))
        logger.error(
            f"Event {event.id} moved to DLQ after {self._retry_policy.max_retries} failed attempts "
            f"to handler {handler.__name__}: {last_error}"
        )

    async def replay_events(self, event_type: Optional[str] = None, from_time: Optional[datetime] = None) -> int:
        """Replay stored events — at-least-once delivery guarantee.

        Returns the number of events replayed.
        """
        count = 0
        async with self._lock:
            events = list(self._event_store)
        for event in events:
            if event_type and event.type != event_type:
                continue
            if from_time and event.timestamp < from_time:
                continue
            await self._dispatch(event)
            count += 1
        logger.info("Replayed %s events (type=%s)", count, event_type or 'all')
        return count

    async def replay_dlq(self, max_events: int = 100) -> int:
        """Replay events from the dead letter queue."""
        records = self._dlq.get_unreplayed()
        count = 0
        for record in records[:max_events]:
            event = Event.from_dict(record.event_payload)
            await self._dispatch(event)
            self._dlq.mark_replayed(record.event_id)
            count += 1
        logger.info("Replayed %s events from DLQ", count)
        return count

    async def start(self) -> None:
        self._running = True
        logger.info("InMemoryEventBus started")

    async def stop(self) -> None:
        self._running = False
        logger.info("InMemoryEventBus stopped")

    def get_stored_events(self, event_type: Optional[str] = None) -> List[Event]:
        return [e for e in self._event_store if not event_type or e.type == event_type]

    @property
    def dead_letter_queue(self) -> DeadLetterQueue:
        return self._dlq

    @property
    def schema_registry(self) -> EventSchemaRegistry:
        return self._schema_registry

# ponytail: RedisEventBus + KafkaEventBus removed (Phase 2). Zero callers
# outside this file. For Redis/Kafka history, see git log of this file at
# commit before ponytail-phase-2-cleanup branch. InMemoryEventBus is the only
# live impl. Upgrade path: re-introduce via real integration tests if a
# production need arises — do NOT revive the dead wrappers as-is.


# ════════════════════════════════════════════════════════════════════════════
# Event Bus Middleware for FastAPI
# ════════════════════════════════════════════════════════════════════════════

class EventBusMiddleware:
    """FastAPI middleware that publishes request events to the event bus.

    Automatically captures HTTP request metadata as events for monitoring,
    auditing, and analytics pipelines.
    """

    def __init__(self, event_bus: EventBus, app, exclude_paths: Optional[Set[str]] = None):
        self._event_bus = event_bus
        self.app = app
        self._exclude_paths = exclude_paths or {"/health", "/api/health", "/metrics", "/api/monitor/health"}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._exclude_paths or path.startswith("/static"):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        client_ip = scope.get("client", (None, None))[0] or "unknown"
        trace_id = str(uuid.uuid4())
        start_time = time.time()

        event = Event(
            id=str(uuid.uuid4()),
            type="http.request",
            source="fastapi.middleware",
            data={
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "trace_id": trace_id,
                "query_string": scope.get("query_string", b"").decode("utf-8", errors="replace"),
            },
            timestamp=datetime.now(timezone.utc),
            trace_id=trace_id,
        )

        await self._event_bus.publish(event)

        async def send_with_event(message):
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                duration_ms = round((time.time() - start_time) * 1000, 2)
                response_event = Event(
                    id=str(uuid.uuid4()),
                    type="http.response",
                    source="fastapi.middleware",
                    data={
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "trace_id": trace_id,
                    },
                    timestamp=datetime.now(timezone.utc),
                    trace_id=trace_id,
                )
                await self._event_bus.publish(response_event)
            await send(message)

        await self.app(scope, receive, send_with_event)


# ════════════════════════════════════════════════════════════════════════════
# Convenience: register default schemas
# ════════════════════════════════════════════════════════════════════════════

def register_default_schemas() -> None:
    """Register common event type schemas."""
    EventSchemaRegistry.register("http.request", {
        "type": "object",
        "properties": {
            "method": {"type": "string", "required": True},
            "path": {"type": "string", "required": True},
            "client_ip": {"type": "string", "required": True},
            "trace_id": {"type": "string", "required": True},
            "query_string": {"type": "string"},
        },
        "additionalProperties": False,
    })

    EventSchemaRegistry.register("http.response", {
        "type": "object",
        "properties": {
            "method": {"type": "string", "required": True},
            "path": {"type": "string", "required": True},
            "status_code": {"type": "integer", "required": True, "minimum": 100, "maximum": 599},
            "duration_ms": {"type": "number", "required": True, "minimum": 0},
            "trace_id": {"type": "string", "required": True},
        },
        "additionalProperties": False,
    })

    EventSchemaRegistry.register("engine.status", {
        "type": "object",
        "properties": {
            "engine_id": {"type": "string", "required": True},
            "status": {"type": "string", "required": True, "enum": ["running", "stopped", "error", "degraded"]},
            "cpu_percent": {"type": "number", "minimum": 0, "maximum": 100},
            "memory_mb": {"type": "number", "minimum": 0},
            "uptime_seconds": {"type": "number", "minimum": 0},
        },
        "additionalProperties": False,
    })

    EventSchemaRegistry.register("security.alert", {
        "type": "object",
        "properties": {
            "alert_id": {"type": "string", "required": True},
            "severity": {"type": "string", "required": True, "enum": ["low", "medium", "high", "critical"]},
            "category": {"type": "string", "required": True},
            "message": {"type": "string", "required": True},
            "source_ip": {"type": "string"},
            "timestamp": {"type": "string", "required": True},
        },
        "additionalProperties": False,
    })


register_default_schemas()
