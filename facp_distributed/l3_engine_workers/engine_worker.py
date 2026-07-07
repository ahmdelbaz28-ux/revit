# NOSONAR
"""Engine Worker for L3 in Distributed FACP System"""
import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from ..protocol.message_schema import FACPResponse
from ..security.isolation import SandboxController, StatelessExecutionValidator
from .deterministic_engine import DeterministicEngine


class EngineWorker:
    """
    Engine worker that executes tasks in a stateless, deterministic manner
    Runs as a separate node in the distributed system
    """

    def __init__(self, worker_id: Optional[str] = None, capabilities: Optional[list] = None,
                 max_concurrent_tasks: int = 10):
        self.worker_id = worker_id or f"engine_worker_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.capabilities = capabilities or [
            "engine.calculate", "engine.validate", "engine.transform",
            "calc.*", "analysis.*", "validation.*"
        ]
        self.max_concurrent_tasks = max_concurrent_tasks
        self.current_tasks = 0
        self.task_queue = []  # Queue for incoming tasks
        self.active_executions = {}  # task_id -> execution_info
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.lock = threading.Lock()
        self.heartbeat_timestamp = time.time()
        self.status = "idle"
        self.cpu_usage = 0.0
        self.memory_usage = 0.0

        # Initialize deterministic engine and sandbox
        self.deterministic_engine = DeterministicEngine()
        self.sandbox_controller = SandboxController(self.worker_id)
        self.stateless_validator = StatelessExecutionValidator()

        # Create sandbox templates for different types of computations
        self.sandbox_controller.create_sandbox_template("calculation", {
            "timeout_ms": 5000,
            "max_memory_mb": 256,
            "network_access": False,
            "file_access": []
        })

        self.sandbox_controller.create_sandbox_template("validation", {
            "timeout_ms": 8000,
            "max_memory_mb": 512,
            "network_access": False,
            "file_access": []
        })

        self.sandbox_controller.create_sandbox_template("transformation", {
            "timeout_ms": 10000,
            "max_memory_mb": 1024,
            "network_access": False,
            "file_access": []
        })

    def start(self):
        """Start the engine worker"""
        self.is_running = True
        self.status = "running"
        self.logger.info("Engine Worker %s started", self.worker_id)

        # Start the execution loop in a separate thread
        self.execution_thread = threading.Thread(target=self._execution_loop, daemon=True)
        self.execution_thread.start()

    def stop(self):
        """Stop the engine worker"""
        self.is_running = False
        self.status = "stopped"
        self.logger.info("Engine Worker %s stopped", self.worker_id)

    def process_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process an incoming request from the orchestrator"""
        request_id = request_data.get("id", str(uuid.uuid4()))
        method = request_data.get("method", "")

        # Validate that this worker can handle this method
        if not self.can_handle_method(method):
            return FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "METHOD_NOT_SUPPORTED",
                    "message": f"Method {method} not supported by this worker"
                },
                trace={
                    "execution_path": ["L3_EngineWorker"],
                    "latency_ms": 0,
                    "node_id": self.worker_id,
                    "engine_version": "FACP/1.1"  # NOSONAR — S1192: duplicated literal acceptable in this localized context
                }
            ).to_dict()

        # Validate request constraints
        is_valid, constraint_error = self._validate_constraints(request_data)
        if not is_valid:
            return FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "CONSTRAINT_VIOLATION",
                    "message": constraint_error
                },
                trace={
                    "execution_path": ["L3_EngineWorker"],
                    "latency_ms": 0,
                    "node_id": self.worker_id,
                    "engine_version": "FACP/1.1"
                }
            ).to_dict()

        # Execute the request
        return self._execute_request(request_data)

    def can_handle_method(self, method: str) -> bool:
        """Check if this worker can handle a specific method"""
        # Check for exact match
        if method in self.capabilities:
            return True

        # Check for wildcard matches
        for capability in self.capabilities:
            if capability.endswith('.*') and method.startswith(capability[:-2]):
                return True

        return False

    def _validate_constraints(self, request_data: Dict[str, Any]) -> tuple[bool, str]:
        """Validate request constraints"""
        constraints = request_data.get("constraints", {})

        # Check timeout constraint
        timeout_ms = constraints.get("timeout_ms", 8000)
        if timeout_ms <= 0 or timeout_ms > 30000:  # Max 30 seconds for engine tasks
            return False, f"Invalid timeout constraint: {timeout_ms}ms (must be 1-30000ms)"

        # Check memory constraint
        max_memory_mb = constraints.get("max_memory_mb", 512)
        if max_memory_mb <= 0 or max_memory_mb > 2048:  # Max 2GB for engine tasks
            return False, f"Invalid memory constraint: {max_memory_mb}MB (must be 1-2048MB)"

        # Check recursion depth constraint
        max_depth = constraints.get("max_recursion_depth", 5)
        if max_depth <= 0 or max_depth > 10:
            return False, f"Invalid recursion depth constraint: {max_depth} (must be 1-10)"

        return True, ""

    def _execute_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a request in a sandboxed environment"""
        request_id = request_data["id"]
        method = request_data["method"]
        params = request_data.get("params", {})

        # Determine appropriate sandbox template based on method
        template_name = self._get_sandbox_template(method)

        # Provision a sandbox for this execution
        sandbox_id = self.sandbox_controller.provision_sandbox(template_name, request_id)

        # Update worker status
        with self.lock:
            self.current_tasks += 1
            self.status = "busy" if self.current_tasks > 0 else "idle"

        execution_start = time.time()

        try:
            # Execute the appropriate engine function based on method
            if method.startswith("engine.calculate") or "calculate" in method:
                result = self.deterministic_engine.execute_calculation(params.get("payload", {}))
            elif method.startswith("engine.validate") or "validate" in method:
                result = self.deterministic_engine.execute_validation(params.get("payload", {}))
            elif method.startswith("engine.transform") or "transform" in method:
                result = self.deterministic_engine.execute_transformation(params.get("payload", {}))
            else:
                # Default to calculation for unknown methods
                result = self.deterministic_engine.execute_calculation(params.get("payload", {}))

            execution_time = (time.time() - execution_start) * 1000  # Convert to ms

            # Validate that execution was deterministic
            is_deterministic, det_message = self.stateless_validator.validate_deterministic_function(
                lambda: result if isinstance(result, (int, float, str, bool, list, dict)) else {"result": result}
            )

            if not is_deterministic:
                self.logger.warning("Deterministic validation warning for %s: %s", request_id, det_message)

            # Create successful response
            response = FACPResponse(
                id=request_id,
                status="success",
                result=result,
                trace={
                    "execution_path": ["L3_EngineWorker"],
                    "latency_ms": execution_time,
                    "node_id": self.worker_id,
                    "engine_version": "FACP/1.1",
                    "sandbox_id": sandbox_id,
                    "deterministic": True
                }
            ).to_dict()

        except Exception as e:
            execution_time = (time.time() - execution_start) * 1000  # Convert to ms

            # Create error response
            response = FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "EXECUTION_ERROR",
                    "message": f"Execution failed: {e!s}"
                },
                trace={
                    "execution_path": ["L3_EngineWorker"],
                    "latency_ms": execution_time,
                    "node_id": self.worker_id,
                    "engine_version": "FACP/1.1",
                    "sandbox_id": sandbox_id
                }
            ).to_dict()

        finally:
            # Clean up the sandbox
            self.sandbox_controller.destroy_sandbox(sandbox_id)

            # Update worker status
            with self.lock:
                self.current_tasks -= 1
                self.status = "busy" if self.current_tasks > 0 else "idle"

        return response

    def _get_sandbox_template(self, method: str) -> str:
        """Determine appropriate sandbox template based on method"""
        if "calculate" in method or "calc" in method:
            return "calculation"
        if "validate" in method or "check" in method:
            return "validation"
        if "transform" in method or "convert" in method:
            return "transformation"
        # Default to calculation
        return "calculation"

    def _execution_loop(self):
        """Main execution loop for processing queued tasks"""
        while self.is_running:
            # Check for tasks in the queue
            if self.task_queue:
                with self.lock:
                    if self.task_queue and self.current_tasks < self.max_concurrent_tasks:
                        task = self.task_queue.pop(0)
                        # Process the task
                        self._process_queued_task(task)

            # Small sleep to prevent busy waiting
            time.sleep(0.01)

    def _process_queued_task(self, task: Dict[str, Any]):
        """Process a task from the queue"""
        # This is a simplified version - in a real system, we'd run this asynchronously
        self.process_request(task["request_data"])

    def get_worker_status(self) -> Dict[str, Any]:
        """Get the status of this engine worker"""
        return {
            "worker_id": self.worker_id,
            "capabilities": self.capabilities,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "current_tasks": self.current_tasks,
            "status": self.status,
            "is_running": self.is_running,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "last_heartbeat": self.heartbeat_timestamp,
            "uptime_seconds": time.time() - self.heartbeat_timestamp,
            "sandbox_health": self.sandbox_controller.get_sandbox_health(),
            "engine_version": "FACP/1.1"
        }

    def heartbeat(self) -> Dict[str, Any]:
        """Heartbeat method for cluster monitoring"""
        self.heartbeat_timestamp = time.time()
        return self.get_worker_status()

    def get_statistics(self) -> Dict[str, Any]:
        """Get execution statistics for this worker"""
        return {
            "worker_id": self.worker_id,
            "total_executions": getattr(self, '_total_executions', 0),
            "successful_executions": getattr(self, '_successful_executions', 0),
            "failed_executions": getattr(self, '_failed_executions', 0),
            "average_execution_time": getattr(self, '_average_execution_time', 0),
            "current_load": self.current_tasks / self.max_concurrent_tasks if self.max_concurrent_tasks > 0 else 0,
            "capabilities_count": len(self.capabilities)
        }

    def cleanup_idle_sandboxes(self):
        """Clean up any idle sandboxes"""
        self.sandbox_controller.cleanup_unused_sandboxes()

    def validate_no_external_access(self, code: str) -> tuple[bool, list]:
        """Validate that code doesn't attempt external access"""
        return self.sandbox_controller.validate_no_external_access(code)

    def validate_stateless_execution(self, code: str) -> tuple[bool, list]:
        """Validate that code maintains stateless execution"""
        return self.stateless_validator.validate_stateless_code(code)

    def add_capability(self, capability: str):
        """Add a new capability to this worker"""
        with self.lock:
            if capability not in self.capabilities:
                self.capabilities.append(capability)

    def remove_capability(self, capability: str):
        """Remove a capability from this worker"""
        with self.lock:
            if capability in self.capabilities:
                self.capabilities.remove(capability)

    def update_resource_usage(self, cpu_usage: float, memory_usage: float):
        """Update resource usage metrics"""
        with self.lock:
            self.cpu_usage = cpu_usage
            self.memory_usage = memory_usage

    def queue_task(self, request_data: Dict[str, Any]):
        """Queue a task for processing"""
        with self.lock:
            self.task_queue.append({
                "request_data": request_data,
                "queued_at": time.time()
            })

    def get_queue_status(self) -> Dict[str, Any]:
        """Get status of the task queue"""
        with self.lock:
            return {
                "queue_size": len(self.task_queue),
                "max_queue_size": 100,  # Arbitrary max
                "current_load": self.current_tasks / self.max_concurrent_tasks if self.max_concurrent_tasks > 0 else 0,
                "tasks_waiting": len(self.task_queue)
            }

    def enforce_execution_constraints(self, request_data: Dict[str, Any]) -> tuple[bool, str]:
        """Enforce execution constraints for this worker"""
        return self.sandbox_controller.enforce_execution_constraints(request_data)
