# FireAI — API Endpoints Index

**Generated:** 2026-06-13  
**Total Endpoints:** 81  
**Source:** `backend/routers/*.py`

---

## 📡 Health & Monitoring

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/health` | health.py | Health check |
| GET | `/api/health/statistics` | health.py | Health statistics |
| GET | `/api/reports/statistics` | health.py | Reports statistics |
| GET | `/api/monitor/health` | monitor.py | Monitor health |
| GET | `/api/monitor/metrics` | monitor.py | System metrics |
| GET | `/api/monitor/engine-status` | monitor.py | Engine status |
| GET | `/api/monitor/agent-activity` | monitor.py | Agent activity |
| GET | `/api/monitor/security-alerts` | monitor.py | Security alerts |
| GET | `/api/monitor/alerts` | monitor.py | All alerts |

---

## 🏢 Projects

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/projects` | projects.py | List all projects |
| POST | `/api/projects` | projects.py | Create project |
| GET | `/api/projects/{project_id}` | projects.py | Get project |
| PUT | `/api/projects/{project_id}` | projects.py | Update project |
| DELETE | `/api/projects/{project_id}` | projects.py | Delete project |

---

## 📱 Devices

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/projects/{project_id}/devices` | devices.py | List devices |
| POST | `/api/projects/{project_id}/devices` | devices.py | Create device |
| GET | `/api/projects/{project_id}/devices/{device_id}` | devices.py | Get device |
| PUT | `/api/projects/{project_id}/devices/{device_id}` | devices.py | Update device |
| DELETE | `/api/projects/{project_id}/devices/{device_id}` | devices.py | Delete device |

---

## 🔗 Connections

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/projects/{project_id}/connections` | connections.py | List connections |
| POST | `/api/projects/{project_id}/connections` | connections.py | Create connection |
| DELETE | `/api/projects/{project_id}/connections/{connection_id}` | connections.py | Delete connection |
| GET | `/api/connections` | connections_v2.py | List connections (UDM) |
| POST | `/api/connections` | connections_v2.py | Create connection (UDM) |
| DELETE | `/api/connections/{connection_id}` | connections_v2.py | Delete connection (UDM) |

---

## 📊 Reports

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/projects/{project_id}/reports` | reports.py | List reports |
| POST | `/api/projects/{project_id}/reports` | reports.py | Generate report |
| GET | `/api/projects/{project_id}/reports/{report_id}` | reports.py | Get report |
| GET | `/api/projects/{project_id}/reports/{report_id}/export` | reports.py | Export report |

---

## 📤 Exports

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/projects/{project_id}/export/dxf` | exports.py | Export DXF |
| GET | `/api/projects/{project_id}/export/revit` | exports.py | Export Revit |
| GET | `/api/projects/{project_id}/export/ifc` | exports.py | Export IFC |

---

## 🔄 Sync

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| POST | `/api/projects/{project_id}/sync` | sync.py | Start sync |
| GET | `/api/projects/{project_id}/sync` | sync.py | Get sync status |

---

## 🌍 Environment

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/environment/countries` | environment.py | List countries |
| GET | `/api/environment/weather` | environment.py | Weather data |
| GET | `/api/environment/geocode` | environment.py | Geocoding |
| GET | `/api/environment/region` | environment.py | Region info |
| GET | `/api/environment/elevation` | environment.py | Elevation data |
| GET | `/api/environment/air-quality` | environment.py | Air quality |
| GET | `/api/environment/severe-weather` | environment.py | Severe weather |
| GET | `/api/environment/hazmat` | environment.py | Hazmat data |
| GET | `/api/environment/hazmat/known` | environment.py | Known hazmat |
| GET | `/api/environment/context` | environment.py | Context data |
| GET | `/api/environment/full-context` | environment.py | Full context |

---

## 🔬 QOMN Engineering

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| POST | `/api/qomn/smoke-spacing` | qomn.py | Smoke detector spacing |
| POST | `/api/qomn/heat-spacing` | qomn.py | Heat detector spacing |
| POST | `/api/qomn/battery` | qomn.py | Battery calculation |
| POST | `/api/qomn/voltage-drop` | qomn.py | Voltage drop calculation |
| POST | `/api/qomn/place-detectors` | qomn.py | Place detectors |
| POST | `/api/qomn/place-duct` | qomn.py | Place duct detectors |
| GET | `/api/qomn/audit` | qomn.py | Audit log |
| GET | `/api/qomn/physics-guards` | qomn.py | Physics guards info |
| GET | `/api/qomn/constants` | qomn.py | NFPA72 constants |
| POST | `/api/qomn/golden-tests` | qomn.py | Run golden tests |

---

## 🔥 FACP (Fire Alarm Control Panel)

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| POST | `/api/facp/facp/select` | facp.py | Select FACP |
| POST | `/api/facp/facp/verify` | facp.py | Verify FACP |
| POST | `/api/facp/facp/schedule` | facp.py | Schedule FACP |
| POST | `/api/facp/facp/spec` | facp.py | Get FACP spec |
| GET | `/api/facp/facp/panels` | facp.py | List panels |

---

## ⚙️ Workflow

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/workflow/status` | workflow.py | Workflow status |
| POST | `/api/workflow/start` | workflow.py | Start workflow |
| GET | `/api/workflow/{workflow_id}/status` | workflow.py | Workflow status |
| POST | `/api/workflow/{workflow_id}/approve` | workflow.py | Approve workflow |
| POST | `/api/workflow/{workflow_id}/reject` | workflow.py | Reject workflow |

---

## 🧠 Memory

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/memory/status` | memory.py | Memory status |
| POST | `/api/memory/add` | memory.py | Add memory |
| POST | `/api/memory/search` | memory.py | Search memories |
| GET | `/api/memory/all` | memory.py | Get all memories |
| DELETE | `/api/memory/{memory_id}` | memory.py | Delete memory |
| GET | `/api/memory/{memory_id}/history` | memory.py | Memory history |

---

## 📐 Elements (UniversalDataModel)

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/elements` | elements.py | List elements |
| POST | `/api/elements` | elements.py | Create element |
| GET | `/api/elements/{element_id}` | elements.py | Get element |
| PUT | `/api/elements/{element_id}` | elements.py | Update element |
| DELETE | `/api/elements/{element_id}` | elements.py | Delete element |

---

## ⚠️ Conflicts

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/conflicts` | conflicts.py | List conflicts |
| POST | `/api/conflicts/detect` | conflicts.py | Detect conflicts |
| POST | `/api/conflicts/{conflict_id}/resolve` | conflicts.py | Resolve conflict |

---

## 📄 DWG Parsing

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| POST | `/api/parse-dwg` | dwg.py | Parse DWG file |

---

## 🔀 Optional Services (Graceful Degradation)

| Service | Endpoint Prefix | Condition |
|---------|-----------------|-----------|
| Workflow | `/api/workflow/*` | Requires `langgraph` |
| Memory | `/api/memory/*` | Requires `mem0` + `qdrant` |

---

## 📝 Response Format

All endpoints return JSON in this format:

```json
{
  "success": true,
  "data": { ... },
  "message": "Optional message"
}
```

Error response:
```json
{
  "success": false,
  "error": "Error message",
  "details": [ ... ]
}
```

---

## 🔒 Authentication

- **API Key**: Required for workflow endpoints
- **Public**: Health, projects, devices, connections, environment (read-only)
- **Internal**: Monitor, security alerts (admin only)

---

*Auto-generated by `fireai/tools/api_indexer.py`*