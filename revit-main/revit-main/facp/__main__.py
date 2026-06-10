"""
FACP Main Entry Point - Demonstrates the FireAI Agent Communication Protocol
"""
from .protocol.message_schema import FACPRequest, FACPResponse, FACPMessageValidator
from .security.auth import AuthProvider, TokenManager
from .security.validation_gate import ValidationGate
from .security.rbac import RBACEngine, PermissionChecker
from .security.audit import AuditLogger
from .runtime.state_machine import ExecutionStateMachine, ExecutionState
from .runtime.resource_manager import ResourceManager, ResourceConstraints
from .runtime.execution_context import ExecutionContext, ExecutionContextConfig
from .runtime.idempotency_manager import IdempotencyManager, IdempotencyMiddleware
from .l1_interface.handler import L1InterfaceHandler
from .l1_interface.transport import HTTPTransport, WebSocketTransport, StdioTransport, TransportRouter
from .l2_orchestrator.orchestrator import Orchestrator
from .l2_orchestrator.task_router import TaskRouter
from .l2_orchestrator.policy_engine import PolicyEngine, RateLimitPolicy, RoleBasedAccessPolicy
from .l2_orchestrator.agent_manager import AgentManager, PlannerAgent, ExecutorAgent, ValidatorAgent, OptimizerAgent
from .l3_engine.engine import DeterministicEngine, Calculator, Validator, Transformer
from typing import Dict, Any
import time
import uuid
import logging
import sys


def setup_logging():
    """Setup basic logging for the FACP system"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def create_facp_runtime():
    """
    Create a complete FACP runtime with all layers properly configured
    """
    print("Setting up FACP runtime...")
    
    # Initialize security components
    print("  Initializing security components...")
    auth_provider = AuthProvider()
    rbac_engine = RBACEngine()
    permission_checker = PermissionChecker(rbac_engine)
    audit_logger = AuditLogger()
    
    # Setup users and permissions
    auth_provider.register_user("admin_user", "admin", ["read", "write", "execute", "admin", "engine_access"])
    auth_provider.register_user("engineer_user", "engineer", ["read", "write", "execute", "engine_access"])
    auth_provider.register_user("guest_user", "guest", ["read"])
    
    # Create tokens for users
    admin_token = auth_provider.create_session_token("admin_user", ["read", "write", "execute", "admin", "engine_access"])
    engineer_token = auth_provider.create_session_token("engineer_user", ["read", "write", "execute", "engine_access"])
    guest_token = auth_provider.create_session_token("guest_user", ["read"])
    
    # Initialize runtime components
    print("  Initializing runtime components...")
    execution_sm = ExecutionStateMachine()
    resource_constraints = ResourceConstraints(timeout_ms=10000, max_memory_mb=256)
    resource_manager = ResourceManager(resource_constraints)
    
    # Initialize protocol and validation
    print("  Initializing protocol and validation...")
    validation_gate = ValidationGate(auth_provider)
    
    # Setup policies
    policy_engine = PolicyEngine()
    policy_engine.add_policy(RateLimitPolicy("rate_limit_basic", 100, 60))  # 100 requests per minute
    policy_engine.add_policy(RoleBasedAccessPolicy("rbac_engine_access", ["admin", "engineer"], ["engine_access"]))
    
    # Initialize L1 interface
    print("  Initializing L1 interface...")
    l1_handler = L1InterfaceHandler(validation_gate, execution_sm)
    
    # Initialize L2 orchestrator
    print("  Initializing L2 orchestrator...")
    task_router = TaskRouter()
    agent_manager = AgentManager()
    
    # Register default agents
    planner_agent = PlannerAgent()
    executor_agent = ExecutorAgent()
    validator_agent = ValidatorAgent()
    optimizer_agent = OptimizerAgent()
    
    agent_manager.register_agent(planner_agent)
    agent_manager.register_agent(executor_agent)
    agent_manager.register_agent(validator_agent)
    agent_manager.register_agent(optimizer_agent)
    
    orchestrator = Orchestrator(task_router, policy_engine, agent_manager, execution_sm, permission_checker)
    
    # Initialize L3 engine
    print("  Initializing L3 engine...")
    engine = DeterministicEngine(resource_constraints)
    
    # Setup transport router
    print("  Setting up transport layer...")
    transport_router = TransportRouter()
    
    # For demonstration purposes, we'll use the StdioTransport
    stdio_transport = StdioTransport()
    stdio_transport.set_l1_handler(l1_handler)
    transport_router.add_transport("stdio", stdio_transport)
    
    # For potential HTTP/WS support when running in proper environment
    try:
        http_transport = HTTPTransport(host="localhost", port=8000)
        http_transport.set_l1_handler(l1_handler)
        transport_router.add_transport("http", http_transport)
    except:
        print("  HTTP transport not available in this environment")
    
    try:
        ws_transport = WebSocketTransport(host="localhost", port=8001)
        ws_transport.set_l1_handler(l1_handler)
        transport_router.add_transport("websocket", ws_transport)
    except:
        print("  WebSocket transport not available in this environment")
    
    # Create the runtime bundle
    runtime = {
        'auth_provider': auth_provider,
        'rbac_engine': rbac_engine,
        'permission_checker': permission_checker,
        'audit_logger': audit_logger,
        'execution_sm': execution_sm,
        'resource_manager': resource_manager,
        'validation_gate': validation_gate,
        'l1_handler': l1_handler,
        'task_router': task_router,
        'agent_manager': agent_manager,
        'orchestrator': orchestrator,
        'engine': engine,
        'transport_router': transport_router,
        'tokens': {
            'admin': admin_token,
            'engineer': engineer_token,
            'guest': guest_token
        }
    }
    
    print("FACP runtime setup complete!")
    return runtime


def demonstrate_facp_flow(runtime: Dict[str, Any]):
    """
    Demonstrate the complete FACP flow with a sample request
    """
    print("\nDemonstrating FACP request flow...")
    
    # Get components
    l1_handler = runtime['l1_handler']
    orchestrator = runtime['orchestrator']
    engine = runtime['engine']
    tokens = runtime['tokens']
    
    # Create a sample request
    request_data = {
        "protocol": "FACP/1.0",
        "type": "request",
        "id": str(uuid.uuid4()),
        "timestamp": "2026-06-10T13:00:00Z",
        "source": "ide",
        "target": "engine",
        "method": "engine.calculate",
        "params": {
            "task": "voltage_drop_calculation",
            "payload": {
                "type": "voltage_drop",
                "params": {
                    "current": 16.0,
                    "length": 50.0,
                    "resistance": 0.0175,
                    "supply_voltage": 230.0,
                    "system_type": "single_phase"
                }
            },
            "context": {},
            "idempotency_key": f"calc_{int(time.time())}"
        },
        "security": {
            "auth_token": tokens['engineer'],
            "permissions": ["read", "write", "execute", "engine_access"],
            "risk_level": "low"
        }
    }
    
    print(f"  Created request with ID: {request_data['id']}")
    
    # Process through L1 (external interface)
    print("  Passing request through L1 interface (validation gate)...")
    l1_success, l1_result = l1_handler.handle_request(request_data, "127.0.0.1")
    
    if not l1_success:
        print(f"  L1 validation failed: {l1_result.get('error', {}).get('message', 'Unknown error')}")
        return
    
    print("  Request passed L1 validation successfully")
    
    # Extract processed request data
    processed_request = l1_result.get('processed_request', {})
    auth_context = processed_request.get('auth_context', {})
    
    # Process through L2 (orchestrator)
    print("  Passing request to L2 orchestrator...")
    l2_success, l2_result = orchestrator.process_request(request_data, auth_context)
    
    if not l2_success:
        print(f"  L2 processing failed: {l2_result.get('error', {}).get('message', 'Unknown error')}")
        # Handle error response
        response = l1_handler.handle_error_response(request_data["id"], 
                                                  l2_result.get("error", {}), 
                                                  "L2_Orchestrator")
        print(f"  Error response prepared: {response}")
        return
    
    # Check if we need to forward to L3 engine
    if l2_result.get("forward_to") == "L3_engine":
        print("  Request forwarded to L3 engine...")
        
        # Extract the original request data to send to engine
        engine_request_data = l2_result.get("request_data", request_data)
        engine_params = engine_request_data["params"]["payload"]["params"]
        engine_method = engine_request_data["method"]
        
        # Execute in L3 engine
        engine_result = engine.execute_method(engine_method, engine_params)
        
        if engine_result["success"]:
            print("  L3 engine execution successful")
            
            # Prepare response
            response_data = {
                "protocol": "FACP/1.0",
                "type": "response",
                "id": request_data["id"],
                "status": "success",
                "result": engine_result["result"],
                "trace": {
                    "engine_version": "FACP/1.0",
                    "execution_path": ["L1", "L2_Orchestrator", "L3_Engine"],
                    "latency_ms": (time.time() - 
                                  float(request_data["timestamp"].replace("T", " ").replace("Z", "").split()[1].replace(":", ""))) * 1000
                }
            }
            
            # Process response through L1
            final_response = l1_handler.handle_response(request_data["id"], response_data)
            print(f"  Final response prepared: {final_response['status']}")
            print(f"  Calculation result: {engine_result['result']}")
        else:
            print(f"  L3 engine execution failed: {engine_result.get('error', 'Unknown error')}")
            error_response = l1_handler.handle_error_response(
                request_data["id"], 
                {"code": "ENGINE_ERROR", "message": engine_result.get("error", "Unknown engine error")}, 
                "L3_Engine"
            )
            print(f"  Error response: {error_response}")
    
    else:
        print(f"  Request handled by agent: {l2_result}")


def demonstrate_security_features(runtime: Dict[str, Any]):
    """
    Demonstrate security features of FACP
    """
    print("\nDemonstrating security features...")
    
    l1_handler = runtime['l1_handler']
    tokens = runtime['tokens']
    
    # Test 1: Valid request
    print("  Test 1: Valid request with proper permissions")
    valid_request = {
        "protocol": "FACP/1.0",
        "type": "request",
        "id": str(uuid.uuid4()),
        "timestamp": "2026-06-10T13:00:00Z",
        "source": "ide",
        "target": "engine",
        "method": "engine.calculate",
        "params": {
            "task": "simple_test",
            "payload": {"type": "generic", "params": {"operation": "add", "operands": [2, 3]}},
            "context": {}
        },
        "security": {
            "auth_token": tokens['engineer'],
            "permissions": ["read", "write", "execute", "engine_access"],
            "risk_level": "low"
        }
    }
    
    success, result = l1_handler.handle_request(valid_request, "127.0.0.1")
    print(f"    Result: {'SUCCESS' if success else 'FAILED'}")
    
    # Test 2: Invalid token
    print("  Test 2: Request with invalid token")
    invalid_token_request = valid_request.copy()
    invalid_token_request["security"]["auth_token"] = "invalid_token_12345"
    
    success, result = l1_handler.handle_request(invalid_token_request, "127.0.0.1")
    print(f"    Result: {'SUCCESS' if success else 'FAILED (as expected)'}")
    if not success:
        print(f"    Error: {result.get('error', {}).get('message', 'No error message')}")
    
    # Test 3: Insufficient permissions
    print("  Test 3: Request with insufficient permissions")
    guest_request = valid_request.copy()
    guest_request["security"]["auth_token"] = tokens['guest']  # Guest token doesn't have engine access
    guest_request["security"]["permissions"] = ["read"]
    
    success, result = l1_handler.handle_request(guest_request, "127.0.0.1")
    print(f"    Result: {'SUCCESS' if success else 'FAILED (as expected)'}")
    if not success:
        print(f"    Error: {result.get('error', {}).get('message', 'No error message')}")


def demonstrate_agent_orchestration(runtime: Dict[str, Any]):
    """
    Demonstrate agent orchestration capabilities
    """
    print("\nDemonstrating agent orchestration...")
    
    orchestrator = runtime['orchestrator']
    tokens = runtime['tokens']
    
    # Create a request that should be handled by an agent
    agent_request = {
        "protocol": "FACP/1.0",
        "type": "request",
        "id": str(uuid.uuid4()),
        "timestamp": "2026-06-10T13:00:00Z",
        "source": "ide",
        "target": "orchestrator",
        "method": "agent.plan",
        "params": {
            "task": "create_installation_plan",
            "payload": {
                "plan": {
                    "type": "electrical_installation",
                    "tasks": ["route_cables", "install_boxes", "connect_devices"],
                    "duration": "2_days"
                }
            },
            "context": {}
        },
        "security": {
            "auth_token": tokens['engineer'],
            "permissions": ["read", "write", "execute"],
            "risk_level": "low"
        }
    }
    
    # Process through orchestrator
    auth_context = {
        "user_id": "engineer_user",
        "role": "engineer",
        "permissions": ["read", "write", "execute", "engine_access"],
        "token_data": {"user_id": "engineer_user"}
    }
    
    success, result = orchestrator.process_request(agent_request, auth_context)
    
    if success and result.get("forward_to") != "L3_engine":
        print("  Agent successfully processed the request")
        print(f"  Agent result: {result}")
    else:
        print(f"  Agent processing result: {result}")


def main():
    """
    Main function to demonstrate FACP capabilities
    """
    print("=" * 60)
    print("FIREAI AGENT COMMUNICATION PROTOCOL (FACP) DEMONSTRATION")
    print("=" * 60)
    
    # Setup logging
    setup_logging()
    
    try:
        # Create FACP runtime
        runtime = create_facp_runtime()
        
        # Demonstrate main flow
        demonstrate_facp_flow(runtime)
        
        # Demonstrate security features
        demonstrate_security_features(runtime)
        
        # Demonstrate agent orchestration
        demonstrate_agent_orchestration(runtime)
        
        # Show runtime statistics
        print("\nRuntime Statistics:")
        print(f"  Total agents registered: {len(runtime['agent_manager'].agents)}")
        print(f"  Engine execution stats: {runtime['engine'].get_stats()}")
        print(f"  Execution state machine stats: {runtime['execution_sm'].get_statistics()}")
        
        print("\n" + "=" * 60)
        print("FACP DEMONSTRATION COMPLETE")
        print("Note: This implementation is designed for Python 3.12+ environments")
        print("Some transport features may require additional dependencies")
        print("=" * 60)
        
    except Exception as e:
        print(f"Error during FACP demonstration: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()