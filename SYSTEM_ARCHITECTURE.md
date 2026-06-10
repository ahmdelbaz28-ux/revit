# FireAI Production System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    FIREAI PRODUCTION SYSTEM                        │
└─────────────────────────────────────────────────────────────────────┘

                                ┌─────────────────┐
                                │  FireAISystem    │
                                │  (Orchestrator) │
                                └────────┬────────┘
                                         │
           ┌─────────────────────────────┼─────────────────────────────┐
           │                           │                             │
           ▼                           ▼                             ▼
   ┌───────────────┐          ┌──────────────────┐      ┌──────────────┐
   │ExpertSystemV12│          │    AuditStore     │      │ProjectMemory│
   │              │◄────────►│ (Tamper-Evidence) │      │             │
   │ - analyse_room│          │                  │      │ - cache     │
   │ - analyse_   │          │ - add_event      │      │ - lookup    │
   │   floor     │          │ - verify_chain   │      │ - insert    │
   └─────────────┘          └───────────────────┘      └──────────────┘
           │
           ▼
   ┌───────────────────────────────────────────────────────────────────┐
   │                   ExpertResultV12                         │
   │  - detector_positions   - room_id                         │
   │  - confidence         - placement_proof                   │
   │  - wall_violations   - regulatory_proof (renamed)         │
   │  - resilience        - mip_fallback_reason              │
   │  - used_mip         - mip_proof                         │
   └───────────────────────────────────────────────────────────────────┘

API Endpoints (fireai_api.py):
  POST  /analyse/room     → Single room analysis
  POST  /analyse/floor    → Multi-room floor analysis  
  GET   /audit/trail      → Audit trail
  GET   /audit/verify     → Verify audit integrity
  GET   /health           → System health
  GET   /version           → Version info
```

## Components

### 1. FireAISystem (fireai_core.py)
**Responsibility**: Central orchestrator that integrates all components
- Combines V12 engine with audit logging
- Provides single entry point for analysis
- Manages audit trail automatically

**Key Methods**:
- `analyse_room(room_spec, user_id, run_resilience) -> ExpertResultV12`
- `analyse_floor(rooms, user_id, run_resilience) -> List[ExpertResultV12]`
- `get_audit_trail() -> List[Dict]`
- `verify_audit_integrity() -> bool`

### 2. ExpertSystemV12 (fire_expert_system_v12.py)
**Responsibility**: Production-grade analysis engine
- Uses MIP optimization when beneficial
- Resilience checking (detector redundancy)
- ProjectMemory for solution caching
- Regulatory proof generation

**Key Features**:
- MIP fallback with mip_fallback_reason
- Resilience checks (single point of failure detection)
- Wall violation detection with cap

### 3. AuditStore (audit_store.py)
**Responsibility**: Tamper-evident audit logging
- Hash chaining for integrity
- Automatic timestamp tracking
- Event logging for all operations

**Key Functions**:
- `add_event(event_type, room_id, details_dict) -> str`
- `verify_chain() -> (bool, Optional[Dict])`
- `get_events() -> List[Dict]`

### 4. ProjectMemory (fire_expert_system_v12.py)
**Responsibility**: Solution caching
- Caches previously solved rooms
- Memory-based routing for efficiency

## Data Flow

```
1. User Request
       │
       ▼
2. FireAISystem.analyse_room()
       │
       ├──────────────────────┐
       │                      │
       ▼                      ▼
3. ExpertSystemV12        AuditStore
    .analyse_room()         .add_event()
       │                      │
       │                      │ (async)
       │                      │
       ▼                      ▼
4. ExpertResultV12 ◄──── Audit Event
       │
       ▼
5. Response + Audit Trail
```

## Operation Modes

### Single Room Analysis
```
FireAISystem.analyse_room(room_spec, user_id="user123")
    │
    ├─→ ExpertSystemV12.analyse_room()
    │       │
    │       ├─→ Check ProjectMemory
    │       ├─→ Run analysis (MIP or Greedy)
    │       ├─→ Resilience check
    │       └─→ Generate regulatory_proof
    │
    └─→ AuditStore.add_event("room_analysis", ...)
```

### Floor Analysis
```
FireAISystem.analyse_floor(rooms, user_id="user123")
    │
    ├─→ ExpertSystemV12.analyse_floor()
    │       │
    │       └─→ Process each room
    │
    └─→ AuditStore.add_event("floor_analysis", ...)
```

## Known Issues

### RoomSpec Compatibility (BLOCKING)
- V12 expects `RoomSpec.polygon_coords` attribute
- Project's RoomSpec (nfpa72_models.py) doesn't have this
- Requires either:
  a) Update project's RoomSpec to add polygon_coords, OR
  b) Modify V12 to use width_m/depth_m directly

### Module Imports
- V12 imports from absolute paths (e.g., `fire_expert_system` not `.fire_expert_system`)
- Requires relative import fixes for package use

## Getting Started

### Installation
```bash
pip install ezdxf shapely
```

### Basic Usage
```python
from fireai.core.fireai_core import FireAISystem
from fireai.core.nfpa72_models import CeilingSpec, CeilingType, RoomSpec

# Create system
system = FireAISystem(db_path="audit.db", memory_max=2048)

# Create room spec
ceiling = CeilingSpec(3.0, 3.0, CeilingType.FLAT)
room_spec = RoomSpec(
    room_id="room_1",
    width_m=10.0,
    depth_m=10.0,
    ceiling_spec=ceiling,
    occupancy_type="office",
)

# Analyze
result = system.analyse_room(room_spec, user_id="user")

# Check audit
trail = system.get_audit_trail()
is_valid = system.verify_audit_integrity()
```

### Running Tests
```bash
python fireai/core/test_integration.py
```

## Version Information

- FireAISystem: 1.0.0
- ExpertSystemV12: 12.0.0
- AuditStore: Hash-chain based
- NFPA Compliance: NFPA 72-2022
================================================================================
QUICK START
================================================================================

## Running the API

```bash
cd /workspace/project/revit
uvicorn fireai.core.fireai_api:app --host 0.0.0.0 --port 8000
```

## API Example with curl

```bash
# Health check
curl http://localhost:8000/health

# Version
curl http://localhost:8000/version

# Analyze room (requires API key)
curl -X POST http://localhost:8000/analyse/room/v10 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "room": {
      "room_id": "room_001",
      "width_m": 10,
      "depth_m": 10,
      "ceiling": {"height_at_low_point_m": 3.0}
    }
  }'
```

================================================================================
ENVIRONMENT VARIABLES
================================================================================

| Variable | Description | Default |
|----------|-------------|---------|
| AUDIT_HMAC_KEY | HMAC key for audit signing | dev-key-change-in-production |
| FIREAI_API_KEY | API key for authentication | change-me-in-production |
| LOG_LEVEL | Logging level | INFO |

================================================================================
ERROR MESSAGES
================================================================================

| Code | Message | Meaning |
|------|---------|---------|
| SAFETY_REFUSAL | Safety validation failed | Room rejected for safety |
| INPUT_ERROR | Invalid input | Missing or invalid parameters |
| COVERAGE_ERROR | Coverage incomplete | Less than 100% coverage |
| PLACEMENT_ERROR | No valid placement | Can't place detectors |
| CEILING_RANGE | Ceiling outside NFPA range | Must be 3.0-15.24m |
| WALL_VIOLATION | Too close to wall | Detector < 0.1m from wall |
| AUDIT_TAMPERED | Audit integrity compromised | HMAC signature mismatch |

================================================================================
PERFORMANCE NOTES
================================================================================

- 10x10m room: ~0.5s (OK)
- 50x50m room: >60s with resilience (use run_resilience=False)
- Single detector rooms: Always resilience=False (no redundancy)
- Multi-worker: ThreadPoolExecutor supported but single-process recommended

================================================================================
COMMIT
================================================================================

Refer to: `git log --oneline -1`
