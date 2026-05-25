# FireAlarmAI Accuracy Engine v1

Deterministic fire alarm device placement using Shapely geometry and NFPA-based rules.

## Quick Start

```bash
pip install -r requirements-accuracy.txt
cd api
uvicorn main:app --reload
```

Open http://localhost:8000

## API

POST /api/accuracy-engine
GET /api/health
GET /api/export/dxf

## Rules

| Room Type | Detector | Density | Radius |
|----------|----------|---------|--------|
| Office | Smoke | 60 m² | 7.5m |
| Storage | Heat | 40 m² | 6.0m |
| Corridor | Smoke (linear) | 50 m² | 7.5m |
| Staircase | Smoke (mandatory) | - | 7.5m |

## Validation

- Coverage must be ≥ 90%
- Minimum device spacing: 3.0m
- All rooms must have at least 1 device