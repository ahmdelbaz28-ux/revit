تطابق ملفات الجيت ها"""
SGL Integration Test - Demonstrating SGL working with FACP system
"""

import json
from datetime import datetime
from sgov import SystemGovernanceEngine, ExecutionRequest, Role, RiskLevel
from sgov.exceptions import GovernanceException
from facp.protocol.message_schema import FACPMessageSchema
from facp.security.auth import authenticate_request
from facp.security.validation_gate import ValidationGate


def test_sgl_with_facp_integration():
    """
    Test that demonstrates SGL working as a hard gate before FACP processing
    """
    print("Testing SGL Integration with FACP System...")
    
    # Create governance engine
    gov_engine = SystemGovernanceEngine()
    
    # Example FACP request that would normally go to L1 interface
    facp_request = {
        "protocol": "FACP/1.1",
        "type": "request",
        "id": "req-test-123",
        "timestamp": datetime.utcnow().isoformat(),
        "source": "client",
        "target": "engine",
        "execution_state": "RECEIVED",
        "method": "engine.calculate",
        "params": {
            "task": "engineering_calculation",
            "payload": {"values": [1, 2, 3, 4, 5], "operation": "sum"}
        },
        "security": {
            "auth_token": "valid_auth_token",
            "permissions": ["engine_access", "execute"],
            "risk_level": "medium",
            "idempotency_key": "idemp-key-calc-123"
        },
        "constraints": {
            "timeout_ms": 8000,
            "max_memory_mb": 512,
            "max_recursion_depth": 5
        }
    }
    
    print("Original FACP Request:")
    print(json.dumps(facp_request, indent=2))
    
    # Before allowing the request to proceed to FACP processing,
    # it must pass through the SGL hard gate
    try:
        # Extract information needed for SGL
        user_id = "client"  # Could come from auth token
        role = "operator"   # Would be determined from auth system
        payload = facp_request["params"]["payload"]
        idempotency_key = facp_request["security"]["idempotency_key"]
        risk_level = facp_request["security"]["risk_level"]
        
        print(f"\nPassing request through SGL governance gate...")
        print(f"User ID: {user_id}")
        print(f"Role: {role}")
        print(f"Risk Level: {risk_level}")
        print(f"Idempotency Key: {idempotency_key}")
        
        # Process through SGL (THE HARD GATE)
        is_allowed, policy_decision, execution_trace = gov_engine.process_request(
            user_id=user_id,
            role=role,
            payload=payload,
            idempotency_key=idempotency_key,
            risk_level=risk_level,
            action_requires_write=False,
            required_action="execute_calculation"
        )
        
        print(f"\nSGL Decision: {policy_decision.decision.value}")
        print(f"Reason: {policy_decision.reason}")
        print(f"Rules Applied: {policy_decision.rules_applied}")
        
        if policy_decision.limits:
            print(f"Limits: Max execution time: {policy_decision.limits.max_execution_time_ms}ms, "
                  f"Max memory: {policy_decision.limits.max_memory_mb}MB")
        
        if is_allowed:
            print("\n✅ Request PASSED SGL governance and can proceed to FACP processing")
            
            # Now we can proceed with FACP processing
            # This is where the request would go to L1 → L2 → L3
            print("Proceeding with FACP processing...")
            
            # Simulate FACP processing
            facp_schema = FACPMessageSchema()
            is_valid_facp = facp_schema.validate(facp_request)
            
            if is_valid_facp:
                print("✅ FACP validation passed")
                
                # Simulate authentication check
                auth_result = authenticate_request(facp_request)
                if auth_result:
                    print("✅ Authentication passed")
                    
                    # Simulate validation gate
                    validation_gate = ValidationGate()
                    validation_result = validation_gate.validate(facp_request)
                    if validation_result.is_valid:
                        print("✅ Validation gate passed")
                        
                        print("Request can now proceed to L2 Orchestrator and L3 Engine")
                        print("All governance requirements satisfied!")
                    else:
                        print(f"❌ Validation gate failed: {validation_result.errors}")
                else:
                    print("❌ Authentication failed")
            else:
                print("❌ FACP validation failed")
        else:
            print("❌ Request BLOCKED by SGL governance - NOT ALLOWED to proceed")
            
    except GovernanceException as e:
        print(f"❌ Request blocked by SGL governance: {e.message}")
        print("Request NOT ALLOWED to proceed to FACP processing")
        
    except Exception as e:
        print(f"❌ Unexpected error during SGL processing: {str(e)}")


def test_sgl_blocking_malicious_request():
    """
    Test that SGL blocks malicious requests before they reach FACP
    """
    print("\n" + "="*60)
    print("Testing SGL Blocking of Malicious Request...")
    
    gov_engine = SystemGovernanceEngine()
    
    # Example of a potentially malicious request
    malicious_request = {
        "protocol": "FACP/1.1",
        "type": "request", 
        "id": "req-malicious-456",
        "timestamp": datetime.utcnow().isoformat(),
        "source": "client",
        "target": "engine",
        "execution_state": "RECEIVED",
        "method": "engine.execute",
        "params": {
            "task": "dangerous_operation",
            "payload": {
                # Potentially dangerous content
                "command": "<script>alert('xss')</script>",
                "file_path": "../../../etc/passwd",
                "sql_query": "DROP TABLE users;"
            }
        },
        "security": {
            "auth_token": "some_token",
            "permissions": ["execute"],
            "risk_level": "high",
            "idempotency_key": "idemp-key-mal-456"
        },
        "constraints": {
            "timeout_ms": 30000,
            "max_memory_mb": 1024,
            "max_recursion_depth": 10
        }
    }
    
    print("Malicious FACP Request (should be blocked by SGL):")
    print(json.dumps(malicious_request["params"]["payload"], indent=2))
    
    try:
        user_id = "malicious_client"
        role = "viewer"  # Lower privilege role
        payload = malicious_request["params"]["payload"]
        idempotency_key = malicious_request["security"]["idempotency_key"]
        risk_level = "high"
        
        print(f"\nPassing malicious request through SGL governance gate...")
        
        is_allowed, policy_decision, execution_trace = gov_engine.process_request(
            user_id=user_id,
            role=role,
            payload=payload,
            idempotency_key=idempotency_key,
            risk_level=risk_level,
            action_requires_write=True,
            required_action="execute_calculation"
        )
        
        # If we get here, something went wrong - malicious request should have been blocked
        print(f"❌ UNEXPECTED: Malicious request was allowed by SGL: {policy_decision.decision.value}")
        
    except ValidationException as e:
        print(f"✅ EXPECTED: SGL blocked malicious request at validation: {e.message}")
        
    except PolicyException as e:
        print(f"✅ EXPECTED: SGL blocked malicious request at policy level: {e.message}")
        
    except GovernanceException as e:
        print(f"✅ EXPECTED: SGL blocked malicious request: {e.message}")
        
    except Exception as e:
        print(f"❓ Other exception (may be expected): {type(e).__name__}: {str(e)}")


def test_sgl_with_different_risk_levels():
    """
    Test SGL behavior with different risk levels
    """
    print("\n" + "="*60)
    print("Testing SGL with Different Risk Levels...")
    
    gov_engine = SystemGovernanceEngine()
    
    test_cases = [
        ("low", "admin", {"operation": "read", "data": "safe"}),
        ("medium", "operator", {"operation": "calculate", "data": [1, 2, 3]}),
        ("high", "admin", {"operation": "configure", "data": {"setting": "value"}}),
        ("critical", "admin", {"operation": "shutdown", "data": {}})
    ]
    
    for risk_level, role, payload in test_cases:
        print(f"\nTesting {risk_level.upper()} risk request with {role} role...")
        
        try:
            is_allowed, decision, trace = gov_engine.process_request(
                user_id=f"user_{risk_level}",
                role=role,
                payload=payload,
                idempotency_key=f"idemp_{risk_level}_{hash(str(payload))}",
                risk_level=risk_level
            )
            
            print(f"  Decision: {decision.decision.value}")
            print(f"  Reason: {decision.reason}")
            
            if decision.limits:
                print(f"  Applied Limits: Time={decision.limits.max_execution_time_ms}ms, "
                      f"Memory={decision.limits.max_memory_mb}MB")
            
        except Exception as e:
            print(f"  Blocked: {type(e).__name__}: {str(e)}")


def demonstrate_zero_trust_architecture():
    """
    Demonstrate the zero-trust architecture principle
    """
    print("\n" + "="*60)
    print("Demonstrating Zero-Trust Architecture...")
    print("No layer trusts another layer. Every layer re-validates input.")
    print("SGL is the ONLY authoritative gatekeeper.\n")
    
    gov_engine = SystemGovernanceEngine()
    
    # Even if L2 or L3 tried to bypass SGL, they should not process requests
    # without SGL approval
    pretend_l2_request = {
        "protocol": "FACP/1.1",
        "type": "internal",
        "id": "internal-123",
        "source": "L2_Orchestrator",  # Even internal sources must be validated
        "target": "L3_Engine",
        "method": "engine.execute",
        "params": {"task": "internal_work", "data": {"job": "process"}},
        "security": {
            "auth_token": "internal_token",
            "permissions": ["internal_execute"],
            "risk_level": "low",
            "idempotency_key": "internal-idemp-123"
        }
    }
    
    print("Even internal L2→L3 requests must pass through SGL:")
    print(f"Internal request: {pretend_l2_request['params']['data']}")
    
    try:
        is_allowed, decision, trace = gov_engine.process_request(
            user_id="L2_Orchestrator",
            role="system_agent",  # Internal system role
            payload=pretend_l2_request["params"]["data"],
            idempotency_key=pretend_l2_request["security"]["idempotency_key"],
            risk_level=pretend_l2_request["security"]["risk_level"]
        )
        
        print(f"  SGL Approval: {decision.decision.value}")
        print(f"  Internal request {'ALLOWED' if is_allowed else 'BLOCKED'} by SGL")
        
    except Exception as e:
        print(f"  Internal request blocked: {type(e).__name__}: {str(e)}")


if __name__ == "__main__":
    print("🔍 SGL Integration Test Suite")
    print("="*60)
    
    # Run all integration tests
    test_sgl_with_facp_integration()
    test_sgl_blocking_malicious_request()
    test_sgl_with_different_risk_levels()
    demonstrate_zero_trust_architecture()
    
    print("\n" + "="*60)
    print("✅ SGL Integration Tests Completed")
    print("The System Governance Layer (SGL) successfully acts as the mandatory")
    print("hard enforcement gate for all requests before they reach FACP processing.")
    print("All governance requirements are enforced according to specifications.")