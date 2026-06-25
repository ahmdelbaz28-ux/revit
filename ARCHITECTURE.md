# FireAI System Architecture

## Overview

The FireAI platform implements a robust, safety-critical architecture for fire protection engineering. The system is designed and architected by **Eng. Ahmed Elbaz** with emphasis on reliability, safety, and performance.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Presentation Layer                           │
├─────────────────────────────────────────────────────────────────┤
│  CAD Integration    │  Web Interface   │  API Gateway          │
│  • AutoCAD Plugin  │  • React UI      │  • RESTful API        │
│  • Revit Add-in    │  • Dashboard     │  • GraphQL API        │
│  • IFC Reader      │  • Reports       │  • WebSocket          │
└─────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Service Layer                                │
├─────────────────────────────────────────────────────────────────┤
│  Engineering Services        │  Integration Services           │
│  • Detector Placement       │  • CAD Parsing                  │
│  • Compliance Checking      │  • BIM Sync                     │
│  • NAC Design              │  • Cloud Storage                │
│  • Evacuation Modeling     │  • Third-party APIs             │
│  • Risk Assessment         │  • Audit Trail                  │
└─────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Core Engine Layer                            │
├─────────────────────────────────────────────────────────────────┤
│  Computational Engine      │  Safety & Validation              │
│  • Spatial Algorithms      │  • Input Validation              │
│  • Optimization Solver     │  • Compliance Verification       │
│  • Physics Simulation      │  • Safety Gates                  │
│  • Coverage Analysis       │  • Error Recovery                │
│  • Load Calculations       │  • Audit Logging                 │
└─────────────────────────────────────────────────────────────────┘
                                │
┌─────────────────────────────────────────────────────────────────┐
│                    Data Layer                                   │
├─────────────────────────────────────────────────────────────────┤
│  • Building Models         │  • Engineering Data              │
│  • CAD Geometry            │  • Compliance Rules              │
│  • Sensor Networks         │  • Historical Records            │
│  • System Configurations   │  • Audit Logs                    │
└─────────────────────────────────────────────────────────────────┘
```

## Actual Repository Structure

```
revit/
├── fireai/                        # Core fire alarm engineering library
│   ├── core/                      # Core computation engine
│   │   ├── qomn_kernel.py         # QOMN-FIRE deterministic engineering kernel
│   │   ├── nfpa72_calculations.py # NFPA 72 Chapter 17 calculations
│   │   ├── nfpa72_models.py       # Data models for NFPA 72
│   │   ├── nfpa72_coverage.py     # Coverage analysis engine
│   │   ├── nfpa72_engine.py       # Main NFPA 72 compliance engine
│   │   ├── nfpa72_schemas.py      # Pydantic schemas for NFPA 72 API
│   │   ├── nfpa72_technology_dispatcher.py  # Detector technology selection
│   │   ├── fire_expert_system.py  # Expert system for fire protection
│   │   ├── floor_orchestrator.py  # Multi-floor analysis orchestration
│   │   ├── fireai_api.py         # FastAPI application
│   │   ├── audit_trail.py        # Immutable audit trail
│   │   ├── room_validator.py     # Room input validation
│   │   ├── rules_engine/         # NFPA 72 rules engine
│   │   ├── spatial_engine/       # Spatial analysis (Voronoi, MIP)
│   │   └── ...                   # 60+ additional core modules
│   ├── constants/                 # Single Source of Truth for standards
│   │   ├── __init__.py           # Re-exports from nfpa72.py + NEC constants
│   │   ├── nfpa72.py             # CANONICAL NFPA 72-2022 constants (SSoT)
│   │   └── nec.py                # NEC (NFPA 70-2023) constants
│   ├── bridges/                   # Integration bridges
│   │   ├── revit_bim_sync.py     # Revit BIM synchronization
│   │   ├── ifc_pipeline.py       # IFC file pipeline
│   │   ├── enterprise_pipeline.py # Enterprise integration
│   │   └── ifc_headless_bridge.py # Headless IFC bridge
│   ├── agents/                    # AI agent modules
│   ├── validation/                # Compliance validation engines
│   ├── analytics/                 # Predictive analytics & ML
│   ├── infrastructure/            # Logging, metrics, health, tracing
│   ├── tools/                     # Dependency analyzer, constant checker
│   ├── integration/               # AutoCAD, Bentley, AR/VR, IoT bridges
│   ├── v17_core/                  # V17 legacy core modules
│   ├── conduit/                   # Conduit fill analysis
│   ├── mcp_server/                # Model Context Protocol server
│   ├── viewers/                   # Visualization components
│   ├── cli.py                     # Command-line interface
│   ├── env_config.py             # Environment configuration
│   ├── version.py                # Version tracking
│   ├── README.md                 # FireAI documentation
│   ├── LIMITATIONS.md            # Known limitations
│   ├── TESTING.md                # Testing documentation
│   ├── SECURITY.md               # Security documentation
│   └── CHANGELOG.md              # Change log
├── backend/                       # FastAPI backend service
│   ├── app.py                    # Backend application entry
│   ├── routers/                  # API route handlers
│   ├── services/                 # Business logic services
│   └── models.py                 # Backend data models
├── frontend/                      # React + TypeScript frontend
│   ├── src/                      # Source code
│   │   ├── pages/                # Page components
│   │   ├── components/           # UI components (shadcn/ui)
│   │   ├── engine/               # Frontend calculation engine
│   │   ├── services/             # API services
│   │   └── hooks/                # React hooks
│   └── electron/                 # Electron desktop wrapper
├── facp_system/                   # Fire Alarm Control Panel system
├── facp_distributed/              # Distributed FACP architecture
│   ├── l1_gateway/               # API gateway layer
│   ├── l2_orchestrator/          # Orchestration layer
│   ├── l3_engine_workers/        # Engine worker layer
│   ├── security/                 # RBAC, auth, audit, isolation
│   ├── event_bus/                # Event dispatching
│   ├── transport/                # HTTP, WebSocket, message bus
│   └── protocol/                 # Message schemas
├── qomn_fire/                     # QOMN-FIRE engine (standalone)
│   ├── core/                     # Core types, constants, errors
│   ├── engine/                   # Placement, routing, panel selection
│   ├── drawing/                  # DXF, hatch, title block
│   ├── output/                   # Revit export
│   ├── parsers/                  # File format parsers
│   └── integration/              # Cable hatch integration
├── qomn_conduit/                  # QOMN conduit routing engine
├── parsers/                       # Multi-format file parsers
├── integration/                   # IFC bridge integration
├── tests/                         # Test suite (200+ test files)
├── deploy/                        # Deployment configurations
│   ├── docker/                   # Docker & docker-compose
│   ├── k8s/                      # Kubernetes manifests
│   ├── helm/                     # Helm charts
│   └── observability/            # Prometheus, Grafana, Loki, Tempo
├── docs/                          # Documentation
├── wiki/                          # Standards wiki
├── skills/                        # Skill modules
├── ARCHITECTURE.md                # This file
├── pyproject.toml                 # Python project config
├── requirements.txt               # Python dependencies
└── CHANGELOG.md                   # Project changelog
```

## Architectural Layers

### L1 - Interface Layer
The interface layer provides multiple access points to the FireAI system:

- **CLI Interface**: Command-line tools for automation and scripting
- **Web Dashboard**: Graphical user interface for interactive design
- **API Gateway**: RESTful and WebSocket APIs for integration
- **Revit Plugin**: Direct integration with Autodesk Revit
- **Mobile App**: Field applications for inspections and verification

*Designed by Eng. Ahmed Elbaz*

### L2 - Orchestration Layer
The orchestration layer manages workflow and coordination:

- **Agent Orchestrator**: Coordinates AI agents for specific tasks
- **Workflow Engine**: Manages complex multi-step processes
- **Event Bus**: Facilitates communication between components
- **Memory System**: Maintains state and context across operations

*Architected by Eng. Ahmed Elbaz*

### L3 - Engine Layer
The engine layer performs core computations and validations:

- **Fire Detection Engine**: Calculates optimal detector placement
- **Suppression Calculator**: Performs hydraulic and pneumatic calculations
- **Compliance Checker**: Validates against NFPA and local codes
- **Physics Simulator**: Models fire dynamics and system responses

*Engineered by Eng. Ahmed Elbaz*

### Single Source of Truth (SSoT)

All NFPA 72-2022 constants are centralized in `fireai/constants/nfpa72.py`.
No other module may define duplicate NFPA 72 constants — all must import from this
canonical source. This eliminates the 5-way parallel implementation bug that
previously existed across the codebase.

Key SSoT rules:
- `fireai/constants/nfpa72.py` is the ONLY place NFPA 72 constants are defined
- `fireai/constants/__init__.py` re-exports from nfpa72.py for convenience
- `fireai/core/qomn_kernel.py` imports from the canonical source
- `fireai/core/nfpa72_calculations.py` imports from the canonical source
- `fireai/core/nfpa72_technology_dispatcher.py` imports from the canonical source

### Compliance Engine

Multi-layered code compliance checking:

- **NFPA 72**: National Fire Alarm and Signaling Code
- **NFPA 13**: Sprinkler system requirements
- **IBC**: International Building Code
- **Local Amendments**: Jurisdiction-specific requirements

### CAD Integration Layer

Supports multiple CAD formats:

- **DXF/DWG**: AutoCAD compatibility
- **IFC**: Industry Foundation Classes (BIM)
- **RVT**: Revit native format
- **PDF**: 2D drawing support

### Fail-Safe Mechanisms
- Conservative assumptions when data is ambiguous
- Multiple independent calculation methods
- Redundant safety checks
- Automatic audit trail generation

### Error Handling
- Graceful degradation on partial failures
- Detailed error reporting
- Recovery mechanisms
- State preservation

## Safety Architecture

### Validation Gates
Multiple validation layers ensure safety:

- **Input Sanitization**: All inputs are validated and verified (QOMN Layer 0)
- **Calculation Verification**: Results are cross-checked using multiple methods
- **Compliance Validation**: All outputs meet code requirements
- **Safety Overrides**: Conservative defaults for critical parameters

*Implemented by Eng. Ahmed Elbaz*

## Security Architecture

### Defense in Depth
1. **Network Layer**: API gateway with rate limiting
2. **Application Layer**: Input validation and sanitization
3. **Data Layer**: Encrypted storage and access controls
4. **Compute Layer**: Isolated execution environments

### Authentication & Authorization
- Role-based access control (RBAC)
- Multi-factor authentication
- Session management
- API key management

## Deployment Architecture

### Development Environment
- Local installation with full engine
- Mock services for external dependencies
- Development database
- Testing infrastructure

### Production Environment
- Containerized deployment (Docker/Kubernetes)
- Load balancing and scaling
- Monitoring and alerting
- Backup and disaster recovery

## Data Architecture

### Storage Strategy
- **Primary Database**: PostgreSQL for structured data
- **Spatial Indexing**: PostGIS for geometric calculations
- **Document Store**: For drawings and reports
- **Cache Layer**: Redis for performance optimization

### Security Model
- **Access Control**: Role-based permissions
- **Audit Logging**: Complete transaction history
- **Data Encryption**: At rest and in transit
- **Compliance Tracking**: Regulatory verification logs

*Data architecture by Eng. Ahmed Elbaz*

### Infrastructure
- **Containerization**: Docker
- **Orchestration**: Kubernetes
- **Monitoring**: Prometheus, Grafana
- **Logging**: ELK Stack

## Deployment Architecture

### Scalability Model
- **Microservices**: Loosely coupled, independently deployable
- **Containerization**: Docker-based deployment
- **Orchestration**: Kubernetes for container management
- **Load Balancing**: Traffic distribution and failover

### Security Boundaries
- **Network Segmentation**: Isolated security zones
- **API Gateway**: Centralized security enforcement
- **Secrets Management**: Secure credential handling
- **Monitoring**: Continuous security posture assessment

*Deployment architecture by Eng. Ahmed Elbaz*

### Reliability
- 99.9% uptime SLA
- Multi-region deployment
- Automated failover
- Comprehensive monitoring

## Technology Stack

### Backend Technologies
- **Python 3.8+**: Primary implementation language
- **FastAPI**: Web framework for API services
- **SQLAlchemy**: ORM for database interactions
- **Redis**: In-memory data store
- **Celery**: Task queue for background jobs

### Frontend Technologies
- **React**: User interface framework
- **D3.js**: Data visualization
- **Leaflet**: Map visualization
- **WebSockets**: Real-time communication

*Technology selection by Eng. Ahmed Elbaz*

## Quality Assurance

### Testing Strategy
- **Unit Tests**: Component-level validation (200+ test files)
- **Integration Tests**: Multi-component verification
- **Safety Tests**: Critical function validation
- **Performance Tests**: Load and stress testing

### Code Quality
- **Static Analysis**: Automated code review
- **Peer Review**: Mandatory code reviews
- **Continuous Integration**: Automated testing pipeline
- **Security Scanning**: Vulnerability detection

*Maintained to high standards by Eng. Ahmed Elbaz*

## Evolution Plan

### Phase 1: Foundation
- Core calculation engines
- Basic BIM integration
- Essential safety features

### Phase 2: Intelligence
- Advanced AI capabilities
- Predictive analytics
- Automated optimization

### Phase 3: Ecosystem
- Third-party integrations
- Marketplace for extensions
- Advanced visualization

*Evolution strategy by Eng. Ahmed Elbaz*

---

*This architecture was conceived and implemented by Eng. Ahmed Elbaz to provide a world-class platform for fire protection engineering.*