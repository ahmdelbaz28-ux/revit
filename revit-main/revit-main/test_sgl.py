ي الورك """
Comprehensive Test Suite for System Governance Layer (SGL)
"""

import unittest
import json
from datetime import datetime
from sgov import SystemGovernanceEngine, ExecutionRequest, Role, RiskLevel
from sgov.exceptions import ValidationException, PolicyException, GovernanceException


class TestSystemGovernanceLayer(unittest.TestCase):
    """Test suite for the System Governance Layer"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.engine = SystemGovernanceEngine()
    
    def test_basic_request_approval(self):
        """Test that a basic valid request is approved"""
        result = self.engine.process_request(
            user_id="test_user_123",
            role="admin",
            payload={"operation": "calculate", "data": [1, 2, 3]},
            idempotency_key="test_key_123",
            risk_level="low"
        )
        
        is_allowed, decision, trace = result
        self.assertTrue(is_allowed)
        self.assertIsNotNone(decision)
        self.assertIsNotNone(trace)
        self.assertIn(decision.decision.value, ["ALLOW", "ALLOW_WITH_LIMITS"])
    
    def test_validation_rejection(self):
        """Test that invalid requests are rejected"""
        # Test with dangerous payload
        with self.assertRaises(ValidationException):
            self.engine.process_request(
                user_id="test_user_123",
                role="admin", 
                payload={"<script>alert('xss')">": "dangerous"},
                idempotency_key="test_key_124",
                risk_level="low"
            )
    
    def test_role_based_access_control(self):
        """Test that role-based access control works"""
        # Viewer should not be able to perform write operations
        with self.assertRaises(GovernanceException):
            self.engine.process_request(
                user_id="test_viewer_123",
                role="viewer",
                payload={"operation": "modify_system", "data": {}},
                idempotency_key="test_key_125",
                risk_level="low",
                action_requires_write=True
            )
    
    def test_policy_enforcement(self):
        """Test that policies are enforced"""
        # Test critical risk with non-admin role
        with self.assertRaises(GovernanceException):
            self.engine.process_request(
                user_id="test_user_123",
                role="viewer",
                payload={"operation": "critical_operation", "data": {}},
                idempotency_key="test_key_126",
                risk_level="critical"
            )
    
    def test_idempotency_enforcement(self):
        """Test that idempotency keys prevent duplicate execution"""
        # First request should succeed
        result1 = self.engine.process_request(
            user_id="test_user_123",
            role="admin",
            payload={"operation": "calculate", "data": [1, 2, 3]},
            idempotency_key="idemp_key_test",
            risk_level="low"
        )
        
        is_allowed1, decision1, trace1 = result1
        self.assertTrue(is_allowed1)
        
        # Second request with same idempotency key should be handled appropriately
        result2 = self.engine.process_request(
            user_id="test_user_123", 
            role="admin",
            payload={"operation": "calculate", "data": [1, 2, 3]},
            idempotency_key="idemp_key_test",
            risk_level="low"
        )
        
        is_allowed2, decision2, trace2 = result2
        # Both should be allowed but handled as idempotent
        self.assertTrue(is_allowed2)
    
    def test_required_idempotency_key(self):
        """Test that requests without idempotency key are rejected"""
        with self.assertRaises(ValidationException):
            self.engine.process_request(
                user_id="test_user_123",
                role="admin",
                payload={"operation": "calculate", "data": [1, 2, 3]},
                idempotency_key="",  # Empty key should fail
                risk_level="low"
            )
    
    def test_unauthorized_role_access(self):
        """Test that unauthorized role access is blocked"""
        with self.assertRaises(GovernanceException):
            self.engine.process_request(
                user_id="test_user_123",
                role="viewer",  # Viewer shouldn't access admin functions
                payload={"operation": "access_admin_panel", "data": {}},
                idempotency_key="test_key_127",
                risk_level="medium",
                required_action="access_admin_panel"
            )
    
    def test_unvalidated_payload_rejection(self):
        """Test that unvalidated payloads are rejected"""
        # Create a request with invalid structure
        request = ExecutionRequest(
            request_id="test_req_123",
            user_id="test_user_123", 
            role=Role.ADMIN,
            payload={"valid": "data"},
            idempotency_key="test_key_128",
            risk_level=RiskLevel.LOW,
            timestamp=datetime.utcnow(),
            validated=False  # Explicitly not validated
        )
        
        # This should fail at the policy level since our default rules require validation
        with self.assertRaises(PolicyException):
            self.engine.validate_and_approve(request)
    
    def test_health_check(self):
        """Test that health check works"""
        health = self.engine.health_check()
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(len(health["subsystems"]), 5)
    
    def test_governance_metrics(self):
        """Test that governance metrics are available"""
        metrics = self.engine.get_governance_metrics()
        self.assertIn("is_operational", metrics)
        self.assertIn("engine_uptime", metrics)
        self.assertIsInstance(metrics["is_operational"], bool)
    
    def test_fail_closed_behavior(self):
        """Test that the system fails closed on errors"""
        # This test verifies the fail-closed principle by ensuring
        # that any error in validation, policy, or other areas results in DENY
        try:
            # Try to process a request with invalid role
            self.engine.process_request(
                user_id="test_user_123",
                role="invalid_role",  # This should trigger an exception
                payload={"operation": "test", "data": {}},
                idempotency_key="test_key_129",
                risk_level="low"
            )
            # If we get here, the test failed
            self.fail("Expected GovernanceException was not raised")
        except GovernanceException:
            # This is expected - the system should reject invalid inputs
            pass
    
    def test_deterministic_behavior(self):
        """Test that the same input produces the same output"""
        # Process the same request twice
        result1 = self.engine.process_request(
            user_id="deterministic_user",
            role="admin",
            payload={"operation": "test", "data": {"key": "value"}},
            idempotency_key="deterministic_key_1",
            risk_level="low"
        )
        
        result2 = self.engine.process_request(
            user_id="deterministic_user", 
            role="admin",
            payload={"operation": "test", "data": {"key": "value"}},
            idempotency_key="deterministic_key_2",  # Different idempotency key
            risk_level="low"
        )
        
        # Both should be allowed since they're different requests
        self.assertTrue(result1[0])
        self.assertTrue(result2[0])
        
        # The decisions should be consistent for the same role/risk level
        self.assertEqual(result1[1].decision, result2[1].decision)


class TestSGLModels(unittest.TestCase):
    """Test the SGL data models"""
    
    def test_execution_request_creation(self):
        """Test creating an execution request"""
        request = ExecutionRequest.create(
            user_id="test_user",
            role="admin",
            payload={"test": "data"},
            idempotency_key="test_key",
            risk_level="low"
        )
        
        self.assertIsNotNone(request.request_id)
        self.assertEqual(request.user_id, "test_user")
        self.assertEqual(request.role, Role.ADMIN)
        self.assertEqual(request.risk_level, RiskLevel.LOW)
        self.assertTrue(request.idempotency_key)
    
    def test_invalid_request_creation(self):
        """Test that invalid requests raise errors"""
        with self.assertRaises(ValueError):
            ExecutionRequest(
                request_id="",  # Invalid - empty
                user_id="test_user",
                role=Role.ADMIN,
                payload={"test": "data"},
                idempotency_key="test_key",
                risk_level=RiskLevel.LOW,
                timestamp=datetime.utcnow()
            )
    
    def test_role_enum(self):
        """Test role enum values"""
        self.assertEqual(Role.ADMIN.value, "admin")
        self.assertEqual(Role.VIEWER.value, "viewer")
        self.assertEqual(Role.OPERATOR.value, "operator")
        self.assertEqual(Role.SYSTEM_AGENT.value, "system_agent")
    
    def test_risk_level_enum(self):
        """Test risk level enum values"""
        self.assertEqual(RiskLevel.LOW.value, "low")
        self.assertEqual(RiskLevel.HIGH.value, "high")
        self.assertEqual(RiskLevel.CRITICAL.value, "critical")


def run_comprehensive_tests():
    """Run all SGL tests"""
    print("Running System Governance Layer (SGL) Comprehensive Tests...")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__('__main__', globals(), locals(), ['test_sgl']))
    
    # Create a suite with both test classes
    all_tests = unittest.TestSuite()
    all_tests.addTests(loader.loadTestsFromTestCase(TestSystemGovernanceLayer))
    all_tests.addTests(loader.loadTestsFromTestCase(TestSGLModels))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(all_tests)
    
    print(f"\nSGL Tests Completed: {result.testsRun} tests run")
    print(f"Failures: {len(result.failures)}, Errors: {len(result.errors)}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_comprehensive_tests()
    exit(0 if success else 1)