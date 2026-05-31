# FireAI V10 – Elite NFPA 72-2022 Fire Alarm Design System

## Overview
FireAI V10 is a production‑grade, safety‑first expert system that automates fire alarm detector placement per **NFPA 72 (2022)**. It covers:
- Room‑by‑room and entire‑floor analysis
- Automatic detector type selection (smoke/heat) based on occupancy
- Coverage proof via grid sampling
- Wall distance and duct detector enforcement
- Voltage drop and battery backup calculations
- Immutable audit trail for professional engineer (PE) review

**Author:** Ahmed Elbaz

## Repository Structure
```
fireai/
├── core/                  # Core library (installable)
│   ├── fire_expert_system.py
│   ├── nfpa72_models.py
│   ├── nfpa72_calculations.py
│   ├── nfpa72_coverage.py
│   ├── floor_orchestrator.py
│   ├── fireai_api.py      # FastAPI application
│   ├── audit_trail.py
│   └── room_validator.py
├── README.md
├── CHANGELOG.md
├── LIMITATIONS.md
├── TESTING.md
└── SECURITY.md
```

## Installation
```bash
pip install -r requirements.txt
```
*Requirements include: fastapi, uvicorn, pydantic, shapely, slowapi, pulp*

## Running the API
```bash
export FIREAI_API_KEYS="your-secret-key"
uvicorn fireai.core.fireai_api:app --host 0.0.0.0 --port 8000
```

## API Usage
### Analyse a single room
```bash
curl -X POST "http://localhost:8000/analyse/room" \
  -H "X-Api-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "room": {
      "room_id": "room1",
      "name": "Office",
      "polygon_coords": [[0,0],[6,0],[6,8],[0,8]],
      "ceiling": {"height_at_low_point_m": 3.0},
      "room_type": "office"
    },
    "required_coverage_pct": 100
  }'
```
### Analyse an entire floor
```bash
curl -X POST "http://localhost:8000/analyse/floor" \
  -H "X-Api-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "floor_id": "floor1",
    "rooms": [...]
  }'
```
## Important Caveats
- Heights below 3.0 m or above 15.24 m are **clamped** to the normative range and flagged for PE review.
- Rooms larger than 5000 m² require manual engineering judgment.
- The system does **not** import DWG/RVT files directly; use the `/projects/` endpoint for raw uploads (JSON format).

## License
Proprietary – contact the repository owner for licensing.