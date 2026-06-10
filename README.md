# FireAI Digital Twin — Safety-Critical Fire Protection Engineering System

> **WARNING: This is a life-safety critical system. Code errors can produce
> fake engineering results that may lead to catastrophic consequences including
> loss of life. All changes must follow the agent.md protocol.**

## Overview

FireAI Digital Twin is a deterministic, safety-critical fire alarm engineering
platform that automates NFPA 72-2022 compliant fire detector placement, battery
sizing, voltage drop calculations, and FACP (Fire Alarm Control Panel) selection.
The system enforces a 5-layer computation pipeline (Physics Guard → NFPA 72
Lookup → IEEE-754 Computation → Result Validation → Audit Log) with
cryptographic signature hashes for every engineering result.

## Architecture

```
revit/
├── backend/           # FastAPI REST API (Python 3.12+, Pydantic V2)
│   ├── app.py         # Main application — CORS, auth, rate limits, security headers
│   ├── routers/       # 16 REST API routers (64 endpoints total)
│   ├── services/      # External API services (weather, geocoding, etc.)
│   ├── database.py    # System A: digital_twin.db (Projects, Devices, Connections)
│   ├── db_service.py  # System B: udm_elements.db (Elements, Relationships, Conflicts)
│   └── project_bridge.py  # Cross-database sync bridge (non-blocking)
├── facp_system/       # FACP Selection Engine (NOTIFIER/SIEMENS/SIMPLEX — 7 panels)
├── fireai/            # Core engineering engine (80+ modules)
│   └── core/          # QOMN kernel, NFPA 72 engine, battery aging, voltage drop
├── qomn_fire/         # QOMN-FIRE sub-package (placement, routing, DXF)
├── qomn_conduit/      # QOMN conduit routing (NEC Chapter 9 compliance)
├── frontend/          # React + TypeScript + Vite (shadcn/ui components)
├── parsers/           # CAD/BIM file parsers (DXF, DWG, IFC, PDF, etc.)
├── tests/             # 60+ test files (5,276 tests passing)
└── pyproject.toml     # Project configuration
```

## API Endpoints (64 total)

| Router | Prefix | Endpoints | Purpose |
|--------|--------|-----------|---------|
| health | /api/health | 2 | Health check, statistics |
| projects | /api/projects | 5 | Project CRUD |
| devices | /api/projects/:id/devices | 5 | Fire alarm device CRUD |
| connections | /api/projects/:id/connections | 3 | Cable connection CRUD |
| reports | /api/projects/:id/reports | 2 | Engineering reports |
| exports | /api/projects/:id/export | 4 | DXF, Revit, IFC exports |
| sync | /api/projects/:id/sync | 3 | Project sync + WebSocket |
| elements | /api/elements | 5 | UDM element CRUD |
| connections_v2 | /api/connections | 3 | UDM relationship connections |
| conflicts | /api/conflicts | 3 | Conflict detection/resolution |
| environment | /api/environment | 9 | Weather, geocoding, elevation, AQI, hazmat |
| workflow | /api/workflow | 5 | LangGraph workflow engine |
| memory | /api/memory | 4 | Mem0 long-term memory |
| facp | /api/facp | 5 | FACP selection & compliance |
| qomn | /api/qomn | 9 | QOMN-FIRE engineering kernel |

## Security

- **API Key Authentication**: All mutating endpoints (POST/PUT/DELETE/PATCH)
  require `X-API-Key` header. Production fails closed without `FIREAI_API_KEY`.
- **Rate Limiting**: Per-path rate limits with longest-prefix match algorithm.
- **Security Headers**: X-Frame-Options, X-Content-Type-Options, CSP,
  Permissions-Policy, Referrer-Policy on every response.
- **CORS**: Wildcards always rejected. Production requires explicit origins.
- **Input Sanitization**: Sort field whitelists, load_unit conversion, null byte
  rejection, path traversal protection.

## International Support

- **Regulatory Frameworks**: NFPA (US), ATEX/IEC (EU), BS 5839-1 (UK),
  Saudi HCIS, UAE Fire Code, Egyptian Fire Code, Kuwait Fire Code, Qatar FC
- **Severe Weather Alerts**: US (NWS), EU/EEA (MeteoAlarm), Global (Open-Meteo)
- **Weather Data**: Open-Meteo (global, free)
- **Geocoding**: Nominatim/OpenStreetMap (global)

## Quick Start

```bash
# Install core dependencies
pip install -r requirements.txt

# Install optional features
pip install fireai[workflow]   # LangGraph workflow engine
pip install fireai[memory]     # Mem0 + Qdrant long-term memory
pip install fireai[ifc]        # IFC (ifcopenshell) support

# Configure environment
cp .env.example .env
# Edit .env: set FIREAI_API_KEY, FIREAI_ENV=development

# Run the API server
python -m backend.app

# Build and serve frontend
cd frontend && npm install && npm run build

# Run tests
pytest tests/ -v
```

## Optional Dependencies

| Package | Install Group | Affects | Without It |
|---------|--------------|---------|------------|
| langgraph | `[workflow]` | /api/workflow/* | Endpoints return 503 |
| mem0 + qdrant-client | `[memory]` | /api/memory/* | Endpoints return 503 |
| ifcopenshell | `[ifc]` | IFC export endpoint | IFC export returns 503 |
| slowapi | `[ratelimit]` | Alternative rate limiting | Custom middleware used |
| bandit + pip-audit | `[audit]` | Security auditing | Manual security review |

## Standards Compliance

- **NFPA 72-2022**: Fire alarm and signaling code
- **NEC 2023**: National Electrical Code (NFPA 70)
- **UL 864 10th Edition**: Control unit listing
- **IEEE 485/1188**: Battery sizing derating
- **IEC 60079-10-1**: Hazardous area classification
- **CSI MasterFormat 28 31 11**: FACP specifications

## Project State

- **Version**: V100
- **Tests**: 5,276 passing (5,007 FireAI + 211 qomn_conduit + 58 qomn_fire)
- **Linting**: ruff, mypy, bandit
- **License**: MIT
