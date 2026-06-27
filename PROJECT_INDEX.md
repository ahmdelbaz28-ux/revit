# 📋 FireAI Project Index — Complete Codebase Map

> **Auto-generated:** V140 Phase 8 — Professional project indexing
> **Last updated:** 2026-06-28
> **Branch:** `fix/v140-pre-launch-build-readiness`

---

## 📊 Project Statistics

| Metric | Count |
|--------|-------|
| **Backend API Endpoints** | 188 |
| **Backend Python Modules** | 386 |
| **Backend Services** | 13 |
| **Frontend Pages** | 21 |
| **Frontend Components** | 131 |
| **Frontend Services** | 10 |
| **Frontend Hooks** | 7 |
| **i18n Keys (EN)** | 7 sections |
| **i18n Keys (AR)** | 10 sections |
| **Skills** | 59 |
| **Python Test Files** | 176 |
| **Frontend Test Files** | 9 |
| **Deploy Files** | 36 |
| **Total Python Files** | 576 |
| **Total TS/TSX Files** | 219 |
| **Total Python Lines** | 279,720 |
| **Total TS/TSX Lines** | 43,144 |

---

## 🏗️ Backend Architecture

### Directory Structure
- `backend/` — FastAPI application — main entry point, routers, services, middleware
- `backend/routers/` — 23 API routers (projects, devices, elements, connections, conflicts, reports, etc.)
- `backend/services/` — 13 service modules (AutoCAD, Revit, weather, geocoding, digital twin, etc.)
- `backend/tests/` — Backend integration tests
- `fireai/` — Core fire protection engine — NFPA 72 calculations, coverage analysis, audit trail
- `fireai/core/` — 100+ modules: NFPA 72 engine, voltage drop, battery, coverage, routing, audit
- `fireai/bridges/` — BIM integration: IFC, Revit, AutoCAD bridges
- `fireai/infrastructure/` — Event bus, GraphRAG, webhook, metrics, health, tracing
- `fireai/conduit/` — Conduit fill, bend, routing calculations
- `fireai/v17_core/` — Battery calculator, acoustic calculator, tenability evaluator
- `fireai/validation/` — Compliance engine, QA engine, multi-standard validator
- `fireai/constants/` — NFPA 72 + NEC constants
- `core/` — Universal data model, retry logic, database
- `parsers/` — DWG, DXF, IFC, PDF, Excel, Word, image parsers
- `qomn_fire/` — QOMN fire alarm: drawing, engine, parsers, output
- `qomn_conduit/` — QOMN conduit: fill, bend, router, catalog, fitting engine
- `marine/` — Marine fire protection: SOLAS, LR, IEC 60092, ISO 15370, NFPA 302, MODU
- `facp_system/` — FACP panel database, selector, verifier, output
- `facp_distributed/` — Distributed FACP: event bus, gateway, orchestrator, workers (optional)
- `adapters/` — PDF-to-rooms adapter
- `integration/` — IFC bridge

### API Endpoints (188 total)

| Router | Method | Path |
|--------|--------|------|
| analyze | `POST` | `/api/v1/None/analyze/battery` |
| analyze | `POST` | `/api/v1/None/analyze/voltage` |
| api_keys | `GET` | `/api/v1/admin/keys` |
| api_keys | `POST` | `/api/v1/admin/keys` |
| api_keys | `DELETE` | `/api/v1/admin/keys/{key_hash}` |
| api_keys | `PUT` | `/api/v1/admin/keys/{key_hash}` |
| api_keys | `GET` | `/api/v1/admin/keys/roles` |
| app | `GET` | `/health` |
| app | `GET` | `/api/v2/health` |
| app | `POST` | `/api/v1/cache/clear` |
| app | `GET` | `/api/v1/cache/stats` |
| autocad | `POST` | `/api/v1/autocad/connect` |
| autocad | `POST` | `/api/v1/autocad/disconnect` |
| autocad | `POST` | `/api/v1/autocad/read_dwg` |
| autocad | `POST` | `/api/v1/autocad/write_dwg` |
| autocad | `POST` | `/api/v1/autocad/draw_line` |
| autocad | `POST` | `/api/v1/autocad/draw_polyline` |
| autocad | `POST` | `/api/v1/autocad/draw_circle` |
| autocad | `POST` | `/api/v1/autocad/draw_text` |
| autocad | `GET` | `/api/v1/autocad/status` |
| autocad | `POST` | `/api/v1/autocad/save` |
| autocad | `POST` | `/api/v1/autocad/upload_dwg` |
| autocad | `DELETE` | `/api/v1/autocad/entity/{handle}` |
| autocad | `PUT` | `/api/v1/autocad/entity/{handle}` |
| conflicts | `GET` | `/api/v1/conflicts` |
| conflicts | `POST` | `/api/v1/conflicts/detect` |
| conflicts | `POST` | `/api/v1/conflicts/{conflict_id}/resolve` |
| connections | `GET` | `/api/v1/projects/{project_id}/connections` |
| connections | `POST` | `/api/v1/projects/{project_id}/connections` |
| connections | `PUT` | `/api/v1/projects/{project_id}/connections/{connection_id}` |
| connections | `DELETE` | `/api/v1/projects/{project_id}/connections/{connection_id}` |
| connections_v2 | `GET` | `/api/v1/connections` |
| connections_v2 | `POST` | `/api/v1/connections` |
| connections_v2 | `DELETE` | `/api/v1/connections/{connection_id}` |
| devices | `GET` | `/api/v1/projects/{project_id}/devices` |
| devices | `POST` | `/api/v1/projects/{project_id}/devices` |
| devices | `GET` | `/api/v1/projects/{project_id}/devices/{device_id}` |
| devices | `PUT` | `/api/v1/projects/{project_id}/devices/{device_id}` |
| devices | `DELETE` | `/api/v1/projects/{project_id}/devices/{device_id}` |
| digital_twin | `POST` | `/api/v1/digital-twin/convert` |
| digital_twin | `GET` | `/api/v1/digital-twin/history` |
| digital_twin | `POST` | `/api/v1/digital-twin/configure` |
| digital_twin | `POST` | `/api/v1/digital-twin/rollback/{version_id}` |
| digital_twin | `GET` | `/api/v1/digital-twin/mappings` |
| digital_twin | `GET` | `/api/v1/digital-twin/status` |
| digital_twin | `POST` | `/api/v1/digital-twin/update_mapping` |
| digital_twin | `GET` | `/api/v1/digital-twin/config` |
| digital_twin | `PUT` | `/api/v1/digital-twin/config` |
| digital_twin | `GET` | `/api/v1/digital-twin/download/{filename:path}` |
| dwg | `POST` | `/api/v1/parse-dwg` |
| elements | `GET` | `/api/v1/elements` |
| elements | `POST` | `/api/v1/elements` |
| elements | `GET` | `/api/v1/elements/{element_id}` |
| elements | `PUT` | `/api/v1/elements/{element_id}` |
| elements | `DELETE` | `/api/v1/elements/{element_id}` |
| environment | `GET` | `/api/v1/environment/countries` |
| environment | `GET` | `/api/v1/environment/weather` |
| environment | `GET` | `/api/v1/environment/geocode` |
| environment | `GET` | `/api/v1/environment/region` |
| environment | `GET` | `/api/v1/environment/elevation` |
| environment | `GET` | `/api/v1/environment/air-quality` |
| environment | `GET` | `/api/v1/environment/severe-weather` |
| environment | `GET` | `/api/v1/environment/hazmat` |
| environment | `GET` | `/api/v1/environment/hazmat/known` |
| environment | `GET` | `/api/v1/environment/context` |
| environment | `GET` | `/api/v1/environment/full-context` |
| exports | `GET` | `/api/v1/projects/{project_id}/export/dxf` |
| exports | `GET` | `/api/v1/projects/{project_id}/export/revit` |
| exports | `GET` | `/api/v1/projects/{project_id}/export/ifc` |
| facp | `POST` | `/api/v1/None/facp/select` |
| facp | `POST` | `/api/v1/None/facp/verify` |
| facp | `POST` | `/api/v1/None/facp/schedule` |
| facp | `POST` | `/api/v1/None/facp/spec` |
| facp | `GET` | `/api/v1/None/facp/panels` |
| health | `GET` | `/api//health` |
| health | `GET` | `/api//health/statistics` |
| health | `GET` | `/api//reports/statistics` |
| marine | `GET` | `/api/v1/marine/standards` |
| marine | `GET` | `/api/v1/marine/fire-classes` |
| marine | `POST` | `/api/v1/marine/ship/validate` |
| marine | `POST` | `/api/v1/marine/ship/design` |
| marine | `POST` | `/api/v1/marine/zones/divide` |
| marine | `POST` | `/api/v1/marine/extinguishing/design` |
| marine | `POST` | `/api/v1/marine/alarm-logic/generate` |
| marine | `POST` | `/api/v1/marine/integrations/scada` |
| marine | `POST` | `/api/v1/marine/detection/design` |
| marine | `POST` | `/api/v1/marine/divisions/generate` |
| marine | `POST` | `/api/v1/marine/power/design` |
| marine | `POST` | `/api/v1/marine/integrations/etap` |
| marine | `POST` | `/api/v1/marine/integrations/dxf` |
| marine | `POST` | `/api/v1/marine/integrations/revit` |
| memory | `GET` | `/api/v1/memory/status` |
| memory | `POST` | `/api/v1/memory/add` |
| memory | `POST` | `/api/v1/memory/search` |
| memory | `GET` | `/api/v1/memory/all` |
| memory | `DELETE` | `/api/v1/memory/{memory_id}` |
| memory | `GET` | `/api/v1/memory/{memory_id}/history` |
| monitor | `GET` | `/api/v1/monitor/health` |
| monitor | `GET` | `/api/v1/monitor/metrics` |
| monitor | `GET` | `/api/v1/monitor/engine-status` |
| monitor | `GET` | `/api/v1/monitor/agent-activity` |
| monitor | `GET` | `/api/v1/monitor/security-alerts` |
| monitor | `GET` | `/api/v1/monitor/alerts` |
| projects | `GET` | `/api/v1/projects` |
| projects | `POST` | `/api/v1/projects` |
| projects | `GET` | `/api/v1/projects/{project_id}` |
| projects | `PUT` | `/api/v1/projects/{project_id}` |
| projects | `DELETE` | `/api/v1/projects/{project_id}` |
| qomn | `POST` | `/api/v1/None/qomn/smoke-spacing` |
| qomn | `POST` | `/api/v1/None/qomn/heat-spacing` |
| qomn | `POST` | `/api/v1/None/qomn/battery` |
| qomn | `POST` | `/api/v1/None/qomn/voltage-drop` |
| qomn | `POST` | `/api/v1/None/qomn/place-detectors` |
| qomn | `POST` | `/api/v1/None/qomn/place-duct` |
| qomn | `GET` | `/api/v1/None/qomn/audit` |
| qomn | `GET` | `/api/v1/None/qomn/physics-guards` |
| qomn | `GET` | `/api/v1/None/qomn/constants` |
| qomn | `POST` | `/api/v1/None/qomn/golden-tests` |
| reports | `GET` | `/api/v1/projects/{project_id}/reports` |
| reports | `POST` | `/api/v1/projects/{project_id}/reports` |
| reports | `GET` | `/api/v1/projects/{project_id}/reports/{report_id}` |
| reports | `GET` | `/api/v1/projects/{project_id}/reports/{report_id}/export` |
| revit | `POST` | `/api/v1/revit/connect` |
| revit | `POST` | `/api/v1/revit/disconnect` |
| revit | `GET` | `/api/v1/revit/status` |
| revit | `POST` | `/api/v1/revit/document/open` |
| revit | `POST` | `/api/v1/revit/document/save` |
| revit | `POST` | `/api/v1/revit/document/close` |
| revit | `POST` | `/api/v1/revit/read_rvt` |
| revit | `POST` | `/api/v1/revit/write_rvt` |
| revit | `POST` | `/api/v1/revit/upload_rvt` |
| revit | `GET` | `/api/v1/revit/elements` |
| revit | `GET` | `/api/v1/revit/elements/selected` |
| revit | `GET` | `/api/v1/revit/elements/{element_id}` |
| revit | `GET` | `/api/v1/revit/elements/{element_id}/parameters` |
| revit | `POST` | `/api/v1/revit/elements/create/wall` |
| revit | `POST` | `/api/v1/revit/elements/create/floor` |
| revit | `POST` | `/api/v1/revit/elements/create/door` |
| revit | `POST` | `/api/v1/revit/elements/create/window` |
| revit | `POST` | `/api/v1/revit/elements/create/column` |
| revit | `POST` | `/api/v1/revit/elements/create/beam` |
| revit | `POST` | `/api/v1/revit/elements/create/family` |
| revit | `PUT` | `/api/v1/revit/elements/{element_id}/parameters` |
| revit | `DELETE` | `/api/v1/revit/elements/{element_id}` |
| revit | `GET` | `/api/v1/revit/views` |
| revit | `GET` | `/api/v1/revit/levels` |
| revit | `GET` | `/api/v1/revit/grids` |
| revit | `GET` | `/api/v1/revit/worksets` |
| revit | `GET` | `/api/v1/revit/families/{category}/symbols` |
| revit | `POST` | `/api/v1/revit/families/load` |
| revit | `POST` | `/api/v1/revit/search/api/load` |
| revit | `POST` | `/api/v1/revit/search/api` |
| revit | `GET` | `/api/v1/revit/search/online` |
| revit | `POST` | `/api/v1/revit/execute` |
| sync | `POST` | `/api/v1/projects/{project_id}/sync` |
| sync | `GET` | `/api/v1/projects/{project_id}/sync` |
| sync | `WEBSOCKET` | `/api/v1/projects/{project_id}/sync/ws` |
| v2 | `POST` | `/api/v1/None/generative/design` |
| v2 | `GET` | `/api/v1/None/bim/providers` |
| v2 | `POST` | `/api/v1/None/bim/extract-rooms` |
| v2 | `GET` | `/api/v1/None/bim/health` |
| v2 | `POST` | `/api/v1/None/ifc43/map-detector` |
| v2 | `POST` | `/api/v1/None/ifc43/map-project` |
| v2 | `POST` | `/api/v1/None/ar/export` |
| v2 | `POST` | `/api/v1/None/webhooks/subscribe` |
| v2 | `GET` | `/api/v1/None/webhooks/subscriptions` |
| v2 | `DELETE` | `/api/v1/None/webhooks/subscriptions/{sub_id}` |
| v2 | `POST` | `/api/v1/None/webhooks/publish` |
| v2 | `POST` | `/api/v1/None/smoke-simulation/state` |
| v2 | `POST` | `/api/v1/None/memory/store` |
| v2 | `POST` | `/api/v1/None/memory/search` |
| v2 | `GET` | `/api/v1/None/memory/health` |
| v2 | `POST` | `/api/v1/None/topology/element` |
| v2 | `POST` | `/api/v1/None/topology/connection` |
| v2 | `POST` | `/api/v1/None/topology/impact` |
| v2 | `GET` | `/api/v1/None/topology/health` |
| v2 | `POST` | `/api/v1/None/graphrag/knowledge` |
| v2 | `POST` | `/api/v1/None/graphrag/ask` |
| v2 | `POST` | `/api/v1/None/graphrag/search` |
| v2 | `GET` | `/api/v1/None/graphrag/health` |
| v2 | `GET` | `/api/v1/None/health` |
| v2 | `GET` | `/api/v1/None/auth/csrf-token` |
| workflow | `GET` | `/api/v1/workflow/status` |
| workflow | `POST` | `/api/v1/workflow/start` |
| workflow | `GET` | `/api/v1/workflow/{workflow_id}/status` |
| workflow | `POST` | `/api/v1/workflow/{workflow_id}/approve` |
| workflow | `POST` | `/api/v1/workflow/{workflow_id}/reject` |
| workflow | `GET` | `/api/v1/workflow/{workflow_id}/audit` |

### Backend Services (13 modules)

| File | Lines |
|------|-------|
| `backend/services/air_quality_service.py` | 479 |
| `backend/services/autocad_service.py` | 751 |
| `backend/services/digital_twin_service.py` | 997 |
| `backend/services/elevation_service.py` | 310 |
| `backend/services/geocoding_service.py` | 279 |
| `backend/services/hazmat_service.py` | 461 |
| `backend/services/marine_service.py` | 192 |
| `backend/services/memory_service.py` | 738 |
| `backend/services/region_service.py` | 316 |
| `backend/services/revit_service.py` | 1671 |
| `backend/services/severe_weather_service.py` | 1285 |
| `backend/services/weather_service.py` | 401 |
| `backend/services/workflow_service.py` | 2173 |

### Top Backend Modules by Size (top 30)

| Module | File | Lines |
|--------|------|-------|
| `fireai.core.models_v21` | `fireai/core/models_v21.py` | 2200 |
| `backend.services.workflow_service` | `backend/services/workflow_service.py` | 2173 |
| `fireai.core.digital_twin` | `fireai/core/digital_twin.py` | 2082 |
| `fireai.integration.ar_vr_visualizer` | `fireai/integration/ar_vr_visualizer.py` | 2001 |
| `fireai.core.bps_allocator` | `fireai/core/bps_allocator.py` | 1916 |
| `fireai.core.pipeline` | `fireai/core/pipeline.py` | 1897 |
| `fireai.core.qomn_self_healing_engine` | `fireai/core/qomn_self_healing_engine.py` | 1883 |
| `fireai.core.multi_floor_orchestrator` | `fireai/core/multi_floor_orchestrator.py` | 1850 |
| `backend.services.revit_service` | `backend/services/revit_service.py` | 1671 |
| `fireai.core.qomn_fire_v4_fail_loud` | `fireai/core/qomn_fire_v4_fail_loud.py` | 1598 |
| `fireai.core.stairwell_smoke_control` | `fireai/core/stairwell_smoke_control.py` | 1596 |
| `fireai.core.routing_engine_v10` | `fireai/core/routing_engine_v10.py` | 1567 |
| `fireai.core.fireai_kernel_v30` | `fireai/core/fireai_kernel_v30.py` | 1514 |
| `fireai.core.floor_analyser` | `fireai/core/floor_analyser.py` | 1503 |
| `fireai.core.hac_classification_engine` | `fireai/core/hac_classification_engine.py` | 1483 |
| `fireai.core.digital_twin_sync` | `fireai/core/digital_twin_sync.py` | 1477 |
| `fireai.validation.qa_engine` | `fireai/validation/qa_engine.py` | 1473 |
| `fireai.core.nfpa72_calculations` | `fireai/core/nfpa72_calculations.py` | 1400 |
| `fireai.core.spatial_engine.density_optimizer` | `fireai/core/spatial_engine/density_optimizer.py` | 1359 |
| `backend.database` | `backend/database.py` | 1347 |
| `fireai.core.digital_twin_interface` | `fireai/core/digital_twin_interface.py` | 1337 |
| `fireai.bridges.integration_bridge` | `fireai/bridges/integration_bridge.py` | 1333 |
| `fireai.core.semi_cfast_engine` | `fireai/core/semi_cfast_engine.py` | 1322 |
| `backend.db_service` | `backend/db_service.py` | 1320 |
| `backend.services.severe_weather_service` | `backend/services/severe_weather_service.py` | 1285 |
| `fireai.core.safety_audit_engine` | `fireai/core/safety_audit_engine.py` | 1282 |
| `fireai.core.constraint_engine` | `fireai/core/constraint_engine.py` | 1269 |
| `fireai.core.ifc_parser` | `fireai/core/ifc_parser.py` | 1267 |
| `fireai.core.acoustics_engine` | `fireai/core/acoustics_engine.py` | 1257 |
| `fireai.validation.multi_standard_validator` | `fireai/validation/multi_standard_validator.py` | 1205 |

---

## 🎨 Frontend Architecture

### Directory Structure
- `frontend/src/pages/` — 21 page components (routes)
- `frontend/src/components/` — 131 UI components
- `frontend/src/components/shared/` — Shared components (ConnectionStatus, FileUploader, ElementList, ConversionPanel, HistoryTimeline, ConfigEditor, ContextualHelpButton, GlobalHelpDrawer)
- `frontend/src/components/ui/` — shadcn/ui base components (50+ components)
- `frontend/src/components/layout/` — AppShell, Sidebar, TopBar, StatusBar
- `frontend/src/components/firealarm/` — CanvasEditor, SymbolLibrary, ZoneNavigator, DeviceProperties
- `frontend/src/components/mockups/engineering/` — 29 engineering mockup components
- `frontend/src/services/` — 10 API service modules
- `frontend/src/hooks/` — 7 custom hooks
- `frontend/src/help/` — Help system (types, topics, context registry, SmartHelpProvider)
- `frontend/src/engine/` — Frontend calculation engines (voltage drop, coverage, battery, NFPA72, BOM)
- `frontend/src/i18n/` — Internationalization (EN + AR locales)
- `frontend/src/types/` — TypeScript type definitions

### Pages (Routes)
| Page | File | Lines |
|------|------|-------|
| AutoCADDrawPage | `frontend/src/pages/AutoCADDrawPage.tsx` | 222 |
| AutoCADPage | `frontend/src/pages/AutoCADPage.tsx` | 182 |
| CADSettingsPage | `frontend/src/pages/CADSettingsPage.tsx` | 533 |
| Conflicts | `frontend/src/pages/Conflicts.tsx` | 296 |
| Connections | `frontend/src/pages/Connections.tsx` | 311 |
| DashboardPage | `frontend/src/pages/DashboardPage.tsx` | 232 |
| DigitalTwinConfigPage | `frontend/src/pages/DigitalTwinConfigPage.tsx` | 60 |
| DigitalTwinConvertPage | `frontend/src/pages/DigitalTwinConvertPage.tsx` | 43 |
| DigitalTwinHistoryPage | `frontend/src/pages/DigitalTwinHistoryPage.tsx` | 16 |
| DigitalTwinPage | `frontend/src/pages/DigitalTwinPage.tsx` | 610 |
| ElementDetail | `frontend/src/pages/ElementDetail.tsx` | 337 |
| Elements | `frontend/src/pages/Elements.tsx` | 472 |
| EngineeringPage | `frontend/src/pages/EngineeringPage.tsx` | 549 |
| FireAlarmPage | `frontend/src/pages/FireAlarmPage.tsx` | 258 |
| ProjectsPage | `frontend/src/pages/ProjectsPage.tsx` | 493 |
| ReportGeneratorPage | `frontend/src/pages/ReportGeneratorPage.tsx` | 487 |
| ReportsPage | `frontend/src/pages/ReportsPage.tsx` | 390 |
| RevitCreatePage | `frontend/src/pages/RevitCreatePage.tsx` | 198 |
| RevitElementsPage | `frontend/src/pages/RevitElementsPage.tsx` | 67 |
| RevitPage | `frontend/src/pages/RevitPage.tsx` | 140 |
| SettingsPage | `frontend/src/pages/SettingsPage.tsx` | 395 |

### Frontend Services (API Layer)

| File | Lines |
|------|-------|
| `frontend/src/services/api.ts` | 319 |
| `frontend/src/services/apiValidation.ts` | 198 |
| `frontend/src/services/autocadService.ts` | 57 |
| `frontend/src/services/dataService.ts` | 487 |
| `frontend/src/services/digitalTwinApi.ts` | 789 |
| `frontend/src/services/digitalTwinService.ts` | 60 |
| `frontend/src/services/fullApi.ts` | 1082 |
| `frontend/src/services/mockServer.ts` | 57 |
| `frontend/src/services/mockWorker.ts` | 57 |
| `frontend/src/services/revitService.ts` | 200 |

### Frontend Hooks

| File | Lines |
|------|-------|
| `frontend/src/hooks/use-mobile.tsx` | 19 |
| `frontend/src/hooks/use-toast.ts` | 189 |
| `frontend/src/hooks/useApi.ts` | 482 |
| `frontend/src/hooks/useDrawing.ts` | 628 |
| `frontend/src/hooks/useReportManager.ts` | 889 |
| `frontend/src/hooks/useSmartHelp.ts` | 169 |
| `frontend/src/hooks/useVoiceControl.ts` | 97 |

### Skills (59 total)

| Skill | SKILL.md | Python Files | TS Files |
|-------|----------|-------------|----------|
| ASR | ✅ | 0 | 1 |
| LLM | ✅ | 0 | 1 |
| TTS | ✅ | 0 | 1 |
| VLM | ✅ | 0 | 1 |
| agent-browser | ✅ | 0 | 0 |
| ai-news-collectors | ✅ | 0 | 0 |
| aminer-academic-search | ✅ | 1 | 0 |
| aminer-daily-paper | ✅ | 1 | 0 |
| aminer-free-academic | ✅ | 0 | 0 |
| anti-pua | ✅ | 0 | 0 |
| auto-target-tracker | ✅ | 0 | 0 |
| blog-writer | ✅ | 1 | 0 |
| charts | ✅ | 0 | 0 |
| cheat-sheet | ✅ | 0 | 0 |
| coding-agent | ✅ | 0 | 0 |
| content-strategy | ✅ | 0 | 0 |
| contentanalysis | ✅ | 0 | 0 |
| docx | ✅ | 5 | 0 |
| dream-interpreter | ✅ | 1 | 0 |
| etap-expert | ✅ | 20 | 0 |
| finance | ✅ | 0 | 0 |
| fullstack-dev | ✅ | 0 | 0 |
| get-fortune-analysis | ✅ | 1 | 0 |
| gift-evaluator | ✅ | 1 | 0 |
| image-edit | ✅ | 0 | 1 |
| image-generation | ✅ | 0 | 1 |
| image-understand | ✅ | 0 | 1 |
| interview-designer | ✅ | 0 | 0 |
| interview-prep | ✅ | 1 | 0 |
| jd-resume-tailor | ✅ | 2 | 0 |
| job-intent-tracker | ✅ | 2 | 0 |
| market-research-reports | ✅ | 1 | 0 |
| marketing-mode | ✅ | 0 | 0 |
| mindfulness-meditation | ✅ | 0 | 0 |
| multi-search-engine | ✅ | 0 | 0 |
| pdf | ✅ | 5 | 0 |
| podcast-generate | ✅ | 0 | 1 |
| ppt | ✅ | 13 | 0 |
| qingyan-research | ✅ | 1 | 0 |
| quiz-html | ✅ | 1 | 0 |
| quiz-mastery | ✅ | 15 | 0 |
| resume-builder | ✅ | 1 | 0 |
| seo-content-writer | ✅ | 0 | 0 |
| skill-creator | ✅ | 10 | 0 |
| skill-finder-cn | ✅ | 0 | 0 |
| skill-vetter | ✅ | 0 | 0 |
| stock-analysis-skill | ✅ | 0 | 7 |
| storyboard-manager | ✅ | 2 | 0 |
| study-buddy | ✅ | 0 | 0 |
| task-review | ✅ | 0 | 0 |
| ui-ux-pro-max | ✅ | 4 | 0 |
| video-generation | ✅ | 0 | 1 |
| video-understand | ✅ | 0 | 1 |
| visual-design-foundations | ✅ | 0 | 0 |
| web-reader | ✅ | 0 | 1 |
| web-search | ✅ | 0 | 1 |
| web-shader-extractor | ✅ | 0 | 0 |
| writing-plans | ✅ | 0 | 0 |
| xlsx | ✅ | 3 | 0 |

---

## 🧪 Test Suite

### Python Tests (176 files)

| File | Lines |
|------|-------|
| `backend/tests/test_api_endpoints.py` | 697 |
| `backend/tests/test_connections_advanced.py` | 337 |
| `backend/tests/test_db_service_and_qomn.py` | 448 |
| `backend/tests/test_devices.py` | 111 |
| `backend/tests/test_devices_advanced.py` | 517 |
| `backend/tests/test_dwg.py` | 180 |
| `backend/tests/test_elements_conflicts_exports.py` | 365 |
| `backend/tests/test_health.py` | 96 |
| `backend/tests/test_integration_enhanced.py` | 548 |
| `backend/tests/test_monitor_integration.py` | 268 |
| `backend/tests/test_monitor_unit.py` | 457 |
| `backend/tests/test_projects.py` | 131 |
| `backend/tests/test_reports_advanced.py` | 336 |
| `backend/tests/test_routers.py` | 1203 |
| `backend/tests/test_sync_websocket.py` | 146 |
| `core/tests/test_utilities.py` | 836 |
| `fireai/core/tests/test_analysis_pipeline.py` | 1333 |
| `fireai/core/tests/test_audit_store.py` | 1283 |
| `fireai/core/tests/test_edge_cases.py` | 608 |
| `fireai/core/tests/test_fireai_core.py` | 1832 |
| `fireai/core/tests/test_floor_analyser.py` | 379 |
| `fireai/core/tests/test_helpers.py` | 491 |
| `fireai/core/tests/test_monte_carlo_pipeline.py` | 1482 |
| `fireai/core/tests/test_multi_floor_orchestrator.py` | 2290 |
| `fireai/core/tests/test_nfpa72_calculations.py` | 824 |
| `fireai/core/tests/test_performance.py` | 369 |
| `fireai/core/tests/test_pipeline_v2.py` | 1471 |
| `fireai/core/tests/test_regression.py` | 476 |
| `fireai/core/tests/test_routing_engine_v10.py` | 1466 |
| `fireai/core/tests/test_security_logging.py` | 531 |
| `marine/output/test_procedures.py` | 68 |
| `marine/tests/test_marine_lr_nfpa302.py` | 140 |
| `marine/tests/test_marine_module.py` | 326 |
| `marine/tests/test_marine_regression_v2.py` | 736 |
| `parsers/tests/test_dwg_parser.py` | 540 |
| `parsers/tests/test_dxf_parser.py` | 685 |
| `parsers/tests/test_ifc_parser.py` | 770 |
| `parsers/tests/test_parser_edge_cases.py` | 717 |
| `parsers/tests/test_path_security_enhanced.py` | 199 |
| `qomn_conduit/tests/test_bend.py` | 177 |
| ... and 136 more |

### Frontend Tests (9 files)

| File | Lines |
|------|-------|
| `frontend/src/components/core/__tests__/PageErrorBoundary.test.tsx` | 60 |
| `frontend/src/components/mockups/engineering/hooks/__tests__/StatusIndicator.test.ts` | 90 |
| `frontend/src/components/mockups/engineering/hooks/__tests__/useFaultLogic.test.ts` | 61 |
| `frontend/src/components/mockups/engineering/hooks/__tests__/useTelemetryStream.test.ts` | 40 |
| `frontend/src/engine/__tests__/CalculationEngine.test.ts` | 320 |
| `frontend/src/lib/__tests__/adversarial.test.ts` | 47 |
| `frontend/src/pages/__tests__/DashboardPage.test.tsx` | 84 |
| `frontend/src/pages/__tests__/EngineeringPage.test.tsx` | 58 |
| `frontend/src/pages/__tests__/SettingsPage.test.tsx` | 84 |

---

## 🚀 Deployment

- **Dockerfile:** ✅
- **docker-compose.yml:** ✅
- **Deploy files:** 36

| File |
|------|
| `deploy/docker/Dockerfile.api` |
| `deploy/docker/Dockerfile.nginx` |
| `deploy/docker/Dockerfile.worker` |
| `deploy/docker/docker-compose.yml` |
| `deploy/docker/entrypoint-worker.sh` |
| `deploy/docker/nginx.conf` |
| `deploy/helm/fireai/Chart.yaml` |
| `deploy/helm/fireai/templates/_helpers.tpl` |
| `deploy/helm/fireai/templates/configmap.yaml` |
| `deploy/helm/fireai/templates/deployment-api.yaml` |
| `deploy/helm/fireai/templates/deployment-worker.yaml` |
| `deploy/helm/fireai/templates/hpa.yaml` |
| `deploy/helm/fireai/templates/ingress.yaml` |
| `deploy/helm/fireai/templates/namespace.yaml` |
| `deploy/helm/fireai/templates/networkpolicy.yaml` |
| `deploy/helm/fireai/templates/pdb.yaml` |
| `deploy/helm/fireai/templates/pvc.yaml` |
| `deploy/helm/fireai/templates/secret.yaml` |
| `deploy/helm/fireai/templates/service.yaml` |
| `deploy/helm/fireai/templates/serviceaccount.yaml` |
| `deploy/helm/fireai/values.yaml` |
| `deploy/k8s/configmap.yaml` |
| `deploy/k8s/deployment-api.yaml` |
| `deploy/k8s/deployment-worker.yaml` |
| `deploy/k8s/ingress.yaml` |
| `deploy/k8s/namespace.yaml` |
| `deploy/k8s/network-policy.yaml` |
| `deploy/k8s/pod-disruption-budget.yaml` |
| `deploy/k8s/secret.yaml` |
| `deploy/k8s/service-api.yaml` |

---

## ⚙️ Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python project config: dependencies, ruff, mypy, pytest, bandit |
| `requirements.txt` | Pinned Python dependencies |
| `requirements-optional.txt` | Optional dependencies (aiohttp, nats-py, etc.) |
| `frontend/package.json` | Frontend npm config: scripts, dependencies |
| `frontend/tsconfig.json` | TypeScript compiler config |
| `frontend/vite.config.ts` | Vite build config |
| `frontend/eslint.config.js` | ESLint rules |
| `frontend/tailwind.config.js` | Tailwind CSS config |
| `.github/workflows/ci.yml` | CI/CD pipeline: 6 gates (static analysis, test suite, property tests, frontend, deps, Docker) |
| `.github/workflows/deploy.yml` | Deployment workflow |
| `Dockerfile` | Multi-stage Docker build (frontend + Python + runtime) |
| `docker-compose.yml` | Docker Compose for local dev |
| `alembic.ini` | Alembic database migration config |
| `render.yaml` | Render.com deployment config |

---

## 🔐 Security

| Feature | Implementation |
|---------|---------------|
| API Key Auth | `X-API-Key` header via `ApiKeyMiddleware` |
| RBAC | 4 roles: ADMIN, ENGINEER, VIEWER, + custom |
| CSRF Protection | Double Submit Cookie pattern (OWASP) |
| CORS | Fail-closed policy with explicit origins |
| Rate Limiting | `slowapi` per-path limits |
| Security Headers | HSTS, CSP, X-Frame-Options, X-Content-Type-Options |
| WebSocket Auth | X-API-Key header + message-based auth |
| Path Traversal Defense | `_path_security.py` with allowed dirs |
| Audit Trail | Hash chain + HMAC signatures |
| Input Validation | Pydantic v2 models on all endpoints |

---

## 📖 Help System

| Component | Description |
|-----------|-------------|
| `GlobalHelpDrawer` | Full user guide with 14-category tree, 35+ topics, bilingual (EN/AR) |
| `ContextualHelpButton` | Floating help button on every page → opens topic for current route |
| Magic Help (F1) | Press F1 anywhere → opens help for the current page |
| `ROUTE_HELP_MAP` | Maps 19 routes → help topics for contextual lookup |
| `HELP_TREE` | 14-category tree structure for global help navigation |
| `HELP_TOPICS` | 35+ comprehensive topics with steps, warnings, related topics |

---

## 🗺️ Route Map (Frontend → Backend)

| Frontend Route | Page Component | Primary Backend APIs |
|----------------|----------------|---------------------|
| `/dashboard` | DashboardPage | GET /health, GET /projects, GET /elements |
| `/projects` | ProjectsPage | CRUD /projects, POST /sync |
| `/engineering` | EngineeringPage | POST /qomn/voltage-drop, /qomn/battery |
| `/fire-alarm` | FireAlarmPage | GET /elements, GET /devices |
| `/fire-alarm/designer` | FireAlarmDesigner | Canvas-based detector placement |
| `/autocad` | AutoCADPage | POST /autocad/connect, GET /autocad/status |
| `/autocad/draw` | AutoCADDrawPage | POST /autocad/draw_line, draw_circle, draw_text |
| `/revit` | RevitPage | POST /revit/connect, GET /revit/status |
| `/revit/create` | RevitCreatePage | POST /revit/elements/create/wall, floor, column |
| `/revit/elements` | RevitElementsPage | GET /revit/elements, DELETE /revit/elements/{id} |
| `/digital-twin` | DigitalTwinPage | GET /digital-twin/status, POST /digital-twin/convert |
| `/digital-twin/convert` | DigitalTwinConvertPage | POST /digital-twin/convert, GET /digital-twin/history |
| `/digital-twin/config` | DigitalTwinConfigPage | GET/PUT /digital-twin/config, GET /digital-twin/mappings |
| `/digital-twin/history` | DigitalTwinHistoryPage | GET /digital-twin/history, POST /digital-twin/rollback/{id} |
| `/reports` | ReportsPage | CRUD /reports, GET /reports/{id}/export |
| `/elements` | Elements | CRUD /elements |
| `/connections` | Connections | CRUD /connections |
| `/conflicts` | Conflicts | GET /conflicts, POST /conflicts/detect |
| `/settings` | SettingsPage | GET /health, /admin/keys |

---

## 📦 Dependency Summary

### Python (pyproject.toml)
- **Core:** FastAPI, Uvicorn, Pydantic v2, SQLAlchemy, Alembic, PyJWT, Passlib, Cryptography
- **Async:** WebSockets, asyncpg, Redis, Celery
- **Optional [facp]:** aiohttp, nats-py, redis, celery
- **Optional [parsing]:** shapely, ezdxf, pymupdf, reportlab, numpy, scipy, matplotlib, opencv-python
- **Optional [dev]:** pytest, pytest-asyncio, pytest-cov, ruff, mypy, bandit, pre-commit

### Frontend (package.json)
- **Framework:** React 18, TypeScript 5, Vite 8
- **UI:** Tailwind CSS 4, shadcn/ui (50+ components), Radix UI primitives
- **State:** TanStack Query, Zustand
- **Routing:** React Router 6
- **i18n:** react-i18next (EN + AR)
- **Icons:** Lucide React
- **Charts:** Recharts
- **3D:** Three.js, React Three Fiber

---

*This index is auto-generated. To regenerate: `python3 scripts/generate_index.py`*
