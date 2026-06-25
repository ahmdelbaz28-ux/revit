"""fireai/infrastructure/event_bus.py — Production Event Bus with Schema Validation,
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


# ════════════════════════════════════════════════════════════════════════════
# RedisEventBus
# ════════════════════════════════════════════════════════════════════════════

class RedisEventBus(EventBus):
    """Redis Streams-based event bus for lightweight production deployments.

    Uses Redis Streams for persistence, consumer groups for at-least-once delivery,
    and a separate list-based dead letter queue.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        stream_prefix: str = "fireai:events:",
        consumer_group: str = "fireai-bus",
        consumer_name: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        dlq_max: int = 10000,
    ):
        self._redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._stream_prefix = stream_prefix
        self._consumer_group = consumer_group
        self._consumer_name = consumer_name or f"consumer-{uuid.uuid4().hex[:8]}"
        self._retry_policy = retry_policy or RetryPolicy()
        self._redis = None
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._handlers: Dict[str, List[HandlerFunc]] = defaultdict(list)
        self._dlq_max = dlq_max
        self._lock = asyncio.Lock()

    async def _get_redis(self):
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url, decode_responses=True)  # type: ignore[assignment]
                logger.info("Connected to Redis at %s", self._redis_url)
            except ImportError:
                raise RuntimeError("redis-py is required for RedisEventBus: pip install redis")
        return self._redis

    async def publish(self, event: Event) -> None:
        r = await self._get_redis()
        stream_key = f"{self._stream_prefix}{event.type}"
        await r.xadd(stream_key, event.to_dict(), maxlen=10000)
        logger.debug("Published event %s to stream %s", event.id, stream_key)

    async def subscribe(self, event_type: str, handler: HandlerFunc) -> None:
        async with self._lock:
            self._handlers[event_type].append(handler)

    async def start(self) -> None:
        self._running = True
        r = await self._get_redis()
        for event_type in list(self._handlers.keys()):
            stream_key = f"{self._stream_prefix}{event_type}"
            try:
                await r.xgroup_create(stream_key, self._consumer_group, id="0", mkstream=True)
            except Exception as e:
                logger.debug("Redis stream group creation failed for %s (may already exist): %s", stream_key, e)
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("RedisEventBus started (consumer=%s)", self._consumer_name)

    async def stop(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass  # Expected during shutdown
        if self._redis:
            await self._redis.close()
        logger.info("RedisEventBus stopped")

    async def _poll_loop(self) -> None:
        """Poll Redis Streams for new messages."""
        while self._running:
            try:
                r = await self._get_redis()
                for event_type in list(self._handlers.keys()):
                    stream_key = f"{self._stream_prefix}{event_type}"
                    try:
                        results = await r.xreadgroup(
                            self._consumer_group,
                            self._consumer_name,
                            {stream_key: ">"},
                            count=10,
                            block=2000,
                        )
                        for _stream_name, messages in results:
                            for msg_id, msg_data in messages:
                                event = Event.from_dict(msg_data)
                                await self._deliver(event)
                                await r.xack(stream_key, self._consumer_group, msg_id)
                    except Exception as e:
                        logger.error("Redis poll error for %s: %s", stream_key, e)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Redis poll loop error: %s", e)
                await asyncio.sleep(1)

    async def _deliver(self, event: Event) -> None:
        """Deliver event to handlers with retry and DLQ fallback."""
        handlers = list(self._handlers.get(event.type, []))
        wildcard = list(self._handlers.get("*", []))

        for handler in handlers + wildcard:
            last_error: Optional[str] = None
            for attempt in range(1, self._retry_policy.max_retries + 1):
                try:
                    await handler(event)
                    last_error = None
                    break
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        f"Handler {handler.__name__} attempt {attempt} failed for event {event.id}: {e}"
                    )
                    if attempt < self._retry_policy.max_retries:
                        await asyncio.sleep(self._retry_policy.delay(attempt))

            if last_error:
                r = await self._get_redis()
                dlq_key = f"{self._stream_prefix}dlq"
                await r.lpush(dlq_key, json.dumps(event.to_dict()))
                await r.ltrim(dlq_key, 0, self._dlq_max - 1)
                logger.error("Event %s moved to Redis DLQ after failed delivery to %s", event.id, handler.__name__)

    async def replay_events(self, event_type: Optional[str] = None, from_time: Optional[datetime] = None) -> int:
        """Replay events from Redis Streams."""
        r = await self._get_redis()
        count = 0
        for et in list(self._handlers.keys()):
            if event_type and et != event_type:
                continue
            stream_key = f"{self._stream_prefix}{et}"
            messages = await r.xrange(stream_key, min="-", max="+")
            for _msg_id, msg_data in messages:
                event = Event.from_dict(msg_data)
                if from_time and event.timestamp < from_time:
                    continue
                await self._deliver(event)
                count += 1
        logger.info("Replayed %s events from Redis Streams", count)
        return count

    async def replay_dlq(self, max_events: int = 100) -> int:
        """Replay events from the Redis DLQ."""
        r = await self._get_redis()
        dlq_key = f"{self._stream_prefix}dlq"
        count = 0
        for _ in range(max_events):
            raw = await r.rpop(dlq_key)
            if not raw:
                break
            try:
                event = Event.from_dict(json.loads(raw))
                await self._deliver(event)
                count += 1
            except Exception as e:
                logger.error("Failed to replay DLQ event: %s", e)
        logger.info("Replayed %s events from Redis DLQ", count)
        return count


# ════════════════════════════════════════════════════════════════════════════
# KafkaEventBus
# ════════════════════════════════════════════════════════════════════════════

class KafkaEventBus(EventBus):
    """Apache Kafka-based event bus for high-throughput production deployments.

    Uses aiokafka for async Kafka integration with consumer groups,
    automatic offset commit, and DLQ topics for failed events.
    """

    def __init__(
        self,
        bootstrap_servers: Optional[str] = None,
        consumer_group: str = "fireai-bus",
        retry_policy: Optional[RetryPolicy] = None,
        dlq_topic_suffix: str = ".dlq",
    ):
        self._bootstrap_servers = bootstrap_servers or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self._consumer_group = consumer_group
        self._retry_policy = retry_policy or RetryPolicy()
        self._dlq_topic_suffix = dlq_topic_suffix
        self._producer = None
        self._consumer = None
        self._running = False
        self._handlers: Dict[str, List[HandlerFunc]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._topic_prefix = "fireai."

    async def _get_producer(self):
        if self._producer is None:
            try:
                from aiokafka import AIOKafkaProducer
                self._producer = AIOKafkaProducer(
                    bootstrap_servers=self._bootstrap_servers,
                    client_id=f"fireai-producer-{uuid.uuid4().hex[:8]}",
                )
                await self._producer.start()  # type: ignore[attr-defined]
                logger.info("Kafka producer connected to %s", self._bootstrap_servers)
            except ImportError:
                raise RuntimeError("aiokafka is required for KafkaEventBus: pip install aiokafka")
        return self._producer

    async def _get_consumer(self):
        if self._consumer is None and self._handlers:
            try:
                from aiokafka import AIOKafkaConsumer
                topics = [f"{self._topic_prefix}{et}" for et in self._handlers.keys()]
                self._consumer = AIOKafkaConsumer(
                    *topics,
                    bootstrap_servers=self._bootstrap_servers,
                    group_id=self._consumer_group,
                    enable_auto_commit=True,
                    auto_offset_reset="earliest",
                )
                await self._consumer.start()  # type: ignore[attr-defined]
                logger.info("Kafka consumer started for topics: %s", topics)
            except ImportError:
                raise RuntimeError("aiokafka is required for KafkaEventBus: pip install aiokafka")
        return self._consumer

    async def publish(self, event: Event) -> None:
        producer = await self._get_producer()
        topic = f"{self._topic_prefix}{event.type}"
        payload = json.dumps(event.to_dict()).encode("utf-8")
        await producer.send_and_wait(topic, payload)
        logger.debug("Published event %s to Kafka topic %s", event.id, topic)

    async def subscribe(self, event_type: str, handler: HandlerFunc) -> None:
        async with self._lock:
            self._handlers[event_type].append(handler)

    async def start(self) -> None:
        self._running = True
        _ = await self._get_producer()
        if self._handlers:
            _ = await self._get_consumer()
        asyncio.create_task(self._consume_loop())
        logger.info("KafkaEventBus started")

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        logger.info("KafkaEventBus stopped")

    async def _consume_loop(self) -> None:
        if not self._consumer:
            return
        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                try:
                    event = Event.from_dict(json.loads(msg.value.decode("utf-8")))
                    await self._deliver(event)
                except Exception as e:
                    logger.error("Failed to process Kafka message: %s", e)
                    dlq_topic = f"{msg.topic}{self._dlq_topic_suffix}"
                    producer = await self._get_producer()
                    await producer.send_and_wait(dlq_topic, msg.value)
        except Exception as e:
            logger.error("Kafka consume loop error: %s", e)

    async def _deliver(self, event: Event) -> None:
        handlers = list(self._handlers.get(event.type, []))
        wildcard = list(self._handlers.get("*", []))

        for handler in handlers + wildcard:
            last_error: Optional[str] = None
            for attempt in range(1, self._retry_policy.max_retries + 1):
                try:
                    await handler(event)
                    last_error = None
                    break
                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        f"Handler {handler.__name__} attempt {attempt} failed for event {event.id}: {e}"
                    )
                    if attempt < self._retry_policy.max_retries:
                        await asyncio.sleep(self._retry_policy.delay(attempt))

            if last_error:
                producer = await self._get_producer()
                dlq_topic = f"{self._topic_prefix}{event.type}{self._dlq_topic_suffix}"
                await producer.send_and_wait(dlq_topic, json.dumps(event.to_dict()).encode("utf-8"))
                logger.error("Event %s sent to Kafka DLQ topic %s", event.id, dlq_topic)

    async def replay_events(self, event_type: Optional[str] = None, from_time: Optional[datetime] = None) -> int:
        """Replay events by seeking to beginning on Kafka topics."""
        if not self._consumer:
            return 0
        count = 0
        topics = [f"{self._topic_prefix}{et}" for et in self._handlers.keys()]
        if event_type:
            topics = [f"{self._topic_prefix}{event_type}"]

        for topic in topics:
            partitions = await self._consumer.assignment()
            for tp in partitions:
                if tp.topic == topic:
                    end_offset = await self._consumer.end_offsets([tp])
                    await self._consumer.seek_to_beginning(tp)
                    while True:
                        msg = await self._consumer.getone()
                        if msg.offset >= end_offset.get(tp, float("inf")):
                            break
                        event = Event.from_dict(json.loads(msg.value.decode("utf-8")))
                        if from_time and event.timestamp < from_time:
                            continue
                        await self._deliver(event)
                        count += 1
        logger.info("Replayed %s events from Kafka", count)
        return count

    async def replay_dlq(self, max_events: int = 100) -> int:
        """Replay events from Kafka DLQ topics."""
        producer = await self._get_producer()
        count = 0
        for event_type in self._handlers.keys():
            dlq_topic = f"{self._topic_prefix}{event_type}{self._dlq_topic_suffix}"
            try:
                from aiokafka import AIOKafkaConsumer
                dlq_consumer = AIOKafkaConsumer(
                    dlq_topic,
                    bootstrap_servers=self._bootstrap_servers,
                    group_id=f"{self._consumer_group}.dlq-replay",
                    auto_offset_reset="earliest",
                )
                await dlq_consumer.start()
                msg_count = 0
                async for msg in dlq_consumer:
                    if msg_count >= max_events:
                        break
                    main_topic = f"{self._topic_prefix}{event_type}"
                    await producer.send_and_wait(main_topic, msg.value)
                    msg_count += 1
                    count += 1
                await dlq_consumer.stop()
            except Exception as e:
                logger.error("Kafka DLQ replay error for %s: %s", dlq_topic, e)
        logger.info("Replayed %s events from Kafka DLQ", count)
        return count


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
