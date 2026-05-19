# FireAlarmAI Architecture

## Overview

FireAlarmAI is an AI-powered fire alarm design system that automates compliance checking and device placement according to international standards (NFPA 72, BS 5839).

## Architecture Principles

This project follows **Clean Architecture** principles with clear separation of concerns:

1. **Domain Layer** (`src/domain/`): Core business entities and rules
2. **Application Layer** (`src/application/`): Use cases and services
3. **Infrastructure Layer** (`src/infrastructure/`): Technical implementations
4. **Interfaces Layer** (`src/interfaces/`): API, CLI, UI adapters

## Directory Structure

```
src/
├── core/                    # Legacy core models (being phased out)
│   └── models.py           # Single source of truth for domain models
├── domain/                  # Domain layer (NEW)
│   ├── __init__.py
│   ├── models.py           # Copy of core/models.py - single source of truth
│   └── standards.py        # NFPA72, BS5839 implementations
├── application/             # Application layer (NEW)
│   ├── __init__.py
│   ├── coverage_service.py
│   ├── wall_distance_service.py
│   ├── normalization_service.py
│   └── compliance_service.py
├── infrastructure/          # Infrastructure layer (TODO)
│   ├── database.py
│   ├── shapely_geometry.py
│   └── vision_engine.py
└── interfaces/              # Interface layer (TODO)
    ├── api.py              # FastAPI REST API
    ├── cli.py              # Command-line interface
    └── web/                # React frontend
```

## Dependency Rules

- **Domain** → No dependencies on other layers
- **Application** → Depends only on Domain
- **Infrastructure** → Depends on Domain and Application
- **Interfaces** → Depends on Application

## Key Components

### Domain Models (`src/domain/models.py`)

Core entities:
- `Point`, `LineString`, `Polygon`: Geometric primitives
- `Room`: Building space with geometry and metadata
- `Device`: Fire alarm device with position and properties
- `Violation`: Code violation with structured information
- `DesignProject`, `DesignSession`: Project management entities

### Standards (`src/domain/standards.py`)

Implementation of international codes:
- `NFPA72`: National Fire Alarm and Signaling Code (US)
- `BS5839`: Fire detection and alarm systems (UK)

Each standard implements:
- Spacing requirements
- Wall distance limits
- Coverage calculations
- Room-specific rules

### Application Services

- `CoverageService`: Checks device coverage adequacy
- `WallDistanceService`: Validates wall distance compliance
- `NormalizationService`: Normalizes input data from various sources
- `ComplianceService`: Orchestrates all compliance checks

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_domain_models.py -v
```

### Code Quality

```bash
# Type checking
mypy src/

# Linting
ruff check src/

# Formatting
ruff format src/
```

## Current Status

### ✅ Completed (Phase 0-1)

- [x] Unified domain models in `src/core/models.py`
- [x] Domain layer structure created
- [x] Standards implementations (NFPA72, BS5839)
- [x] Application services implemented
- [x] Unit tests for domain models (24 tests)
- [x] Unit tests for application services (19 tests)
- [x] All 43 tests passing

### 🚧 In Progress (Phase 2)

- [ ] Infrastructure layer implementation
- [ ] Database integration (PostgreSQL + PostGIS)
- [ ] Vision engine integration
- [ ] REST API endpoints

### 📋 Planned (Phase 3+)

- [ ] React frontend
- [ ] CAD/BIM import
- [ ] AI model training pipeline
- [ ] CI/CD pipeline
- [ ] Documentation site

## Design Decisions

### Why Clean Architecture?

1. **Testability**: Business logic can be tested without infrastructure
2. **Maintainability**: Clear boundaries make changes easier
3. **Flexibility**: Can swap infrastructure (database, UI) without changing core logic
4. **Independence**: Frameworks and tools are details, not core

### Single Source of Truth

All domain models are defined in `src/core/models.py` and copied to `src/domain/models.py`. This ensures:
- No duplicate definitions
- Consistent types across the codebase
- Easy refactoring

### Violation Design

Violations use structured data instead of plain text messages:
- `violation_code`: Machine-readable identifier
- `description_template`: Human-readable template
- `params`: Structured parameters for template
- `message`: Generated from template + params (property)

This enables:
- Internationalization (different languages for templates)
- Programmatic handling of violations
- Better reporting and analytics

## Contributing

1. Follow the dependency rules strictly
2. Write tests before or with new features (TDD preferred)
3. Keep domain layer pure (no external dependencies)
4. Document public APIs

## License

[To be determined]
