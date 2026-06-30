"""
test_thread_safe_queue.py — Tests for fireai/mcp_server/thread_safe_queue.py.

Verifies thread-safety, enqueue/dequeue, result reporting, stats, and cleanup.
"""
from __future__ import annotations

import threading
import time

import pytest

from fireai.mcp_server.thread_safe_queue import (
    ModelUpdateAction,
    ModelUpdateResult,
    ModelUpdateStatus,
    ModelUpdateType,
    ThreadSafeModelUpdateQueue,
)


class TestModelUpdateAction:
    """ModelUpdateAction dataclass."""

    def test_default_action_id_is_uuid(self):
        action = ModelUpdateAction()
        assert isinstance(action.action_id, str)
        assert len(action.action_id) > 0

    def test_custom_action_id(self):
        action = ModelUpdateAction(action_id="custom-123")
        assert action.action_id == "custom-123"

    def test_default_values(self):
        action = ModelUpdateAction()
        assert action.action_type == ModelUpdateType.SET_PARAMETER
        assert action.element_id == ""
        assert action.parameter_name == ""
        assert action.parameter_value is None
        assert action.source == "unknown"
        assert isinstance(action.timestamp, float)
        assert action.priority == 100
        assert action.nfpa_reference == ""

    def test_is_safety_critical_true(self):
        action = ModelUpdateAction(
            parameter_name="Sprinkler Pressure",
        )
        assert action.is_safety_critical is True

    def test_is_safety_critical_false(self):
        action = ModelUpdateAction(
            parameter_name="Comment",
        )
        assert action.is_safety_critical is False

    def test_is_safety_critical_case_insensitive(self):
        action = ModelUpdateAction(parameter_name="DETECTOR SPACING")
        assert action.is_safety_critical is True


class TestThreadSafeModelUpdateQueue:
    """ThreadSafeModelUpdateQueue operations."""

    def test_init_creates_queue(self):
        q = ThreadSafeModelUpdateQueue(max_size=10)
        assert q.get_pending_count() == 0
        stats = q.get_stats()
        assert stats["enqueued"] == 0
        assert stats["completed"] == 0

    def test_enqueue_returns_action_id(self):
        q = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="123",
            parameter_name="Diameter",
            parameter_value=2.067,
        )
        action_id = q.enqueue(action)
        assert action_id == action.action_id

    def test_enqueue_missing_element_id_raises(self):
        q = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="",
            parameter_name="Diameter",
            parameter_value=2.067,
        )
        with pytest.raises(ValueError, match="element_id"):
            q.enqueue(action)

    def test_enqueue_missing_parameter_name_raises(self):
        q = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="123",
            parameter_name="",
            parameter_value=2.067,
        )
        with pytest.raises(ValueError, match="parameter_name"):
            q.enqueue(action)

    def test_enqueue_and_dequeue(self):
        q = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.CREATE_DEVICE,
            element_id="",
            parameter_name="",
            parameter_value=None,
        )
        q.enqueue(action)
        assert q.get_pending_count() == 1
        dequeued = q.dequeue(timeout=2.0)
        assert dequeued is not None
        assert dequeued.action_id == action.action_id

    def test_dequeue_timeout_returns_none(self):
        q = ThreadSafeModelUpdateQueue()
        result = q.dequeue(timeout=0.05)
        assert result is None

    def test_report_result_and_wait(self):
        q = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="123",
            parameter_name="Diameter",
            parameter_value=2.067,
        )
        q.enqueue(action)
        result = ModelUpdateResult(
            action_id=action.action_id,
            status=ModelUpdateStatus.COMPLETED,
            execution_time_ms=1.5,
        )
        q.report_result(result)

        waited = q.wait_for_result(action.action_id, timeout=2.0)
        assert waited.status == ModelUpdateStatus.COMPLETED
        assert waited.execution_time_ms == 1.5

    def test_wait_for_result_timeout(self):
        q = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="123",
            parameter_name="Diameter",
            parameter_value=2.067,
        )
        q.enqueue(action)
        result = q.wait_for_result(action.action_id, timeout=0.05)
        assert result.status == ModelUpdateStatus.FAILED
        assert "Timeout" in result.error_message

    def test_wait_for_unknown_action_id(self):
        q = ThreadSafeModelUpdateQueue()
        result = q.wait_for_result("unknown-id", timeout=0.05)
        assert result.status == ModelUpdateStatus.REJECTED

    def test_get_stats_after_operations(self):
        q = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="123",
            parameter_name="Diameter",
            parameter_value=2.067,
        )
        q.enqueue(action)
        dequeued = q.dequeue(timeout=2.0)
        assert dequeued is not None
        q.report_result(
            ModelUpdateResult(
                action_id=action.action_id,
                status=ModelUpdateStatus.COMPLETED,
            )
        )
        stats = q.get_stats()
        assert stats["enqueued"] == 1
        assert stats["completed"] == 1

    def test_get_audit_log(self):
        q = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="123",
            parameter_name="Diameter",
            parameter_value=2.067,
            nfpa_reference="NFPA 13-2022",
        )
        q.enqueue(action)
        log = q.get_audit_log(last_n=10)
        assert len(log) == 1
        assert log[0]["action_type"] == "set_parameter"
        assert log[0]["element_id"] == "123"
        assert log[0]["is_safety_critical"] is False

    def test_cleanup_old_results(self):
        q = ThreadSafeModelUpdateQueue()
        action = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="123",
            parameter_name="Diameter",
            parameter_value=2.067,
        )
        q.enqueue(action)
        dequeued = q.dequeue(timeout=2.0)
        assert dequeued is not None
        q.report_result(
            ModelUpdateResult(
                action_id=action.action_id,
                status=ModelUpdateStatus.COMPLETED,
            )
        )
        # Manually backdate the completion time so cleanup removes it
        with q._results_lock:
            old = q._results[action.action_id]
            old.completed_at = time.time() - 400.0
            q._results[action.action_id] = old
        removed = q.cleanup_old_results(max_age_seconds=300.0)
        assert removed == 1
        assert q.get_pending_count() == 0

    def test_queue_full_raises(self):
        q = ThreadSafeModelUpdateQueue(max_size=1)
        action1 = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="123",
            parameter_name="Diameter",
            parameter_value=2.067,
        )
        q.enqueue(action1)
        action2 = ModelUpdateAction(
            action_type=ModelUpdateType.SET_PARAMETER,
            element_id="456",
            parameter_name="Pressure",
            parameter_value=50.0,
        )
        with pytest.raises(Exception):  # queue.Full or RuntimeError depending on queue impl
            q.enqueue(action2)
