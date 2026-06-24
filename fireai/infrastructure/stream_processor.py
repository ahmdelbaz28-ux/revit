"""fireai/infrastructure/stream_processor.py — Stream Processor with
Transform/Filter/Sink Pipeline, Windowed Aggregations (1min, 5min, 1h),
and Throttled Output (max 1 event per window per key).

Architecture:
  - StreamProcessor:       Core class — add transforms, filters, sinks.
  - WindowedAggregator:     Sliding window aggregation (1min, 5min, 1h).
  - ThrottledOutput:       Ensures max 1 event per window per key.
  - process():            Runs the full pipeline for each event.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fireai.infrastructure.event_bus import Event

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Sliding Window
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class WindowSpec:
    """Specification for a sliding time window."""

    duration: timedelta
    slide: timedelta
    name: str

    @classmethod
    def one_minute(cls) -> WindowSpec:
        return cls(
            duration=timedelta(minutes=1),
            slide=timedelta(seconds=30),
            name="1min",
        )

    @classmethod
    def five_minutes(cls) -> WindowSpec:
        return cls(
            duration=timedelta(minutes=5),
            slide=timedelta(minutes=1),
            name="5min",
        )

    @classmethod
    def one_hour(cls) -> WindowSpec:
        return cls(
            duration=timedelta(hours=1),
            slide=timedelta(minutes=15),
            name="1h",
        )


class WindowedAggregation:
    """Sliding window aggregation over event streams.

    Supports count, sum, avg, min, max, and custom aggregators.
    Each window tracks events by a grouping key.
    """

    def __init__(self, window_spec: WindowSpec):
        self._window_spec = window_spec
        self._windows: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
        self._lock = threading.Lock()

    def add(self, key: str, value: float, timestamp: Optional[datetime] = None) -> None:
        ts = timestamp or datetime.now(timezone.utc)
        with self._lock:
            self._windows[key].append((ts, value))
            self._prune(key)

    def _prune(self, key: str) -> None:
        cutoff = datetime.now(timezone.utc) - self._window_spec.duration
        self._windows[key] = [
            (ts, v) for ts, v in self._windows[key] if ts >= cutoff
        ]

    def count(self, key: str) -> int:
        with self._lock:
            self._prune(key)
            return len(self._windows[key])

    def sum(self, key: str) -> float:
        with self._lock:
            self._prune(key)
            return sum(v for _, v in self._windows[key])

    def avg(self, key: str) -> float:
        with self._lock:
            self._prune(key)
            values = [v for _, v in self._windows[key]]
            return sum(values) / len(values) if values else 0.0

    def min(self, key: str) -> float:
        with self._lock:
            self._prune(key)
            values = [v for _, v in self._windows[key]]
            return min(values) if values else 0.0

    def max(self, key: str) -> float:
        with self._lock:
            self._prune(key)
            values = [v for _, v in self._windows[key]]
            return max(values) if values else 0.0

    def snapshot(self, key: str) -> Dict[str, Any]:
        """Return a snapshot of all aggregations for a key."""
        return {
            "window": self._window_spec.name,
            "duration_s": self._window_spec.duration.total_seconds(),
            "key": key,
            "count": self.count(key),
            "sum": round(self.sum(key), 4),
            "avg": round(self.avg(key), 4),
            "min": round(self.min(key), 4),
            "max": round(self.max(key), 4),
        }

    def all_keys(self) -> List[str]:
        with self._lock:
            return list(self._windows.keys())

    def clear(self) -> None:
        with self._lock:
            self._windows.clear()

    @property
    def window_spec(self) -> WindowSpec:
        return self._window_spec


# ════════════════════════════════════════════════════════════════════════════
# Throttled Output
# ════════════════════════════════════════════════════════════════════════════

class ThrottledOutput:
    """Ensures at most 1 event per window per key is emitted.

    Used to prevent downstream systems from being overwhelmed by
    high-frequency events that all aggregate to the same key.
    """

    def __init__(self):
        self._last_emitted: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._lock = threading.Lock()

    def should_emit(self, key: str, window_name: str, now: Optional[float] = None) -> bool:
        """Check if an event for this key+window should be emitted."""
        now = now or time.time()
        with self._lock:
            last = self._last_emitted[key].get(window_name, 0.0)
            if now - last >= self._window_duration_seconds(window_name):
                self._last_emitted[key][window_name] = now
                return True
            return False

    @staticmethod
    def _window_duration_seconds(window_name: str) -> float:
        mapping = {
            "1min": 60.0,
            "5min": 300.0,
            "1h": 3600.0,
        }
        return mapping.get(window_name, 60.0)

    def clear(self) -> None:
        with self._lock:
            self._last_emitted.clear()


# ════════════════════════════════════════════════════════════════════════════
# Stream Processor
# ════════════════════════════════════════════════════════════════════════════

class StreamProcessor:
    """Configurable stream processing pipeline.

    Supports:
      - Transforms:     Map events (Event → Optional[Event])
      - Filters:        Predicate-based event filtering
      - Sinks:          Async consumers (Event → Awaitable[None])
      - Windowed aggregations (1min, 5min, 1h)
      - Throttled output (max 1 event per window per key)
    """

    def __init__(self, name: str = "default"):
        self._name = name
        self._transforms: List[Tuple[str, Callable[[Event], Optional[Event]]]] = []
        self._filters: List[Tuple[str, Callable[[Event], bool]]] = []
        self._sinks: List[Tuple[str, Callable[[Event], Awaitable[None]]]] = []
        self._aggregators: Dict[str, WindowedAggregation] = {}
        self._throttle = ThrottledOutput()
        self._metrics_lock = threading.Lock()
        self._events_processed: int = 0
        self._events_dropped: int = 0
        self._events_errored: int = 0
        self._last_error: Optional[str] = None
        self._lock = asyncio.Lock()

    # ── Pipeline configuration ──────────────────────────────────────────────

    def add_transform(
        self, name: str, fn: Callable[[Event], Optional[Event]]
    ) -> StreamProcessor:
        """Add a transform function to the pipeline.

        The function receives an Event and returns either a transformed Event
        or None to drop the event from the pipeline.
        """
        self._transforms.append((name, fn))
        logger.info("StreamProcessor '%s': added transform '%s'", self._name, name)
        return self

    def add_filter(self, name: str, fn: Callable[[Event], bool]) -> StreamProcessor:
        """Add a filter function to the pipeline.

        Events that return False are dropped from the pipeline.
        """
        self._filters.append((name, fn))
        logger.info("StreamProcessor '%s': added filter '%s'", self._name, name)
        return self

    def add_sink(
        self, name: str, fn: Callable[[Event], Awaitable[None]]
    ) -> StreamProcessor:
        """Add an async sink function to the pipeline.

        Each event that passes all transforms and filters is delivered
        to every sink. Sinks run concurrently.
        """
        self._sinks.append((name, fn))
        logger.info("StreamProcessor '%s': added sink '%s'", self._name, name)
        return self

    def add_aggregator(self, name: str, window_spec: WindowSpec) -> WindowedAggregation:
        """Add a windowed aggregation to the pipeline.

        Returns the WindowedAggregation instance for extracting snapshots.
        """
        agg = WindowedAggregation(window_spec)
        self._aggregators[name] = agg
        logger.info(
            f"StreamProcessor '{self._name}': added aggregator '{name}' "
            f"({window_spec.name}, duration={window_spec.duration})"
        )
        return agg

    # ── Event processing ────────────────────────────────────────────────────

    async def process(self, event: Event) -> None:
        """Run the full pipeline for a single event.

        1. Apply all transforms (in order, short-circuit on None).
        2. Apply all filters (short-circuit on False).
        3. Deliver to all sinks concurrently.
        4. Update aggregators if configured.
        """
        async with self._lock:
            try:
                current = event

                # Transforms
                for name, transform_fn in self._transforms:
                    try:
                        result = transform_fn(current)
                        if result is None:
                            with self._metrics_lock:
                                self._events_dropped += 1
                            logger.debug(
                                f"StreamProcessor '{self._name}': event {event.id} "
                                f"dropped by transform '{name}'"
                            )
                            return
                        current = result
                    except Exception as e:
                        logger.error(
                            f"StreamProcessor '{self._name}': transform '{name}' "
                            f"raised error on event {event.id}: {e}"
                        )
                        with self._metrics_lock:
                            self._events_errored += 1
                            self._last_error = str(e)
                        return

                # Filters
                for name, filter_fn in self._filters:
                    try:
                        if not filter_fn(current):
                            with self._metrics_lock:
                                self._events_dropped += 1
                            logger.debug(
                                f"StreamProcessor '{self._name}': event {event.id} "
                                f"filtered out by '{name}'"
                            )
                            return
                    except Exception as e:
                        logger.error(
                            f"StreamProcessor '{self._name}': filter '{name}' "
                            f"raised error on event {event.id}: {e}"
                        )
                        with self._metrics_lock:
                            self._events_errored += 1
                            self._last_error = str(e)
                        return

                # Aggregators — extract numeric data from event
                agg_key = f"{event.type}:{event.source}"
                agg_value = self._extract_numeric_value(current)
                if agg_value is not None:
                    for agg_name, agg in self._aggregators.items():
                        try:
                            agg.add(agg_key, agg_value, current.timestamp)
                        except Exception as e:
                            logger.error(
                                f"StreamProcessor '{self._name}': aggregator '{agg_name}' "
                                f"error on event {event.id}: {e}"
                            )

                # Sinks — run concurrently for throughput
                if self._sinks:
                    tasks = []
                    for name, sink_fn in self._sinks:
                        tasks.append(self._run_sink(name, sink_fn, current))
                    await asyncio.gather(*tasks, return_exceptions=True)

                with self._metrics_lock:
                    self._events_processed += 1

            except Exception as e:
                with self._metrics_lock:
                    self._events_errored += 1
                    self._last_error = str(e)
                logger.error(
                    f"StreamProcessor '{self._name}': unhandled error processing "
                    f"event {event.id}: {e}"
                )

    async def _run_sink(
        self, name: str, sink_fn: Callable[[Event], Awaitable[None]], event: Event
    ) -> None:
        """Run a single sink with error handling."""
        try:
            await sink_fn(event)
        except Exception as e:
            logger.error(
                f"StreamProcessor '{self._name}': sink '{name}' failed "
                f"on event {event.id}: {e}"
            )
            with self._metrics_lock:
                self._events_errored += 1
                self._last_error = str(e)

    @staticmethod
    def _extract_numeric_value(event: Event) -> Optional[float]:
        """Try to extract a numeric value from event data for aggregation.

        Looks for common numeric fields in the event data.
        """
        candidates = ["value", "duration_ms", "cpu_percent", "memory_mb",
                       "count", "latency_ms", "size_bytes", "load", "voltage",
                       "current", "temperature", "pressure"]
        for key in candidates:
            val = event.data.get(key)
            if isinstance(val, (int, float)):
                return float(val)
        return None

    # ── Metrics ─────────────────────────────────────────────────────────────

    def get_metrics(self) -> Dict[str, Any]:
        """Return current processing metrics."""
        with self._metrics_lock:
            return {
                "name": self._name,
                "events_processed": self._events_processed,
                "events_dropped": self._events_dropped,
                "events_errored": self._events_errored,
                "last_error": self._last_error,
                "transform_count": len(self._transforms),
                "filter_count": len(self._filters),
                "sink_count": len(self._sinks),
                "aggregator_count": len(self._aggregators),
            }

    def get_aggregator_snapshots(self, key: Optional[str] = None) -> Dict[str, Any]:
        """Return snapshots from all windowed aggregators."""
        results: Dict[str, Any] = {}
        for name, agg in self._aggregators.items():
            keys = [key] if key else agg.all_keys()
            results[name] = {
                "window": agg.window_spec.name,
                "duration_s": agg.window_spec.duration.total_seconds(),
                "keys": {k: agg.snapshot(k) for k in keys if agg.count(k) > 0},
            }
        return results

    def should_throttle(self, key: str, window_name: str) -> bool:
        """Check if an event should be throttled for the given key and window.

        Returns True if the event should be SUPPRESSED (already emitted
        in this window), False if it should be ALLOWED.
        """
        return not self._throttle.should_emit(key, window_name)

    def reset(self) -> None:
        """Reset all metrics and aggregations."""
        with self._metrics_lock:
            self._events_processed = 0
            self._events_dropped = 0
            self._events_errored = 0
            self._last_error = None
        for agg in self._aggregators.values():
            agg.clear()
        self._throttle.clear()
        logger.info("StreamProcessor '%s': reset", self._name)

    @property
    def name(self) -> str:
        return self._name
