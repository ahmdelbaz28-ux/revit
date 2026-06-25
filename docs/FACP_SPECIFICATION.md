# FIREAI AGENT COMMUNICATION PROTOCOL (FACP)
Version 1.0 — Formal Specification

## 1. Status of This Specification

This document defines the FireAI Agent Communication Protocol (FACP v1.0).

Runtime-independent specification
Implementation-agnostic (Python, Go, Rust, etc.)
Compatible design target for future:
Agent Client Protocol (ACP)
Not bound to any execution environment

## 2. Protocol Overview

FACP defines a structured communication layer between:

External Editors / IDEs
Agent Orchestration Layer
Core Engineering Engine

It standardizes:

message transport
request/response schema
execution contracts
security boundaries

## 3. Architectural Model

### 3.1 Logical Layers

FACP defines 3-layer separation:

#### L1 — External Interface Layer

Untrusted boundary:

IDEs
Editors
External tools
User requests

#### L2 — Agent Orchestration Layer

Controlled intelligence layer:

task routing
context management
tool selection
policy enforcement

#### L3 — Core Engine Layer

Deterministic execution kernel:

engineering calculations
compliance evaluation
transformation logic
unified model execution

### 3.2 Principle of Separation

No layer is allowed to directly bypass the layer beneath it.

L1 → cannot access L3 directly
L2 → cannot modify L3 logic
L3 → cannot depend on L1 or L2 state

## 4. Transport Model

FACP is transport-agnostic but defines canonical formats:

Supported transports:

JSON-RPC 2.0 (primary)
WebSocket streaming
stdio subprocess channels
HTTP/REST fallback

Canonical recommendation:

JSON-RPC 2.0 style messaging

## 5. Message Specification

### 5.1 Request Object
```json
{
  "protocol": "FACP/1.0",
  "type": "request",
  "id": "uuid",
  "timestamp": "ISO-8601",
  "source": "ide|agent|system",
  "target": "orchestrator|engine",
  "method": "string",
  "params": {
    "task": "string",
    "payload": {},
    "context": {}
  },
  "security": {
    "auth_token": "string|null",
    "permissions": [],
    "risk_level": "low|medium|high|critical"
  }
}
```

### 5.2 Response Object
```json
{
  "protocol": "FACP/1.0",
  "type": "response",
  "id": "uuid",
  "status": "success|error",
  "result": {},
  "error": {
    "code": "string",
    "message": "string"
  },
  "trace": {
    "engine_version": "string",
    "execution_path": ["layer1", "layer2", "layer3"],
    "latency_ms": 0
  }
}
```

### 5.3 Agent Message Contract
```json
{
  "agent_id": "string",
  "role": "planner|executor|validator|optimizer",
  "action": "analyze|compute|validate|transform",
  "input": {},
  "constraints": {
    "deterministic": true,
    "bounded_execution": true,
    "max_depth": 5
  }
}
```

## 6. Execution Flow Model

### 6.1 Standard Flow
```
[External Editor / IDE]
        ↓
[External Interface Layer]
        ↓
[Agent Orchestrator]
        ↓
[Policy + Validation Gate]
        ↓
[Core Engine]
        ↓
[Result Formatter]
        ↓
[External Interface Layer]
        ↓
[Editor Response]
```

### 6.2 Execution Rules
All requests must pass validation gate before orchestration
Orchestrator cannot modify engine logic
Engine is deterministic and stateless by contract
All responses must include trace metadata

## 7. Security Model

### 7.1 Trust Boundaries
| Layer | Trust Level |
|-------|-------------|
| IDE / Editor | Untrusted |
| Orchestrator | Controlled |
| Engine | Fully Trusted |

### 7.2 Security Controls
Mandatory Controls:
- Input schema validation
- Role-based access control (RBAC)
- Execution sandboxing
- Audit logging for all requests

Prohibited:
- direct code execution from external layer
- dynamic injection into engine layer
- bypassing orchestrator policies

### 7.3 Threat Model (Abstract)

FACP assumes protection against:

- malformed requests
- unauthorized execution attempts
- state manipulation
- cross-layer contamination

## 8. ACP Compatibility Strategy

### Evaluation
Target Protocol

Agent Client Protocol (ACP)

### Position of FACP

FACP is:

- SUPerset-compatible design
- NOT dependent on ACP
- structurally mappable to ACP later

### Mapping Strategy
| FACP Concept | ACP Equivalent |
|--------------|----------------|
| request/response | JSON-RPC message |
| orchestrator | agent runtime |
| IDE interface | editor client |

### Decision
FACP = internal canonical protocol
ACP = future interoperability adapter

## 9. Deployment Model (Abstract)

### Supported Topologies

#### 1. Local Runtime
- single process
- stdio or HTTP

#### 2. Containerized Runtime
- isolated services
- engine separated from orchestrator

#### 3. Distributed Runtime (future)
- multi-agent scaling
- event-driven architecture

## 10. Validation Contract

A compliant FACP implementation MUST ensure:

### Determinism
Same input → same output (engine layer)

### Isolation
No cross-layer mutation

### Traceability
Every execution must expose:
- execution path
- engine version
- latency

### Reproducibility
Requests must be replayable without semantic drift

## 11. Non-Negotiable Constraints
- Architecture must remain runtime-agnostic
- Execution layer must remain isolated from protocol definition
- No dependency on Python version or runtime environment
- Protocol must be implementable in any modern system language

## 12. Versioning Policy
- Breaking changes → major version increment
- Backward-compatible changes → minor version
- Schema additions → patch version

## FINAL SUMMARY

FACP v1.0 defines:

- a strict 3-layer agent architecture
- deterministic engine execution model
- secure communication protocol
- ACP-compatible future pathway
- runtime-independent specification standard

## SELF-CRITIQUE (important)

This spec is intentionally:

- strict in separation of concerns
- minimal in runtime assumptions
- ACP-compatible but not ACP-dependent

Limitations:

- does not define actual transport implementation details (by design)
- defers performance optimization and scaling policies to implementation phase