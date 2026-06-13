# FireAI — API Endpoints Index

**Generated:** 2026-06-13  
**Total Endpoints:** 66  
**Source:** `backend/routers/*.py`

---

## Health & Monitoring

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/api/monitor/health` | Health & Monitoring | ) |
| GET | `/api/monitor/metrics` | Health & Monitoring | ) |
| GET | `/api/monitor/engine-status` | Health & Monitoring | ) |
| GET | `/api/monitor/agent-activity` | Health & Monitoring | ) |
| GET | `/api/monitor/security-alerts` | Health & Monitoring | ) |
| GET | `/api/monitor/alerts` | Health & Monitoring |  |
| GET | `/health` | Health & Monitoring | ) |
| GET | `/health/statistics` | Health & Monitoring | ) |
| GET | `/reports/statistics` | Health & Monitoring |  |

## Projects

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/{project_id}` | Projects |  |
| PUT | `/{project_id}` | Projects |  |
| DELETE | `/{project_id}` | Projects |  |

## Devices

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/{device_id}` | Devices |  |
| PUT | `/{device_id}` | Devices |  |
| DELETE | `/{device_id}` | Devices |  |

## Connections

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| PUT | `/{connection_id}` | Connections |  |
| DELETE | `/{connection_id}` | Connections |  |
| DELETE | `/{connection_id}` | Connections |  |

## Reports

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/{report_id}` | Reports | ) |
| GET | `/{report_id}/export` | Reports |  |

## Exports

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/dxf` | Exports | ) |
| GET | `/revit` | Exports | ) |
| GET | `/ifc` | Exports |  |

## Environment

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/countries` | Environment | ) |
| GET | `/weather` | Environment | ) |
| GET | `/geocode` | Environment | ) |
| GET | `/region` | Environment | ) |
| GET | `/elevation` | Environment | ) |
| GET | `/air-quality` | Environment | ) |
| GET | `/severe-weather` | Environment | ) |
| GET | `/hazmat` | Environment | ) |
| GET | `/hazmat/known` | Environment | ) |
| GET | `/context` | Environment | ) |
| GET | `/full-context` | Environment |  |

## QOMN Engineering

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/qomn/audit` | QOMN Engineering | ) |
| GET | `/qomn/physics-guards` | QOMN Engineering | ) |
| GET | `/qomn/constants` | QOMN Engineering |  |
| POST | `/qomn/smoke-spacing` | QOMN Engineering | ) |
| POST | `/qomn/heat-spacing` | QOMN Engineering | ) |
| POST | `/qomn/battery` | QOMN Engineering | ) |
| POST | `/qomn/voltage-drop` | QOMN Engineering | ) |
| POST | `/qomn/place-detectors` | QOMN Engineering | ) |
| POST | `/qomn/place-duct` | QOMN Engineering | ) |
| POST | `/qomn/golden-tests` | QOMN Engineering |  |

## FACP

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/facp/panels` | FACP |  |
| POST | `/facp/select` | FACP | ) |
| POST | `/facp/verify` | FACP | ) |
| POST | `/facp/schedule` | FACP | ) |
| POST | `/facp/spec` | FACP |  |

## Workflow

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/status` | Workflow | , dependencies=[Depends(verify_api_key_dep)]) |
| GET | `/{workflow_id}/status` | Workflow | , dependencies=[Depends(verify_api_key_dep)]) |
| GET | `/{workflow_id}/audit` | Workflow |  |
| POST | `/start` | Workflow | , dependencies=[Depends(verify_api_key_dep)]) |
| POST | `/{workflow_id}/approve` | Workflow | , dependencies=[Depends(verify_api_key_dep)]) |
| POST | `/{workflow_id}/reject` | Workflow |  |

## Memory

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/status` | Memory | , summary="Get all memories") |
| GET | `/all` | Memory | , summary="Get memory history") |
| GET | `/{memory_id}/history` | Memory |  |
| POST | `/add` | Memory | , summary="Search memories") |
| POST | `/search` | Memory |  |
| DELETE | `/{memory_id}` | Memory |  |

## Elements

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/{element_id}` | Elements |  |
| PUT | `/{element_id}` | Elements |  |
| DELETE | `/{element_id}` | Elements |  |

## Conflicts

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| POST | `/detect` | Conflicts | , response_model=ApiResponse[ConflictResponse]) |
| POST | `/{conflict_id}/resolve` | Conflicts |  |

