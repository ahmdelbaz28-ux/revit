"""thread_safe_queue.py — Thread-Safe Model Update Queue for Revit API
===================================================================
LIFE-SAFETY CRITICAL: The Revit API is SINGLE-THREADED — all model
modifications MUST occur on the Revit UI thread. Any attempt to modify
the Revit model from a background thread (e.g., an MCP server handler)
will cause:
  1. Silent memory corruption in the .rvt file
  2. Revit application crash (data loss of unsaved changes)
  3. Race conditions that write incorrect fire protection parameters
  4. Corrupted BIM model that looks correct but contains wrong values

This module implements the Python-side equivalent of the C#
IExternalEventHandler pattern required by the Revit API.

Architecture:
  - MCP handlers enqueue ModelUpdateAction objects (thread-safe)
  - A Revit add-in (C# IExternalEventHandler) dequeues and executes
    actions on the Revit UI thread inside a Transaction
  - The C# side must implement the companion ThreadSafeQueueHandler
    (see templates/revit_addin/ThreadSafeQueueHandler.cs)

Standards:
  - Revit API SDK Concurrency Guidelines
  - ISO 17822 (Software Quality in Building Engineering)
  - OWASP A03:2021 (Injection Prevention)

Forensic Audit Reference:
  - Finding 1: Unsafe Multithreading on Revit API (Catastrophic)
  - Root Cause: MCP server called Revit API from background thread
  - This module provides the CORRECT pattern for all model updates
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ACTION TYPES
# ═══════════════════════════════════════════════════════════════════════════════

class ModelUpdateType(str, Enum):
    """Types of model updates that can be queued.

    SAFETY: Each type maps to a specific Revit API operation.
    Unknown types are REJECTED — no dynamic dispatch.
    """

    SET_PARAMETER = "set_parameter"
    SET_ROOM_NAME = "set_room_name"
    SET_HAZARD_CLASS = "set_hazard_class"
    SET_PIPE_DIAMETER = "set_pipe_diameter"
    SET_SPRINKLER_PRESSURE = "set_sprinkler_pressure"
    SET_DETECTOR_LOCATION = "set_detector_location"
    CREATE_DEVICE = "create_device"
    DELETE_DEVICE = "delete_device"
    UPDATE_ANNOTATION = "update_annotation"


class ModelUpdateStatus(str, Enum):
    """Status of a model update action."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"  # Sanitization or validation failure


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ModelUpdateAction:
    """A single model update action to be executed on the Revit UI thread.

    SAFETY: All string fields must be sanitized BEFORE creating this object.
    The queue handler does NOT re-sanitize — it trusts that the MCP handler
    has already validated all inputs.

    Attributes:
        action_id: Unique identifier for tracking and audit trail.
        action_type: Type of model update (enum, not string — no dynamic dispatch).
        element_id: Revit ElementId as string (e.g., "12345").
        parameter_name: Revit parameter name (sanitized).
        parameter_value: Value to write (sanitized and type-checked).
        source: Origin of this action (e.g., "mcp_claude", "mcp_gpt").
        timestamp: When this action was created.
        priority: Execution priority (lower = higher priority).
        nfpa_reference: Engineering code reference for audit trail.

    """

    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_type: ModelUpdateType = ModelUpdateType.SET_PARAMETER
    element_id: str = ""
    parameter_name: str = ""
    parameter_value: Any = None
    source: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    priority: int = 100
    nfpa_reference: str = ""

    @property
    def is_safety_critical(self) -> bool:
        """Whether this action affects life-safety parameters."""
        safety_critical_params = {
            "pipe_diameter", "sprinkler_pressure", "hazard_class",
            "detector_spacing", "coverage_area", "k_factor",
            "flow_rate", "residual_pressure",
        }
        return (self.parameter_name.lower().replace(" ", "_")
                in safety_critical_params)


@dataclass
class ModelUpdateResult:
    """Result of executing a model update action.

    Attributes:
        action_id: Matches the submitted ModelUpdateAction.action_id.
        status: Execution status (COMPLETED, FAILED, REJECTED).
        error_message: Error details if FAILED or REJECTED.
        execution_time_ms: How long the Revit Transaction took.
        audit_trail_id: Reference to the audit log entry.
        completed_at: Timestamp when the result was reported (epoch seconds).

    """

    action_id: str = ""
    status: ModelUpdateStatus = ModelUpdateStatus.PENDING
    error_message: str = ""
    execution_time_ms: float = 0.0
    audit_trail_id: str = ""
    completed_at: float = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# THREAD-SAFE MODEL UPDATE QUEUE
# ═══════════════════════════════════════════════════════════════════════════════

class ThreadSafeModelUpdateQueue:
    """Thread-safe queue for Revit model updates.

    SAFETY: This is the ONLY approved way to modify the Revit model from
    external sources (MCP, API, etc.). Direct Revit API calls from
    background threads are FORBIDDEN and will cause data corruption.

    The queue works with a companion C# IExternalEventHandler that:
      1. Registers with Revit's ExternalEvent system
      2. On Revit UI thread idle, dequeues pending actions
      3. Wraps each action in a Transaction
      4. Commits on success, rolls back on failure
      5. Reports results back via the results dictionary

    Usage (Python MCP handler side):
        queue = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PIPE_DIAMETER,
            element_id="12345",
            parameter_name="Diameter",
            parameter_value=2.067,
            nfpa_reference="NFPA 13-2022 Chapter 23",
        )
        queue.enqueue(action)
        # ... C# side processes the action on Revit UI thread ...
        result = queue.wait_for_result(action.action_id, timeout=30.0)

    Usage (C# Revit add-in side):
        // See templates/revit_addin/ThreadSafeQueueHandler.cs
        // The C# handler dequeues actions and executes them inside
        // Transaction scope on the Revit UI thread.
    """

    def __init__(self, max_size: int = 1000) -> None:
        """Initialize the thread-safe queue.

        Args:
            max_size: Maximum number of pending actions. Prevents
                memory exhaustion from runaway MCP clients.

        """
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_size)
        self._results: Dict[str, ModelUpdateResult] = {}
        self._results_lock = threading.Lock()
        self._results_events: Dict[str, threading.Event] = {}
        self._action_log: List[Dict[str, Any]] = []
        self._log_lock = threading.Lock()
        self._stats = {
            "enqueued": 0,
            "completed": 0,
            "failed": 0,
            "rejected": 0,
        }
        self._stats_lock = threading.Lock()

    def enqueue(self, action: ModelUpdateAction) -> str:
        """Enqueue a model update action for safe execution on Revit UI thread.

        SAFETY: This method is thread-safe and can be called from any
        background thread (MCP handler, API handler, etc.).

        Args:
            action: The model update action to enqueue.

        Returns:
            The action_id for tracking.

        Raises:
            ValueError: If action is invalid or missing required fields.
            queue.Full: If the queue is at capacity.

        """
        # Validate required fields
        if not action.action_id:
            action.action_id = str(uuid.uuid4())

        if not action.element_id and action.action_type != ModelUpdateType.CREATE_DEVICE:
            raise ValueError(
                f"element_id is required for {action.action_type.value} actions. "
                "Cannot modify a Revit element without knowing which one."
            )

        if not action.parameter_name and action.action_type in (
            ModelUpdateType.SET_PARAMETER,
            ModelUpdateType.SET_PIPE_DIAMETER,
            ModelUpdateType.SET_SPRINKLER_PRESSURE,
            ModelUpdateType.SET_HAZARD_CLASS,
            ModelUpdateType.SET_ROOM_NAME,
        ):
            raise ValueError(
                f"parameter_name is required for {action.action_type.value} actions."
            )

        # Create result placeholder and event
        with self._results_lock:
            self._results[action.action_id] = ModelUpdateResult(
                action_id=action.action_id,
                status=ModelUpdateStatus.PENDING,
            )
            self._results_events[action.action_id] = threading.Event()

        # Enqueue with priority
        self._queue.put((action.priority, action), block=True, timeout=5.0)

        # Log for audit trail
        log_entry = {
            "action_id": action.action_id,
            "action_type": action.action_type.value,
            "element_id": action.element_id,
            "parameter_name": action.parameter_name,
            "source": action.source,
            "timestamp": action.timestamp,
            "enqueued_at": time.time(),
            "is_safety_critical": action.is_safety_critical,
            "nfpa_reference": action.nfpa_reference,
        }
        with self._log_lock:
            self._action_log.append(log_entry)

        with self._stats_lock:
            self._stats["enqueued"] += 1

        logger.info(
            f"[MCP QUEUE]: Enqueued {action.action_type.value} "
            f"action_id={action.action_id} element={action.element_id} "
            f"param={action.parameter_name} source={action.source}"
        )

        return action.action_id

    def dequeue(self, timeout: float = 1.0) -> Optional[ModelUpdateAction]:
        """Dequeue the next action for execution.

        SAFETY: This should ONLY be called by the C# IExternalEventHandler
        bridge code running on the Revit UI thread.

        Args:
            timeout: Maximum time to wait for an action (seconds).

        Returns:
            The next ModelUpdateAction, or None if queue is empty.

        """
        try:
            priority, action = self._queue.get(block=True, timeout=timeout)
            return action
        except queue.Empty:
            return None

    def report_result(self, result: ModelUpdateResult) -> None:
        """Report the result of executing a model update action.

        SAFETY: Called by the C# bridge after Transaction commit/rollback.

        Args:
            result: The execution result.

        """
        # Stamp completion time for cleanup_old_results age-based filtering
        result.completed_at = time.time()
        with self._results_lock:
            self._results[result.action_id] = result
            event = self._results_events.get(result.action_id)
            if event:
                event.set()

        with self._stats_lock:
            if result.status == ModelUpdateStatus.COMPLETED:
                self._stats["completed"] += 1
            elif result.status == ModelUpdateStatus.FAILED:
                self._stats["failed"] += 1
            elif result.status == ModelUpdateStatus.REJECTED:
                self._stats["rejected"] += 1

        logger.info(
            f"[MCP QUEUE]: Result for {result.action_id}: "
            f"{result.status.value} "
            f"({result.execution_time_ms:.1f}ms) "
            f"{result.error_message or ''}"
        )

    def wait_for_result(
        self,
        action_id: str,
        timeout: float = 30.0,
    ) -> ModelUpdateResult:
        """Wait for a model update action to complete.

        SAFETY: Blocks the calling thread until the C# bridge reports
        the result. Use with caution in MCP handlers — long timeouts
        can block the MCP server.

        Args:
            action_id: The action to wait for.
            timeout: Maximum wait time in seconds.

        Returns:
            The ModelUpdateResult.

        """
        with self._results_lock:
            event = self._results_events.get(action_id)

        if event is None:
            return ModelUpdateResult(
                action_id=action_id,
                status=ModelUpdateStatus.REJECTED,
                error_message=f"Unknown action_id: {action_id}",
            )

        completed = event.wait(timeout=timeout)

        with self._results_lock:
            if not completed:
                # Timeout — return FAILED instead of PENDING
                return ModelUpdateResult(
                    action_id=action_id,
                    status=ModelUpdateStatus.FAILED,
                    error_message=(
                        f"Timeout after {timeout:.1f}s waiting for "
                        "Revit to process action. The action may still "
                        "be pending in the queue — check audit log."
                    ),
                )
            return self._results.get(action_id, ModelUpdateResult(
                action_id=action_id,
                status=ModelUpdateStatus.FAILED,
                error_message="Result not found after event was set.",
            ))

    def get_pending_count(self) -> int:
        """Return the number of pending actions in the queue."""
        return self._queue.qsize()

    def get_stats(self) -> Dict[str, int]:
        """Return queue statistics."""
        with self._stats_lock:
            return dict(self._stats)

    def get_audit_log(self, last_n: int = 100) -> List[Dict[str, Any]]:
        """Return the last N audit log entries."""
        with self._log_lock:
            return list(self._action_log[-last_n:])

    def cleanup_old_results(self, max_age_seconds: float = 300.0) -> int:
        """Remove old results to prevent memory leaks.

        Args:
            max_age_seconds: Remove results older than this.

        Returns:
            Number of results removed.

        """
        cutoff = time.time() - max_age_seconds
        removed = 0
        with self._results_lock:
            to_remove = []
            for action_id, result in self._results.items():
                # Only remove terminal-status results older than max_age_seconds
                is_terminal = result.status in (
                    ModelUpdateStatus.COMPLETED,
                    ModelUpdateStatus.FAILED,
                    ModelUpdateStatus.REJECTED,
                )
                if not is_terminal:
                    continue
                # Use completed_at timestamp for age check
                if result.completed_at > 0 and result.completed_at < cutoff:
                    to_remove.append(action_id)
            for action_id in to_remove:
                del self._results[action_id]
                self._results_events.pop(action_id, None)
                removed += 1
        return removed
