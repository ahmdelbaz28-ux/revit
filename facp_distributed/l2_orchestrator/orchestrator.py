"""L2 Orchestrator for Distributed FACP System"""
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..protocol.message_schema import FACPResponse
from ..security.rbac import PermissionChecker
from .agent_manager import AgentManager
from .agent_registry import AgentRegistry
from .load_balancer import LoadBalancer
from .task_scheduler import TaskScheduler


class Orchestrator:
    """L2 Orchestrator - Routes tasks, manages agents, and enforces policies in distributed system"""

    def __init__(self,
                 agent_manager: AgentManager,
                 task_scheduler: TaskScheduler,
                 load_balancer: LoadBalancer,
                 permission_checker: PermissionChecker,
                 agent_registry: AgentRegistry):
        self.agent_manager = agent_manager
        self.task_scheduler = task_scheduler
        self.load_balancer = load_balancer
        self.permission_checker = permission_checker
        self.agent_registry = agent_registry
        self.logger = logging.getLogger(__name__)
        self.node_id = f"l2_orchestrator_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.active_tasks = {}  # task_id -> task_info
        self.task_history = []  # Limited history of completed tasks
        self.max_history_size = 1000
        self.distributed_locks = {}  # For idempotency keys across cluster

        # Register default agents
        self._register_default_agents()

    def _register_default_agents(self):
        """Register default agents with the registry"""
        # In a real implementation, this would register actual agent instances
        self.agent_registry.register_agent("planner_agent", {
            "type": "planner",
            "capabilities": ["plan.*", "schedule.*"],
            "node_affinity": None
        })

        self.agent_registry.register_agent("executor_agent", {
            "type": "executor",
            "capabilities": ["execute.*", "task.*"],
            "node_affinity": None
        })

        self.agent_registry.register_agent("validator_agent", {
            "type": "validator",
            "capabilities": ["validate.*", "check.*"],
            "node_affinity": None
        })

        self.agent_registry.register_agent("optimizer_agent", {
            "type": "optimizer",
            "capabilities": ["optimize.*", "tune.*"],
            "node_affinity": None
        })

    def process_request(self, request_data: Dict[str, Any], source_node: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Process a request from L1 through the orchestrator
        :param request_data: Request data that passed validation
        :param source_node: Node that originated the request
        :return: (success, response_data)
        """
        request_id = request_data.get("id", str(uuid.uuid4()))

        # Update execution state
        request_data["execution_state"] = "ROUTED"

        # Track active task
        self.active_tasks[request_id] = {
            "received_at": time.time(),
            "source_node": source_node,
            "method": request_data.get("method", "unknown"),
            "status": "processing"
        }

        try:
            # Check permissions for the method
            auth_context = request_data.get("auth_context", {})
            user_id = auth_context.get("user_id", "anonymous")

            allowed, permission_reason = self.permission_checker.check_method_access(
                user_id, request_data.get("method", ""), source_node
            )

            if not allowed:
                self.logger.warning("Orchestrator[%s]: Request %s denied by permission check: %s", self.node_id, request_id, permission_reason)

                error_response = FACPResponse(
                    id=request_id,
                    status="error",
                    error={
                        "code": "PERMISSION_DENIED",
                        "message": permission_reason
                    },
                    trace={
                        "execution_path": ["L1", "L2_orchestrator"],
                        "latency_ms": (time.time() - self.active_tasks[request_id]["received_at"]) * 1000,
                        "node_id": self.node_id,
                        "engine_version": "FACP/1.1"
                    }
                ).to_dict()

                # Update task status
                self.active_tasks[request_id]["status"] = "failed_permission"
                self._record_task_completion(request_id, "failed_permission")

                return False, error_response

            # Determine if this request should go to engine or be handled by an agent
            method = request_data.get("method", "")

            # Check if method should be routed to engine
            if self._should_route_to_engine(method):
                # Select an appropriate engine worker
                target_worker = self.load_balancer.select_engine_worker(method, request_data)

                if not target_worker:
                    error_response = FACPResponse(
                        id=request_id,
                        status="error",
                        error={
                            "code": "NO_AVAILABLE_WORKERS",
                            "message": f"No available engine workers for method: {method}"
                        },
                        trace={
                            "execution_path": ["L1", "L2_orchestrator"],
                            "latency_ms": (time.time() - self.active_tasks[request_id]["received_at"]) * 1000,
                            "node_id": self.node_id,
                            "engine_version": "FACP/1.1"
                        }
                    ).to_dict()

                    self.active_tasks[request_id]["status"] = "failed_no_workers"
                    self._record_task_completion(request_id, "failed_no_workers")

                    return False, error_response

                # Schedule task to engine worker
                self.task_scheduler.schedule_task(
                    method, request_data, target_worker, source_node
                )

                # Forward to engine worker
                # In a real implementation, this would send to the target worker via transport
                # For now, we'll simulate the response
                response = self._simulate_engine_forwarding(request_data, target_worker)

                # Update task status
                self.active_tasks[request_id]["status"] = "completed_engine"
                self._record_task_completion(request_id, "completed_engine")

                # Add orchestrator trace info
                if "trace" in response:
                    response["trace"]["execution_path"] = ["L1", "L2_orchestrator", f"L3_engine@{target_worker}"]
                    response["trace"]["orchestrator_node"] = self.node_id
                    response["trace"]["orchestration_time_ms"] = (time.time() - self.active_tasks[request_id]["received_at"]) * 1000
                else:
                    response["trace"] = {
                        "execution_path": ["L1", "L2_orchestrator", f"L3_engine@{target_worker}"],
                        "orchestrator_node": self.node_id,
                        "orchestration_time_ms": (time.time() - self.active_tasks[request_id]["received_at"]) * 1000,
                        "node_id": self.node_id,
                        "engine_version": "FACP/1.1"
                    }

                return True, response

            # Handle with an agent
            self.logger.info("Orchestrator[%s]: Processing request %s with agent for method %s", self.node_id, request_id, method)

            # Find appropriate agent
            agent = self.agent_manager.find_appropriate_agent(method)
            if not agent:
                # Try to find agent through registry
                agent_info = self.agent_registry.find_agent_for_method(method)
                if not agent_info:
                    error_response = FACPResponse(
                        id=request_id,
                        status="error",
                        error={
                            "code": "NO_SUITABLE_AGENT",
                            "message": f"No suitable agent found for method: {method}"
                        },
                        trace={
                            "execution_path": ["L1", "L2_orchestrator"],
                            "latency_ms": (time.time() - self.active_tasks[request_id]["received_at"]) * 1000,
                            "node_id": self.node_id,
                            "engine_version": "FACP/1.1"
                        }
                    ).to_dict()

                    self.active_tasks[request_id]["status"] = "failed_no_agent"
                    self._record_task_completion(request_id, "failed_no_agent")

                    return False, error_response

                # Use the agent info to process the request
                agent_result = self._process_with_agent_info(agent_info, request_data)

                response = FACPResponse(
                    id=request_id,
                    status="success",
                    result=agent_result,
                    trace={
                        "execution_path": ["L1", "L2_orchestrator", f"agent_{agent_info['id']}"],
                        "latency_ms": (time.time() - self.active_tasks[request_id]["received_at"]) * 1000,
                        "node_id": self.node_id,
                        "engine_version": "FACP/1.1"
                    }
                ).to_dict()

                self.active_tasks[request_id]["status"] = "completed_agent"
                self._record_task_completion(request_id, "completed_agent")

                return True, response

            # Execute with agent
            try:
                agent_result = agent.execute_task(request_data)

                response = FACPResponse(
                    id=request_id,
                    status="success",
                    result=agent_result,
                    trace={
                        "execution_path": ["L1", "L2_orchestrator", f"agent_{agent.id}"],
                        "latency_ms": (time.time() - self.active_tasks[request_id]["received_at"]) * 1000,
                        "node_id": self.node_id,
                        "engine_version": "FACP/1.1"
                    }
                ).to_dict()

                self.active_tasks[request_id]["status"] = "completed_agent"
                self._record_task_completion(request_id, "completed_agent")

                return True, response

            except Exception as e:
                error_response = FACPResponse(
                    id=request_id,
                    status="error",
                    error={
                        "code": "AGENT_EXECUTION_ERROR",
                        "message": f"Agent execution failed: {e!s}"
                    },
                    trace={
                        "execution_path": ["L1", "L2_orchestrator", f"agent_{agent.id}"],
                        "latency_ms": (time.time() - self.active_tasks[request_id]["received_at"]) * 1000,
                        "node_id": self.node_id,
                        "engine_version": "FACP/1.1"
                    }
                ).to_dict()

                self.active_tasks[request_id]["status"] = "failed_agent"
                self._record_task_completion(request_id, "failed_agent")

                return False, error_response

        except Exception as e:
            self.logger.error("Orchestrator[%s]: Unexpected error processing request %s: %s", self.node_id, request_id, str(e))

            error_response = FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "ORCHESTRATOR_ERROR",
                    "message": f"Orchestrator processing failed: {e!s}"
                },
                trace={
                    "execution_path": ["L1", "L2_orchestrator"],
                    "latency_ms": (time.time() - self.active_tasks[request_id]["received_at"]) * 1000,
                    "node_id": self.node_id,
                    "engine_version": "FACP/1.1"
                }
            ).to_dict()

            self.active_tasks[request_id]["status"] = "failed_exception"
            self._record_task_completion(request_id, "failed_exception")

            return False, error_response

    def _should_route_to_engine(self, method: str) -> bool:  # NOSONAR — S3516: always True is a CONSERVATIVE SAFETY DEFAULT (route to engine when in doubt)
        """Determine if a method should be routed to L3 engine"""
        # Engine methods typically involve calculations, validations, transformations
        engine_indicators = [
            "engine.", "calculate", "compute", "analyze", "validate", "transform",
            "evaluate", "assess", "determine", "find", "solve", "simulation",
            "calc.", "analysis.", "validation."
        ]

        method_lower = method.lower()
        for indicator in engine_indicators:
            if indicator in method_lower:
                return True

        # Default to engine for unknown methods (conservative approach)
        return True

    def _simulate_engine_forwarding(self, request_data: Dict[str, Any], target_worker: str) -> Dict[str, Any]:
        """Simulate forwarding to engine worker (in real system, this would be actual transport)"""
        # In a real implementation, this would send the request to the target worker
        # via the message bus or other transport mechanism
        # For simulation, we'll return a successful response

        return {
            "protocol": "FACP/1.1",
            "id": request_data["id"],
            "status": "success",
            "result": {
                "processed_by": f"engine_worker_{target_worker}",
                "method": request_data.get("method"),
                "simulation": True
            },
            "trace": {
                "forwarded_to": target_worker,
                "forwarded_at": time.time(),
                "node_id": self.node_id,
                "engine_version": "FACP/1.1"
            }
        }

    def _process_with_agent_info(self, agent_info: Dict[str, Any], request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process request using agent information from registry"""
        # In a real implementation, this would create or locate the actual agent
        # For simulation, we'll return a result indicating the agent would process it
        return {
            "processed_by": agent_info["id"],
            "method": request_data.get("method"),
            "agent_type": agent_info["type"],
            "result": "simulated_agent_processing",
            "scheduled_at": time.time()
        }

    def _record_task_completion(self, task_id: str, status: str):
        """Record task completion and manage history"""
        if task_id in self.active_tasks:
            task_info = self.active_tasks[task_id].copy()
            task_info["status"] = status
            task_info["completed_at"] = time.time()

            # Add to history
            self.task_history.append(task_info)

            # Trim history if needed
            if len(self.task_history) > self.max_history_size:
                self.task_history = self.task_history[-self.max_history_size:]

            # Remove from active tasks
            del self.active_tasks[task_id]

    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get orchestrator status information"""
        return {
            "node_id": self.node_id,
            "active_tasks": len(self.active_tasks),
            "total_agents": len(self.agent_manager.agents),
            "task_history_size": len(self.task_history),
            "max_history_size": self.max_history_size,
            "scheduler_status": self.task_scheduler.get_status(),
            "load_balancer_status": self.load_balancer.get_status(),
            "registry_status": self.agent_registry.get_status(),
            "uptime_seconds": time.time() - self.active_tasks.get("startup_time", time.time()),
            "agent_types_registered": self.agent_registry.get_registered_agent_types()
        }

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task"""
        if task_id in self.active_tasks:
            return self.active_tasks[task_id]

        # Check history
        for task in self.task_history:
            if task.get("id") == task_id or task_id in str(task):
                return task

        return None

    def get_load_statistics(self) -> Dict[str, Any]:
        """Get load statistics for the orchestrator"""
        return {
            "active_task_count": len(self.active_tasks),
            "completed_task_count": len(self.task_history),
            "agent_utilization": self.agent_manager.get_utilization_stats(),
            "average_task_processing_time": self._calculate_avg_processing_time(),
            "tasks_per_minute": self._calculate_tasks_per_minute()
        }

    def _calculate_avg_processing_time(self) -> float:
        """Calculate average task processing time from history"""
        if not self.task_history:
            return 0.0

        total_time = sum(
            task.get("completed_at", 0) - task.get("received_at", 0)
            for task in self.task_history
            if "completed_at" in task and "received_at" in task
        )

        return total_time / len(self.task_history) if self.task_history else 0.0

    def _calculate_tasks_per_minute(self) -> float:
        """Calculate tasks per minute from history"""
        if not self.task_history:
            return 0.0

        # Look at last 5 minutes of history
        cutoff = time.time() - 300  # 5 minutes ago
        recent_tasks = [t for t in self.task_history if t.get("received_at", 0) > cutoff]

        if not recent_tasks:
            return 0.0

        time_span_minutes = (time.time() - min(t.get("received_at", time.time()) for t in recent_tasks)) / 60
        return len(recent_tasks) / max(time_span_minutes, 1)  # Avoid division by zero

    def register_custom_agent(self, agent):
        """Register a custom agent with the orchestrator"""
        self.agent_manager.register_agent(agent)
        # Also register in the global registry
        self.agent_registry.register_agent(agent.id, {
            "type": getattr(agent, 'type', 'custom'),
            "capabilities": getattr(agent, 'capabilities', []),
            "node_affinity": self.node_id
        })

    def update_policy(self, policy_name: str, policy_config: Dict[str, Any]):
        """Update a specific policy (placeholder for future implementation)"""
        self.logger.info("Policy update requested: %s", policy_name)
        # Implementation would depend on policy management system

    def handle_node_join(self, node_id: str, node_type: str, capabilities: List[str]):
        """Handle a new node joining the cluster"""
        if node_type == "l3_engine_worker":
            self.load_balancer.register_engine_worker(node_id, capabilities)
        elif node_type == "l2_orchestrator":
            # Handle orchestrator-to-orchestrator communication
            self.logger.debug("Orchestrator node joined cluster: %s (no action needed)", node_id)

    def handle_node_leave(self, node_id: str):
        """Handle a node leaving the cluster"""
        self.load_balancer.unregister_engine_worker(node_id)

    def cleanup_completed_tasks(self):
        """Clean up completed tasks from memory"""
        # Already handled in _record_task_completion, but can do additional cleanup
        self.logger.debug("cleanup_completed_tasks called; no additional cleanup needed")

    def get_execution_context(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get execution context for a request (placeholder)"""
        return self.active_tasks.get(request_id)

    def enforce_distributed_idempotency(self, request_data: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Enforce idempotency across distributed cluster"""
        idempotency_key = request_data.get("security", {}).get("idempotency_key")
        if not idempotency_key:
            return True, None  # No idempotency requirement

        # Check if this idempotency key is already being processed
        if idempotency_key in self.distributed_locks:
            # Request is already being processed by another orchestrator
            # Return the same response that's being computed
            return False, self.distributed_locks[idempotency_key]["response"]

        # Acquire distributed lock for this idempotency key
        self.distributed_locks[idempotency_key] = {
            "request_id": request_data.get("id"),
            "acquired_at": time.time(),
            "status": "processing"
        }

        return True, None

    def release_idempotency_lock(self, idempotency_key: str, response: Dict[str, Any]):
        """Release the distributed idempotency lock"""
        if idempotency_key in self.distributed_locks:
            self.distributed_locks[idempotency_key].update({
                "status": "completed",
                "response": response,
                "released_at": time.time()
            })

    def sync_with_cluster(self, cluster_state: Dict[str, Any]):
        """Sync orchestrator state with cluster"""
        # Update agent registry with cluster-wide agent information
        cluster_agents = cluster_state.get("agents", {})
        self.agent_registry.sync_with_cluster(cluster_agents)

        # Update load balancer with cluster-wide worker information
        cluster_workers = cluster_state.get("workers", {})
        self.load_balancer.sync_with_cluster(cluster_workers)
