# FireAI API Documentation

## Base URL

```
Production: https://your-domain.com/api
Development: http://localhost:8000/api
```

## Authentication

All mutating endpoints (POST, PUT, DELETE, PATCH) require the `X-API-Key` header.

```http
POST /api/projects
X-API-Key: your-api-key-here
```

GET endpoints do not require authentication by default.

## Rate Limiting

Per-path rate limits with longest-prefix match algorithm. Configurable via environment variables.

## Endpoints (64 total)

| Router | Prefix | Endpoints | Description |
|--------|--------|-----------|-------------|
| health | `/api/health` | 2 | Health check, statistics |
| projects | `/api/projects` | 5 | Project CRUD |
| devices | `/api/projects/:id/devices` | 5 | Fire alarm device CRUD |
| connections | `/api/projects/:id/connections` | 3 | Cable connection CRUD |
| reports | `/api/projects/:id/reports` | 2 | Engineering reports |
| exports | `/api/projects/:id/export` | 4 | DXF, Revit, IFC exports |
| sync | `/api/projects/:id/sync` | 3 | Project sync + WebSocket |
| elements | `/api/elements` | 5 | UDM element CRUD |
| connections_v2 | `/api/connections` | 3 | UDM relationship connections |
| conflicts | `/api/conflicts` | 3 | Conflict detection/resolution |
| environment | `/api/environment` | 9 | Weather, geocoding, elevation, AQI, hazmat |
| facp | `/api/facp` | 5 | FACP selection & compliance |
| qomn | `/api/qomn` | 9 | QOMN-FIRE engineering kernel |
| workflow* | `/api/workflow` | 5 | LangGraph workflow engine |
| memory* | `/api/memory` | 4 | Mem0 long-term memory |

*Optional — requires separate dependencies (`pip install fireai[workflow]` or `pip install fireai[memory]`). Returns 503 if not installed.

## Common Response Format

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

Error responses:
```json
{
  "success": false,
  "data": null,
  "error": "Description of the error"
}
```

## Key Endpoints

### Health Check
```
GET /api/health → {"status": "ok", "version": "1.0.0", "database": "connected"}
```

### Create Project
```
POST /api/projects
Body: {"name": "Project Name", "description": "..."}
Response: {"id": "...", "name": "...", "created_at": "..."}
```

### NFPA 72 Analysis (QOMN)
```
POST /api/qomn/analyze
Body: {"room_id": "...", "room_type": "...", "ceiling_height": 3.0, "area_m2": 100.0}
Response: {"detector_count": 3, "spacing_m": 9.0, "compliant": true}
```

### FACP Selection
```
POST /api/facp/select
Body: {"device_count": 150, "required_zones": 10}
Response: {"recommended_panel": "NOTIFIER NFS2-3030", "compliant": true}
```