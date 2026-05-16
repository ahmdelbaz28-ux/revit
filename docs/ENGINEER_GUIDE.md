# FireAI Engineer Guide

Complete operational guide for FireAI V10 production system.

## Quick Start

### 1. Run the System

```bash
cd /workspace/project/revit

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest fireai/core/test_coverage.py -v

# Start API
python -m uvicorn fireai.core.fireai_api:app --host 0.0.0.0 --port 8000
```

### 2. Analyze a Room

**Using Python:**
```python
from fireai.core.fireai_core import FireAISystem
from fireai.core.nfpa72_models import RoomSpec, CeilingSpec

system = FireAISystem(db_path=':memory:')
room = RoomSpec(
    room_id='room_1',
    width_m=10,
    depth_m=10,
    ceiling_spec=CeilingSpec(3.0)
)

result = system.analyse_room(room, run_resilience=True)
print(f"Detectors: {len(result.detector_positions)}")
print(f"Confidence: {result.confidence}")
```

**Using curl:**
```bash
# Set API key
export FIREAI_API_KEYS="test-key-123"

# Analyze room via API
curl -X POST http://localhost:8000/analyse/room/v10 \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: test-key-123" \
  -d '{
    "room": {
      "room_id": "room_1",
      "width_m": 10,
      "depth_m": 10,
      "ceiling_spec": {
        "height_at_low_point_m": 3.0
      }
    }
  }'
```

### 3. Analyze a Floor

**Using Python:**
```python
rooms = [
    RoomSpec(room_id='office', width_m=10, depth_m=10, ceiling_spec=CeilingSpec(3.0)),
    RoomSpec(room_id='kitchen', width_m=5, depth_m=5, ceiling_spec=CeilingSpec(3.0)),
    RoomSpec(room_id='corridor', width_m=3, depth_m=10, ceiling_spec=CeilingSpec(3.0)),
]

results = system.analyse_floor(rooms, run_resilience=True)
print(f"Floor: {len(results)} rooms analyzed")
```

**Using curl:**
```bash
curl -X POST http://localhost:8000/analyse/floor/v10 \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: test-key-123" \
  -d '{
    "rooms": [
      {"room_id": "office", "width_m": 10, "depth_m": 10, "ceiling_spec": {"height_at_low_point_m": 3.0}},
      {"room_id": "kitchen", "width_m": 5, "depth_m": 5, "ceiling_spec": {"height_at_low_point_m": 3.0}},
      {"room_id": "corridor", "width_m": 3, "depth_m": 10, "ceiling_spec": {"height_at_low_point_m": 3.0}}
    ]
  }'
```

### 4. Async Floor Analysis

For large floors (10+ rooms), use async endpoint:

```bash
# Submit async job
curl -X POST http://localhost:8000/analyse/floor/async \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: test-key-123" \
  -d '{
    "rooms": [
      {"room_id": "room_1", "width_m": 10, "depth_m": 10, "ceiling_spec": {"height_at_low_point_m": 3.0}},
      ...
    ]
  }'

# Returns: {"task_id": "abc-123", "status": "processing"}

# Poll for results
curl http://localhost:8000/task/abc-123 -H "X-Api-Key: test-key-123"
# Returns: {"status": "completed", "result": {...}}
```

## 5. Audit Trail

### Read Audit Trail
```python
events = system.get_audit_trail()
for event in events:
    print(f"{event['event_type']}: {event.get('room_id')}")
```

### Verify Integrity
```python
is_valid = system.verify_audit_integrity()
print(f"Audit valid: {is_valid}")
```

### Using curl
```bash
curl http://localhost:8000/audit/trail -H "X-Api-Key: test-key-123"
curl http://localhost:8000/audit/verify -H "X-Api-Key: test-key-123"
```

---

## Error Messages Reference

| Error Code | Message | Meaning | Action |
|-----------|---------|---------|--------|
| SAFETY_REFUSAL | Design rejected: insufficient coverage | NFPA 72 coverage requirements not met | Redesign room layout |
| INPUT_VALIDATION | Invalid room dimensions | Width or depth out of range | Fix room specs |
| CEILING_TOO_HIGH | Ceiling exceeds max height | Room too tall for standard detection | Use elevated ceiling spec |
| CEILING_TOO_LOW | Ceiling below minimum | Room too low | Check ceiling height |
| WALL_DISTANCE | Detector too close to wall | NFPA 72 §17.6.3.1.1 violation | Reposition detectors |
| HVAC_OBSTRUCTION | HVAC duct blocks coverage | Duct in detection path | Use duct-mounted detector |
| RESILIENCE_FAILED | Single-point failure risk | No redundancy in design | Add detectors |
| HMAC_INVALID | Audit chain tampered | Event log modified | DO NOT trust results |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|------------|
| AUDIT_HMAC_KEY | Yes | Secret key for HMAC signing (min 32 chars) |
| FIREAI_API_KEYS | Yes | Comma-separated API keys |
| DATABASE_PATH | No | Path to SQLite database (default: ./audit.db) |
| REQUEST_TIMEOUT_SECONDS | No | API timeout (default: 30.0) |

### Setting Up Environment

```bash
# Generate HMAC key
export AUDIT_HMAC_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# Set API keys
export FIREAI_API_KEYS="key1,key2,key3"

# Optional: database path
export DATABASE_PATH="/data/fireai_audit.db"
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    API Layer                        │
│  /analyse/room/v10, /analyse/floor/v10, /task/{id} │
└─────────────────────┬───────────────────────────────┘
                     │
┌─────────────────────▼───────────────────────────────┐
│              FireAISystem (Orchestrator)             │
│  - analyse_room()                               │
│  - analyse_floor()                           │
│  - audit_store.add_event()                    │
└─────────────────────┬───────────────────────────────┘
                     │
┌─────────────────────▼───────────────────────────────┐
│         fire_expert_system (V10 Enhanced)        │
│  - ExpertSystem.analyse_room()               │
│  - ResilienceResult (Monte Carlo)            │
│  - EnhancedExpertResult                    │
└─────────────────────────────────────────────┘
                     │
┌─────────────────────▼───────────────────────────────┐
│               AuditStore (HMAC)              │
│  - Tamper-evident event log                 │
│  - Chain verification                      │
└─────────────────────────────────────────────┘
```

---

## Testing

### Run All Tests
```bash
python -m pytest fireai/core/test_coverage.py -v
python -m pytest fireai/core/test_domain_models.py -v
python -m pytest fireai/core/test_hmac_tamper.py -v
```

### Quick Validation
```python
from fireai.core.fireai_core import FireAISystem
from fireai.core.nfpa72_models import RoomSpec, CeilingSpec

system = FireAISystem(db_path=':memory:')
room = RoomSpec(room_id='test', width_m=10, depth_m=10, ceiling_spec=CeilingSpec(3.0))
result = system.analyse_room(room, run_resilience=True)

assert result.confidence.value in ['CERTIFIED', 'HIGH', 'MEDIUM']
assert len(result.detector_positions) > 0
print("Validation: PASS")
```

---

## Production Checklist

- [ ] AUDIT_HMAC_KEY set (32+ random characters)
- [ ] FIREAI_API_KEYS set (valid keys)
- [ ] All tests passing
- [ ] Audit verify returns valid
- [ ] API rate limiting configured
- [ ] Request timeout configured (30s)

---

*Generated: 2026-05-16 | Version: 10.0.0*