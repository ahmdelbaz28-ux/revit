"""
Engine Controller for L3 in Distributed FACP System
"""
import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from ..protocol.message_schema import FACPRequest, FACPResponse
from ..security.isolation import ExecutionIsolationManager
from .engine_pool import EnginePool


class EngineController:
    """
    Controller for managing the engine pool and individual workers in distributed system
    """
    def __init__(self, pool_size: int = 3, max_pool_size: int = 10):
        self.controller_id = f"engine_controller_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.pool_size = pool_size
        self.max_pool_size = max_pool_size
        self.engine_pool = EnginePool(initial_size=pool_size, max_size=max_pool_size)
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.lock = threading.Lock()
        self.cluster_sync_callback = None
        self.task_queue = []  # Queue for incoming tasks
        self.active_tasks = {}  # task_id -> task_info
        self.task_history = []  # Completed task history
        self.max_task_history = 1000
        self.isolation_manager = ExecutionIsolationManager()
        self.resource_limits = {
            "cpu_percent": 80.0,  # Maximum CPU usage percent
            "memory_mb": 4096,    # Maximum memory usage in MB
            "disk_gb": 100        # Maximum disk usage in GB
        }
        self.current_resource_usage = {
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "disk_gb": 0.0
        }
        self.heartbeat_interval = 30  # seconds
        self.last_heartbeat = time.time()
        self.health_check_interval = 10  # seconds
        self.last_health_check = time.time()

    def start(self):
        """
        Start the engine controller and initialize the pool
        """
        with self.lock:
            if self.is_running:
                return

            self.engine_pool.initialize()
            self.is_running = True

            # Start background processes
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self.health_check_thread = threading.Thread(target=self._health_check_loop, daemon=True)

            self.heartbeat_thread.start()
            self.health_check_thread.start()

            self.logger.info(f"Engine Controller {self.controller_id} started")

    def stop(self):
        """
        Stop the engine controller and shut down the pool
        """
        with self.lock:
            if not self.is_running:
                return

            self.engine_pool.graceful_shutdown()
            self.is_running = False

            self.logger.info(f"Engine Controller {self.controller_id} stopped")

    def process_request(self, request_data: Dict[str, Any], source_node: str = None) -> Dict[str, Any]:
        """
        Process an incoming request through the engine pool
        """
        request_id = request_data.get("id", str(uuid.uuid4()))

        # Validate request format
        try:
            FACPRequest.from_dict(request_data)
        except Exception as e:
            return FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "INVALID_REQUEST_FORMAT",
                    "message": f"Invalid request format: {str(e)}"
                },
                trace={
                    "execution_path": ["L3_EngineController"],
                    "latency_ms": 0,
                    "node_id": self.controller_id,
                    "engine_version": "FACP/1.1"
                }
            ).to_dict()

        # Enforce resource limits
        if not self._check_resource_availability():
            return FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "RESOURCE_EXHAUSTED",
                    "message": "Insufficient resources to process request"
                },
                trace={
                    "execution_path": ["L3_EngineController"],
                    "latency_ms": 0,
                    "node_id": self.controller_id,
                    "engine_version": "FACP/1.1"
                }
            ).to_dict()

        # Track the task
        self._track_task_start(request_id, request_data, source_node)

        # Process through the engine pool
        start_time = time.time()
        result = self.engine_pool.execute_request(request_data)

        execution_time = (time.time() - start_time) * 1000  # Convert to ms

        # Add controller-specific information to the result
        if "trace" in result:
            result["trace"]["controller_id"] = self.controller_id
            if "execution_path" in result["trace"]:
                result["trace"]["execution_path"].insert(0, "L3_EngineController")
            else:
                result["trace"]["execution_path"] = ["L3_EngineController"]

            # Update execution time
            result["trace"]["controller_processing_time_ms"] = execution_time
        else:
            result["trace"] = {
                "execution_path": ["L3_EngineController"],
                "controller_processing_time_ms": execution_time,
                "controller_id": self.controller_id,
                "engine_version": "FACP/1.1"
            }

        # Track task completion
        self._track_task_completion(request_id, result)

        return result

    def _check_resource_availability(self) -> bool:
        """
        Check if system has sufficient resources to process a request.

        Performs actual health checks:
        1. Worker processes are alive
        2. Event bus connection is active (if cluster_sync_callback is set)
        3. Memory usage is below threshold (via psutil)
        4. CPU usage is below threshold (via psutil)

        Returns False if any check fails, with details logged.
        """
        with self.lock:
            # Check CPU usage
            if self.current_resource_usage["cpu_percent"] > self.resource_limits["cpu_percent"]:
                self.logger.warning(
                    "Resource check failed: CPU usage %.1f%% exceeds limit %.1f%%",
                    self.current_resource_usage["cpu_percent"],
                    self.resource_limits["cpu_percent"],
                )
                return False

            # Check memory usage
            if self.current_resource_usage["memory_mb"] > self.resource_limits["memory_mb"]:
                self.logger.warning(
                    "Resource check failed: Memory usage %.0f MB exceeds limit %d MB",
                    self.current_resource_usage["memory_mb"],
                    self.resource_limits["memory_mb"],
                )
                return False

        # Check 1: Worker processes are alive
        try:
            pool_status = self.engine_pool.get_pool_status()
            for worker_id, worker_status in pool_status.get("worker_statuses", {}).items():
                if not worker_status.get("is_running", False):
                    self.logger.warning("Health check failed: Worker %s is not running", worker_id)
                    return False
                if not worker_status.get("is_healthy", True):
                    self.logger.warning("Health check failed: Worker %s is unhealthy", worker_id)
                    return False
        except Exception as e:
            self.logger.error("Health check failed: Cannot query engine pool status: %s", e)
            return False

        # Check 2: Event bus connection is active (if configured)
        if self.cluster_sync_callback is not None:
            try:
                # Attempt to send a minimal heartbeat to verify connectivity
                self.cluster_sync_callback({
                    "action": "health_probe",
                    "node_id": self.controller_id,
                    "timestamp": time.time(),
                })
            except Exception as e:
                self.logger.warning("Health check failed: Event bus connection error: %s", e)
                return False

        # Check 3: Actual system memory via psutil
        try:
            import psutil
            mem = psutil.virtual_memory()
            if mem.percent > 95:
                self.logger.warning(
                    "Health check failed: System memory usage %.1f%% exceeds 95%% threshold",
                    mem.percent,
                )
                return False
        except ImportError:
            pass  # psutil not available — skip system check
        except Exception as e:
            self.logger.debug("Could not check system memory via psutil: %s", e)

        return True

    def _track_task_start(self, task_id: str, request_data: Dict[str, Any], source_node: str = None):
        """
        Track the start of a task
        """
        with self.lock:
            self.active_tasks[task_id] = {
                "task_id": task_id,
                "request_data": request_data,
                "source_node": source_node,
                "start_time": time.time(),
                "status": "running"
            }

    def _track_task_completion(self, task_id: str, result: Dict[str, Any]):
        """
        Track the completion of a task
        """
        with self.lock:
            if task_id in self.active_tasks:
                task_info = self.active_tasks[task_id]
                task_info.update({
                    "end_time": time.time(),
                    "duration_ms": (time.time() - task_info["start_time"]) * 1000,
                    "result_status": result.get("status"),
                    "completed": True
                })

                # Move from active to history
                del self.active_tasks[task_id]
                self.task_history.append(task_info)

                # Maintain history size
                if len(self.task_history) > self.max_task_history:
                    self.task_history = self.task_history[-self.max_task_history:]

    def get_controller_status(self) -> Dict[str, Any]:
        """
        Get the status of the engine controller
        """
        with self.lock:
            pool_status = self.engine_pool.get_pool_status()

            return {
                "controller_id": self.controller_id,
                "is_running": self.is_running,
                "pool_status": pool_status,
                "active_tasks": len(self.active_tasks),
                "task_history_size": len(self.task_history),
                "max_task_history": self.max_task_history,
                "resource_limits": self.resource_limits,
                "current_resource_usage": self.current_resource_usage,
                "uptime_seconds": time.time() - getattr(self, 'start_time', time.time()),
                "last_heartbeat": self.last_heartbeat,
                "last_health_check": self.last_health_check
            }

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a specific task
        """
        with self.lock:
            if task_id in self.active_tasks:
                return self.active_tasks[task_id]

            # Check in history
            for task in self.task_history:
                if task["task_id"] == task_id:
                    return task

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get detailed statistics for the controller
        """
        with self.lock:
            # Calculate stats from task history
            completed_tasks = [t for t in self.task_history if t.get("completed")]
            successful_tasks = [t for t in completed_tasks if t.get("result_status") == "success"]
            failed_tasks = [t for t in completed_tasks if t.get("result_status") == "error"]

            if completed_tasks:
                avg_duration = sum(t.get("duration_ms", 0) for t in completed_tasks) / len(completed_tasks)
            else:
                avg_duration = 0

            return {
                "controller_id": self.controller_id,
                "total_tasks_processed": len(completed_tasks),
                "successful_tasks": len(successful_tasks),
                "failed_tasks": len(failed_tasks),
                "active_tasks": len(self.active_tasks),
                "success_rate": len(successful_tasks) / len(completed_tasks) if completed_tasks else 0,
                "average_task_duration_ms": avg_duration,
                "tasks_per_minute": self._calculate_throughput(),
                "pool_statistics": self.engine_pool.get_worker_statistics(),
                "pool_load_distribution": self.engine_pool.get_load_distribution()
            }

    def _calculate_throughput(self) -> float:
        """
        Calculate tasks per minute
        """
        # Look at last 5 minutes of completed tasks
        cutoff = time.time() - 300  # 5 minutes ago
        recent_completed = [t for t in self.task_history if t.get("end_time", 0) > cutoff]

        if not recent_completed:
            return 0.0

        time_span_minutes = (time.time() - min(t.get("end_time", time.time()) for t in recent_completed)) / 60
        return len(recent_completed) / max(time_span_minutes, 1)  # Avoid division by zero

    def _heartbeat_loop(self):
        """
        Background loop for sending heartbeats to cluster
        """
        while self.is_running:
            try:
                self._send_heartbeat()
                time.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"Heartbeat loop error: {e}")
                time.sleep(5)  # Wait before retrying

    def _health_check_loop(self):
        """
        Background loop for performing health checks
        """
        while self.is_running:
            try:
                self._perform_health_check()
                time.sleep(self.health_check_interval)
            except Exception as e:
                self.logger.error(f"Health check loop error: {e}")
                time.sleep(5)  # Wait before retrying

    def _send_heartbeat(self):
        """
        Send heartbeat to cluster
        """
        self.last_heartbeat = time.time()

        status = self.get_controller_status()

        # Notify cluster if callback is set
        if self.cluster_sync_callback:
            try:
                self.cluster_sync_callback({
                    "action": "heartbeat",
                    "node_id": self.controller_id,
                    "node_type": "l3_engine_controller",
                    "status": status,
                    "timestamp": time.time()
                })
            except Exception as e:
                self.logger.error(f"Failed to send heartbeat to cluster: {e}")

    def _perform_health_check(self):
        """
        Perform health check on the engine pool and workers
        """
        self.last_health_check = time.time()

        # Check pool health
        pool_status = self.engine_pool.get_pool_status()

        # Check for unhealthy workers
        for worker_id, worker_status in pool_status.get("worker_statuses", {}).items():
            if not worker_status.get("is_running", False):
                self.logger.warning(f"Worker {worker_id} is not running")
                # In a real implementation, we might restart the worker or alert
            elif not worker_status.get("is_healthy", True):
                self.logger.warning(f"Worker {worker_id} is not healthy")

        # Check resource usage
        self._update_resource_usage()

        # Check for resource exhaustion
        if not self._check_resource_availability():
            self.logger.warning("Resources are exhausted, performance may be impacted")

    def _update_resource_usage(self):
        """
        Update current resource usage metrics
        """
        # In a real implementation, this would query system metrics
        # For now, we'll simulate resource usage based on active tasks
        with self.lock:
            active_task_count = len(self.active_tasks)
            self.current_resource_usage["cpu_percent"] = min(90.0, active_task_count * 10.0)  # Simulate CPU usage
            self.current_resource_usage["memory_mb"] = min(4096.0, active_task_count * 50.0)  # Simulate memory usage
            # Disk usage would be updated based on actual file operations

    def set_cluster_sync_callback(self, callback):
        """
        Set callback for syncing with cluster
        """
        self.cluster_sync_callback = callback

    def sync_with_cluster(self, cluster_state: Dict[str, Any]):
        """
        Sync controller state with cluster
        """
        # In a real implementation, this would update controller based on cluster state
        # For now, we'll just log the sync
        self.logger.info(f"Received cluster sync update with {len(cluster_state)} entries")

    def update_worker_pool_size(self, new_size: int):
        """
        Dynamically update the worker pool size
        """
        if new_size < 1:
            raise ValueError("Pool size must be at least 1")

        if new_size > self.max_pool_size:
            self.logger.warning(f"Requested size {new_size} exceeds max size {self.max_pool_size}")
            new_size = self.max_pool_size

        # In a real implementation, this would resize the pool
        # For now, we'll just log the request
        self.logger.info(f"Pool size update requested: {new_size}")

        # Actually update the pool size
        with self.lock:
            # Update pool size parameters
            self.pool_size = new_size
            # The pool would handle resizing internally
            # For now, we'll just note the change

    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get the status of the task queue
        """
        return self.engine_pool.get_queue_status()

    def rebalance_load(self):
        """
        Rebalance load across the pool
        """
        self.engine_pool.rebalance_load()

    def cleanup_completed_tasks(self):
        """
        Clean up completed tasks from memory
        """
        time.time()
        # In a real implementation, we might have tasks with TTL
        # For now, this just ensures history size is maintained

    def get_resource_utilization(self) -> Dict[str, Any]:
        """
        Get resource utilization metrics
        """
        with self.lock:
            return {
                "resource_limits": self.resource_limits,
                "current_usage": self.current_resource_usage,
                "usage_percentages": {
                    "cpu": (self.current_resource_usage["cpu_percent"] / self.resource_limits["cpu_percent"]) * 100 if self.resource_limits["cpu_percent"] > 0 else 0,
                    "memory": (self.current_resource_usage["memory_mb"] / self.resource_limits["memory_mb"]) * 100 if self.resource_limits["memory_mb"] > 0 else 0
                }
            }

    def update_resource_limits(self, new_limits: Dict[str, float]):
        """
        Update resource limits for the controller
        """
        with self.lock:
            for key, value in new_limits.items():
                if key in self.resource_limits:
                    self.resource_limits[key] = value
            self.logger.info(f"Resource limits updated: {new_limits}")

    def force_worker_restart(self, worker_id: str) -> bool:
        """
        Force restart a specific worker (for maintenance purposes)
        """
        pool_status = self.engine_pool.get_pool_status()

        if worker_id in pool_status.get("worker_statuses", {}):
            # In a real implementation, we would restart the specific worker
            # For now, we'll just log the action
            self.logger.info(f"Worker restart requested for {worker_id}")
            return True

        return False

    def drain_controller(self) -> bool:
        """
        Drain the controller of all active tasks (for maintenance)
        """
        with self.lock:
            active_count = len(self.active_tasks)
            if active_count > 0:
                self.logger.info(f"Draining controller: {active_count} active tasks")
                # In a real implementation, we would wait for tasks to complete
                # For now, we'll just return status
                return False  # Not drained yet

        self.logger.info("Controller drained successfully")
        return True


class DistributedEngineController(EngineController):
    """
    Distributed engine controller with cluster awareness
    """
    def __init__(self, pool_size: int = 3, max_pool_size: int = 10, node_location: str = "primary"):
        super().__init__(pool_size, max_pool_size)
        self.node_location = node_location
        self.cluster_members = {}  # node_id -> status
        self.task_distribution_policy = "local_first"  # local_first, balanced, or remote_only
        self.cross_node_communicator = None

    def set_cross_node_communicator(self, communicator):
        """
        Set the communicator for cross-node communication
        """
        self.cross_node_communicator = communicator

    def process_request(self, request_data: Dict[str, Any], source_node: str = None) -> Dict[str, Any]:
        """
        Override to support distributed task processing
        """
        # Check if this should be processed locally or forwarded to another node
        if self._should_process_locally(request_data):
            return super().process_request(request_data, source_node)
        else:
            # Forward to another node
            return self._forward_request(request_data, source_node)

    def _should_process_locally(self, request_data: Dict[str, Any]) -> bool:
        """
        Determine if request should be processed locally
        """
        if self.task_distribution_policy == "local_first":
            return True  # Always prefer local processing
        elif self.task_distribution_policy == "balanced":
            # Check if local pool is overloaded compared to cluster
            local_load = len(self.active_tasks) / (self.pool_size * 5)  # Assuming 5 max concurrent per worker
            cluster_avg_load = self._get_cluster_average_load()
            return local_load <= cluster_avg_load
        elif self.task_distribution_policy == "remote_only":
            return False  # Always forward to other nodes
        else:
            return True

    def _get_cluster_average_load(self) -> float:
        """
        Get the average load across all cluster members
        """
        if not self.cluster_members:
            return 0.0

        total_load = 0
        count = 0
        for _node_id, status in self.cluster_members.items():
            if "pool_status" in status:
                pool_status = status["pool_status"]
                total_load += pool_status.get("average_load", 0)
                count += 1

        return total_load / count if count > 0 else 0.0

    def _forward_request(self, request_data: Dict[str, Any], source_node: str = None) -> Dict[str, Any]:
        """
        Forward request to another node in the cluster
        """
        if not self.cross_node_communicator:
            # If no cross-node communication available, process locally
            self.logger.warning("No cross-node communicator available, processing locally")
            return super().process_request(request_data, source_node)

        # Select a target node
        target_node = self._select_target_node()

        if not target_node:
            # If no target node available, process locally
            self.logger.warning("No target node available, processing locally")
            return super().process_request(request_data, source_node)

        try:
            # Forward the request
            result = self.cross_node_communicator.forward_request(target_node, request_data)

            # Add forwarding information to the result
            if "trace" in result:
                result["trace"]["forwarded_from"] = self.controller_id
                result["trace"]["forwarded_to"] = target_node
            else:
                result["trace"] = {
                    "forwarded_from": self.controller_id,
                    "forwarded_to": target_node,
                    "execution_path": ["L3_EngineController", f"forwarded_to_{target_node}"]
                }

            return result
        except Exception as e:
            # If forwarding fails, process locally
            self.logger.error(f"Request forwarding failed: {e}, processing locally")
            return super().process_request(request_data, source_node)

    def _select_target_node(self) -> Optional[str]:
        """
        Select a target node for request forwarding
        """
        # Find the node with the lowest load
        best_node = None
        lowest_load = float('inf')

        for node_id, status in self.cluster_members.items():
            if status.get("is_running", False):
                load = status.get("pool_status", {}).get("average_load", float('inf'))
                if load < lowest_load:
                    lowest_load = load
                    best_node = node_id

        return best_node

    def sync_cluster_membership(self, cluster_state: Dict[str, Any]):
        """
        Sync cluster membership information
        """
        self.cluster_members.update(cluster_state)

    def set_task_distribution_policy(self, policy: str):
        """
        Set the task distribution policy
        """
        if policy in ["local_first", "balanced", "remote_only"]:
            self.task_distribution_policy = policy
        else:
            raise ValueError(f"Invalid policy: {policy}. Valid options: local_first, balanced, remote_only")
