# Distributed FireAI Agent Communication Protocol (FACP) System v1.1

## Overview

The Distributed FireAI Agent Communication Protocol (FACP) System is a production-ready, distributed architecture designed to facilitate secure, reliable communication between AI agents and engineering systems across multiple nodes. This system implements the FACP/1.1 specification with a three-plane distributed model.

## Architecture

The system follows a strict three-layer separation:

```
┌──────────────────────────────┐
│ L1: External Clients (IDE)   │
└─────────────┬────────────────┘
              │ HTTP / WebSocket
              ▼
┌──────────────────────────────┐
│ L2: Orchestrator Cluster     │  (Stateful)
│ - Agent routing              │
│ - Policy engine             │
│ - Task decomposition        │
│ - Load balancing            │
└─────────────┬────────────────┘
              │ Event Bus (Redis/NATS abstraction)
              ▼
┌──────────────────────────────┐
│ L3: Engine Worker Cluster    │  (Stateless)
│ - Deterministic execution    │
│ - Power system computation   │
│ - Sandboxed runtime          │
└──────────────────────────────┘
```

## Features

- **Distributed Architecture**: Multi-node support with cluster coordination
- **Security First**: Three-tier validation firewall with RBAC
- **Deterministic Execution**: State-free engine nodes for reproducible results
- **Scalable Design**: Horizontal scaling for both orchestrator and engine nodes
- **Fault Tolerance**: Node failure handling and recovery mechanisms
- **Idempotency**: Distributed idempotency guarantees
- **Resource Management**: Execution constraints and sandboxing
- **Monitoring**: Built-in metrics and health checks

## Installation

```bash
pip install facp-distributed
```

## Quick Start

### Running a Single Node

```bash
# Start the distributed system
python -m facp_distributed --mode run --port 8000
```

### Running in Test Mode

```bash
# Run a test scenario
python -m facp_distributed --mode test
```

### Configuration

Create a configuration file (`config.yaml`):

```yaml
auth_secret: "your-secret-key-here"
engine_pool_size: 3
engine_max_pool_size: 10
node_location: "primary"
l1_port: 8000
l2_port: 8001
```

## Usage

### Sending Requests

The system accepts FACP/1.1 requests:

```json
{
  "protocol": "FACP/1.1",
  "type": "request",
  "id": "unique-request-id",
  "timestamp": "2023-10-01T10:00:00Z",
  "source": "client",
  "target": "engine",
  "execution_state": "RECEIVED",
  "method": "engine.calculate",
  "params": {
    "task": "electrical_calculation",
    "payload": {
      "calculation_type": "voltage_drop",
      "current": 20,
      "length": 50,
      "resistance": 0.02,
      "supply_voltage": 230
    }
  },
  "security": {
    "auth_token": "valid-jwt-token",
    "permissions": ["engine_access", "execute"],
    "risk_level": "low",
    "idempotency_key": "unique-key-for-retry-protection"
  },
  "constraints": {
    "timeout_ms": 8000,
    "max_memory_mb": 512,
    "max_recursion_depth": 5
  }
}
```

## Security

The system implements multiple layers of security:

1. **L1 Validation Firewall**: Basic schema and security validation
2. **L2 Authorization**: Method-level permission checking
3. **L3 Execution Isolation**: Sandboxed, deterministic execution

### Authentication

The system supports JWT-based authentication with configurable secret keys.

### Authorization

Role-based access control (RBAC) with support for:
- Viewer
- Operator
- Admin
- System roles

## Monitoring & Health Checks

- Health endpoint: `GET /health`
- Metrics endpoint: `GET /metrics`
- Distributed tracing included in all responses

## Cluster Configuration

For multi-node deployments:

1. Start the first node as the leader
2. Join additional nodes using the peer discovery mechanism
3. Monitor cluster status through the health endpoints

## API Reference

### L1 Gateway Endpoints

- `POST /facp/request`: Submit FACP requests
- `GET /health`: Health check
- `GET /metrics`: System metrics

### Security Headers

All requests should include appropriate authentication and authorization information in the `security` block of the request.

## Testing

Run the comprehensive test suite:

```bash
python -m pytest facp_distributed/tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please contact the FireAI Engineering Team or open an issue in the GitHub repository.