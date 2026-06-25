"""
Task Scheduler for L2 Orchestrator in Distributed FACP System
"""
import logging
import threading
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskStatus(Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskScheduler:
    """
    Schedules tasks to appropriate engine workers in the distributed system
    """
    def __init__(self):
        self.tasks = {}  # task_id -> task_info
        self.pending_tasks = []  # Priority queue for pending tasks
        self.scheduled_tasks = {}  # task_id -> scheduled_info
        self.running_tasks = {}  # task_id -> running_info
        self.completed_tasks = []  # Limited history of completed tasks
        self.failed_tasks = []  # Limited history of failed tasks
        self.max_history_size = 1000
        self.lock = threading.Lock()
        self.scheduler_id = f"scheduler_{uuid.uuid4().hex[:8]}"
        self.worker_task_queues = {}  # worker_id -> [task_ids]
        self.task_dependencies = {}  # task_id -> [dependency_task_ids]
        self.task_notifications = {}  # task_id -> [callback_functions]
        self.last_cleanup = time.time()
        self.cleanup_interval = 60  # seconds

    def schedule_task(self, method: str, request_data: Dict[str, Any],
                     target_worker: str, source_node: str = None) -> Dict[str, Any]:
        """
        Schedule a task to be executed on a specific worker
        """
        task_id = str(uuid.uuid4())

        # Determine priority based on request constraints
        constraints = request_data.get("constraints", {})
        priority = self._determine_priority(constraints)

        task_info = {
            "task_id": task_id,
            "method": method,
            "request_data": request_data,
            "target_worker": target_worker,
            "source_node": source_node,
            "priority": priority,
            "created_at": time.time(),
            "scheduled_at": time.time(),
            "status": TaskStatus.SCHEDULED.value,
            "attempts": 0,
            "max_retries": 1,  # As specified in requirements
            "timeout": constraints.get("timeout_ms", 8000) / 1000.0  # Convert to seconds
        }

        with self.lock:
            self.tasks[task_id] = task_info
            self.scheduled_tasks[task_id] = task_info

            # Add to worker's queue
            if target_worker not in self.worker_task_queues:
                self.worker_task_queues[target_worker] = []
            self.worker_task_queues[target_worker].append(task_id)

        return task_info

    def _determine_priority(self, constraints: Dict[str, Any]) -> TaskPriority:
        """
        Determine task priority based on constraints
        """
        risk_level = constraints.get("risk_level", "low")

        if risk_level == "critical":
            return TaskPriority.CRITICAL
        elif risk_level == "high":
            return TaskPriority.HIGH
        elif risk_level == "medium":
            return TaskPriority.NORMAL
        else:
            return TaskPriority.LOW

    def start_task_execution(self, task_id: str) -> bool:
        """
        Mark a task as running
        """
        with self.lock:
            if task_id in self.scheduled_tasks:
                task_info = self.scheduled_tasks[task_id]
                task_info["status"] = TaskStatus.RUNNING.value
                task_info["started_at"] = time.time()

                # Move from scheduled to running
                del self.scheduled_tasks[task_id]
                self.running_tasks[task_id] = task_info

                return True
        return False

    def complete_task(self, task_id: str, result: Dict[str, Any]) -> bool:
        """
        Mark a task as completed successfully
        """
        with self.lock:
            if task_id in self.running_tasks:
                task_info = self.running_tasks[task_id]
                task_info["status"] = TaskStatus.COMPLETED.value
                task_info["completed_at"] = time.time()
                task_info["result"] = result

                # Move from running to completed history
                del self.running_tasks[task_id]

                # Add to completed history (with size limit)
                self.completed_tasks.append(task_info)
                if len(self.completed_tasks) > self.max_history_size:
                    self.completed_tasks = self.completed_tasks[-self.max_history_size:]

                # Update the main tasks dict
                self.tasks[task_id] = task_info

                # Notify any listeners
                self._notify_task_completion(task_id, result)

                return True
        return False

    def fail_task(self, task_id: str, error: str) -> bool:
        """
        Mark a task as failed
        """
        with self.lock:
            if task_id in self.running_tasks:
                task_info = self.running_tasks[task_id]
                task_info["status"] = TaskStatus.FAILED.value
                task_info["failed_at"] = time.time()
                task_info["error"] = error
                task_info["attempts"] += 1

                # Check if we should retry
                if task_info["attempts"] < task_info["max_retries"]:
                    # Reschedule the task
                    task_info["status"] = TaskStatus.SCHEDULED.value
                    task_info["scheduled_at"] = time.time()

                    # Move back to scheduled
                    del self.running_tasks[task_id]
                    self.scheduled_tasks[task_id] = task_info
                else:
                    # Permanently fail the task
                    del self.running_tasks[task_id]

                    # Add to failed history (with size limit)
                    self.failed_tasks.append(task_info)
                    if len(self.failed_tasks) > self.max_history_size:
                        self.failed_tasks = self.failed_tasks[-self.max_history_size:]

                # Update the main tasks dict
                self.tasks[task_id] = task_info

                return True
        return False

    def cancel_task(self, task_id: str, reason: str = "cancelled_by_user") -> bool:
        """
        Cancel a pending or scheduled task
        """
        with self.lock:
            # Check in pending tasks
            if task_id in self.tasks and self.tasks[task_id]["status"] in [TaskStatus.PENDING.value, TaskStatus.SCHEDULED.value]:
                task_info = self.tasks[task_id]
                task_info["status"] = TaskStatus.CANCELLED.value
                task_info["cancelled_at"] = time.time()
                task_info["cancel_reason"] = reason

                # Remove from any queues
                if task_id in self.scheduled_tasks:
                    del self.scheduled_tasks[task_id]

                # Remove from worker queues
                for _worker_id, task_queue in self.worker_task_queues.items():
                    if task_id in task_queue:
                        task_queue.remove(task_id)

                return True
        return False

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a specific task
        """
        with self.lock:
            if task_id in self.tasks:
                return self.tasks[task_id]

            # Check in history
            for task in self.completed_tasks + self.failed_tasks:
                if task["task_id"] == task_id:
                    return task

        return None

    def get_worker_queue_status(self, worker_id: str) -> Dict[str, Any]:
        """
        Get the status of a worker's task queue
        """
        with self.lock:
            task_ids = self.worker_task_queues.get(worker_id, [])

            queue_info = {
                "worker_id": worker_id,
                "queue_size": len(task_ids),
                "tasks": []
            }

            for task_id in task_ids:
                task_info = self.tasks.get(task_id)
                if task_info:
                    queue_info["tasks"].append({
                        "task_id": task_id,
                        "method": task_info.get("method"),
                        "priority": task_info.get("priority").value if isinstance(task_info.get("priority"), TaskPriority) else task_info.get("priority"),
                        "created_at": task_info.get("created_at"),
                        "status": task_info.get("status")
                    })

            return queue_info

    def get_scheduler_status(self) -> Dict[str, Any]:
        """
        Get overall scheduler status
        """
        with self.lock:
            return {
                "scheduler_id": self.scheduler_id,
                "total_tasks_managed": len(self.tasks),
                "pending_tasks": len(self.pending_tasks),
                "scheduled_tasks": len(self.scheduled_tasks),
                "running_tasks": len(self.running_tasks),
                "completed_tasks_history": len(self.completed_tasks),
                "failed_tasks_history": len(self.failed_tasks),
                "worker_queues": {wid: len(tasks) for wid, tasks in self.worker_task_queues.items()},
                "active_workers": len([wid for wid, tasks in self.worker_task_queues.items() if len(tasks) > 0])
            }

    def register_task_dependency(self, task_id: str, dependency_task_ids: List[str]):
        """
        Register dependencies for a task
        """
        with self.lock:
            self.task_dependencies[task_id] = dependency_task_ids

    def add_task_notification(self, task_id: str, callback):
        """
        Add a notification callback for when a task completes
        """
        with self.lock:
            if task_id not in self.task_notifications:
                self.task_notifications[task_id] = []
            self.task_notifications[task_id].append(callback)

    def _notify_task_completion(self, task_id: str, result: Dict[str, Any]):
        """
        Notify listeners about task completion
        """
        with self.lock:
            if task_id in self.task_notifications:
                for callback in self.task_notifications[task_id]:
                    try:
                        callback(task_id, result)
                    except Exception as e:
                        # Don't let callback errors affect the scheduler
                        logger.warning("Task notification callback error: %s", e)
                del self.task_notifications[task_id]

    def cleanup_completed_tasks(self):
        """
        Clean up old completed and failed tasks to prevent memory leaks
        """
        current_time = time.time()

        with self.lock:
            # Only do cleanup periodically
            if current_time - self.last_cleanup < self.cleanup_interval:
                return

            self.last_cleanup = current_time

            # Trim histories if needed
            if len(self.completed_tasks) > self.max_history_size:
                self.completed_tasks = self.completed_tasks[-self.max_history_size:]

            if len(self.failed_tasks) > self.max_history_size:
                self.failed_tasks = self.failed_tasks[-self.max_history_size:]

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get scheduler statistics
        """
        with self.lock:
            completed_count = len(self.completed_tasks)
            failed_count = len(self.failed_tasks)
            total_processed = completed_count + failed_count

            avg_completion_time = 0
            if completed_count > 0:
                total_time = sum(
                    task.get("completed_at", 0) - task.get("started_at", 0)
                    for task in self.completed_tasks
                    if "completed_at" in task and "started_at" in task
                )
                avg_completion_time = total_time / completed_count

            return {
                "total_tasks_created": len(self.tasks),
                "tasks_pending": len(self.pending_tasks),
                "tasks_scheduled": len(self.scheduled_tasks),
                "tasks_running": len(self.running_tasks),
                "tasks_completed": completed_count,
                "tasks_failed": failed_count,
                "completion_rate": completed_count / total_processed if total_processed > 0 else 0,
                "failure_rate": failed_count / total_processed if total_processed > 0 else 0,
                "average_completion_time": avg_completion_time,
                "tasks_per_minute": self._calculate_throughput()
            }

    def _calculate_throughput(self) -> float:
        """
        Calculate tasks per minute processed
        """
        # Look at last 5 minutes of completed tasks
        cutoff = time.time() - 300  # 5 minutes ago
        recent_completed = [t for t in self.completed_tasks if t.get("completed_at", 0) > cutoff]

        if not recent_completed:
            return 0.0

        time_span_minutes = (time.time() - min(t.get("completed_at", time.time()) for t in recent_completed)) / 60
        return len(recent_completed) / max(time_span_minutes, 1)  # Avoid division by zero

    def check_task_timeout(self, task_id: str) -> bool:
        """
        Check if a task has timed out
        """
        with self.lock:
            if task_id in self.running_tasks:
                task_info = self.running_tasks[task_id]
                elapsed_time = time.time() - task_info.get("started_at", task_info.get("scheduled_at", time.time()))

                if elapsed_time > task_info["timeout"]:
                    return True

        return False

    def handle_worker_failure(self, worker_id: str):
        """
        Handle the failure of a worker by rescheduling its tasks
        """
        with self.lock:
            if worker_id in self.worker_task_queues:
                task_ids = self.worker_task_queues[worker_id][:]

                for task_id in task_ids:
                    if task_id in self.scheduled_tasks:
                        task_info = self.scheduled_tasks[task_id]
                        # Move back to pending for rescheduling
                        del self.scheduled_tasks[task_id]
                        # We'll need to reschedule this task later

                        # For now, mark as failed
                        task_info["status"] = TaskStatus.FAILED.value
                        task_info["failed_at"] = time.time()
                        task_info["error"] = f"Worker {worker_id} failed"
                        task_info["attempts"] += 1

                        # Check if we should retry
                        if task_info["attempts"] < task_info["max_retries"]:
                            # Put back in scheduled state to be reassigned
                            task_info["status"] = TaskStatus.SCHEDULED.value
                            task_info["scheduled_at"] = time.time()
                            self.scheduled_tasks[task_id] = task_info
                        else:
                            # Add to failed history
                            self.failed_tasks.append(task_info)
                            if len(self.failed_tasks) > self.max_history_size:
                                self.failed_tasks = self.failed_tasks[-self.max_history_size:]

                # Clear the worker's queue
                self.worker_task_queues[worker_id] = []

    def get_ready_tasks_for_worker(self, worker_id: str, max_tasks: int = 1) -> List[Dict[str, Any]]:
        """
        Get tasks ready for a specific worker
        """
        with self.lock:
            if worker_id not in self.worker_task_queues:
                return []

            ready_tasks = []
            worker_queue = self.worker_task_queues[worker_id][:]

            for task_id in worker_queue[:max_tasks]:
                if task_id in self.scheduled_tasks:
                    task_info = self.scheduled_tasks[task_id]
                    ready_tasks.append(task_info)

            return ready_tasks

    def remove_worker_tasks(self, worker_id: str) -> List[str]:
        """
        Remove all tasks assigned to a worker and return their IDs
        """
        with self.lock:
            if worker_id not in self.worker_task_queues:
                return []

            task_ids = self.worker_task_queues[worker_id][:]
            del self.worker_task_queues[worker_id]

            # Remove these tasks from scheduled tasks
            for task_id in task_ids:
                if task_id in self.scheduled_tasks:
                    del self.scheduled_tasks[task_id]

            return task_ids


class DistributedTaskScheduler(TaskScheduler):
    """
    Distributed version of task scheduler with cluster coordination
    """
    def __init__(self):
        super().__init__()
        self.cluster_sync_callback = None
        self.global_task_registry = {}  # task_id -> node_id mapping
        self.cross_node_dependencies = {}  # task_id -> [(dependency_task_id, dependency_node_id), ...]

    def set_cluster_sync_callback(self, callback):
        """
        Set callback for syncing task state with cluster
        """
        self.cluster_sync_callback = callback

    def schedule_task(self, method: str, request_data: Dict[str, Any],
                     target_worker: str, source_node: str = None) -> Dict[str, Any]:
        """
        Override to support cluster-wide task scheduling
        """
        task_info = super().schedule_task(method, request_data, target_worker, source_node)

        # Register with global registry
        self.global_task_registry[task_info["task_id"]] = source_node or "unknown"

        # Notify cluster if callback is available
        if self.cluster_sync_callback:
            self.cluster_sync_callback({
                "action": "task_scheduled",
                "task_info": task_info,
                "node_id": source_node or "unknown",
                "timestamp": time.time()
            })

        return task_info

    def complete_task(self, task_id: str, result: Dict[str, Any]) -> bool:
        """
        Override to support cluster-wide task completion
        """
        success = super().complete_task(task_id, result)

        if success and self.cluster_sync_callback:
            self.cluster_sync_callback({
                "action": "task_completed",
                "task_id": task_id,
                "result": result,
                "timestamp": time.time()
            })

        return success

    def fail_task(self, task_id: str, error: str) -> bool:
        """
        Override to support cluster-wide task failure
        """
        success = super().fail_task(task_id, error)

        if success and self.cluster_sync_callback:
            self.cluster_sync_callback({
                "action": "task_failed",
                "task_id": task_id,
                "error": error,
                "timestamp": time.time()
            })

        return success

    def sync_with_cluster(self, cluster_task_state: Dict[str, Any]):
        """
        Sync task scheduler with cluster state
        """
        # Implementation would update scheduler with cluster-wide task information
        logger.debug("sync_with_cluster called with %d entries; not yet implemented", len(cluster_task_state))
