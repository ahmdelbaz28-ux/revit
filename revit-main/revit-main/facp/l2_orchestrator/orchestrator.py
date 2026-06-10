"""
FACP L2 Orchestrator - Agent routing and policy enforcement
"""
from typing import Dict, Any, Optional, Tuple
from ..protocol.message_schema import FACPRequest, FACPResponse
from ..runtime.state_machine import ExecutionStateMachine, ExecutionState
from ..runtime.execution_context import ExecutionContext
from ..security.rbac import PermissionChecker
from .task_router import TaskRouter
from .policy_engine import PolicyEngine
from .agent_manager import AgentManager
import time
import uuid
import logging


class Orchestrator:
    """
    Main orchestrator that routes requests to appropriate agents or engines
    Enforces policies and maintains execution context
    """
    def __init__(self, 
                 task_router: TaskRouter, 
                 policy_engine: PolicyEngine, 
                 agent_manager: AgentManager,
                 execution_sm: ExecutionStateMachine,
                 permission_checker: PermissionChecker):
        self.task_router = task_router
        self.policy_engine = policy_engine
        self.agent_manager = agent_manager
        self.execution_sm = execution_sm
        self.permission_checker = permission_checker
        self.logger = logging.getLogger(__name__)

    def process_request(self, 
                       request_data: Dict[str, Any], 
                       auth_context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Process a request from L1 through the orchestrator
        :param request_data: Request data that passed validation
        :param auth_context: Authentication context from L1
        :return: (success, response_data)
        """
        request_id = request_data.get("id", str(uuid.uuid4()))
        
        # Update execution state to executing
        self.execution_sm.transition_to(request_id, ExecutionState.EXECUTING,
                                      "Request processing in orchestrator",
                                      {"auth_context": auth_context})
        
        # Create execution context for this request
        execution_context = ExecutionContext()
        execution_context.set_variable("auth_context", auth_context)
        execution_context.set_variable("request_data", request_data)
        
        try:
            # Apply policies to the request
            policy_result = self.policy_engine.apply_policies(request_data, auth_context)
            if not policy_result["allowed"]:
                self.logger.warning(f"Orchestrator: Request {request_id} denied by policy: {policy_result['reason']}")
                self.execution_sm.transition_to(request_id, ExecutionState.FAILED,
                                              "Request denied by policy engine",
                                              {"policy_reason": policy_result["reason"]})
                
                error_response = FACPResponse(
                    id=request_id,
                    status="error",
                    error={
                        "code": "POLICY_DENIED",
                        "message": policy_result["reason"]
                    },
                    trace={
                        "engine_version": "FACP/1.0",
                        "execution_path": ["L1", "L2_orchestrator"],
                        "latency_ms": (time.time() - self.execution_sm.requests[request_id]["created_at"]) * 1000
                    }
                ).to_dict()
                
                return False, error_response
            
            # Route the task based on method
            method = request_data.get("method", "")
            
            # Check permissions for the method
            allowed, permission_reason = self.permission_checker.check_method_access(
                auth_context["user_id"], method
            )
            
            if not allowed:
                self.logger.warning(f"Orchestrator: Request {request_id} denied by permission check: {permission_reason}")
                self.execution_sm.transition_to(request_id, ExecutionState.FAILED,
                                              "Request denied by permission check",
                                              {"permission_reason": permission_reason})
                
                error_response = FACPResponse(
                    id=request_id,
                    status="error",
                    error={
                        "code": "PERMISSION_DENIED",
                        "message": permission_reason
                    },
                    trace={
                        "engine_version": "FACP/1.0",
                        "execution_path": ["L1", "L2_orchestrator"],
                        "latency_ms": (time.time() - self.execution_sm.requests[request_id]["created_at"]) * 1000
                    }
                ).to_dict()
                
                return False, error_response
            
            # Determine if this request should go to engine or be handled by an agent
            if self.task_router.should_route_to_engine(method):
                # Forward to L3 engine
                self.logger.info(f"Orchestrator: Routing request {request_id} to L3 engine")
                
                # Update execution state
                self.execution_sm.transition_to(request_id, ExecutionState.EXECUTING,
                                              "Forwarding to L3 engine",
                                              {"target": "L3_engine"})
                
                # Prepare response indicating it should be forwarded to engine
                return True, {
                    "request_id": request_id,
                    "forward_to": "L3_engine",
                    "request_data": request_data,
                    "auth_context": auth_context,
                    "execution_context": execution_context.capture_snapshot()
                }
            else:
                # Handle with an agent
                self.logger.info(f"Orchestrator: Processing request {request_id} with agent")
                
                # Find appropriate agent
                agent = self.agent_manager.find_appropriate_agent(method)
                if not agent:
                    error_response = FACPResponse(
                        id=request_id,
                        status="error",
                        error={
                            "code": "NO_SUITABLE_AGENT",
                            "message": f"No suitable agent found for method: {method}"
                        },
                        trace={
                            "engine_version": "FACP/1.0",
                            "execution_path": ["L1", "L2_orchestrator"],
                            "latency_ms": (time.time() - self.execution_sm.requests[request_id]["created_at"]) * 1000
                        }
                    ).to_dict()
                    
                    self.execution_sm.transition_to(request_id, ExecutionState.FAILED,
                                                  "No suitable agent found",
                                                  {"method": method})
                    
                    return False, error_response
                
                # Execute with agent
                try:
                    agent_result = agent.execute_task(request_data, execution_context)
                    
                    response = FACPResponse(
                        id=request_id,
                        status="success",
                        result=agent_result,
                        trace={
                            "engine_version": "FACP/1.0",
                            "execution_path": ["L1", "L2_orchestrator", f"agent_{agent.id}"],
                            "latency_ms": (time.time() - self.execution_sm.requests[request_id]["created_at"]) * 1000
                        }
                    ).to_dict()
                    
                    self.execution_sm.transition_to(request_id, ExecutionState.COMPLETED,
                                                  "Agent execution completed",
                                                  {"agent_id": agent.id})
                    
                    return True, response
                    
                except Exception as e:
                    error_response = FACPResponse(
                        id=request_id,
                        status="error",
                        error={
                            "code": "AGENT_EXECUTION_ERROR",
                            "message": f"Agent execution failed: {str(e)}"
                        },
                        trace={
                            "engine_version": "FACP/1.0",
                            "execution_path": ["L1", "L2_orchestrator", f"agent_{agent.id}"],
                            "latency_ms": (time.time() - self.execution_sm.requests[request_id]["created_at"]) * 1000
                        }
                    ).to_dict()
                    
                    self.execution_sm.transition_to(request_id, ExecutionState.FAILED,
                                                  "Agent execution failed",
                                                  {"agent_id": agent.id, "error": str(e)})
                    
                    return False, error_response
        
        except Exception as e:
            self.logger.error(f"Orchestrator: Unexpected error processing request {request_id}: {str(e)}")
            
            error_response = FACPResponse(
                id=request_id,
                status="error",
                error={
                    "code": "ORCHESTRATOR_ERROR",
                    "message": f"Orchestrator processing failed: {str(e)}"
                },
                trace={
                    "engine_version": "FACP/1.0",
                    "execution_path": ["L1", "L2_orchestrator"],
                    "latency_ms": (time.time() - self.execution_sm.requests[request_id]["created_at"]) * 1000
                }
            ).to_dict()
            
            self.execution_sm.transition_to(request_id, ExecutionState.FAILED,
                                          "Orchestrator error",
                                          {"error": str(e)})
            
            return False, error_response

    def get_orchestrator_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics"""
        return {
            "total_requests_handled": len([req for req in self.execution_sm.requests.values() 
                                         if "L2_orchestrator" in str(req.get("state_history", []))]),
            "active_agents": len(self.agent_manager.agents),
            "policy_engine_status": self.policy_engine.get_status(),
            "task_router_status": self.task_router.get_status()
        }

    def register_custom_agent(self, agent):
        """Register a custom agent with the orchestrator"""
        self.agent_manager.register_agent(agent)

    def update_policy(self, policy_name: str, policy_config: Dict[str, Any]):
        """Update a specific policy"""
        self.policy_engine.update_policy(policy_name, policy_config)

    def get_execution_context(self, request_id: str) -> Optional[ExecutionContext]:
        """Get execution context for a request (if available)"""
        # This would normally maintain contexts, but for this implementation
        # we'll just return a basic context
        return ExecutionContext()


class FallbackOrchestrator:
    """
    Fallback orchestrator that provides basic routing when primary orchestrator fails
    """
    def __init__(self):
        self.fallback_mode = False
        self.logger = logging.getLogger(__name__)

    def set_fallback_mode(self, enabled: bool):
        """Enable or disable fallback mode"""
        self.fallback_mode = enabled
        self.logger.warning(f"Fallback mode {'enabled' if enabled else 'disabled'}")

    def process_request(self, request_data: Dict[str, Any], auth_context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Simplified request processing for fallback mode
        """
        if not self.fallback_mode:
            # Should not be called in normal mode
            return False, {
                "error": {
                    "code": "INVALID_MODE",
                    "message": "Fallback orchestrator called in normal mode"
                }
            }

        request_id = request_data.get("id", str(uuid.uuid4()))

        # Simple routing - if it looks like an engine method, route to engine
        method = request_data.get("method", "")
        if method.startswith("engine.") or method.startswith("calculate") or method.startswith("validate"):
            return True, {
                "request_id": request_id,
                "forward_to": "L3_engine",
                "request_data": request_data,
                "auth_context": auth_context,
                "via_fallback": True
            }
        else:
            # Route to default agent
            return True, {
                "request_id": request_id,
                "forward_to": "default_agent",
                "request_data": request_data,
                "auth_context": auth_context,
                "via_fallback": True
            }