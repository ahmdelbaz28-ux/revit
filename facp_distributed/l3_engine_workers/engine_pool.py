"""Engine Pool for L3 in Distributed FACP System"""
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from .engine_worker import EngineWorker


class EnginePool:
    """Pool of engine workers for load distribution and redundancy in distributed system"""

    def __init__(self, initial_size: int = 3, max_size: int = 10):
        self.pool_id = f"engine_pool_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.initial_size = initial_size
        self.max_size = max_size
        self.workers: List[EngineWorker] = []
        self.active_workers: Dict[str, EngineWorker] = {}
        self.worker_status: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)
        self.is_initialized = False
        self.last_scaling_decision = time.time()
        self.scaling_interval = 60  # seconds between scaling decisions
        self.load_threshold_high = 0.8  # Scale up when load exceeds this
        self.load_threshold_low = 0.3   # Scale down when load falls below this
        self.current_size = 0

    def initialize(self):
        """Initialize the engine pool with initial workers"""
        with self.lock:
            if self.is_initialized:
                return

            for i in range(self.initial_size):
                worker = self._create_worker(f"worker_{i}_{int(time.time())}")
                self.workers.append(worker)
                self.active_workers[worker.worker_id] = worker
                self.worker_status[worker.worker_id] = worker.get_worker_status()
                worker.start()

            self.current_size = self.initial_size
            self.is_initialized = True
            self.logger.info("Engine Pool %s initialized with %s workers", self.pool_id, self.current_size)

    def _create_worker(self, worker_name: str) -> EngineWorker:
        """Create a new engine worker"""
        return EngineWorker(
            worker_id=worker_name,
            capabilities=[
                "engine.calculate", "engine.validate", "engine.transform",
                "calc.*", "analysis.*", "validation.*", "transform.*"
            ],
            max_concurrent_tasks=5
        )

    def get_available_worker(self) -> Optional[EngineWorker]:
        """Get an available worker from the pool"""
        with self.lock:
            for _worker_id, worker in self.active_workers.items():
                status = worker.get_worker_status()
                if status["status"] == "idle" and status["is_running"]:
                    return worker

            # If no idle workers, return the least busy one
            least_busy = None
            min_load = float('inf')

            for _worker_id, worker in self.active_workers.items():
                status = worker.get_worker_status()
                if status["is_running"]:
                    load = status["current_tasks"] / status["max_concurrent_tasks"]
                    if load < min_load:
                        min_load = load
                        least_busy = worker

            return least_busy

    def execute_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a request using an available worker from the pool"""
        worker = self.get_available_worker()

        if not worker:
            # Try to scale up if possible
            if self.current_size < self.max_size:
                self._scale_up()
                worker = self.get_available_worker()

            if not worker:
                return {
                    "status": "error",
                    "error": {
                        "code": "NO_AVAILABLE_WORKERS",
                        "message": "No available engine workers in pool"
                    },
                    "trace": {
                        "execution_path": ["L3_EnginePool"],
                        "latency_ms": 0,
                        "pool_id": self.pool_id,
                        "engine_version": "FACP/1.1"
                    }
                }

        # Process the request with the selected worker
        result = worker.process_request(request_data)

        # Update worker status
        with self.lock:
            self.worker_status[worker.worker_id] = worker.get_worker_status()

        # Add pool information to trace
        if "trace" in result:
            result["trace"]["pool_id"] = self.pool_id
            if "execution_path" in result["trace"]:
                result["trace"]["execution_path"].insert(0, "L3_EnginePool")
            else:
                result["trace"]["execution_path"] = ["L3_EnginePool"]

        return result

    def _scale_up(self):
        """Scale up the pool by adding more workers"""
        if self.current_size >= self.max_size:
            return

        with self.lock:
            if self.current_size >= self.max_size:
                return

            new_worker = self._create_worker(f"worker_{self.current_size}_{int(time.time())}")
            self.workers.append(new_worker)
            self.active_workers[new_worker.worker_id] = new_worker
            self.worker_status[new_worker.worker_id] = new_worker.get_worker_status()
            new_worker.start()

            self.current_size += 1
            self.logger.info("Engine Pool scaled up to %s workers", self.current_size)

    def _scale_down(self):
        """Scale down the pool by removing idle workers"""
        if self.current_size <= self.initial_size:
            return

        with self.lock:
            if self.current_size <= self.initial_size:
                return

            # Find an idle worker to remove
            idle_workers = []
            for _worker_id, worker in self.active_workers.items():
                status = worker.get_worker_status()
                if status["status"] == "idle" and status["current_tasks"] == 0:
                    idle_workers.append(worker)

            if idle_workers:
                worker_to_remove = idle_workers[0]

                # Stop and remove the worker
                worker_to_remove.stop()
                del self.active_workers[worker_to_remove.worker_id]
                del self.worker_status[worker_to_remove.worker_id]

                # Remove from main workers list
                self.workers = [w for w in self.workers if w.worker_id != worker_to_remove.worker_id]

                self.current_size -= 1
                self.logger.info("Engine Pool scaled down to %s workers", self.current_size)

    def perform_scaling_decision(self):
        """Make a scaling decision based on current load"""
        current_time = time.time()
        if current_time - self.last_scaling_decision < self.scaling_interval:
            return

        with self.lock:
            if not self.active_workers:
                return

            # Calculate average load across all workers
            total_load = 0
            running_workers = 0

            for _worker_id, worker in self.active_workers.items():
                status = worker.get_worker_status()
                if status["is_running"]:
                    total_load += status["current_tasks"] / status["max_concurrent_tasks"]
                    running_workers += 1

            if running_workers > 0:
                avg_load = total_load / running_workers
            else:
                avg_load = 0

            # Make scaling decision
            if avg_load > self.load_threshold_high and self.current_size < self.max_size:
                self._scale_up()
            elif avg_load < self.load_threshold_low and self.current_size > self.initial_size:
                self._scale_down()

            self.last_scaling_decision = current_time

    def get_pool_status(self) -> Dict[str, Any]:
        """Get the status of the entire pool"""
        with self.lock:
            worker_statuses = {}
            for worker_id, worker in self.active_workers.items():
                worker_statuses[worker_id] = worker.get_worker_status()

            running_workers = [ws for ws in worker_statuses.values() if ws["is_running"]]
            idle_workers = [ws for ws in worker_statuses.values() if ws["status"] == "idle"]

            return {
                "pool_id": self.pool_id,
                "total_workers": len(self.active_workers),
                "running_workers": len(running_workers),
                "idle_workers": len(idle_workers),
                "current_size": self.current_size,
                "initial_size": self.initial_size,
                "max_size": self.max_size,
                "worker_statuses": worker_statuses,
                "average_load": sum(ws["current_tasks"] / ws["max_concurrent_tasks"] for ws in worker_statuses.values()
                                  if ws["max_concurrent_tasks"] > 0) / len(worker_statuses) if worker_statuses else 0,
                "initialized": self.is_initialized,
                "uptime_seconds": time.time() - getattr(self, 'start_time', time.time())
            }

    def get_worker_statistics(self) -> Dict[str, Any]:
        """Get statistics for all workers in the pool"""
        with self.lock:
            stats = {}
            for worker_id, worker in self.active_workers.items():
                stats[worker_id] = worker.get_statistics()
            return stats

    def cleanup_idle_workers(self):
        """Clean up any idle workers if needed"""
        with self.lock:
            for worker in self.active_workers.values():
                worker.cleanup_idle_sandboxes()

    def graceful_shutdown(self):
        """Gracefully shut down all workers in the pool"""
        self.logger.info("Starting graceful shutdown of Engine Pool %s", self.pool_id)

        with self.lock:
            for worker in self.active_workers.values():
                worker.stop()

            self.active_workers.clear()
            self.worker_status.clear()
            self.workers.clear()
            self.current_size = 0
            self.is_initialized = False

        self.logger.info("Engine Pool %s shutdown complete", self.pool_id)

    def get_queue_status(self) -> Dict[str, Any]:
        """Get the combined queue status of all workers in the pool"""
        with self.lock:
            total_queue_size = 0
            total_max_queue_size = 0
            total_tasks_waiting = 0

            for worker in self.active_workers.values():
                queue_status = worker.get_queue_status()
                total_queue_size += queue_status["queue_size"]
                total_max_queue_size += queue_status["max_queue_size"]
                total_tasks_waiting += queue_status["tasks_waiting"]

            return {
                "pool_id": self.pool_id,
                "total_queue_size": total_queue_size,
                "total_max_queue_size": total_max_queue_size,
                "total_tasks_waiting": total_tasks_waiting,
                "average_queue_size_per_worker": total_queue_size / len(self.active_workers) if self.active_workers else 0,
                "pool_congestion_ratio": total_queue_size / total_max_queue_size if total_max_queue_size > 0 else 0
            }

    def add_worker_capability(self, capability: str):
        """Add a capability to all workers in the pool"""
        with self.lock:
            for worker in self.active_workers.values():
                worker.add_capability(capability)

    def remove_worker_capability(self, capability: str):
        """Remove a capability from all workers in the pool"""
        with self.lock:
            for worker in self.active_workers.values():
                worker.remove_capability(capability)

    def update_resource_usage(self, worker_id: str, cpu_usage: float, memory_usage: float):
        """Update resource usage for a specific worker"""
        with self.lock:
            if worker_id in self.active_workers:
                self.active_workers[worker_id].update_resource_usage(cpu_usage, memory_usage)
                self.worker_status[worker_id] = self.active_workers[worker_id].get_worker_status()

    def get_load_distribution(self) -> Dict[str, Any]:
        """Get load distribution across all workers"""
        with self.lock:
            loads = {}
            for worker_id, worker in self.active_workers.items():
                status = worker.get_worker_status()
                if status["max_concurrent_tasks"] > 0:
                    loads[worker_id] = status["current_tasks"] / status["max_concurrent_tasks"]
                else:
                    loads[worker_id] = 0

            if loads:
                return {
                    "loads": loads,
                    "min_load": min(loads.values()),
                    "max_load": max(loads.values()),
                    "avg_load": sum(loads.values()) / len(loads),
                    "std_dev_load": (sum((load - sum(loads.values())/len(loads))**2 for load in loads.values()) / len(loads))**0.5 if loads else 0
                }
            return {
                "loads": {},
                "min_load": 0,
                "max_load": 0,
                "avg_load": 0,
                "std_dev_load": 0
            }

    def rebalance_load(self):
        """Rebalance load across workers if there's significant imbalance"""
        load_stats = self.get_load_distribution()

        if load_stats["std_dev_load"] > 0.3:  # If there's significant load imbalance
            self.logger.info("Load rebalancing initiated. Current std dev: %.2f", load_stats['std_dev_load'])
            # In a real implementation, this would redistribute tasks among workers
            # For now, we'll just log the action
            pass  # NOSONAR - python:S2772


class AdaptiveEnginePool(EnginePool):
    """Adaptive engine pool that automatically scales based on demand"""

    def __init__(self, initial_size: int = 3, max_size: int = 10):
        super().__init__(initial_size, max_size)
        self.adaptive_scaling_enabled = True
        self.auto_scale_thread = None
        self.scale_check_interval = 30  # seconds

    def start_auto_scaling(self):
        """Start the auto-scaling background thread"""
        if not self.auto_scale_thread or not self.auto_scale_thread.is_alive():
            self.auto_scale_thread = threading.Thread(target=self._auto_scale_loop, daemon=True)
            self.auto_scale_thread.start()

    def stop_auto_scaling(self):
        """Stop the auto-scaling background thread"""
        # The thread is daemon, so it will stop when main program exits
        pass

    def _auto_scale_loop(self):
        """Background loop for auto-scaling"""
        while True:
            if self.adaptive_scaling_enabled and self.is_initialized:
                self.perform_scaling_decision()

            time.sleep(self.scale_check_interval)

    def execute_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Override to include auto-scaling considerations"""
        # Check if we need to scale before executing
        if self.adaptive_scaling_enabled:
            self.perform_scaling_decision()

        return super().execute_request(request_data)

    def set_scaling_parameters(self, high_threshold: float, low_threshold: float, interval: int):
        """Set parameters for adaptive scaling"""
        with self.lock:
            self.load_threshold_high = high_threshold
            self.load_threshold_low = low_threshold
            self.scaling_interval = interval
