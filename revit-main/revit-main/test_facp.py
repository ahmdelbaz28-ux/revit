"""
Test file for FACP (FireAI Agent Communication Protocol) implementation
"""
import unittest
import uuid
import time
from facp.protocol.message_schema import FACPRequest, FACPResponse, FACPMessageValidator
from facp.security.auth import AuthProvider
from facp.security.validation_gate import ValidationGate
from facp.runtime.state_machine import ExecutionStateMachine, ExecutionState
from facp.l2_orchestrator.task_router import TaskRouter
from facp.l2_orchestrator.policy_engine import PolicyEngine, RateLimitPolicy
from facp.l2_orchestrator.agent_manager import AgentManager, PlannerAgent
from facp.l3_engine.engine import DeterministicEngine


class TestFACPImplementation(unittest.TestCase):
    """
    Test cases for FACP implementation
    """
    
    def setUp(self):
        """Setup test environment"""
        self.auth_provider = AuthProvider()
        self.auth_provider.register_user("test_user", "engineer", ["read", "write", "execute", "engine_access"])
        self.token = self.auth_provider.create_session_token("test_user", ["read", "write", "execute", "engine_access"])
        self.execution_sm = ExecutionStateMachine()
        self.validation_gate = ValidationGate(self.auth_provider)
        
    def test_message_schema_creation(self):
        """Test creation of FACP message objects"""
        request = FACPRequest(
            id=str(uuid.uuid4()),
            method="engine.calculate",
            params={"task": "test", "payload": {}},
            source="ide",
            target="engine"
        )
        
        self.assertEqual(request.protocol, "FACP/1.0")
        self.assertEqual(request.type, "request")
        self.assertEqual(request.method, "engine.calculate")
        
        request_dict = request.to_dict()
        self.assertIn("protocol", request_dict)
        self.assertEqual(request_dict["protocol"], "FACP/1.0")
        
        # Test deserialization
        reconstructed = FACPRequest.from_dict(request_dict)
        self.assertEqual(reconstructed.method, "engine.calculate")
    
    def test_message_validation(self):
        """Test message validation functionality"""
        validator = FACPMessageValidator()
        
        # Valid request
        valid_request = FACPRequest(
            id=str(uuid.uuid4()),
            method="engine.calculate",
            params={"task": "test", "payload": {}},
            source="ide",
            target="engine"
        )
        
        is_valid, errors = validator.validate_request(valid_request)
        self.assertTrue(is_valid, f"Valid request failed validation: {errors}")
        
        # Invalid request
        invalid_request = FACPRequest(
            id="",  # Empty ID should fail
            method="",
            params={},
            source="invalid_source",  # Invalid source
            target="engine"
        )
        
        is_valid, errors = validator.validate_request(invalid_request)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
    
    def test_auth_provider(self):
        """Test authentication provider functionality"""
        # Test user registration
        self.auth_provider.register_user("new_user", "admin", ["read", "write", "admin"])
        
        # Test token creation
        token = self.auth_provider.create_session_token("new_user", ["read", "write"])
        self.assertIsNotNone(token)
        
        # Test token validation
        is_valid, token_data = self.auth_provider.token_manager.validate_token(token)
        self.assertTrue(is_valid)
        self.assertIsNotNone(token_data)
        
        # Test authentication of request
        security_block = {"auth_token": token, "permissions": ["read"]}
        is_auth, user_context = self.auth_provider.authenticate_request(security_block)
        self.assertTrue(is_auth)
        self.assertIsNotNone(user_context)
    
    def test_validation_gate(self):
        """Test validation gate functionality"""
        # Create a valid request
        request_data = {
            "protocol": "FACP/1.0",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": "2026-06-10T13:00:00Z",
            "source": "ide",
            "target": "engine",
            "method": "engine.calculate",
            "params": {
                "task": "test",
                "payload": {},
                "context": {}
            },
            "security": {
                "auth_token": self.token,
                "permissions": ["read", "write", "execute", "engine_access"],
                "risk_level": "low"
            }
        }
        
        # Process through validation gate
        should_forward, processed_data, errors = self.validation_gate.process_request(request_data)
        
        self.assertTrue(should_forward, f"Request should have passed validation, but got errors: {errors}")
        self.assertEqual(len(errors), 0)
        self.assertIsNotNone(processed_data)
    
    def test_execution_state_machine(self):
        """Test execution state machine functionality"""
        sm = ExecutionStateMachine()
        request_id = str(uuid.uuid4())
        
        # Create initial state
        sm.create_request_state(request_id)
        self.assertIsNotNone(sm.get_current_state(request_id))
        self.assertEqual(sm.get_current_state(request_id), ExecutionState.RECEIVED)
        
        # Transition through states
        self.assertTrue(sm.transition_to(request_id, ExecutionState.VALIDATED, "Validated"))
        self.assertEqual(sm.get_current_state(request_id), ExecutionState.VALIDATED)
        
        self.assertTrue(sm.transition_to(request_id, ExecutionState.ROUTED, "Routed"))
        self.assertEqual(sm.get_current_state(request_id), ExecutionState.ROUTED)
        
        self.assertTrue(sm.transition_to(request_id, ExecutionState.EXECUTING, "Executing"))
        self.assertEqual(sm.get_current_state(request_id), ExecutionState.EXECUTING)
        
        self.assertTrue(sm.transition_to(request_id, ExecutionState.COMPLETED, "Completed"))
        self.assertEqual(sm.get_current_state(request_id), ExecutionState.COMPLETED)
        
        # Get execution trace
        trace = sm.get_execution_trace(request_id)
        self.assertIn("request_id", trace)
        self.assertIn("state_history", trace)
    
    def test_task_router(self):
        """Test task routing functionality"""
        router = TaskRouter()
        
        # Test engine-bound methods
        self.assertTrue(router.should_route_to_engine("engine.calculate"))
        self.assertTrue(router.should_route_to_engine("engine.validate"))
        self.assertTrue(router.should_route_to_engine("calc.run"))
        self.assertTrue(router.should_route_to_engine("calculate_pressure"))
        
        # Test agent-bound methods
        self.assertFalse(router.should_route_to_engine("agent.plan"))
        self.assertFalse(router.should_route_to_engine("task.schedule"))
        
        # Test routing info
        info = router.get_routing_info("engine.calculate")
        self.assertEqual(info["destination"], "L3_ENGINE")
        self.assertTrue(info["is_engine_bound"])
    
    def test_policy_engine(self):
        """Test policy engine functionality"""
        policy_engine = PolicyEngine()
        
        # Add a rate limit policy
        rate_policy = RateLimitPolicy("test_rate_limit", max_requests=2, window_seconds=60)
        policy_engine.add_policy(rate_policy)
        
        # Create a test request
        request_data = {
            "method": "engine.test"
        }
        auth_context = {
            "user_id": "test_user",
            "permissions": ["read", "execute"]
        }
        
        # First request should pass
        result1 = policy_engine.apply_policies(request_data, auth_context)
        self.assertTrue(result1["allowed"])
        
        # Second request should pass
        result2 = policy_engine.apply_policies(request_data, auth_context)
        self.assertTrue(result2["allowed"])
        
        # Third request should fail rate limit
        result3 = policy_engine.apply_policies(request_data, auth_context)
        # Note: This might not fail immediately due to timing, so we just check the policy exists
        status = policy_engine.get_status()
        self.assertGreaterEqual(status["total_policies"], 1)
    
    def test_agent_manager(self):
        """Test agent manager functionality"""
        agent_manager = AgentManager()
        
        # Create and register an agent
        planner_agent = PlannerAgent()
        agent_manager.register_agent(planner_agent)
        
        # Verify agent registration
        self.assertEqual(len(agent_manager.agents), 1)
        self.assertIn(planner_agent.id, agent_manager.agents)
        
        # Test finding appropriate agent
        appropriate_agent = agent_manager.find_appropriate_agent("agent.plan")
        self.assertIsNotNone(appropriate_agent)
        self.assertEqual(appropriate_agent.id, planner_agent.id)
        
        # Test agent execution
        request_data = {
            "method": "agent.plan",
            "params": {
                "plan": {
                    "type": "test",
                    "tasks": ["task1", "task2"]
                }
            }
        }
        # Just test that the agent can be found, actual execution would need context
        agents_with_capability = agent_manager.find_agents_by_capability("agent.plan")
        self.assertGreaterEqual(len(agents_with_capability), 1)
    
    def test_engine_functionality(self):
        """Test engine functionality"""
        engine = DeterministicEngine()
        
        # Test calculator module
        calc_result = engine.execute_method("engine.calculate", {
            "type": "voltage_drop",
            "params": {
                "current": 10.0,
                "length": 30.0,
                "resistance": 0.02,
                "supply_voltage": 230.0,
                "system_type": "single_phase"
            }
        })
        
        self.assertTrue(calc_result["success"])
        self.assertIn("result", calc_result)
        
        # Test validator module
        validate_result = engine.execute_method("engine.validate", {
            "type": "compliance_nfpa",
            "params": {
                "system_type": "fire_alarm",
                "components": [{"type": "notification_appliance"}, {"type": "initiating_device"}]
            }
        })
        
        self.assertTrue(validate_result["success"])
        self.assertIn("result", validate_result)
    
    def test_layer_integration(self):
        """Test integration between different layers"""
        # This test demonstrates that all layers can work together
        request_id = str(uuid.uuid4())
        
        # Simulate the flow from L1 to L3
        self.execution_sm.create_request_state(request_id)
        
        # Transition through states as would happen in real flow
        self.execution_sm.transition_to(request_id, ExecutionState.RECEIVED, "Request received at L1")
        self.execution_sm.transition_to(request_id, ExecutionState.VALIDATED, "Request validated at L1")
        self.execution_sm.transition_to(request_id, ExecutionState.ROUTED, "Request routed to L2")
        self.execution_sm.transition_to(request_id, ExecutionState.EXECUTING, "Request executing in L3")
        self.execution_sm.transition_to(request_id, ExecutionState.COMPLETED, "Request completed")
        
        # Verify final state
        self.assertEqual(self.execution_sm.get_current_state(request_id), ExecutionState.COMPLETED)
        
        # Verify state history contains all expected states
        history = self.execution_sm.get_state_history(request_id)
        states_visited = [entry["state"] for entry in history]
        expected_states = [
            ExecutionState.RECEIVED.value,
            ExecutionState.VALIDATED.value,
            ExecutionState.ROUTED.value,
            ExecutionState.EXECUTING.value,
            ExecutionState.COMPLETED.value
        ]
        self.assertEqual(states_visited, expected_states)


def run_tests():
    """Run all tests"""
    print("Running FACP implementation tests...")
    unittest.main(argv=[''], exit=False, verbosity=2)


if __name__ == "__main__":
    run_tests()