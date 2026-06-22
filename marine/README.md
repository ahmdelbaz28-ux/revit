# Marine Fire-Safety Module

**Version:** 1.0.0 · **Standards:** IMO SOLAS II-2, IEC 60092-502/504, ISO 15370, LR Rules, NFPA 302

Dedicated package for **ship and marine fire-protection engineering** — the marine counterpart to `fireai/` (which targets buildings per NFPA 72/13).

## Overview

The `marine/` package implements fire-safety design for ships per the international maritime codes. It is the marine counterpart to `fireai/` (which targets buildings per NFPA 72/13). The two packages share the same FastAPI backend (`backend/routers/marine.py`) and the same integration bridges (Revit, AutoCAD, SCADA, ETAP).

## Standards Implemented

| Standard | Scope | Module |
|----------|-------|--------|
| IMO SOLAS Ch. II-2 (2024) | Fire protection, detection, extinction | `marine/solas/chapter_ii_2.py` |
| IMO FSS Code Ch. 9 | Fire detection & alarm systems | `marine/iec60092/part_502.py` |
| IMO FSS Code Ch. 14 | Sprinkler systems | `marine/engine/extinguishment.py` |
| IMO MSC.1/Circ.1316 | CO2 total flooding | `marine/engine/extinguishment.py` |
| IMO MSC.1/Circ.1165 | Water mist systems | `marine/engine/extinguishment.py` |
| IEC 60092-502:1999 | Tankers electrical + fire detection | `marine/iec60092/part_502.py` |
| IEC 60092-504 | Ships carrying dangerous goods | `marine/iec60092/part_504.py` |
| IEC 60092-301/350 | Shipboard electrical | `marine/iec60092/electrical_installations.py` |
| ISO 15370:2001 | Thermal alarms for passenger ships | `marine/iso15370/thermal_alarms.py` |
| Lloyd's Register Part 6 | Fire protection (supplements SOLAS) | `marine/lr_rules/fire_protection.py` |
| NFPA 302-2020 | Small craft fire protection | `marine/nfpa302/small_craft.py` |

## Quick Start

```python
from marine.core.types import ShipProject, ShipType
from backend.services.marine_service import get_marine_service

ship = ShipProject(
    project_id="P-001", ship_name="MV Test",
    ship_type=ShipType.CARGO, length_overall_m=120.0,
    gross_tonnage=8000.0,
)
result = get_marine_service().design_full(ship)
print(f"Zones: {result['summary']['zone_count']}")
print(f"Detectors: {result['summary']['detector_count']}")
print(f"Divisions: {result['summary']['division_count']}")
```

## Architecture

```
marine/
├── core/           # Domain types, constants, errors (single source of truth)
│   ├── types.py    # ShipType, FireClass, DetectorType, ExtinguishingSystem, ...
│   └── constants.py # SOLAS/IEC/IMO numerical constants
├── solas/          # IMO SOLAS Chapter II-2 compliance engine
├── iec60092/       # IEC 60092-502 (fire detection) + 60092-504 (dangerous goods)
├── iso15370/       # ISO 15370 thermal alarms (passenger ships)
├── lr_rules/       # Lloyd's Register Rules
├── nfpa302/        # NFPA 302 (small craft)
├── engine/         # Core calculation engines
│   ├── zone_mapper.py          # SOLAS main vertical zone division
│   ├── fire_resistance.py      # A-60/B-15 class assignment
│   ├── extinguishment.py       # Water mist / CO2 / foam / sprinkler / IG sizing
│   └── alarm_logic.py          # PLC/DCS logic tree (IEC 61131-3 ST)
├── integration/    # External system bridges
│   ├── scada_bridge.py         # MQTT + OPC-UA + Modbus
│   ├── etap_bridge.py          # ETAP power-system CSV export
│   ├── revit_exporter.py       # Revit family + placement generation
│   └── autocad_exporter.py     # DXF layer + entity generation
├── tests/          # Unit + property-based tests
└── __init__.py
```

## REST API

All endpoints are mounted under `/api/v1/marine/` and require authentication.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/standards` | List supported standards |
| GET | `/fire-classes` | List SOLAS fire division classes |
| POST | `/ship/validate` | Validate SOLAS compliance |
| POST | `/ship/design` | Full design pipeline |
| POST | `/zones/divide` | Divide ship into MVZs |
| POST | `/extinguishing/design` | Size extinguishing system |
| POST | `/alarm-logic/generate` | Generate PLC/DCS logic tree |
| POST | `/integrations/scada` | Generate SCADA config |

## Ship Types Supported

- **Passenger ships** (>12 passengers) — SOLAS II-2 Part D
- **Cargo ships** — SOLAS II-2 Part C
- **Tankers** (oil/chemical/gas) — IEC 60092-502
- **Offshore** (MODU) — MODU Code
- **Small craft** (<24m) — NFPA 302

## Extinguishing Systems Sized

| System | Standard | Application |
|--------|----------|-------------|
| Water mist | IMO MSC.1/Circ.1165 | Engine rooms, accommodation |
| CO2 total flooding | IMO MSC.1/Circ.1316 | Cargo holds, engine rooms |
| Low-expansion foam | SOLAS II-2/10.8 | Cargo tank deck (tankers) |
| High-expansion foam | SOLAS II-2/10.7 | Engine rooms |
| AFFF | CAP 437 / ICAO Annex 14 | Helidecks |
| Dry chemical | SOLAS II-2/10.6 | Galley hoods |
| Sprinkler | SOLAS II-2/8 + FSS Ch. 14 | Accommodation |
| Inert gas | SOLAS II-2/4.5.5 + FSS Ch. 15 | Cargo tanks |

## Test Coverage

Run the test suite:

```bash
pytest marine/tests/ -v
```

Tests cover: SOLAS compliance, IEC 60092-502 detector selection, fire-class hierarchy, extinguishing sizing, alarm-logic generation, hazardous-zone classification, and SCADA integration.

## Integration with FireAI Platform

The marine module is fully integrated with the existing FireAI platform:

- **Backend**: `backend/routers/marine.py` + `backend/services/marine_service.py`
- **Auth**: All endpoints use `require_permission(...)` (ENGINEER+ for writes, VIEWER+ for reads)
- **Rate limiting**: 10–100 req/min per endpoint
- **Database**: Shares the same DB as fireai/building projects
- **Frontend**: Accessible via the same React app (marine views pending)

## References

- IMO SOLAS consolidated edition 2024
- IMO FSS Code (Fire Safety Systems Code) 2023
- IEC 60092 series (electrical installations in ships)
- ISO 15370:2001 (thermal alarms)
- Lloyd's Register Rules for Fire Protection, Detection & Extinguishment 2024
- NFPA 302-2020 (Fire Protection for Craft and Small Commercial Vessels)
