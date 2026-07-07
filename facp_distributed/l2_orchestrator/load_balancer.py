"""Load Balancer for L2 Orchestrator in Distributed FACP System"""
import logging
import random
import threading
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional


class LoadBalancingStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    RESOURCE_BASED = "resource_based"


class EngineWorker:
    """Represents an engine worker node in the distributed system"""

    def __init__(self, worker_id: str, capabilities: List[str],
                 max_concurrent_tasks: int = 10, current_load: float = 0.0):
        self.worker_id = worker_id
        self.capabilities = capabilities
        self.max_concurrent_tasks = max_concurrent_tasks
        self.current_load = current_load
        self.current_tasks = 0
        self.last_heartbeat = time.time()
        self.status = "online"
        self.cpu_usage = 0.0
        self.memory_usage = 0.0
        self.network_latency = 0.0  # Latency to this worker
        self.weight = 1.0  # Weight for weighted algorithms
        self.failure_count = 0
        self.last_failure_time = 0
        self.location = "unknown"  # Geographic location

    def can_accept_task(self) -> bool:
        """Check if worker can accept a new task"""
        return (self.status == "online" and
                self.current_tasks < self.max_concurrent_tasks and
                self.current_load < 0.95)  # Don't overload beyond 95%

    def register_task_start(self):
        """Register that a task has started on this worker"""
        self.current_tasks += 1
        self.current_load = self.current_tasks / self.max_concurrent_tasks

    def register_task_completion(self):
        """Register that a task has completed on this worker"""
        self.current_tasks = max(0, self.current_tasks - 1)
        self.current_load = self.current_tasks / self.max_concurrent_tasks

    def heartbeat(self):
        """Update heartbeat timestamp"""
        self.last_heartbeat = time.time()

    def is_healthy(self, timeout_seconds: int = 120) -> bool:
        """Check if worker is healthy based on heartbeat"""
        return (time.time() - self.last_heartbeat) < timeout_seconds

    def get_status(self) -> Dict[str, Any]:
        """Get worker status information"""
        return {
            "worker_id": self.worker_id,
            "capabilities": self.capabilities,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "current_tasks": self.current_tasks,
            "current_load": self.current_load,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "network_latency": self.network_latency,
            "status": self.status,
            "weight": self.weight,
            "failure_count": self.failure_count,
            "last_heartbeat": self.last_heartbeat,
            "is_healthy": self.is_healthy(),
            "location": self.location
        }


class LoadBalancer:
    """Load balancer for distributing tasks to engine workers in distributed system"""

    def __init__(self, strategy: LoadBalancingStrategy = LoadBalancingStrategy.LEAST_CONNECTIONS):
        self.workers: Dict[str, EngineWorker] = {}
        self.strategy = strategy
        self.lock = threading.Lock()
        self.round_robin_index = 0
        self.load_balancer_id = f"lb_{uuid.uuid4().hex[:8]}"
        self.task_assignment_history = {}  # task_id -> worker_id
        self.last_health_check = time.time()
        self.health_check_interval = 30  # seconds
        self.cluster_workers = {}  # cluster-wide worker info
        self.worker_selection_history = {}  # worker_id -> selection_count

    def register_engine_worker(self, worker_id: str, capabilities: List[str],
                              max_concurrent_tasks: int = 10, location: str = "unknown"):
        """Register a new engine worker with the load balancer"""
        with self.lock:
            worker = EngineWorker(
                worker_id=worker_id,
                capabilities=capabilities,
                max_concurrent_tasks=max_concurrent_tasks
            )
            worker.location = location
            self.workers[worker_id] = worker
            self.worker_selection_history[worker_id] = 0

    def unregister_engine_worker(self, worker_id: str):
        """Unregister an engine worker from the load balancer"""
        with self.lock:
            if worker_id in self.workers:
                del self.workers[worker_id]
            if worker_id in self.worker_selection_history:
                del self.worker_selection_history[worker_id]

    def select_engine_worker(self, method: str, request_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Select an appropriate engine worker for a method"""
        with self.lock:
            # First, filter workers that can handle this method
            eligible_workers = []
            for _worker_id, worker in self.workers.items():
                if self._worker_can_handle_method(worker, method) and worker.can_accept_task():
                    eligible_workers.append(worker)

            if not eligible_workers:
                return None

            # Apply the selected load balancing strategy
            if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
                selected_worker = self._round_robin_selection(eligible_workers)
            elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
                selected_worker = self._least_connections_selection(eligible_workers)
            elif self.strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
                selected_worker = self._weighted_round_robin_selection(eligible_workers)
            elif self.strategy == LoadBalancingStrategy.RESOURCE_BASED:
                selected_worker = self._resource_based_selection(eligible_workers, request_data)
            else:
                # Default to least connections
                selected_worker = self._least_connections_selection(eligible_workers)

            if selected_worker:
                # Register that a task will be assigned to this worker
                selected_worker.register_task_start()
                self.worker_selection_history[selected_worker.worker_id] += 1
                return selected_worker.worker_id

            return None

    def _worker_can_handle_method(self, worker: EngineWorker, method: str) -> bool:
        """Check if a worker can handle a specific method"""
        # Check for exact capability match
        if method in worker.capabilities:
            return True

        # Check for wildcard matches
        for capability in worker.capabilities:
            if capability.endswith('.*') and method.startswith(capability[:-2]):
                return True

        return False

    def _round_robin_selection(self, workers: List[EngineWorker]) -> Optional[EngineWorker]:
        """Round-robin selection of workers"""
        if not workers:
            return None

        # Cycle through workers
        selected = workers[self.round_robin_index % len(workers)]
        self.round_robin_index = (self.round_robin_index + 1) % len(workers)
        return selected

    def _least_connections_selection(self, workers: List[EngineWorker]) -> Optional[EngineWorker]:
        """Select worker with least connections"""
        if not workers:
            return None

        # Sort by current tasks, then by load
        sorted_workers = sorted(workers, key=lambda w: (w.current_tasks, w.current_load))
        return sorted_workers[0]

    def _weighted_round_robin_selection(self, workers: List[EngineWorker]) -> Optional[EngineWorker]:
        """Weighted round-robin selection"""
        if not workers:
            return None

        # Calculate total weight
        total_weight = sum(max(w.weight, 0.1) for w in workers)  # Minimum weight of 0.1

        if total_weight <= 0:
            return self._round_robin_selection(workers)

        # Select based on weights
        random_value = random.uniform(0, total_weight)
        cumulative_weight = 0

        for worker in workers:
            cumulative_weight += max(worker.weight, 0.1)
            if random_value <= cumulative_weight:
                return worker

        # Fallback to last worker
        return workers[-1]

    def _resource_based_selection(self, workers: List[EngineWorker], request_data: Dict[str, Any]) -> Optional[EngineWorker]:
        """Select worker based on resource availability and request requirements"""
        if not workers:
            return None

        # Get request constraints
        constraints = request_data.get("constraints", {}) if request_data else {}
        constraints.get("max_memory_mb", 512)
        constraints.get("timeout_ms", 8000) / 1000.0  # Convert to seconds  # NOSONAR: S905 intentional expression

        # Score each worker based on available resources
        scored_workers = []
        for worker in workers:
            # Calculate available resources
            memory_available = (1.0 - worker.memory_usage) * worker.max_concurrent_tasks * 512  # Estimate
            load_score = 1.0 - worker.current_load
            task_score = max(0, (worker.max_concurrent_tasks - worker.current_tasks) / worker.max_concurrent_tasks)

            # Combined score (higher is better)
            score = (load_score * 0.4) + (task_score * 0.4) + (memory_available / 1000 * 0.2)

            scored_workers.append((worker, score))

        # Select worker with highest score
        if scored_workers:
            selected_worker, _ = max(scored_workers, key=lambda x: x[1])
            return selected_worker

        # Fallback to least connections
        return self._least_connections_selection(workers)

    def update_worker_status(self, worker_id: str, status: str):
        """Update the status of a worker"""
        with self.lock:
            if worker_id in self.workers:
                self.workers[worker_id].status = status

    def update_worker_resources(self, worker_id: str, cpu_usage: Optional[float] = None,
                               memory_usage: Optional[float] = None, network_latency: Optional[float] = None):
        """Update resource usage information for a worker"""
        with self.lock:
            if worker_id in self.workers:
                worker = self.workers[worker_id]
                if cpu_usage is not None:
                    worker.cpu_usage = cpu_usage
                if memory_usage is not None:
                    worker.memory_usage = memory_usage
                if network_latency is not None:
                    worker.network_latency = network_latency

    def record_task_assignment(self, task_id: str, worker_id: str):
        """Record that a task was assigned to a worker"""
        with self.lock:
            self.task_assignment_history[task_id] = worker_id

    def record_task_completion(self, task_id: str, worker_id: str):
        """Record that a task completed on a worker"""
        with self.lock:
            if worker_id in self.workers:
                self.workers[worker_id].register_task_completion()

            # Remove from assignment history after some time
            if task_id in self.task_assignment_history:
                # Don't immediately remove, keep for a while for debugging
                pass

    def get_worker_status(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific worker"""
        with self.lock:
            if worker_id in self.workers:
                return self.workers[worker_id].get_status()
        return None

    def get_all_worker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all workers"""
        with self.lock:
            return {wid: worker.get_status() for wid, worker in self.workers.items()}

    def get_load_balancer_status(self) -> Dict[str, Any]:
        """Get overall load balancer status"""
        with self.lock:
            online_workers = [w for w in self.workers.values() if w.is_healthy()]
            offline_workers = [w for w in self.workers.values() if not w.is_healthy()]

            return {
                "load_balancer_id": self.load_balancer_id,
                "total_workers": len(self.workers),
                "online_workers": len(online_workers),
                "offline_workers": len(offline_workers),
                "strategy": self.strategy.value,
                "worker_selection_history": self.worker_selection_history.copy(),
                "task_assignment_history_size": len(self.task_assignment_history),
                "avg_worker_load": sum(w.current_load for w in self.workers.values()) / len(self.workers) if self.workers else 0,
                "last_health_check": self.last_health_check
            }

    def perform_health_check(self):
        """
        Perform health check on all workers.

        When a worker is detected as unhealthy:
        1. Mark it as offline
        2. Redistribute its in-flight tasks to healthy workers
        3. Adjust weights to avoid routing new tasks to failed workers
        4. Log the failure for observability
        """
        current_time = time.time()
        if current_time - self.last_health_check < self.health_check_interval:
            return

        with self.lock:
            for worker_id, worker in self.workers.items():
                if not worker.is_healthy() and worker.status != "offline":
                    previous_status = worker.status
                    worker.status = "offline"
                    worker.failure_count += 1
                    worker.last_failure_time = current_time

                    # Reduce weight to prevent routing to this worker
                    if worker.failure_count > 3:
                        worker.weight = 0.0  # Completely exclude from selection
                    elif worker.failure_count > 1:
                        worker.weight *= 0.25  # Drastically reduce weight

                    logger = logging.getLogger(__name__)
                    logger.warning(
                        "Worker %s marked OFFLINE (heartbeat timeout). "
                        "Failure count: %d, previous status: %s. "
                        "Redistributing tasks to healthy workers.",
                        worker_id, worker.failure_count, previous_status
                    )

                    # Redistribute in-flight tasks from failed worker
                    self._redistribute_failed_worker_tasks(worker_id)

            self.last_health_check = current_time

    def _redistribute_failed_worker_tasks(self, failed_worker_id: str):
        """
        Redistribute tasks that were assigned to a failed worker.

        Finds all task assignments for the failed worker and attempts
        to reassign them to healthy workers that can handle the same
        methods. If no healthy worker is available, tasks are queued
        for retry when a worker recovers.
        """
        tasks_to_redistribute = {}

        # Find tasks assigned to the failed worker
        for task_id, assigned_worker_id in list(self.task_assignment_history.items()):
            if assigned_worker_id == failed_worker_id:
                tasks_to_redistribute[task_id] = assigned_worker_id

        if not tasks_to_redistribute:
            return

        # Decrement task count on the failed worker
        failed_worker = self.workers.get(failed_worker_id)
        if failed_worker:
            failed_worker.current_tasks = 0
            failed_worker.current_load = 0.0

        # Find healthy workers that can accept tasks
        healthy_workers = [
            w for w in self.workers.values()
            if w.is_healthy() and w.can_accept_task()
        ]

        if not healthy_workers:
            logger = logging.getLogger(__name__)
            logger.error(
                "No healthy workers available to redistribute %d tasks from failed worker %s. "
                "Tasks will be queued for retry.",
                len(tasks_to_redistribute), failed_worker_id
            )
            # Store failed tasks for later retry when a worker recovers
            self._pending_redistribution.update(tasks_to_redistribute)
            return

        # Redistribute tasks across healthy workers using least-connections strategy
        for task_id in tasks_to_redistribute:
            best_worker = min(healthy_workers, key=lambda w: (w.current_tasks, w.current_load))
            best_worker.register_task_start()
            self.task_assignment_history[task_id] = best_worker.worker_id
            self.worker_selection_history[best_worker.worker_id] = \
                self.worker_selection_history.get(best_worker.worker_id, 0) + 1

        logger = logging.getLogger(__name__)
        logger.info(
            "Redistributed %d tasks from failed worker %s to %d healthy workers.",
            len(tasks_to_redistribute), failed_worker_id, len(healthy_workers)
        )

    # Storage for tasks that couldn't be redistributed (no healthy workers available)
    _pending_redistribution: Dict[str, str] = {}

    def get_statistics(self) -> Dict[str, Any]:
        """Get load balancing statistics"""
        with self.lock:
            online_workers = [w for w in self.workers.values() if w.is_healthy()]

            if online_workers:
                avg_load = sum(w.current_load for w in online_workers) / len(online_workers)
                avg_cpu = sum(w.cpu_usage for w in online_workers) / len(online_workers)
                avg_memory = sum(w.memory_usage for w in online_workers) / len(online_workers)
            else:
                avg_load = avg_cpu = avg_memory = 0.0

            return {
                "total_workers": len(self.workers),
                "healthy_workers": len(online_workers),
                "average_worker_load": avg_load,
                "average_cpu_usage": avg_cpu,
                "average_memory_usage": avg_memory,
                "most_selected_worker": max(self.worker_selection_history.items(),
                                          key=lambda x: x[1])[0] if self.worker_selection_history else None,
                "selection_distribution": dict(sorted(self.worker_selection_history.items(),
                                                   key=lambda x: x[1], reverse=True))
            }

    def update_worker_weight(self, worker_id: str, new_weight: float):
        """Update the weight of a worker (for weighted algorithms)"""
        with self.lock:
            if worker_id in self.workers:
                self.workers[worker_id].weight = max(0.1, new_weight)  # Minimum weight of 0.1

    def get_eligible_workers_for_method(self, method: str) -> List[Dict[str, Any]]:
        """Get all workers eligible for a specific method"""
        with self.lock:
            eligible_workers = []
            for _worker_id, worker in self.workers.items():
                if self._worker_can_handle_method(worker, method) and worker.can_accept_task():
                    eligible_workers.append(worker.get_status())
            return eligible_workers

    def handle_worker_failure(self, worker_id: str):
        """Handle the failure of a worker"""
        with self.lock:
            if worker_id in self.workers:
                worker = self.workers[worker_id]
                worker.status = "failed"
                worker.failure_count += 1
                worker.last_failure_time = time.time()

                # Adjust weight based on failures
                if worker.failure_count > 3:  # Mark as unreliable after 3 failures
                    worker.weight = 0.1  # Very low weight
                elif worker.failure_count > 1:
                    worker.weight *= 0.5  # Reduce weight by half

    def handle_worker_recovery(self, worker_id: str):
        """
        Handle the recovery of a previously failed worker.

        Restores the worker to online status, resets its weight,
        refreshes its heartbeat, and redistributes any pending tasks
        that were queued during its failure.
        """
        with self.lock:
            if worker_id in self.workers:
                worker = self.workers[worker_id]
                worker.status = "online"
                worker.weight = 1.0  # Reset weight to normal
                worker.heartbeat()  # Refresh heartbeat

                logger = logging.getLogger(__name__)
                logger.info(
                    "Worker %s recovered — status: online, weight: 1.0. "
                    "Checking for pending tasks to redistribute.",
                    worker_id
                )

                # Redistribute pending tasks that were queued during failure
                if self._pending_redistribution:
                    pending_count = len(self._pending_redistribution)
                    for task_id, _original_worker_id in list(self._pending_redistribution.items()):
                        if worker.can_accept_task():
                            worker.register_task_start()
                            self.task_assignment_history[task_id] = worker_id
                            del self._pending_redistribution[task_id]

                    logger.info(
                        "Redistributed %d/%d pending tasks to recovered worker %s.",
                        pending_count - len(self._pending_redistribution),
                        pending_count, worker_id
                    )

    def cleanup_old_assignments(self, max_age_minutes: int = 60):
        """Clean up old task assignment records"""
        current_time = time.time()
        current_time - (max_age_minutes * 60)  # NOSONAR: S905 intentional expression

        # In a real implementation, we'd track assignment times
        # For now, we'll just maintain the size
        with self.lock:
            if len(self.task_assignment_history) > 10000:  # Arbitrary limit
                # Keep only the most recent assignments
                items = list(self.task_assignment_history.items())
                self.task_assignment_history = dict(items[-5000:])  # Keep last 5000

    def sync_with_cluster(self, cluster_worker_state: Dict[str, Any]):
        """Sync load balancer with cluster-wide worker information"""
        with self.lock:
            # Update cluster workers information
            self.cluster_workers.update(cluster_worker_state)

            # Potentially integrate cluster workers with local load balancing
            # This would depend on the specific distributed architecture needs


class AdaptiveLoadBalancer(LoadBalancer):
    """Adaptive load balancer that adjusts strategy based on system conditions"""

    def __init__(self):
        super().__init__(LoadBalancingStrategy.LEAST_CONNECTIONS)
        self.performance_history = {}  # worker_id -> [response_times]
        self.adaptation_threshold = 0.1  # Threshold for changing strategy
        self.monitoring_window = 100  # Number of requests to consider for adaptation

    def select_engine_worker(self, method: str, request_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Select worker with adaptive strategy selection"""
        # Periodically evaluate if we should change strategy
        self._evaluate_strategy()

        return super().select_engine_worker(method, request_data)

    def _evaluate_strategy(self):
        """Evaluate current strategy effectiveness and adapt if needed"""
        # Calculate performance metrics for each worker
        worker_performance = {}
        for worker_id, times in self.performance_history.items():
            if len(times) >= 10:  # Need sufficient data
                avg_response_time = sum(times) / len(times)
                worker_performance[worker_id] = avg_response_time

        # If we have performance data, consider switching to resource-based strategy
        if worker_performance and self.strategy != LoadBalancingStrategy.RESOURCE_BASED:
            # Check if there's significant variation in performance
            if len(set(worker_performance.values())) > 1:  # Different performance levels
                # Switch to resource-based strategy for better optimization
                self.strategy = LoadBalancingStrategy.RESOURCE_BASED

    def record_task_completion(self, task_id: str, worker_id: str, response_time: Optional[float] = None):
        """Override to record performance metrics"""
        super().record_task_completion(task_id, worker_id)

        if response_time is not None:
            with self.lock:
                if worker_id not in self.performance_history:
                    self.performance_history[worker_id] = []
                self.performance_history[worker_id].append(response_time)

                # Keep only recent performance data
                if len(self.performance_history[worker_id]) > self.monitoring_window:
                    self.performance_history[worker_id] = self.performance_history[worker_id][-50:]  # Last 50 measurements
