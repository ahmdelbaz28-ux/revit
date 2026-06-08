# FireAlarmAI Architecture

## Overview

FireAlarmAI is an AI-powered fire alarm design system that automates compliance checking and device placement according to international standards (NFPA 72, BS 5839).

## Directory Structure

```
fireai/                  # Main Python package
├── core/               # Core business logic (models, calculations, engines)
│   ├── nfpa72_models.py           # NFPA 72 domain models & spacing tables
│   ├── qomn_kernel.py             # QOMN-FIRE kernel (physics guards, spacing)
│   ├── nfpa72_calculations.py     # NFPA 72 calculations
│   ├── nfpa72_engine.py           # NFPA 72 compliance engine
│   ├── analysis_pipeline.py       # Processing pipeline
│   ├── pipeline.py                # Pipeline orchestration
│   ├── contracts.py               # Contracts & typing
│   ├── contracts_validation.py    # Input validation
│   ├── rules_engine/              # Rules engine subpackage
│   ├── spatial_engine/            # Spatial analysis subpackage
│   └── ... (100+ engine modules)
├── constants/          # Canonical constants (NFPA 72, NEC, etc.)
│   ├── nfpa72.py                  # NFPA 72 constants (single source of truth)
│   └── nec.py                     # NEC constants
├── bridges/            # Bridge adapters between subsystems
├── conduit/            # Conduit communication layer
├── infrastructure/     # Infrastructure implementations
├── validation/         # Input/output validation
├── mcp_server/         # MCP server
├── tools/              # CLI tools
├── viewers/            # Visualization tools
├── v17_core/           # Legacy v17 core
│   ├── __init__.py
│   ├── cli.py
│   ├── env_config.py
│   └── version.py
backend/                # FastAPI backend
├── routers/            # API route handlers
└── services/           # Backend services
frontend/               # Frontend application
├── src/
│   ├── components/     # UI components
│   ├── services/       # API client services
│   ├── pages/          # Page views
│   └── store/          # State management
qomn_fire/              # QOMN Fire subsystem
├── core/               # QOMN core logic
├── drawing/            # Drawing generation
├── engine/             # QOMN engine logic
├── integration/        # Integration adapters
├── output/             # Output formatting
├── parsers/            # File parsers
└── tests/              # Subsystem tests
qomn_conduit/           # QOMN Conduit communication layer
├── tests/
│   └── golden/         # Golden test fixtures
facp_system/            # FACP (Fire Alarm Control Panel) system
parsers/                # File format parsers
tests/                  # Full test suite
├── test_nfpa72_models.py
├── test_qomn_kernel.py
├── test_pipeline.py
└── ... (100+ test files)
scripts/                # Build & automation scripts
db/                     # Database files & migrations
```

## Layer Architecture

The system follows a **layered architecture** with strict inward dependency:

```
Frontend / CLI / API
      ↓
Backend (FastAPI)
      ↓
QOMN Kernel (physics guards, compute)
      ↓
FireAI Core (NFPA models, engines, rules)
      ↓
Constants (NFPA 72, NEC — single source of truth)
```

### 1. Constants Layer (`fireai/constants/`)
- Single source of truth for all NFPA 72, NEC constants
- No business logic — pure data definitions
- Referenced by all upper layers

### 2. Core Layer (`fireai/core/`)
- NFPA 72 domain models and spacing tables (`nfpa72_models.py`)
- QOMN-FIRE physics guards and spacing computation (`qomn_kernel.py`)
- Rule engines, spatial engines, analysis pipelines
- Audit trail, evidence chain, compliance proof documentation
- Cable routing, circuit topology, voltage drop calculations
- All ~100+ engine modules

### 3. QOMN Kernel (`fireai/core/qomn_kernel.py`)
- Layer 0 physics guards (NaN/Inf, ceiling height, area, voltage, current)
- Detector spacing computation (smoke, heat)
- Battery sizing, voltage drop
- Audit log with HMAC chain integrity
- Rejects physically impossible inputs

### 4. Backend (`backend/`)
- FastAPI application exposing REST endpoints
- Input validation via Pydantic + `contracts_validation.py`
- Delegates computation to QOMN Kernel

### 5. Frontend (`frontend/`)
- React-based UI
- Components, state management (store), API services

## Key Components

### NFPA 72 Models (`fireai/core/nfpa72_models.py`)
Core NFPA 72 entities:
- `CeilingSpec`, `RoomSpec` — building space models
- `SmokeDetectorSpec`, `HeatDetectorSpec` — device specs
- `DetectorPlacement` — placement logic
- Spacing tables: `get_smoke_detector_radius()`, `get_smoke_detector_coverage_max()`
- Safe variants: `get_smoke_detector_radius_safe()`, `CeilingSpec.create_safe()`
- Validation: `validate_ceiling_height()`, `CeilingHeightError`

### QOMN Kernel (`fireai/core/qomn_kernel.py`)
Physics guards and computation:
- `guard_ceiling_height_m()`, `guard_area_m2()`, `guard_current_a()`
- `compute_smoke_detector_spacing()`, `compute_heat_detector_spacing()`
- `compute_battery_capacity()`, `compute_voltage_drop()`
- `QOMNAuditLog` — append-only audit with HMAC-SHA256 chain

### Constants (`fireai/constants/nfpa72.py`)
Single source of truth:
- `SMOKE_MAX_SPACING_M`, `HEAT_MAX_SPACING_M`
- `SMOKE_MAX_CEILING_HEIGHT_M`, `CEILING_HEIGHT_HARD_LIMIT_M`
- `SMOKE_HEIGHT_SPACING_TABLE`
- `BATTERY_STANDBY_HOURS`, `BATTERY_ALARM_MINUTES`

## Dependency Rules

- **Constants** → No internal dependencies
- **Core** → Depends on Constants only
- **Backend** → Depends on Core, Constants
- **Frontend** → Depends on Backend API only

## Safety & Compliance

- **Rule 10**: Never modify tests — fix production code to match test expectations
- **Conservative defaults**: Ceiling height capped at 15.24m (50ft) for detector spacing — forces PE review above this height
- **Physics guards** reject: NaN, Inf, negative/zero heights, physically impossible inputs
- **Audit trail**: Every computation recorded with HMAC chain integrity verification

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=fireai --cov-report=html

# Run specific test file
pytest tests/test_nfpa72_models.py -v
```

### Code Quality

```bash
# Type checking
mypy fireai/

# Linting
ruff check fireai/

# Formatting
ruff format fireai/
```

## Design Decisions

### Why Conservative Ceiling Height (15.24m / 50ft)?

NFPA 72-2022 §17.7.3.2.4 allows spot-type smoke detectors up to 60ft (18.288m), but this module uses a conservative 50ft limit:

1. **Safety**: More detectors = more coverage redundancy
2. **PE review trigger**: Any ceiling above 50ft requires licensed Professional Engineer review
3. **Heat detector parity**: NFPA 72 §17.6.3.1 limits heat detectors to 50ft; using consistent limits avoids confusion
4. **Stratification**: Above 20ft (6.096m), smoke stratification makes detection unreliable per §17.7.1.11

### Single Source of Truth

All NFPA 72 constants are defined in `fireai/constants/nfpa72.py` and imported by all consumers. No duplicate definitions.

### Audit Integrity

Every computation through the QOMN kernel produces an audit entry with:
- Timestamp, input hash, result hash
- HMAC-SHA256 chain linking consecutive entries
- Exportable as signed JSON for submittal packages
