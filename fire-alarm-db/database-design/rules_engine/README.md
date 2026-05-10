# FireAlarmAI Rules Engine

Deterministic rules engine for fire alarm device placement based on NFPA-informed logic.

## Usage

```python
from core.engine import run_fire_alarm_engine

rooms = [
    {
        "id": "office1",
        "type": "office",
        "area": 120,
        "polygon": [(0, 0), (10, 0), (10, 12), (0, 12)]
    }
]

result = run_fire_alarm_engine(rooms)
print(result)
```

## API

POST /run-engine

Request body: list of Room objects
Response: devices, zones, validation report

## Rules

| Room Type | Detector | Spacing |
|----------|----------|---------|
| Office | Smoke | 7.5m radius, 15m spacing |
| Corridor | Smoke (linear) | 7.5m |
| Storage/Kitchen | Heat | 5.0m radius |
| Staircase | Smoke | Mandatory |