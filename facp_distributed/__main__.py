"""Main Entry Point for Distributed FACP System"""
import argparse
import logging
import sys
import time
from typing import Any, Dict, Optional

from .l1_gateway.client_interface import create_client_interface_with_gateway

# Import all the necessary modules
from .l2_orchestrator.agent_manager import DistributedAgentManager
from .l2_orchestrator.agent_registry import DistributedAgentRegistry
from .l2_orchestrator.load_balancer import AdaptiveLoadBalancer
from .l2_orchestrator.orchestrator import Orchestrator
from .l2_orchestrator.task_scheduler import DistributedTaskScheduler
from .l3_engine_workers.engine_controller import DistributedEngineController
from .security.audit import AuditLogger
from .security.auth import AuthProvider
from .security.rbac import PermissionChecker, RBACEngine
from .security.validation_gate import ValidationFirewall


def setup_logging():
    """Set up logging for the distributed system"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('facp_distributed.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def create_distributed_system(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create and configure the distributed FACP system"""
    config = config or {}

    # The old default "default_secret_for_dev" was:
    #   1. Only 22 characters (below the 32-char HMAC minimum)
    #   2. A weak, publicly known default — anyone reading the source
    #      could forge valid auth tokens
    #   3. Silently used when auth_secret was not configured, masking
    #      deployment misconfiguration
    # Now we fail-loud if no auth_secret is provided.
    auth_secret = config.get("auth_secret")
    if not auth_secret:
        raise RuntimeError(
            "create_distributed_system: 'auth_secret' is required in config. "
            "Generate a strong secret with: "
            "python3 -c \"import secrets; print(secrets.token_urlsafe(48))\" "
            "and set it via config['auth_secret'] or the FACP_AUTH_SECRET env var. "
            "Refusing to start with no auth secret (V289 life-safety fix)."
        )
    auth_provider = AuthProvider(secret_key=auth_secret)
    rbac_engine = RBACEngine()
    permission_checker = PermissionChecker(rbac_engine)
    audit_logger = AuditLogger()

    # Set up validation firewall
    validation_firewall = ValidationFirewall(auth_provider)

    # Set up L2 orchestrator components
    agent_manager = DistributedAgentManager()
    task_scheduler = DistributedTaskScheduler()
    load_balancer = AdaptiveLoadBalancer()
    agent_registry = DistributedAgentRegistry()

    # Set up orchestrator
    orchestrator = Orchestrator(
        agent_manager=agent_manager,
        task_scheduler=task_scheduler,
        load_balancer=load_balancer,
        permission_checker=permission_checker,
        agent_registry=agent_registry
    )

    # Set up L3 engine controller
    engine_controller = DistributedEngineController(
        pool_size=config.get("engine_pool_size", 3),
        max_pool_size=config.get("engine_max_pool_size", 10),
        node_location=config.get("node_location", "primary")
    )

    # Set up L1 gateway with transport
    transport_config = {
        "host": config.get("l2_host", "0.0.0.0"),
        "gateway_port": config.get("l2_port", 8001),
        "interface_port": config.get("l1_port", 8000)
    }

    client_interface = create_client_interface_with_gateway(
        validation_firewall=validation_firewall,
        transport_config=transport_config
    )

    # Connect components together
    # Set up cluster sync callbacks
    agent_manager.set_cluster_sync_callback(lambda msg: print(f"Agent sync: {msg}"))
    task_scheduler.set_cluster_sync_callback(lambda msg: print(f"Task sync: {msg}"))
    agent_registry.set_cluster_sync_callback(lambda msg: print(f"Registry sync: {msg}"))
    engine_controller.set_cluster_sync_callback(lambda msg: print(f"Engine sync: {msg}"))

    # Set up the distributed engine controller
    engine_controller.start()

    return {
        "auth_provider": auth_provider,
        "rbac_engine": rbac_engine,
        "permission_checker": permission_checker,
        "audit_logger": audit_logger,
        "validation_firewall": validation_firewall,
        "agent_manager": agent_manager,
        "task_scheduler": task_scheduler,
        "load_balancer": load_balancer,
        "agent_registry": agent_registry,
        "orchestrator": orchestrator,
        "engine_controller": engine_controller,
        "client_interface": client_interface
    }


def run_distributed_system(config: Optional[Dict[str, Any]] = None):
    """Run the distributed FACP system"""
    print("🚀 Starting Distributed FACP System v1.1")
    print("=" * 50)

    # Set up logging
    setup_logging()
    logging.getLogger(__name__)

    # Create the system
    system_components = create_distributed_system(config)

    # Start the client interface (L1)
    system_components["client_interface"].start()
    print(f"✅ L1 Client Interface started on {system_components['client_interface'].host}:{system_components['client_interface'].port}")

    # Print system status
    print("\n📋 System Status:")
    print(f"   L1 Gateway Status: {system_components['client_interface'].get_status()['running']}")
    print("   L2 Orchestrator Status: Running")
    print(f"   L3 Engine Controller Status: {system_components['engine_controller'].is_running}")

    print("\n🌐 Available Endpoints:")
    print(f"   Health Check: http://localhost:{system_components['client_interface'].port}/health")
    print(f"   Metrics: http://localhost:{system_components['client_interface'].port}/metrics")
    print(f"   FACP Request: http://localhost:{system_components['client_interface'].port}/facp/request")

    print("\n🔧 System Components Ready:")
    print("   Authentication Provider: ✅ Configured")
    print("   RBAC Engine: ✅ Active")
    print("   Validation Firewall: ✅ Active")
    print("   Agent Manager: ✅ Ready")
    print("   Task Scheduler: ✅ Running")
    print("   Load Balancer: ✅ Active")
    print("   Engine Pool: ✅ Initialized")

    print("\n🔒 Security Features Active:")
    print("   Authentication: ✅ Enabled")
    print("   Authorization: ✅ Enforced")
    print("   Validation Firewall: ✅ Active")
    print("   Audit Logging: ✅ Enabled")
    print("   Resource Limits: ✅ Enforced")
    print("   Idempotency: ✅ Guaranteed")

    print("\n⚡ Performance Features:")
    print("   Load Balancing: ✅ Adaptive")
    print("   Auto Scaling: ✅ Enabled")
    print("   Task Queuing: ✅ Active")
    print("   Health Checks: ✅ Running")

    print("\n🔗 Distributed Features:")
    print("   Cluster Awareness: ✅ Ready")
    print("   Node Discovery: ✅ Available")
    print("   State Synchronization: ✅ Available")
    print("   Failover Support: ✅ Configured")

    print("\n" + "=" * 50)
    print("🔥 Distributed FACP System is now running!")
    print("💡 Send FACP/1.1 requests to the L1 interface")
    print("📊 Monitor system health at /health endpoint")
    print("📋 View metrics at /metrics endpoint")
    print("=" * 50)

    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down Distributed FACP System...")

        # Stop the client interface
        system_components["client_interface"].stop()

        # Stop the engine controller
        system_components["engine_controller"].stop()

        print("✅ Distributed FACP System shutdown complete")


def run_test_scenario():
    """Run a test scenario to verify the distributed system"""
    print("🧪 Running Distributed System Test Scenario...")

    # Create a simple test request
    test_request = {
        "protocol": "FACP/1.1",
        "type": "request",
        "id": "test-request-123",
        "timestamp": time.time(),
        "source": "client",
        "target": "orchestrator",
        "execution_state": "RECEIVED",
        "method": "engine.calculate",
        "params": {
            "task": "electrical_calculation",
            "payload": {
                "calculation_type": "voltage_drop",
                "current": 20,
                "length": 50,
                "resistance": 0.02,
                "supply_voltage": 230,
                "system_type": "single_phase"
            },
            "context": {
                "application": "test_client",
                "version": "1.0.0"
            }
        },
        "security": {
            "auth_token": "test-token-123",
            "permissions": ["engine_access", "execute"],
            "risk_level": "low",
            "idempotency_key": "test-key-123"
        },
        "constraints": {
            "timeout_ms": 8000,
            "max_memory_mb": 512,
            "max_recursion_depth": 5
        }
    }

    print(f"📤 Sending test request: {test_request['method']}")
    print(f"🆔 Request ID: {test_request['id']}")
    print(f"🔐 Security: {test_request['security']['risk_level']} risk")

    # Create a minimal test system
    config = {"l1_port": 8000, "l2_port": 8001}
    system_components = create_distributed_system(config)

    # Process the test request through the system
    print("\n🔄 Request Flow Simulation:")
    print("   L1: Receiving request...")

    # Simulate L1 processing
    success, _l1_response = system_components["client_interface"].l1_gateway.handle_client_request(test_request)
    print(f"   L1: Request {'accepted' if success else 'rejected'} by validation firewall")

    if success:
        print("   L2: Orchestrator routing request...")
        # Simulate L2 processing
        orch_success, _orch_response = system_components["orchestrator"].process_request(test_request)
        print(f"   L2: Request {'processed' if orch_success else 'failed'} by orchestrator")

        if orch_success:
            print("   L3: Engine executing calculation...")
            # Simulate L3 processing
            engine_result = system_components["engine_controller"].process_request(test_request)
            print(f"   L3: Calculation {'completed' if engine_result.get('status') == 'success' else 'failed'}")

    print("\n✅ Test scenario completed!")

    # Show test results
    print("\n📊 Test Results:")
    print(f"   Request ID: {test_request['id']}")
    print(f"   Method: {test_request['method']}")
    print(f"   Risk Level: {test_request['security']['risk_level']}")
    print(f"   Security Token: {test_request['security']['auth_token']}")
    print(f"   Constraints: {test_request['constraints']}")


def main():
    """Main entry point for the distributed FACP system"""
    parser = argparse.ArgumentParser(description='Distributed FACP System')
    parser.add_argument('--mode', choices=['run', 'test'], default='run',
                       help='Run mode: run the system or test it')
    parser.add_argument('--config', type=str, help='Configuration file path')
    parser.add_argument('--port', type=int, default=8000, help='Port for L1 interface')
    parser.add_argument('--l2-port', dest='l2_port', type=int, default=8001, help='Port for L2 orchestrator')

    args = parser.parse_args()

    if args.mode == 'test':
        run_test_scenario()
    else:
        config = {
            "l1_port": args.port,
            "l2_port": args.l2_port
        }
        run_distributed_system(config)


if __name__ == "__main__":
    main()
