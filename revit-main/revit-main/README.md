# FireAI Agent Communication Protocol (FACP)

FACP (FireAI Agent Communication Protocol) v1.0 is a runtime-independent communication protocol designed for secure, deterministic communication between engineering AI agents and core computational engines.

## Overview

FACP implements a strict 3-layer architecture:

- **L1 (External Interface)**: Untrusted boundary for external requests (IDEs, editors, external tools)
- **L2 (Agent Orchestrator)**: Controlled intelligence layer for task routing and policy enforcement
- **L3 (Core Engine)**: Deterministic execution kernel for engineering calculations

## Key Features

- **Security First**: Multiple validation layers and authentication
- **Deterministic Execution**: Ensures consistent results across environments
- **Idempotency**: Built-in protection against duplicate requests
- **Resource Management**: Constraints on execution time, memory, and depth
- **Extensible Architecture**: Pluggable agents and policies
- **Comprehensive Auditing**: Full execution traceability

## Architecture

```
[External IDE/Editor]
        ↓
[L1 Interface Layer] ← Validation Gate (Security Firewall)
        ↓
[L2 Orchestrator] ← Policy Enforcement
        ↓
[L3 Engine Layer] ← Deterministic Execution
```

## Security Model

FACP implements a robust security model with:
- Strict input validation
- Role-based access control (RBAC)
- Request rate limiting
- Resource consumption limits
- Execution sandboxing
- Comprehensive audit logging

## Installation

```bash
pip install facp
```

## Usage

```python
from facp import FACP

# Create a FACP runtime
facp_runtime = FACP.create_runtime()

# Send a request
request = {
    "protocol": "FACP/1.0",
    "method": "engine.calculate",
    "params": {...},
    "security": {...}
}

response = facp_runtime.process_request(request)
```

## Components

### Protocol Layer
- Message schema validation
- JSON-RPC 2.0 compatible messaging
- Request/response formatting

### Security Layer
- Authentication and authorization
- Validation gates
- RBAC engine
- Audit logging

### Runtime Layer
- Execution state machine
- Resource management
- Idempotency handling

### L1 Interface
- External request handling
- Transport abstraction (HTTP, WebSocket, STDIO)

### L2 Orchestrator
- Agent management
- Task routing
- Policy enforcement

### L3 Engine
- Deterministic calculation engine
- Validation engine
- Transformation engine

## Transport Support

FACP supports multiple transport mechanisms:
- HTTP/REST
- WebSocket
- STDIO (for IDE integrations)

## Contributing

We welcome contributions to FACP. Please see our contributing guidelines for more information.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Note

This implementation is designed for Python 3.12+ environments. Some features may require additional dependencies depending on the transport mechanism used.