# FireAI — API Endpoints Index

**Generated:** 2026-06-13  
**Total Endpoints:** 69  
**Source:** `backend/routers/*.py`

---

## Health & Monitoring

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/health` | Health & Monitoring | , dependencies=[Depends(require_permission(Permission.HEALTH |
| GET | `/health/statistics` | Health & Monitoring | , dependencies=[Depends(require_permission(Permission.HEALTH |
| GET | `/reports/statistics` | Health & Monitoring |  |
| GET | `/api/v1/monitor/health` | Health & Monitoring | , dependencies=[Depends(require_permission(Permission.MONITO |
| GET | `/api/v1/monitor/metrics` | Health & Monitoring | , dependencies=[Depends(require_permission(Permission.MONITO |
| GET | `/api/v1/monitor/engine-status` | Health & Monitoring | , dependencies=[Depends(require_permission(Permission.MONITO |
| GET | `/api/v1/monitor/agent-activity` | Health & Monitoring | , dependencies=[Depends(require_permission(Permission.MONITO |
| GET | `/api/v1/monitor/security-alerts` | Health & Monitoring | , dependencies=[Depends(require_permission(Permission.MONITO |
| GET | `/api/v1/monitor/alerts` | Health & Monitoring |  |

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
| DELETE | `/{connection_id}` | Connections |  |
| PUT | `/{connection_id}` | Connections |  |
| DELETE | `/{connection_id}` | Connections |  |

## Reports

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/{report_id}` | Reports | , dependencies=[Depends(require_permission(Permission.REPORT |
| GET | `/{report_id}/export` | Reports |  |

## Exports

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/dxf` | Exports | , dependencies=[Depends(require_permission(Permission.EXPORT |
| GET | `/revit` | Exports | , dependencies=[Depends(require_permission(Permission.EXPORT |
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
| GET | `/qomn/audit` | QOMN Engineering | , dependencies=[Depends(require_permission(Permission.QOMN_R |
| GET | `/qomn/physics-guards` | QOMN Engineering | , dependencies=[Depends(require_permission(Permission.QOMN_R |
| GET | `/qomn/constants` | QOMN Engineering |  |
| POST | `/qomn/smoke-spacing` | QOMN Engineering | , dependencies=[Depends(require_permission(Permission.QOMN_E |
| POST | `/qomn/heat-spacing` | QOMN Engineering | , dependencies=[Depends(require_permission(Permission.QOMN_E |
| POST | `/qomn/battery` | QOMN Engineering | , dependencies=[Depends(require_permission(Permission.QOMN_E |
| POST | `/qomn/voltage-drop` | QOMN Engineering | , dependencies=[Depends(require_permission(Permission.QOMN_E |
| POST | `/qomn/place-detectors` | QOMN Engineering | , dependencies=[Depends(require_permission(Permission.QOMN_E |
| POST | `/qomn/place-duct` | QOMN Engineering | , dependencies=[Depends(require_permission(Permission.QOMN_E |
| POST | `/qomn/golden-tests` | QOMN Engineering |  |

## FACP

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/facp/panels` | FACP |  |
| POST | `/facp/select` | FACP | , dependencies=[Depends(require_permission(Permission.FACP_M |
| POST | `/facp/verify` | FACP | , dependencies=[Depends(require_permission(Permission.FACP_M |
| POST | `/facp/schedule` | FACP | , dependencies=[Depends(require_permission(Permission.FACP_M |
| POST | `/facp/spec` | FACP |  |

## Workflow

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/status` | Workflow | , dependencies=[Depends(require_permission(Permission.WORKFL |
| GET | `/{workflow_id}/status` | Workflow | , dependencies=[Depends(require_permission(Permission.WORKFL |
| GET | `/{workflow_id}/audit` | Workflow |  |
| POST | `/start` | Workflow | , dependencies=[Depends(require_permission(Permission.WORKFL |
| POST | `/{workflow_id}/approve` | Workflow | , dependencies=[Depends(require_permission(Permission.WORKFL |
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
| POST | `/detect` | Conflicts | , response_model=ApiResponse[ConflictResponse], dependencies |
| POST | `/{conflict_id}/resolve` | Conflicts |  |

## Admin

| Method | Endpoint | Handler | Description |
|--------|----------|---------|-------------|
| GET | `/roles` | Admin |  |
| PUT | `/{key_hash}` | Admin |  |
| DELETE | `/{key_hash}` | Admin |  |

