# FireAI System Architecture

## Overview

FireAI V10 is a production fire alarm design system implementing NFPA 72-2022 requirements. The system provides automated detector placement with tamper-evident audit trail.

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      API Layer                        │
│                                                       │
│  fireai_api.py                                         │
│  ├── POST /analyse/room/v10                          │
│  ├── POST /analyse/floor/v10                        │
│  ├── POST /analyse/floor/async                      │
│  ├── GET /task/{task_id}                            │
│  ├── GET /audit/trail                              │
│  └── GET /audit/verify                            │
└─────────────────────┬───────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │   FireAISystem          │
        │   (Orchestrator)        │
        │                       │
        │ fireai_core.py        │
        │ ├── analyse_room()    │
        │ ├── analyse_floor()  │
        │ └── audit_store      │
        └──────────┬───────────┘
                   │
    ┌──────────────▼──────────┐
    │ fire_expert_system.py   │
    │ (V10 Enhanced)        │
    │                      │
    │ ├── ExpertSystem     │
    │ ├── ResilienceResult │
    │ └── EnhancedExpertResult
    └──────────┬───────────┘
               │
    ┌─────────▼──────────┐
    │ AuditStore       │
    │ (HMAC)         │
    │                │
    │ - Event log    │
    │ - Chain      │
    │ - Verify    │
    └──────────────┘
```

## Data Flow

### Room Analysis

1. **API** receives `RoomSpecIn` from request
2. **FireAISystem** validates and orchestrates
3. **fire_expert_system.V10** computes detector placement
4. **AuditStore** logs each event with HMAC signature
5. **API** returns `EnhancedExpertResult`

### Floor Analysis

1. **API** receives list of `RoomSpecIn`
2. **FireAISystem** calls `analyse_floor()`
3. Each room → `analyse_room()` (individual audit)
4. Single `floor_analysis` event logged
5. Returns list of results

## Key Components

### fireai_core.py (FireAISystem)

- **Purpose**: Orchestration and audit integration
- **Public API**:
  - `analyse_room(room_spec, user_id, run_resilience) -> EnhancedExpertResult`
  - `analyse_floor(rooms, user_id, run_resilience) -> List[EnhancedExpertResult]`
  - `get_audit_trail() -> List[Dict]`
  - `verify_audit_integrity() -> bool`

### fire_expert_system.py (V10)

- **Purpose**: Core NFPA 72 analysis engine
- **Public API**:
  - `ExpertSystem.analyse_room(room_spec) -> ExpertResult`
  - `analyse_room_enhanced(...) -> EnhancedExpertResult`
  - `enhance_result(...) -> EnhancedExpertResult`

### nfpa72_models.py

- **Purpose**: Data models
- **Models**:
  - `RoomSpec`
  - `CeilingSpec`
  - `DetectorType`
  - `OccupancyClass`
  - `ConfidenceLevel`

### audit_store.py

- **Purpose**: Tamper-evident logging
- **Public API**:
  - `add_event(event_type, room_id, details_dict)`
  - `get_events() -> List[Dict]`
  - `verify_chain() -> (bool, details)`

## Security Model

### HMAC Chain

Each event is signed with HMAC-SHA256:
```python
event_data = json.dumps(event, sort_keys=True)
signature = hmac.new(key, event_data.encode(), hashlib.sha256).hexdigest()
```

### Chain Verification

```python
is_valid, details = audit_store.verify_chain()
# Returns False if any event modified after creation
```

## API Endpoints

| Endpoint | Method | Description |
|---------|--------|------------|
| `/analyse/room/v10` | POST | Analyze single room |
| `/analyse/floor/v10` | POST | Analyze floor (sync) |
| `/analyse/floor/async` | POST | Analyze floor (async) |
| `/task/{task_id}` | GET | Get async result |
| `/audit/trail` | GET | Get audit trail |
| `/audit/verify` | GET | Verify audit |
| `/health` | GET | Health check |
| `/version` | GET | Version info |

## Resilience

V10 Enhanced includes Monte Carlo resilience testing:
- Simulates single-detector failure
- Requires 80% minimum coverage after failure
- Sets `confidence = CERTIFIED` if resilient

---

*Generated: 2026-05-16 | Version: 10.0.0*