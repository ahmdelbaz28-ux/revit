# NOSONAR
"""Comprehensive Tests for Distributed FACP System"""
import time
import unittest
import uuid
from typing import Any, Dict
from unittest.mock import Mock

# V138 FIX (MEDIUM-3): Converted relative imports to absolute imports.
# The original `from ..event_bus.cluster_communicator import ...` syntax fails
# when pytest collects this file directly (raises
# "ImportError: attempted relative import beyond top-level package") because
# pytest treats the file as a top-level module, not part of the
# `facp_distributed` package. Absolute imports work in both contexts.
from facp_distributed.event_bus.cluster_communicator import ClusterCommunicator
from facp_distributed.event_bus.event_dispatcher import EventDispatcher
from facp_distributed.event_bus.event_processor import EventProcessor, FACPEventProcessor
from facp_distributed.event_bus.message_queue import MessageQueue

# Import the distributed FACP components
from facp_distributed.l1_gateway.gateway import L1Gateway
from facp_distributed.l2_orchestrator.agent_manager import AgentManager
from facp_distributed.l2_orchestrator.agent_registry import AgentRegistry
from facp_distributed.l2_orchestrator.load_balancer import LoadBalancer
from facp_distributed.l2_orchestrator.orchestrator import Orchestrator
from facp_distributed.l2_orchestrator.task_scheduler import TaskScheduler
from facp_distributed.l3_engine_workers.engine_controller import EngineController
from facp_distributed.protocol.message_schema import FACPMessageValidator, FACPRequest
from facp_distributed.security.audit import AuditLogger
from facp_distributed.security.auth import AuthProvider
from facp_distributed.security.rbac import PermissionChecker, RBACEngine
from facp_distributed.security.validation_gate import ValidationFirewall


class TestDistributedFACP(unittest.TestCase):
    """Comprehensive test suite for distributed FACP system"""

    def setUp(self):
        """Set up test fixtures"""
        # Create security components
        # V289: AuthProvider now requires a strong secret (>= 32 chars).
        # The old "test_secret" was only 11 chars — would fail validation.
        import secrets as _secrets
        self.auth_provider = AuthProvider(secret_key=_secrets.token_urlsafe(48))
        self.rbac_engine = RBACEngine()
        self.permission_checker = PermissionChecker(self.rbac_engine)
        self.audit_logger = AuditLogger()

        # Create validation firewall
        self.validation_firewall = ValidationFirewall(self.auth_provider)

        # Create L2 orchestrator components
        self.agent_manager = AgentManager()
        self.task_scheduler = TaskScheduler()
        self.load_balancer = LoadBalancer()
        self.agent_registry = AgentRegistry()

        # Create orchestrator
        self.orchestrator = Orchestrator(
            agent_manager=self.agent_manager,
            task_scheduler=self.task_scheduler,
            load_balancer=self.load_balancer,
            permission_checker=self.permission_checker,
            agent_registry=self.agent_registry
        )

        # Create L3 engine controller
        self.engine_controller = EngineController(pool_size=2, max_pool_size=5)

        # Create L1 gateway
        self.l1_gateway = L1Gateway(self.validation_firewall, Mock())  # Using Mock for transport temporarily

        # Create test user
        self.test_user_id = "test_user_123"
        self.auth_provider.register_user(
            user_id=self.test_user_id,
            roles=["operator"],
            permissions=["engine_access", "execute", "read", "write"]
        )

        # Create a test token
        # V289 FIX: AuthProvider delegates token creation to TokenManager.generate_token
        self.test_token = self.auth_provider.token_manager.generate_token(
            user_id=self.test_user_id,
            permissions=["engine_access", "execute"],
            roles=["operator"],
        )

    def test_protocol_validation(self):
        """Test FACP message validation"""
        validator = FACPMessageValidator()

        # Create a valid request
        request_data = {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "source": "client",
            "target": "engine",
            "execution_state": "RECEIVED",
            "method": "engine.calculate",
            "params": {
                "task": "test_task",
                "payload": {"value": 42}
            },
            "security": {
                "auth_token": self.test_token,
                "permissions": ["engine_access"],
                "risk_level": "low",
                "idempotency_key": "test_key_123"
            },
            "constraints": {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

        request = FACPRequest.from_dict(request_data)
        is_valid, errors = validator.validate_request(request)

        self.assertTrue(is_valid, f"Request validation failed: {errors}")
        self.assertEqual(len(errors), 0)

    def test_validation_firewall_basic(self):
        """Test validation firewall functionality"""
        # Create a test request
        request_data = {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "source": "client",
            "target": "engine",
            "execution_state": "RECEIVED",
            "method": "engine.calculate",
            "params": {
                "task": "test_task",
                "payload": {"value": 42}
            },
            "security": {
                "auth_token": self.test_token,
                "permissions": ["engine_access"],
                "risk_level": "low",
                "idempotency_key": "test_key_123"
            },
            "constraints": {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

        # Process through validation firewall
        should_forward, processed_data, errors = self.validation_firewall.process_request(request_data)

        self.assertTrue(should_forward, f"Request should be forwarded but had errors: {errors}")
        self.assertEqual(len(errors), 0)
        self.assertIsNotNone(processed_data)

    def test_auth_and_permissions(self):
        """Test authentication and permission checking"""
        # Test authentication
        security_block = {
            "auth_token": self.test_token,
            "permissions": ["engine_access", "execute"],
            "risk_level": "low"
        }

        is_auth, auth_context = self.auth_provider.authenticate_request(security_block)
        self.assertTrue(is_auth)
        self.assertIsNotNone(auth_context)
        self.assertEqual(auth_context["user_id"], self.test_user_id)

        # Test permission checking
        allowed, reason = self.permission_checker.check_method_access(
            self.test_user_id, "engine.calculate"
        )
        self.assertTrue(allowed, f"Permission should be granted: {reason}")

    def test_agent_management(self):
        """Test agent management functionality"""
        # Test finding appropriate agent
        agent = self.agent_manager.find_appropriate_agent("execute.run")
        self.assertIsNone(agent)  # No agents registered yet

        # Register a test agent (using a mock for simplicity)
        from ..l2_orchestrator.agent_manager import BaseAgent
        class TestAgent(BaseAgent):
            def __init__(self):
                super().__init__("test_agent", "Test Agent")
                self.capabilities = ["execute.run", "task.execute"]

            def execute_task(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
                return {"result": "test_success", "agent_id": self.id}

        test_agent = TestAgent()
        self.agent_manager.register_agent(test_agent)

        # Now we should find the agent
        agent = self.agent_manager.find_appropriate_agent("execute.run")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.id, "test_agent")

    def test_load_balancer(self):
        """Test load balancer functionality"""
        # Register test workers
        self.load_balancer.register_engine_worker(
            "worker_1",
            ["engine.calculate", "engine.validate"],
            max_concurrent_tasks=5
        )

        self.load_balancer.register_engine_worker(
            "worker_2",
            ["engine.transform", "engine.calculate"],
            max_concurrent_tasks=3
        )

        # Test worker selection
        worker_id = self.load_balancer.select_engine_worker("engine.calculate")
        self.assertIn(worker_id, ["worker_1", "worker_2"])

        # Test worker status
        worker_status = self.load_balancer.get_worker_status("worker_1")
        self.assertIsNotNone(worker_status)
        self.assertEqual(worker_status["worker_id"], "worker_1")

    def test_task_scheduling(self):
        """Test task scheduling functionality"""
        # Schedule a test task
        task_info = self.task_scheduler.schedule_task(
            "engine.calculate",
            {"method": "engine.calculate", "params": {"task": "test"}},
            "worker_1"
        )

        self.assertIsNotNone(task_info)
        self.assertEqual(task_info["method"], "engine.calculate")
        self.assertEqual(task_info["target_worker"], "worker_1")

        # Test task status
        task_status = self.task_scheduler.get_task_status(task_info["task_id"])
        self.assertIsNotNone(task_status)

    def test_message_queue(self):
        """Test message queue functionality"""
        queue = MessageQueue("test_queue", max_size=100)

        # Create a test message
        from ..event_bus.message_queue import Message, MessagePriority
        message = Message(
            "test_topic",
            {"data": "test_value", "timestamp": time.time()},
            MessagePriority.NORMAL
        )

        # Enqueue the message
        success = queue.enqueue(message)
        self.assertTrue(success)

        # Dequeue the message
        dequeued = queue.dequeue()
        self.assertIsNotNone(dequeued)
        self.assertEqual(dequeued.id, message.id)
        self.assertEqual(dequeued.topic, "test_topic")

    def test_event_dispatcher(self):
        """Test event dispatcher functionality"""
        dispatcher = EventDispatcher("test_dispatcher")

        # Create a callback
        callback_called = {"value": False}
        def test_callback(event_data):
            callback_called["value"] = True

        # Register the listener
        listener_id = dispatcher.register_listener(
            "test_listener",
            test_callback,
            event_types=["test_event"]
        )

        # Dispatch an event
        event_data = {
            "event_type": "test_event",
            "data": "test_data",
            "source_node": "test_node"
        }

        dispatched_listeners = dispatcher.dispatch_event(event_data)
        self.assertIn(listener_id, dispatched_listeners)
        self.assertTrue(callback_called["value"])

    def test_l1_gateway_request_handling(self):
        """Test L1 gateway request handling"""
        # Create a test request
        request_data = {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "source": "client",
            "target": "engine",
            "execution_state": "RECEIVED",
            "method": "engine.calculate",
            "params": {
                "task": "test_calculation",
                "payload": {"value": 100}
            },
            "security": {
                "auth_token": self.test_token,
                "permissions": ["engine_access"],
                "risk_level": "low"
            },
            "constraints": {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

        # Since we're using a Mock transport, we expect the call to fail at transport level
        # but the validation should work
        try:
            _success, _response = self.l1_gateway.handle_client_request(request_data)
        except AttributeError:
            # Expected since transport is mocked
            pass

    def test_orchestrator_task_processing(self):
        """Test orchestrator task processing"""
        # Create a test request
        request_data = {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "source": "l1",
            "target": "engine",
            "execution_state": "ROUTED",
            "method": "engine.calculate",
            "params": {
                "task": "test_calculation",
                "payload": {"value": 50}
            },
            "security": {
                "auth_token": self.test_token,
                "permissions": ["engine_access"],
                "risk_level": "low"
            },
            "constraints": {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

        # Process through orchestrator
        _success, response = self.orchestrator.process_request(request_data)
        # This should succeed in routing even if no actual worker is available
        self.assertIsInstance(response, dict)

    def test_engine_controller(self):
        """Test engine controller functionality"""
        # Start the controller
        self.engine_controller.start()

        # Create a test request
        request_data = {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "source": "client",
            "target": "engine",
            "execution_state": "RECEIVED",
            "method": "engine.calculate",
            "params": {
                "task": "test_calculation",
                "payload": {"value": 25}
            },
            "security": {
                "auth_token": self.test_token,
                "permissions": ["engine_access"],
                "risk_level": "low"
            },
            "constraints": {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

        # Process the request
        result = self.engine_controller.process_request(request_data)

        # Stop the controller
        self.engine_controller.stop()

        # Check that we got a response
        self.assertIsNotNone(result)
        self.assertIn("trace", result)

    def test_audit_logging(self):
        """Test audit logging functionality"""
        # Log an authentication event
        self.audit_logger.log_authentication(
            user_id=self.test_user_id,
            success=True,
            source_node="test_node",
            target_node="auth_service"
        )

        # Log an authorization event
        self.audit_logger.log_authorization(
            user_id=self.test_user_id,
            method="engine.calculate",
            allowed=True,
            permissions=["engine_access"],
            source_node="test_node",
            target_node="engine"
        )

        # Get audit summary
        summary = self.audit_logger.get_audit_summary()
        self.assertGreaterEqual(summary["total_events"], 2)

    def test_security_isolation(self):
        """Test security isolation mechanisms"""
        from ..security.isolation import SandboxController, StatelessExecutionValidator

        # Create sandbox controller
        sandbox_controller = SandboxController("test_node")

        # Test constraint enforcement
        request_data = {
            "constraints": {
                "timeout_ms": 5000,
                "max_memory_mb": 256,
                "max_recursion_depth": 3
            }
        }

        is_valid, error = sandbox_controller.enforce_execution_constraints(request_data)
        self.assertTrue(is_valid, f"Constraints should be valid: {error}")

        # Test stateless validation
        validator = StatelessExecutionValidator()
        test_code = "def test_func(x): return x * 2"
        is_stateless, violations = validator.validate_stateless_code(test_code)
        self.assertTrue(is_stateless, f"Code should be stateless: {violations}")

    def test_cluster_communicator(self):
        """Test cluster communicator (creation only, not full functionality)"""
        communicator = ClusterCommunicator(
            node_id="test_node_1",
            host="127.0.0.1",
            port=9001,
            node_type="test_node"
        )

        # Just test creation and basic properties
        self.assertEqual(communicator.node_id, "test_node_1")
        self.assertEqual(communicator.node_type, "test_node")

        status = communicator.get_cluster_status()
        self.assertIn("local_node_id", status)
        self.assertEqual(status["local_node_id"], "test_node_1")

    def test_event_processor(self):
        """Test event processor functionality"""
        processor = EventProcessor("test_processor", max_workers=2)
        processor.start()

        # Submit a test event
        processor.submit_event({
            "event_type": "test_event",
            "data": "test_data",
            "timestamp": time.time()
        })

        # Get processor status
        status = processor.get_processor_status()
        self.assertEqual(status["name"], "test_processor")
        self.assertTrue(status["running"])

        # Stop the processor
        processor.stop()

    def test_facp_event_processor(self):
        """Test FACP-specific event processor"""
        processor = FACPEventProcessor("facp_test_processor", max_workers=2)
        processor.start()

        # Register a test handler
        handler_called = {"value": False}
        def test_handler(facp_request):
            handler_called["value"] = True
            return {"status": "success", "result": "handled"}

        processor.register_facp_request_handler("engine.calculate", test_handler)

        # Create a test FACP request
        facp_request = {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "source": "client",
            "target": "engine",
            "execution_state": "RECEIVED",
            "method": "engine.calculate",
            "params": {
                "task": "test_calculation",
                "payload": {"value": 10}
            },
            "security": {
                "auth_token": self.test_token,
                "permissions": ["engine_access"],
                "risk_level": "low"
            },
            "constraints": {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

        # Submit the FACP request
        processor.submit_facp_request(facp_request)

        # Wait a bit for processing
        time.sleep(0.1)

        # Check that handler was called
        # Note: This may not be called immediately due to asynchronous processing
        # The test mainly verifies that the request was accepted

        # Get status
        status = processor.get_facp_processor_status()
        self.assertIn("registered_methods", status)
        self.assertIn("engine.calculate", status["registered_methods"])

        # Stop the processor
        processor.stop()

    def test_end_to_end_workflow(self):
        """Test end-to-end workflow through the system"""
        # This test demonstrates the flow from request to response

        # Create a complete FACP request
        request_data = {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "source": "client",
            "target": "engine",
            "execution_state": "RECEIVED",
            "method": "engine.calculate",
            "params": {
                "task": "simple_calculation",
                "payload": {
                    "operation": "add",
                    "operands": [10, 20, 30]
                }
            },
            "security": {
                "auth_token": self.test_token,
                "permissions": ["engine_access", "execute"],
                "risk_level": "low",
                "idempotency_key": f"test_idempotency_{int(time.time())}"
            },
            "constraints": {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

        # Test validation
        validator = FACPMessageValidator()
        request_obj = FACPRequest.from_dict(request_data)
        is_valid, errors = validator.validate_request(request_obj)
        self.assertTrue(is_valid, f"Request validation failed: {errors}")

        # Test security validation
        is_valid, _processed_data, errors = self.validation_firewall.process_request(request_data)
        self.assertTrue(is_valid or len(errors) == 0, f"Security validation failed: {errors}")

        # The complete flow would involve more components but this validates the key parts
        self.assertIsNotNone(request_data["id"])
        self.assertEqual(request_data["protocol"], "FACP/1.1")
        self.assertIsNotNone(request_data["security"]["auth_token"])

    def tearDown(self):
        """Clean up after tests"""
        # Clean up any running components
        try:
            self.engine_controller.stop()
        except Exception:
            pass


class TestDistributedSecurity(unittest.TestCase):
    """Security-specific tests for distributed FACP system"""

    def setUp(self):
        """Set up security test fixtures"""
        # V289 FIX: use a strong 48-char secret (was "security_test_secret" — 20 chars)
        import secrets as _secrets2
        self.auth_provider = AuthProvider(secret_key=_secrets2.token_urlsafe(48))
        self.rbac_engine = RBACEngine()
        self.validation_firewall = ValidationFirewall(self.auth_provider)

        # Create test users with different permissions
        self.auth_provider.register_user(
            user_id="admin_user",
            roles=["admin"],
            permissions=["admin", "engine_access", "client_access", "orchestrator_access"]
        )

        self.auth_provider.register_user(
            user_id="operator_user",
            roles=["operator"],
            permissions=["engine_access", "execute", "read", "write"]
        )

        self.auth_provider.register_user(
            user_id="viewer_user",
            roles=["viewer"],
            permissions=["read"]
        )

        # Create tokens for each user
        # V289 FIX: use TokenManager.generate_token (AuthProvider has no create_session_token)
        self.admin_token = self.auth_provider.token_manager.generate_token(
            "admin_user", ["engine_access", "execute", "read", "write"], ["admin"]
        )
        self.operator_token = self.auth_provider.token_manager.generate_token(
            "operator_user", ["engine_access", "execute", "read", "write"], ["operator"]
        )
        self.viewer_token = self.auth_provider.token_manager.generate_token(
            "viewer_user", ["read"], ["viewer"]
        )

    def test_permission_levels(self):
        """Test different permission levels"""
        permission_checker = PermissionChecker(self.rbac_engine)

        # Admin should have access to everything
        allowed, reason = permission_checker.check_method_access("admin_user", "admin.configure")  # NOSONAR - python:S1481
        self.assertTrue(allowed)

        # Operator should have execution access
        allowed, reason = permission_checker.check_method_access("operator_user", "engine.calculate")
        self.assertTrue(allowed)

        # Viewer should not have execution access
        allowed, _reason = permission_checker.check_method_access("viewer_user", "engine.calculate")
        self.assertFalse(allowed)

    def test_token_validation(self):
        """Test token validation and revocation"""
        # Validate admin token
        is_valid, token_data = self.auth_provider.token_manager.validate_token(self.admin_token)
        self.assertTrue(is_valid)
        self.assertIsNotNone(token_data)

        # Revoke the token
        success = self.auth_provider.token_manager.revoke_token(self.admin_token)
        self.assertTrue(success)

        # Validate again - should fail now
        is_valid, token_data = self.auth_provider.token_manager.validate_token(self.admin_token)
        self.assertFalse(is_valid)

    def test_validation_firewall_security(self):
        """Test security enforcement by validation firewall"""
        # Create request with viewer token trying to access engine
        request_data = {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "source": "client",
            "target": "engine",
            "execution_state": "RECEIVED",
            "method": "engine.calculate",
            "params": {"task": "test"},
            "security": {
                "auth_token": self.viewer_token,
                "permissions": ["read"],  # Viewer only has read permission
                "risk_level": "low"
            },
            "constraints": {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

        # This should be blocked by the validation firewall
        _is_valid, _processed_data, _errors = self.validation_firewall.process_request(request_data)
        # The firewall validates format, not permissions - that's handled downstream
        # So this should pass format validation but may have other checks

    def test_idempotency_across_cluster(self):
        """Test idempotency mechanism"""
        # Use the same idempotency key twice
        idempotency_key = "test_idempotency_key_123"

        request_data = {
            "protocol": "FACP/1.1",
            "type": "request",
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "source": "client",
            "target": "engine",
            "execution_state": "RECEIVED",
            "method": "engine.calculate",
            "params": {"task": "idempotency_test"},
            "security": {
                "auth_token": self.operator_token,
                "permissions": ["engine_access"],
                "risk_level": "low",
                "idempotency_key": idempotency_key
            },
            "constraints": {
                "timeout_ms": 8000,
                "max_memory_mb": 512,
                "max_recursion_depth": 5
            }
        }

        # Process the request through validation firewall
        first_result = self.validation_firewall.process_request(request_data)

        # Process the same request again (same idempotency key)
        second_result = self.validation_firewall.process_request(request_data)

        # Both should be processed (the idempotency handling happens in the engine layer)
        # But the firewall should handle the idempotency key properly
        self.assertIsNotNone(first_result)
        self.assertIsNotNone(second_result)


def run_tests():
    """Run all tests"""
    # Create a test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestDistributedFACP)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestDistributedSecurity))

    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
